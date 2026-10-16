import os
from dataclasses import dataclass, fields

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


class ConfigError(ValueError):
    """설정이 비행에 쓸 수 없는 상태. 이륙 전에 걸러야 한다."""


def validate(cfg: "VisionConfig") -> list[str]:
    """설정 정합성 점검. 문제 목록을 돌려준다. 비어 있으면 정상.

    잘못된 설정은 조용히 잘못된 판단을 만든다. 예를 들어 경고 임계치가
    위험 임계치보다 높으면 WARNING 상태가 영영 나오지 않고, 화각이 0이면
    모든 거리 계산이 무한대가 된다. 이륙 전에 걸러야 한다.
    """
    p: list[str] = []

    if not 0 < cfg.camera_pitch_deg <= 90:
        p.append(f"CAMERA_PITCH_DEG={cfg.camera_pitch_deg} — 0 초과 90 이하여야 합니다 "
                 f"(45 권장, 90 은 수직 하향)")
    if not 0 < cfg.hfov_deg < 180 or not 0 < cfg.vfov_deg < 180:
        p.append(f"화각이 비정상입니다 (H={cfg.hfov_deg}, V={cfg.vfov_deg})")
    if cfg.min_detect_px < 4:
        p.append(f"MIN_DETECT_PX={cfg.min_detect_px} — 너무 작으면 보이지 않는 구역을 "
                 f"'사람 없음'으로 오인합니다 (8~16 권장)")

    if cfg.density_warn >= cfg.density_danger:
        p.append(f"DENSITY_WARN({cfg.density_warn}) >= DENSITY_DANGER({cfg.density_danger}) "
                 f"— 경고 단계가 영영 나오지 않습니다")
    if cfg.grid_warning_threshold >= cfg.grid_danger_threshold:
        p.append(f"GRID_WARN({cfg.grid_warning_threshold}) >= "
                 f"GRID_DANGER({cfg.grid_danger_threshold}) — 경고 단계가 나오지 않습니다")
    if cfg.grid_rows < 1 or cfg.grid_cols < 1:
        p.append(f"그리드 크기가 비정상입니다 ({cfg.grid_rows}x{cfg.grid_cols})")

    if not 0.0 < cfg.alert_off_ratio <= cfg.alert_on_ratio <= 1.0:
        p.append(f"경보 히스테리시스가 비정상입니다 "
                 f"(on={cfg.alert_on_ratio}, off={cfg.alert_off_ratio}) — "
                 f"0 < off <= on <= 1 이어야 합니다")
    if cfg.alert_window < 3:
        p.append(f"ALERT_WINDOW={cfg.alert_window} — 너무 짧으면 한 프레임 오검출이 "
                 f"비행 명령이 됩니다 (10 이상 권장)")
    if cfg.count_window < 1:
        p.append(f"COUNT_WINDOW={cfg.count_window} 는 1 이상이어야 합니다")

    if cfg.imgsz % 32 != 0:
        p.append(f"YOLO_IMGSZ={cfg.imgsz} — 32 의 배수여야 합니다 (320, 416, 640)")
    if not 0.0 < cfg.conf_threshold < 1.0:
        p.append(f"CONF_THRESHOLD={cfg.conf_threshold} 는 0~1 사이여야 합니다")
    if cfg.altitude_m < 0:
        p.append(f"ALTITUDE_M={cfg.altitude_m} 은 음수일 수 없습니다")

    return p


def assert_valid(cfg: "VisionConfig") -> None:
    problems = validate(cfg)
    if problems:
        raise ConfigError("설정 오류:\n  - " + "\n  - ".join(problems))


def summary(cfg: "VisionConfig") -> str:
    """사람이 읽는 설정 요약. 비행 전 눈으로 확인하기 위한 것."""
    lines = []
    for f in fields(cfg):
        lines.append(f"  {f.name:<24} {getattr(cfg, f.name)}")
    return "\n".join(lines)
