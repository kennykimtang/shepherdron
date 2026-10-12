import argparse
import time
import os
import cv2
from datetime import datetime
from config import VisionConfig
from vision.detector import PersonDetector
from vision.density_analyzer import DensityAnalyzer
from vision.stream_handler import StreamHandler


def parse_args():
    parser = argparse.ArgumentParser(description="Shepherdron Vision Crowd Density Analysis Module")
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Video stream source: IP Webcam URL (e.g. http://192.168.0.10:8080/video) or webcam index (0, 1) or video file",
    )
    parser.add_argument("--model", type=str, default=None, help="YOLO model path (default: yolov8n.pt)")
    parser.add_argument("--conf", type=float, default=None, help="YOLO confidence threshold (default: 0.45)")
    parser.add_argument("--grid-rows", type=int, default=None, help="Grid rows (default: 3)")
    parser.add_argument("--grid-cols", type=int, default=None, help="Grid columns (default: 3)")
    parser.add_argument("--danger", type=int, default=None, help="Per-grid cell danger threshold (default: 5)")
    parser.add_argument("--total-danger", type=int, default=None, help="Total crowd danger threshold (default: 15)")
    parser.add_argument("--headless", action="store_true", help="Run without cv2 GUI display window")
    return parser.parse_args()


def on_overcrowded_event(analysis, frame):
    """
    과밀집 감지 시 트리거되는 콜백 함수
    (라즈베리파이/Pixhawk 환경에서는 이 시점에 MAVLink 드론 이동 명령 및 액추에이터 전개로 연계됨)
    """
    print("\n" + "=" * 60)
    print(f"🚨 [ALERT] CROWD DENSITY OVER-LIMIT DETECTED at {datetime.now().strftime('%H:%M:%S')}")
    print(f"   - Total Count: {analysis.total_persons} persons")
    for reason in analysis.alarm_reasons:
        print(f"   - Reason: {reason}")
    if analysis.max_dense_cell:
        mc = analysis.max_dense_cell
        print(f"   - Peak Dense Area: Grid Cell ({mc.row}, {mc.col}) with {mc.count} persons")
        print(f"   - Screen Center Coordinate: {mc.center}")
        print("   - [DRONE ACTION] -> Calculating GPS target coordinate & readying guidance deployment...")
    print("=" * 60 + "\n")


def main():
    args = parse_args()
    cfg = VisionConfig()

    # CLI 인자가 주어졌을 경우 config 값 덮어쓰기
    if args.source:
        cfg.stream_source = args.source
    if args.model:
        cfg.model_name = args.model
    if args.conf is not None:
        cfg.conf_threshold = args.conf
    if args.grid_rows is not None:
        cfg.grid_rows = args.grid_rows
    if args.grid_cols is not None:
        cfg.grid_cols = args.grid_cols
    if args.danger is not None:
        cfg.grid_danger_threshold = args.danger
    if args.total_danger is not None:
        cfg.total_danger_threshold = args.total_danger

    print("=" * 65)
    print("  🛰️  SHEPHERDRON: Vision Crowd Density Analysis System")
    print("=" * 65)
    print(f"  * Stream Source : {cfg.stream_source}")
    print(f"  * YOLO Model    : {cfg.model_name} (conf={cfg.conf_threshold})")
    print(f"  * Grid Setup    : {cfg.grid_rows} x {cfg.grid_cols}")
    print(f"  * Cell Danger   : >= {cfg.grid_danger_threshold} persons")
    print(f"  * Total Danger  : >= {cfg.total_danger_threshold} persons")
    print("=" * 65)

    # 1. 검출기 및 밀집도 분석기 초기화
    detector = PersonDetector(
        model_name=cfg.model_name,
        conf_threshold=cfg.conf_threshold,
        iou_threshold=cfg.iou_threshold,
        device=cfg.device,
    )

    analyzer = DensityAnalyzer(
        grid_rows=cfg.grid_rows,
        grid_cols=cfg.grid_cols,
        warn_threshold=cfg.grid_warning_threshold,
        danger_threshold=cfg.grid_danger_threshold,
        total_threshold=cfg.total_danger_threshold,
        heatmap_alpha=cfg.heatmap_alpha,
    )

    # 2. 비디오 스트림 시작
    stream = StreamHandler(source=cfg.stream_source).start()

    # 토글 상태
    show_boxes = cfg.show_boxes
    show_footpoints = cfg.show_footpoints
    show_grid = cfg.show_grid
    show_heatmap = cfg.show_heatmap

    prev_time = time.time()
    last_alert_time = 0.0
    alert_cooldown = 3.0  # 알림 중복 출력 방지 쿨다운 (초)

    window_name = "Shepherdron Crowd Vision Monitor"
    if not args.headless:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    print("\n[INFO] Starting vision analysis loop. Controls:")
    print("  [q] Quit  |  [s] Save Frame  |  [g] Toggle Grid")
    print("  [h] Toggle Heatmap  |  [b] Toggle Boxes  |  [f] Toggle Footpoints\n")

    try:
        while True:
            ret, frame = stream.read()
            if not ret or frame is None:
                # 프레임 수신 대기
                time.sleep(0.03)
                continue

            # FPS 연산
            current_time = time.time()
            fps = 1.0 / (current_time - prev_time) if (current_time - prev_time) > 0 else 0.0
            prev_time = current_time

            # 1. 인물 검출 (YOLOv8)
            detection = detector.detect(frame)

            # 2. 인구 밀집도 및 과밀집 분석
            analysis = analyzer.analyze(frame.shape, detection)

            # 3. 과밀집 이벤트 발생 시 트리거
            if analysis.is_overcrowded:
                if (current_time - last_alert_time) > alert_cooldown:
                    on_overcrowded_event(analysis, frame)
                    last_alert_time = current_time

            # 4. 시각화 렌더링
            vis_frame = analyzer.draw_visualization(
                frame=frame,
                detection=detection,
                analysis=analysis,
                fps=fps,
                show_boxes=show_boxes,
                show_footpoints=show_footpoints,
                show_grid=show_grid,
                show_heatmap=show_heatmap,
            )

            if not args.headless:
                cv2.imshow(window_name, vis_frame)
                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    print("[INFO] Exit requested by user.")
                    break
                elif key == ord("s"):
                    save_dir = "captures"
                    os.makedirs(save_dir, exist_ok=True)
                    fname = os.path.join(save_dir, f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                    cv2.imwrite(fname, vis_frame)
                    print(f"📸 Saved screenshot: {fname}")
                elif key == ord("g"):
                    show_grid = not show_grid
                    print(f"[TOGGLE] Grid display: {show_grid}")
                elif key == ord("h"):
                    show_heatmap = not show_heatmap
                    print(f"[TOGGLE] Heatmap display: {show_heatmap}")
                elif key == ord("b"):
                    show_boxes = not show_boxes
                    print(f"[TOGGLE] Boxes display: {show_boxes}")
                elif key == ord("f"):
                    show_footpoints = not show_footpoints
                    print(f"[TOGGLE] Foot-points display: {show_footpoints}")
            else:
                # 헤드리스 모드: 콘솔에 간략 상태 주기적 출력
                if int(current_time) % 2 == 0:
                    status_str = "OVERCROWDED!" if analysis.is_overcrowded else "OK"
                    print(f"\r[STATUS] Count: {analysis.total_persons} | Status: {status_str} | FPS: {fps:.1f}", end="")

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user.")
    finally:
        stream.stop()
        if not args.headless:
            cv2.destroyAllWindows()
        print("[INFO] Shepherdron vision module terminated safely.")


if __name__ == "__main__":
    main()
