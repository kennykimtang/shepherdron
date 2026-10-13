import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _f(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _i(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _b(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class VisionConfig:
    # ── 입력 소스 ───────────────────────────────────────────────
    # IP Webcam URL | 웹캠 번호("0") | 동영상 파일 | "csi" (라즈베리파이 카메라)
    stream_source: str = os.getenv("STREAM_SOURCE", "http://192.168.0.10:8080/video")
    capture_width: int = _i("CAPTURE_WIDTH", 1280)
    capture_height: int = _i("CAPTURE_HEIGHT", 720)
    capture_fps: int = _i("CAPTURE_FPS", 30)

    # ── 모델 ────────────────────────────────────────────────────
    # 라즈베리파이에서는 scripts/export_ncnn.py 로 만든
    # "yolov8n_ncnn_model" 디렉터리를 지정하고 imgsz 를 320 으로 낮춘다.
    model_name: str = os.getenv("YOLO_MODEL", "yolov8n.pt")
    conf_threshold: float = _f("CONF_THRESHOLD", 0.45)
    iou_threshold: float = _f("IOU_THRESHOLD", 0.5)
    device: str = os.getenv("YOLO_DEVICE", "auto")      # auto | mps | cpu | cuda
    imgsz: int = _i("YOLO_IMGSZ", 640)                  # Pi 4 에서는 320 권장

    # ── 추적 ────────────────────────────────────────────────────
    use_tracking: bool = _b("USE_TRACKING", True)
    tracker: str = os.getenv("TRACKER", "bytetrack.yaml")

    # ── 그리드 ──────────────────────────────────────────────────
    grid_rows: int = _i("GRID_ROWS", 3)
    grid_cols: int = _i("GRID_COLS", 3)

    # ── 임계치: 미캘리브레이션 시 (셀당 인원수) ──────────────────
    grid_warning_threshold: int = _i("GRID_WARN_THRESHOLD", 3)
    grid_danger_threshold: int = _i("GRID_DANGER_THRESHOLD", 5)
    total_danger_threshold: int = _i("TOTAL_DANGER_THRESHOLD", 15)

    # ── 임계치: 캘리브레이션 시 (persons/m^2) ────────────────────
    # 군중안전 문헌 통용 구간: 2.0 보행 저하 / 4.0 자력 이동 곤란 / 5.0+ 압착 위험
    density_warn: float = _f("DENSITY_WARN", 2.0)
    density_danger: float = _f("DENSITY_DANGER", 4.0)
    ground_plane_path: str = os.getenv("GROUND_PLANE", "calibration/ground_plane.json")

    # ── 카메라 기하 (Camera Module 3 Wide 기본값) ────────────────
    hfov_deg: float = _f("HFOV_DEG", 102.0)
    vfov_deg: float = _f("VFOV_DEG", 67.0)
    camera_pitch_deg: float = _f("CAMERA_PITCH_DEG", 45.0)   # 45 = 비스듬, 90 = 수직 하향
    min_detect_px: int = _i("MIN_DETECT_PX", 12)              # 이보다 작은 사람은 검출 불가로 본다
    altitude_m: float = _f("ALTITUDE_M", 0.0)                # 0 = 미지정

    # ── 시간축 안정화 ───────────────────────────────────────────
    alert_window: int = _i("ALERT_WINDOW", 15)
    alert_on_ratio: float = _f("ALERT_ON_RATIO", 0.6)
    alert_off_ratio: float = _f("ALERT_OFF_RATIO", 0.25)
    alert_min_on_s: float = _f("ALERT_MIN_ON_S", 5.0)
    count_window: int = _i("COUNT_WINDOW", 9)

    # ── 표시 ────────────────────────────────────────────────────
    show_boxes: bool = True
    show_footpoints: bool = True
    show_grid: bool = True
    show_heatmap: bool = True
    heatmap_alpha: float = _f("HEATMAP_ALPHA", 0.35)
