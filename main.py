"""Shepherdron 비전 실행기 — 군중 밀집도 분석 및 과밀집 타겟 산출."""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path

import cv2

from config import VisionConfig
from vision.camera import open_source
from vision.density_analyzer import DensityAnalyzer
from vision.detector import PersonDetector
from vision.geometry import CameraModel, GroundPlane
from vision.pipeline import CrowdPipeline, PipelineResult
from vision.stability import AlertDebouncer, RollingCounter, TargetSmoother


def parse_args():
    p = argparse.ArgumentParser(
        description="Shepherdron vision crowd-density module",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--source", help='스트림 소스: IP Webcam URL / 웹캠 번호 / 파일 / "csi"')
    p.add_argument("--model", help="YOLO 가중치 또는 NCNN 모델 디렉터리")
    p.add_argument("--imgsz", type=int, help="추론 입력 크기 (Pi 4 는 320 권장)")
    p.add_argument("--conf", type=float, help="confidence 임계값")
    p.add_argument("--grid-rows", type=int)
    p.add_argument("--grid-cols", type=int)
    p.add_argument("--danger", type=int, help="셀당 위험 인원수 (미캘리브레이션 시)")
    p.add_argument("--total-danger", type=int, help="전체 위험 인원수")
    p.add_argument("--density-danger", type=float, help="위험 밀집도 persons/m^2 (캘리브레이션 시)")
    p.add_argument("--calibration", help="지상 평면 JSON 경로")
    p.add_argument("--altitude", type=float, help="AGL 고도(m). 주면 타겟을 미터 오프셋으로 환산")
    p.add_argument("--pitch", type=float, help="카메라 하향각(도). 90 = 수직 하향")
    p.add_argument("--no-tracking", action="store_true", help="ByteTrack 끄기 (프레임 단위 검출만)")
    p.add_argument("--headless", action="store_true", help="GUI 창 없이 실행")
    p.add_argument("--max-frames", type=int, help="이 프레임 수만큼만 처리하고 종료 (벤치마크용)")
    p.add_argument("--loop", action="store_true", help="동영상 파일을 끝에서 되감아 반복")
    return p.parse_args()


def apply_overrides(cfg: VisionConfig, a) -> VisionConfig:
    for arg, field in (
        ("source", "stream_source"), ("model", "model_name"), ("imgsz", "imgsz"),
        ("conf", "conf_threshold"), ("grid_rows", "grid_rows"), ("grid_cols", "grid_cols"),
        ("danger", "grid_danger_threshold"), ("total_danger", "total_danger_threshold"),
        ("density_danger", "density_danger"), ("calibration", "ground_plane_path"),
        ("altitude", "altitude_m"), ("pitch", "camera_pitch_deg"),
    ):
        v = getattr(a, arg)
        if v is not None:
            setattr(cfg, field, v)
    if a.no_tracking:
        cfg.use_tracking = False
    return cfg


def build_pipeline(cfg: VisionConfig) -> CrowdPipeline:
    plane = None
    path = Path(cfg.ground_plane_path)
    if path.exists():
        plane = GroundPlane.load(path)
        print(f"  * Ground plane  : {path}  ({plane.label or 'no label'})")
    else:
        print(f"  * Ground plane  : 없음 — 원근 보정 없이 셀당 인원수로 판정합니다")
        print(f"                    (python scripts/calibrate_ground.py 로 생성)")

    detector = PersonDetector(
        model_name=cfg.model_name, conf_threshold=cfg.conf_threshold,
        iou_threshold=cfg.iou_threshold, device=cfg.device,
        imgsz=cfg.imgsz, tracker=cfg.tracker,
    )
    camera = CameraModel(
        width=cfg.capture_width, height=cfg.capture_height,
        hfov_deg=cfg.hfov_deg, vfov_deg=cfg.vfov_deg,
        pitch_deg=cfg.camera_pitch_deg, min_detect_px=cfg.min_detect_px,
    )
    analyzer = DensityAnalyzer(
        camera=camera,
        grid_rows=cfg.grid_rows, grid_cols=cfg.grid_cols,
        warn_threshold=cfg.grid_warning_threshold,
        danger_threshold=cfg.grid_danger_threshold,
        total_threshold=cfg.total_danger_threshold,
        heatmap_alpha=cfg.heatmap_alpha, ground_plane=plane,
        density_warn=cfg.density_warn, density_danger=cfg.density_danger,
    )
    return CrowdPipeline(
        detector=detector, analyzer=analyzer, camera=camera,
        use_tracking=cfg.use_tracking,
        debouncer=AlertDebouncer(window=cfg.alert_window, on_ratio=cfg.alert_on_ratio,
                                 off_ratio=cfg.alert_off_ratio, min_on_s=cfg.alert_min_on_s),
        counter=RollingCounter(window=cfg.count_window),
        smoother=TargetSmoother(),
        altitude_m=cfg.altitude_m or None,
    )


def on_alert(result: PipelineResult) -> None:
    """과밀집 경보 상승 에지. Phase 2 에서 이 지점이 MAVLink goto 호출로 바뀐다."""
    a = result.analysis
    print("\n" + "=" * 68)
    print(f"🚨 OVER-DENSITY ALERT  {datetime.now():%H:%M:%S}")
    print(f"   count          : {result.smoothed_count} (raw {a.total_persons})")
    if a.peak_density is not None:
        print(f"   peak density   : {a.peak_density:.2f} persons/m^2")
    for r in a.alarm_reasons:
        print(f"   reason         : {r}")
    if a.max_dense_cell:
        print(f"   busiest cell   : ({a.max_dense_cell.row}, {a.max_dense_cell.col})")
    t = result.target
    if t:
        print(f"   target pixel   : {t.pixel}")
        print(f"   bearing offset : yaw {t.yaw_offset_deg:+.1f}°  pitch {t.pitch_offset_deg:+.1f}°")
        if t.has_ground_fix:
            print(f"   ground offset  : forward {t.forward_m:+.1f} m, "
                  f"right {t.right_m:+.1f} m  (AGL {t.altitude_m:.1f} m)")
            print( "   [PHASE 2]      -> MAVLink GUIDED goto 로 전달 가능")
        else:
            print( "   ground offset  : 고도 미지정 — --altitude 를 주면 미터로 환산됩니다")
    print("=" * 68 + "\n")


def main() -> int:
    args = parse_args()
    cfg = apply_overrides(VisionConfig(), args)

    print("=" * 68)
    print("  🛰️  SHEPHERDRON — Vision Crowd Density Core")
    print("=" * 68)
    print(f"  * Source        : {cfg.stream_source}")
    print(f"  * Model         : {cfg.model_name}  (imgsz {cfg.imgsz}, conf {cfg.conf_threshold})")
    print(f"  * Tracking      : {'ByteTrack' if cfg.use_tracking else 'OFF (detect only)'}")
    print(f"  * Grid          : {cfg.grid_rows} x {cfg.grid_cols}")
    print(f"  * Thresholds    : cell>={cfg.grid_danger_threshold}p  total>={cfg.total_danger_threshold}p"
          f"  density>={cfg.density_danger} p/m^2")
    print(f"  * Alert hyst.   : {cfg.alert_on_ratio:.0%} on / {cfg.alert_off_ratio:.0%} off"
          f"  over {cfg.alert_window} frames, hold {cfg.alert_min_on_s:.0f}s")
    pipeline = build_pipeline(cfg)
    if cfg.altitude_m:
        print(f"  * Altitude      : {cfg.altitude_m:.1f} m AGL, camera pitch {cfg.camera_pitch_deg:.0f}°")
    print("=" * 68)

    stream = open_source(cfg.stream_source, cfg.capture_width,
                         cfg.capture_height, cfg.capture_fps)
    if args.loop and hasattr(stream, "loop_files"):
        stream.loop_files = True
    stream.start()

    idle_since = None

    flags = dict(show_boxes=cfg.show_boxes, show_footpoints=cfg.show_footpoints,
                 show_grid=cfg.show_grid, show_heatmap=cfg.show_heatmap)
    window = "Shepherdron Crowd Vision Monitor"
    if not args.headless:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        print("\n[keys] q quit | s save | g grid | h heatmap | b boxes | f footpoints | r reset\n")

    try:
        while True:
            if getattr(stream, "finished", False):
                print("\n[info] source exhausted")
                break

            ok, frame = stream.read()
            if not ok or frame is None:
                now = time.monotonic()
                idle_since = idle_since or now
                if now - idle_since > 15.0:
                    print("\n[info] no frames for 15 s - giving up on the source")
                    break
                time.sleep(0.03)
                continue
            idle_since = None

            result = pipeline.process(frame)
            if result.alert_rising_edge:
                on_alert(result)

            if args.max_frames and result.frame_index + 1 >= args.max_frames:
                print(f"\n[info] reached --max-frames {args.max_frames}")
                break

            if args.headless:
                if result.frame_index % 15 == 0:
                    state = "ALERT" if result.alert_active else "ok"
                    dens = (f" {result.analysis.peak_density:.1f}p/m2"
                            if result.analysis.peak_density is not None else "")
                    print(f"\r[{state:5}] n={result.smoothed_count:3d}{dens} "
                          f"fps={result.fps:4.1f}", end="", flush=True)
                continue

            cv2.imshow(window, pipeline.render(frame, result, **flags))
            k = cv2.waitKey(1) & 0xFF
            if k == ord("q"):
                break
            elif k == ord("s"):
                os.makedirs("captures", exist_ok=True)
                fn = f"captures/capture_{datetime.now():%Y%m%d_%H%M%S}.jpg"
                cv2.imwrite(fn, pipeline.render(frame, result, **flags))
                print(f"📸 saved {fn}")
            elif k == ord("r"):
                pipeline.reset()
                print("[reset] tracker and temporal filters cleared")
            elif k in (ord("g"), ord("h"), ord("b"), ord("f")):
                key = {"g": "show_grid", "h": "show_heatmap",
                       "b": "show_boxes", "f": "show_footpoints"}[chr(k)]
                flags[key] = not flags[key]
                print(f"[toggle] {key} = {flags[key]}")

    except KeyboardInterrupt:
        print("\n[info] interrupted")
    finally:
        stream.stop()
        if not args.headless:
            cv2.destroyAllWindows()
        print("[info] shepherdron vision module terminated safely.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
