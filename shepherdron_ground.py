"""지상국 — 노트북에서 YOLO 를 돌리고 관측 결과만 기체로 보낸다.

구조
    영상 수신 (Pi MJPEG 스트림 / IP Webcam / 웹캠) → CrowdPipeline → VisionReport → UDP

**여기서 비행 명령을 보내지 않는다.** 보내는 것은 "무엇을 보았는가" 뿐이고,
판단과 구동은 기체의 shepherdron_pi.py 가 한다. 노트북이 꺼지거나 Wi-Fi 가
끊겨도 기체는 마지막 타겟까지 간 뒤 타임아웃으로 안전하게 복귀한다.

사용법
    python shepherdron_ground.py --source http://10.42.0.1:8000/stream.mjpg --pi 10.42.0.1
    python shepherdron_ground.py --source 0 --pi 127.0.0.1        # 로컬 테스트
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

import cv2

from config import VisionConfig, validate
from link import Receiver, Sender, TelemetryReport, VisionReport
from main import apply_overrides, build_pipeline


def parse_args():
    p = argparse.ArgumentParser(description="Shepherdron ground station (perception)")
    p.add_argument("--source", help="영상 소스: Pi MJPEG URL / IP Webcam / 웹캠 번호 / 파일")
    p.add_argument("--pi", default="127.0.0.1", help="기체(라즈베리파이) 주소")
    p.add_argument("--vision-port", type=int, default=47600, help="관측 송신 포트")
    p.add_argument("--telemetry-port", type=int, default=47601, help="텔레메트리 수신 포트")
    p.add_argument("--model"); p.add_argument("--imgsz", type=int)
    p.add_argument("--conf", type=float)
    p.add_argument("--calibration"); p.add_argument("--pitch", type=float)
    p.add_argument("--density-danger", type=float)
    p.add_argument("--danger", type=int); p.add_argument("--total-danger", type=int)
    p.add_argument("--grid-rows", type=int); p.add_argument("--grid-cols", type=int)
    p.add_argument("--altitude", type=float, help=argparse.SUPPRESS)   # 지상국에선 미사용
    p.add_argument("--no-tracking", action="store_true")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--max-frames", type=int); p.add_argument("--loop", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = apply_overrides(VisionConfig(), args)

    print("=" * 70)
    print("  🛰️  SHEPHERDRON — 지상국 (지각 전담)")
    print("=" * 70)
    print(f"  * 영상 소스     : {cfg.stream_source}")
    print(f"  * 모델          : {cfg.model_name}  (imgsz {cfg.imgsz})")
    print(f"  * 기체 주소     : {args.pi}:{args.vision_port}")
    print(f"  * 텔레메트리    : 0.0.0.0:{args.telemetry_port}")
    print("  * 전송 내용     : 관측 결과만. 비행 명령은 보내지 않음")
    problems = validate(cfg)
    if problems:
        print("  * 설정 점검     : ❌")
        for pr in problems:
            print(f"      - {pr}")
        print("=" * 70)
        return 1
    print("  * 설정 점검     : ✅")
    pipeline = build_pipeline(cfg)
    print("=" * 70)

    from vision.camera import open_source
    stream = open_source(cfg.stream_source, cfg.capture_width,
                         cfg.capture_height, cfg.capture_fps)
    if args.loop and hasattr(stream, "loop_files"):
        stream.loop_files = True
    stream.start()

    tx = Sender(args.pi, args.vision_port)
    rx = Receiver(TelemetryReport, port=args.telemetry_port).start()

    flags = dict(show_boxes=cfg.show_boxes, show_footpoints=cfg.show_footpoints,
                 show_grid=cfg.show_grid, show_heatmap=cfg.show_heatmap)
    window = "Shepherdron Ground Station"
    if not args.headless:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        print("\n[keys] q 종료 | s 저장 | g 그리드 | h 히트맵 | b 박스 | f 발목점 | r 리셋\n")

    seq = 0
    idle_since = None
    last_print = 0.0

    try:
        while True:
            if getattr(stream, "finished", False):
                print("\n[info] 영상 소스 종료")
                break
            ok, frame = stream.read()
            if not ok or frame is None:
                now = time.monotonic()
                idle_since = idle_since or now
                if now - idle_since > 15.0:
                    print("\n[info] 15초간 프레임 없음 — 중단")
                    break
                time.sleep(0.03)
                continue
            idle_since = None

            result = pipeline.process(frame)
            seq += 1
            tx.send(VisionReport.from_pipeline(seq, result, frame.shape))

            if result.alert_rising_edge:
                a = result.analysis
                dens = f"  peak {a.peak_density:.2f} p/m²" if a.peak_density else ""
                print(f"\n🚨 과밀집 {datetime.now():%H:%M:%S}  "
                      f"{result.smoothed_count}명{dens}  → 기체로 보고 전송")

            telem = rx.latest()
            now = time.monotonic()
            if now - last_print >= 2.0:
                if telem:
                    print(f"\r[기체] {telem.mission_state:<11} {telem.mode:<8} "
                          f"구조물 {telem.payload_state:<10} "
                          f"alt {telem.relative_alt_m or 0:5.1f}m  "
                          f"batt {telem.battery_pct or 0:3d}%  "
                          f"link {telem.vision_age_s or 0:.2f}s  "
                          f"| [지상] {result.smoothed_count}명 {result.fps:4.1f}fps",
                          end="", flush=True)
                else:
                    print(f"\r[기체] 텔레메트리 없음  "
                          f"| [지상] {result.smoothed_count}명 {result.fps:4.1f}fps  "
                          f"(전송 {tx.sent})", end="", flush=True)
                last_print = now

            if args.max_frames and seq >= args.max_frames:
                print(f"\n[info] --max-frames {args.max_frames} 도달")
                break
            if args.headless:
                continue

            cv2.imshow(window, pipeline.render(frame, result, **flags))
            k = cv2.waitKey(1) & 0xFF
            if k == ord("q"):
                break
            elif k == ord("r"):
                pipeline.reset()
                print("\n[reset] 추적·시간축 필터 초기화")
            elif k in (ord("g"), ord("h"), ord("b"), ord("f")):
                key = {"g": "show_grid", "h": "show_heatmap",
                       "b": "show_boxes", "f": "show_footpoints"}[chr(k)]
                flags[key] = not flags[key]

    except KeyboardInterrupt:
        print("\n[info] 중단")
    finally:
        stream.stop(); tx.close(); rx.stop()
        if not args.headless:
            cv2.destroyAllWindows()
        print(f"\n[info] 지상국 종료 (전송 {tx.sent}, 실패 {tx.errors})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
