from dataclasses import dataclass, field
from typing import List, Tuple
import numpy as np
import torch
from ultralytics import YOLO

@dataclass
class DetectionResult:
    """YOLO 추론 결과 데이터 구조체"""
    boxes: List[Tuple[int, int, int, int]] = field(default_factory=list)  # (x1, y1, x2, y2)
    confidences: List[float] = field(default_factory=list)
    foot_points: List[Tuple[int, int]] = field(default_factory=list)      # (foot_x, foot_y)
    count: int = 0


class PersonDetector:
    """YOLOv8 기반 인물(Person) 전용 검출기"""

    def __init__(self, model_name: str = "yolov8n.pt", conf_threshold: float = 0.45, iou_threshold: float = 0.5, device: str = "auto"):
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.device = self._select_device(device)
        
        print(f"[PersonDetector] Loading YOLO model: {model_name} on device: {self.device}...")
        self.model = YOLO(model_name)
        print(f"[PersonDetector] Model loaded successfully.")

    def _select_device(self, preferred: str) -> str:
        if preferred != "auto":
            return preferred
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def detect(self, frame: np.ndarray) -> DetectionResult:
        """
        입력 영상 프레임에서 Person (클래스 0) 객체를 검출하고
        바운딩 박스 및 발목 좌표(Foot-point)를 반환합니다.
        """
        if frame is None or frame.size == 0:
            return DetectionResult()

        # classes=[0] -> Person 클래스만 필터링
        results = self.model(
            frame,
            classes=[0],
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False,
        )

        boxes: List[Tuple[int, int, int, int]] = []
        confidences: List[float] = []
        foot_points: List[Tuple[int, int]] = []

        if len(results) > 0 and results[0].boxes is not None:
            boxes_data = results[0].boxes.xyxy.cpu().numpy()
            confs_data = results[0].boxes.conf.cpu().numpy()

            for box, conf in zip(boxes_data, confs_data):
                x1, y1, x2, y2 = map(int, box)
                # 발목 좌표: 지상 위치 투영에 사용되는 바운딩박스 하단 중앙
                foot_x = int((x1 + x2) / 2)
                foot_y = y2

                boxes.append((x1, y1, x2, y2))
                confidences.append(float(conf))
                foot_points.append((foot_x, foot_y))

        return DetectionResult(
            boxes=boxes,
            confidences=confidences,
            foot_points=foot_points,
            count=len(boxes)
        )
