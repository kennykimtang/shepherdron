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


def save_shot(canvas, folder: str) -> str:
    Path(folder).mkdir(parents=True, exist_ok=True)
    path = str(Path(folder) / f"shot_{datetime.now():%H%M%S}.png")
    cv2.imwrite(path, canvas)
    print(f"[demo] 저장 {path}")
    return path


# ─────────────────────── 녹화 모드 ───────────────────────
def run_record(args) -> int:
    pipe, renderer, field, label, mission = build(args)
    from vision.stream_handler import StreamHandler
    src = StreamHandler(source=args.source, loop_files=False).start()

    writer = cv2.VideoWriter(args.record, cv2.VideoWriter_fourcc(*"mp4v"),
                             args.fps, (args.width, args.height))
    if not writer.isOpened():
        print(f"[demo] mp4 를 열 수 없습니다: {args.record}", file=sys.stderr)
        return 2

    n, t0 = 0, time.monotonic()
    print(f"[demo] 녹화 시작 → {args.record}")
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
    print(f"[demo] 완료 — {n} 프레임, {n / args.fps:.1f} 초 → {args.record}")
    print("[demo] 이 파일을 PowerPoint 슬라이드에 끌어다 놓으세요.")
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


def main() -> int:
    args = parse_args()
    return run_record(args) if args.record else run_live(args)


if __name__ == "__main__":
    raise SystemExit(main())
