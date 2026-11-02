#!/usr/bin/env python3
"""발표용 실시간 군중 밀집도 시연기.

드론 카메라가 없어도 된다. 확정 구조상 YOLO 는 어차피 노트북에서 도는데,
강의실 관객석이 곧 군중이기 때문이다.

두 가지로 쓴다.

  1) PPT 에 넣을 영상 만들기 (실패 가능성 0)
     python demo_presentation.py --source clip.mp4 --record slide.mp4
     만들어진 mp4 를 슬라이드에 끌어다 놓으면 끝이다.

  2) 발표장 라이브
     python demo_presentation.py --source 0 --fallback slide_src.mp4
     웹캠이 끊기면 자동으로 녹화본으로 넘어가 검은 화면이 뜨지 않는다.

단축키
  q 종료   f 전체화면   space 일시정지   s 현재 화면 PNG 저장
  b 검출박스  h 히트맵  r 분석영역  m 수동 출동  t 라이브/녹화본 전환
  [ ] 커널 폭(sigma) 조절
"""
from __future__ import annotations

import argparse
import contextlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

from config import VisionConfig
from vision.density_analyzer import DensityAnalyzer
from vision.density_field import DensityFieldEstimator
from vision.detector import PersonDetector
from vision.failover import FailoverSource
from vision.geometry import CameraModel, GroundPlane
from vision.pipeline import CrowdPipeline
from flight.virtual_drone import DemoMission
from vision.presentation import Layout, PresentationRenderer
from vision.stability import AlertDebouncer, RollingCounter, TargetSmoother
from vision.tactical import build_picture

WIN = "Shepherdron Demo"


def parse_args():
    p = argparse.ArgumentParser(
        description="Shepherdron 발표용 군중 밀집도 시연기",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--source", default="0",
                   help="웹캠 번호 / 동영상 파일 / 폰 IP캠 URL")
    p.add_argument("--fallback", help="라이브가 끊겼을 때 틀 예비 클립")
    p.add_argument("--record", help="처리 결과를 이 mp4 로 저장 (PPT 삽입용)")
    p.add_argument("--duration", type=float,
                   help="--record 시 최대 녹화 길이(초)")
    p.add_argument("--shots", default="demo_shots", help="s 키로 저장할 폴더")

    p.add_argument("--model"); p.add_argument("--imgsz", type=int)
    p.add_argument("--conf", type=float)
    p.add_argument("--sigma", type=float, default=0.75,
                   help="KDE 커널 폭(m). 작을수록 좁은 군집에 민감")
    p.add_argument("--warn", type=float, default=2.0, help="주의 임계 명/m²")
    p.add_argument("--danger", type=float, default=4.0, help="위험 임계 명/m²")
    p.add_argument("--person-height", type=float, default=1.7,
                   help="거리 환산에 쓰는 평균 키(m)")
    p.add_argument("--calibration", help="지상 평면 JSON (있으면 더 정확)")
    p.add_argument("--altitude", type=float, help="AGL 고도(m). 주면 지령을 미터로")
    p.add_argument("--pitch", type=float, default=45.0, help="카메라 하향각(도)")

    p.add_argument("--no-tracking", action="store_true")
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--fps", type=float, default=20.0, help="--record 출력 fps")
    p.add_argument("--lang", choices=["ko", "en"])
    p.add_argument("--roi", help="분석 영역 꼭짓점 'x,y;x,y;x,y;...' (생략 시 화면 전체)")
    p.add_argument("--roi-area", type=float,
                   help="분석 영역의 실제 바닥 면적(m²). 재어 두면 추정보다 정확")
    p.add_argument("--tiers", default="1,2,3,4",
                   help="0-안전/1-관심/2-주의/3-경계 경계값 명/m²")
    p.add_argument("--channel", default="CAM 01", help="화면에 띄울 채널 이름")
    p.add_argument("--hfov", type=float, default=70.0,
                   help="카메라 수평 화각(도). 노트북 웹캠 약 70, Camera Module 3 Wide 102")
    p.add_argument("--no-sim", action="store_true",
                   help="가상 기체를 끄고 인식 화면만 쓴다")
    p.add_argument("--check", action="store_true",
                   help="리허설 점검 : 카메라 목록 · 한글 폰트 · 처리 속도")
    return p.parse_args()


def build(args):
    cfg = VisionConfig()
    model = args.model or cfg.model_name
    detector = PersonDetector(
        model_name=model,
        conf_threshold=args.conf if args.conf is not None else cfg.conf_threshold,
        iou_threshold=cfg.iou_threshold,
        device=cfg.device,
        imgsz=args.imgsz or cfg.imgsz,
    )
    plane = None
    if args.calibration:
        plane = GroundPlane.load(args.calibration)
        print(f"[demo] 지상 평면 로드: {args.calibration}")

    camera = CameraModel(width=cfg.capture_width, height=cfg.capture_height,
                         pitch_deg=args.pitch)
    analyzer = DensityAnalyzer(ground_plane=plane, camera=camera,
                               density_warn=args.warn, density_danger=args.danger)
    field = DensityFieldEstimator(sigma_m=args.sigma, warn=args.warn,
                                  danger=args.danger,
                                  person_height_m=args.person_height,
                                  ground_plane=plane)
    pipe = CrowdPipeline(
        detector=detector, analyzer=analyzer, camera=camera,
        use_tracking=not args.no_tracking,
        debouncer=AlertDebouncer(), counter=RollingCounter(),
        smoother=TargetSmoother(), altitude_m=args.altitude,
        field_estimator=field,
    )
    roi = None
    if args.roi:
        roi = [tuple(int(float(v)) for v in pt.split(","))
               for pt in args.roi.split(";") if pt.strip()]
    tiers = tuple(float(v) for v in args.tiers.split(","))
    renderer = PresentationRenderer(
        layout=Layout(w=args.width, h=args.height), lang=args.lang,
        channel=args.channel, roi=roi, roi_area_m2=args.roi_area, tiers=tiers,
        hfov_deg=args.hfov)
    if not renderer.T.has_korean:
        print("[demo] 경고: 한글 폰트를 찾지 못했습니다. SHEPHERDRON_FONT 로 지정하세요.")
    mission = None if args.no_sim else DemoMission()
    label = f"{Path(str(model)).stem} {args.imgsz or cfg.imgsz}"
    return pipe, renderer, field, label, mission


def step(args, pipe, renderer, field, mission, frame, now=None, **view):
    """한 프레임 : 인식 → 전술 투영 → 임무 갱신 → 화면 합성."""
    res = pipe.process(frame)
    h, w = frame.shape[:2]
    pic = build_picture(res.detection, w, h, field.sigma_m, args.hfov,
                        args.person_height)
    if mission is not None:
        mission.update(res.alert_rising_edge, res.alert_active,
                       res.smoothed_count, pic.hotspot, now=now)
    return res, renderer.render(frame, res, tactical=pic, mission=mission, **view)


@contextlib.contextmanager
def _quiet_stderr():
    """OpenCV 가 장치·코덱을 더듬을 때 뱉는 경고를 가린다."""
    fd = sys.stderr.fileno()
    saved = os.dup(fd)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        sys.stderr.flush()
        os.dup2(devnull, fd)
        yield
    finally:
        os.dup2(saved, fd)
        os.close(devnull)
        os.close(saved)


def save_shot(canvas, folder: str) -> str:
    Path(folder).mkdir(parents=True, exist_ok=True)
    path = str(Path(folder) / f"shot_{datetime.now():%H%M%S}.png")
    cv2.imwrite(path, canvas)
    print(f"[demo] 저장 {path}")
    return path


# ─────────────────────── 녹화 모드 ───────────────────────
def open_writer(path: str, fps: float, size):
    """PowerPoint 가 재생할 수 있는 mp4 를 연다.

    OpenCV 기본값인 'mp4v' 는 MPEG-4 Part 2(FMP4) 로 쓰는데, 윈도우
    PowerPoint 는 이걸 못 여는 경우가 많다. 발표용 파일을 다른 PC 로
    들고 가야 하므로 H.264(avc1) 를 먼저 시도한다.
    """
    for tag in ("avc1", "H264", "mp4v"):
        with _quiet_stderr():
            w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*tag), fps, size)
        if w.isOpened():
            if tag == "mp4v":
                print("[demo] 주의 : H.264 인코더가 없어 FMP4 로 저장합니다.")
                print("       윈도우 PowerPoint 에서 재생이 안 되면 "
                      "변환 후 삽입하세요 (예: HandBrake, 무료).")
            return w, tag
        w.release()
    return None, None
def run_record(args) -> int:
    pipe, renderer, field, label, mission = build(args)
    from vision.stream_handler import StreamHandler
    src = StreamHandler(source=args.source, loop_files=False).start()

    writer, codec = open_writer(args.record, args.fps, (args.width, args.height))
    if writer is None:
        print(f"[demo] mp4 를 열 수 없습니다: {args.record}", file=sys.stderr)
        return 2

    n, t0 = 0, time.monotonic()
    print(f"[demo] 녹화 시작 → {args.record}  ({args.width}x{args.height}, "
          f"{codec}, {args.fps:g}fps)")
    try:
        while True:
            ok, frame = src.read()
            if not ok:
                if getattr(src, "finished", False):
                    break
                time.sleep(0.01)
                if time.monotonic() - t0 > 15:
                    print("[demo] 소스에서 프레임이 오지 않습니다.", file=sys.stderr)
                    break
                continue
            # 녹화는 실시간보다 빠르거나 느리게 돈다. 임무 시계를 영상 시간에 맞춘다.
            res, canvas = step(args, pipe, renderer, field, mission, frame,
                               now=n / args.fps,
                               source_label=Path(str(args.source)).name,
                               model_label=label)
            writer.write(canvas)
            n += 1
            if n % 30 == 0:
                print(f"  {n} 프레임  최대 {res.field.peak_density:.1f} 명/m²")
            if args.duration and n / args.fps >= args.duration:
                break
    finally:
        writer.release()
        src.stop()
    mb = Path(args.record).stat().st_size / 1e6 if Path(args.record).exists() else 0
    print(f"[demo] 완료 — {n} 프레임, {n / args.fps:.1f} 초, {mb:.1f} MB "
          f"→ {args.record}")
    print("[demo] PowerPoint : 삽입 > 비디오 > '이 디바이스'로 넣으세요.")
    print("       (파일 '연결'이 아니라 '삽입'이어야 다른 PC 에서도 재생됩니다)")
    return 0


# ─────────────────────── 라이브 모드 ───────────────────────
def run_live(args) -> int:
    pipe, renderer, field, label, mission = build(args)
    src = FailoverSource(primary=args.source, fallback=args.fallback).start()

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 1280, 720)
    full = args.fullscreen
    if full:
        cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    show_boxes = show_heat = show_roi = True
    paused = False
    last = None
    print("[demo] q 종료 · f 전체화면 · space 일시정지 · s 저장 · "
          "b 검출 · h 히트맵 · r 영역 · m 수동출동 · t 소스전환 · [ ] 커널")
    try:
        while True:
            if not paused:
                ok, frame = src.read()
                if ok:
                    _, last = step(
                        args, pipe, renderer, field, mission, frame,
                        source_label=str(src.active_label),
                        on_fallback=src.on_fallback, show_heatmap=show_heat,
                        show_boxes=show_boxes, show_roi=show_roi,
                        model_label=label)
            if last is not None:
                cv2.imshow(WIN, last)
            else:
                time.sleep(0.03)

            k = cv2.waitKey(1) & 0xFF
            if k in (ord("q"), 27):
                break
            elif k == ord("f"):
                full = not full
                cv2.setWindowProperty(
                    WIN, cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_FULLSCREEN if full else cv2.WINDOW_NORMAL)
            elif k == ord(" "):
                paused = not paused
            elif k == ord("s") and last is not None:
                save_shot(last, args.shots)
            elif k == ord("b"):
                show_boxes = not show_boxes
            elif k == ord("h"):
                show_heat = not show_heat
            elif k == ord("r"):
                show_roi = not show_roi
            elif k == ord("m") and mission is not None:
                mission.dispatch()
                renderer.log.add("운용자 수동 출동", "mission", 0, "수동")
            elif k == ord("t"):
                src.toggle()
            elif k in (ord("["), ord("]")):
                field.sigma_m = max(0.2, min(3.0, field.sigma_m
                                             + (0.05 if k == ord("]") else -0.05)))
                print(f"[demo] σ = {field.sigma_m:.2f} m")
    finally:
        src.stop()
        cv2.destroyAllWindows()
    return 0


# ─────────────────────── 리허설 점검 ───────────────────────
def probe_cameras(limit: int = 6, warmup: int = 12):
    """열리는 카메라 번호와 해상도를 찾는다. 폰 웹캠 앱이 몇 번인지 알아내는 용도.

    카메라는 열린 직후 첫 몇 프레임을 돌려주지 않는 일이 흔하다. 한 번 읽고
    없다고 단정하면 멀쩡한 장치를 놓친다. 그래서 잠깐 기다리며 다시 읽는다.
    """
    found, misses = [], 0
    for i in range(limit):
        with _quiet_stderr():
            cap = cv2.VideoCapture(i)
            try:
                hit = None
                if cap.isOpened():
                    for _ in range(warmup):
                        ok, frame = cap.read()
                        if ok and frame is not None:
                            hit = (i, frame.shape[1], frame.shape[0])
                            break
                        time.sleep(0.05)
            finally:
                cap.release()
        if hit:
            found.append(hit)
            misses = 0
        else:
            misses += 1
            if misses >= 2 and found:      # 번호가 끊기면 더 볼 필요가 없다
                break
    return found


def run_check(args) -> int:
    print("Shepherdron 시연 점검\n" + "=" * 46)

    print("\n[1] 카메라")
    print("  찾는 중...")
    cams = probe_cameras()
    if not cams:
        print("  없음. 폰 웹캠 앱을 켰는지, 다른 프로그램이 카메라를 "
              "쓰고 있지 않은지 확인하세요.")
    for i, w, h in cams:
        role = "내장 웹캠(발표자 쪽일 가능성 높음)" if i == 0 else "외부 — 관객용으로 쓰세요"
        print(f"  --source {i}   {w}x{h}   {role}")

    print("\n[2] 한글 폰트")
    from vision.text_painter import TextPainter
    t = TextPainter()
    if t.has_korean:
        print(f"  정상 — {t._paths['regular']}")
    else:
        print("  없음. 한글이 네모로 나옵니다.")
        print("  SHEPHERDRON_FONT=/경로/폰트.ttf 로 지정하세요.")
    print(f"  고정폭 — {t._paths.get('mono') or '없음(숫자가 흔들립니다)'}")

    print("\n[3] 예비 클립")
    if args.fallback:
        ok = Path(args.fallback).exists()
        print(f"  {args.fallback} — {'있음' if ok else '없음! 경로를 확인하세요'}")
    else:
        print("  지정 안 됨. --fallback 으로 예비 클립을 꼭 준비하세요.")

    print("\n[4] 처리 속도")
    src_name = args.source
    if not cams and str(src_name).isdigit():
        print("  카메라가 없어 건너뜁니다.")
        return 0
    pipe, renderer, field, label, mission = build(args)
    from vision.stream_handler import StreamHandler
    src = StreamHandler(source=src_name, loop_files=True).start()

    # 첫 몇 프레임은 모델 워밍업이라 느리다. 측정에서 뺀다.
    warm, deadline = 0, time.monotonic() + 25
    while warm < 5 and time.monotonic() < deadline:
        ok, frame = src.read()
        if not ok:
            time.sleep(0.02)
            continue
        step(args, pipe, renderer, field, mission, frame)
        warm += 1

    t0, n = time.monotonic(), 0
    while n < 20 and time.monotonic() - t0 < 20:
        ok, frame = src.read()
        if not ok:
            time.sleep(0.02)
            continue
        step(args, pipe, renderer, field, mission, frame)
        n += 1
    el = time.monotonic() - t0
    src.stop()
    if n:
        fps = n / el
        verdict = ("충분" if fps >= 10 else
                   "조금 느림 — --imgsz 320 권장" if fps >= 6 else
                   "느림 — --imgsz 320 으로 낮추세요")
        print(f"  --source {src_name} : {fps:.1f} FPS — {verdict}")
    else:
        print(f"  {src_name} 에서 프레임을 받지 못했습니다.")
    print("\n전체 절차는 DEMO.md 를 보세요.")
    return 0


def main() -> int:
    args = parse_args()
    if args.check:
        return run_check(args)
    return run_record(args) if args.record else run_live(args)


if __name__ == "__main__":
    raise SystemExit(main())
