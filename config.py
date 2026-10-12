import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class VisionConfig:
    # 스트림 소스: IP Webcam URL 또는 웹캠 번호(0, 1...) 또는 동영상 파일 경로
    # 예: "http://192.168.0.15:8080/video"
    stream_source: str = os.getenv("STREAM_SOURCE", "http://192.168.0.10:8080/video")
    
    # YOLO 모델 설정
    model_name: str = os.getenv("YOLO_MODEL", "yolov8n.pt")  # yolov8n.pt (경량화)
    conf_threshold: float = float(os.getenv("CONF_THRESHOLD", "0.45"))
    iou_threshold: float = float(os.getenv("IOU_THRESHOLD", "0.5"))
    device: str = os.getenv("YOLO_DEVICE", "auto")  # 'auto', 'mps', 'cpu', 'cuda'
    
    # 그리드 및 밀집도 분석 설정
    grid_rows: int = int(os.getenv("GRID_ROWS", "3"))      # 세로 분할 수
    grid_cols: int = int(os.getenv("GRID_COLS", "3"))      # 가로 분할 수
    
    # 밀집도 임계치
    grid_warning_threshold: int = int(os.getenv("GRID_WARN_THRESHOLD", "3"))    # 그리드 주의
    grid_danger_threshold: int = int(os.getenv("GRID_DANGER_THRESHOLD", "5"))   # 그리드 과밀집(경고)
    total_danger_threshold: int = int(os.getenv("TOTAL_DANGER_THRESHOLD", "15")) # 전체 과밀집
    
    # 화면 표시 및 디버그 설정
    show_boxes: bool = True
    show_footpoints: bool = True
    show_grid: bool = True
    show_heatmap: bool = True
    heatmap_alpha: float = 0.35  # 히트맵 투명도
