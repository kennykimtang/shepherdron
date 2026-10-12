from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import torch
from ultralytics import YOLO


@dataclass
class DetectionResult:
    """YOLO 추론 결과 데이터 구조체.

    track_ids 는 추적을 켰을 때만 채워진다. 꺼져 있으면 전부 None 이며,
    이 경우 프레임 간 동일 인물을 식별할 수 없다.
    """

    boxes: List[Tuple[int, int, int, int]] = field(default_factory=list)   # (x1, y1, x2, y2)
    confidences: List[float] = field(default_factory=list)
    foot_points: List[Tuple[int, int]] = field(default_factory=list)       # (foot_x, foot_y)
    track_ids: List[Optional[int]] = field(default_factory=list)
    count: int = 0

    @property
    def tracked(self) -> bool:
        return bool(self.track_ids) and any(t is not None for t in self.track_ids)


class PersonDetector:
    """YOLOv8 기반 인물(Person) 전용 검출기.

    detect() 는 프레임 단위 독립 검출, track() 은 ByteTrack 으로 프레임 간
    동일 인물에 ID 를 유지한다. 군중 카운트를 드론 명령으로 연결하려면
    track() 을 쓰는 쪽이 안전하다 — 한 프레임 미검출로 인원수가 흔들리는 것을
    추적기가 보간해 주기 때문이다.
    """

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        conf_threshold: float = 0.45,
        iou_threshold: float = 0.5,
        device: str = "auto",
        imgsz: int = 640,
        tracker: str = "bytetrack.yaml",
    ):
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.imgsz = imgsz
        self.tracker = tracker
        self.device = self._select_device(device)

        print(f"[PersonDetector] Loading YOLO model: {model_name} on device: {self.device} (imgsz={imgsz})...")
        self.model = YOLO(model_name)
        print("[PersonDetector] Model loaded successfully.")

    # ─────────────────────────── 장치 선택 ───────────────────────────
    @staticmethod
    def _select_device(preferred: str) -> str:
        if preferred != "auto":
            return preferred
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    # ─────────────────────────── 공통 파싱 ───────────────────────────
    def _parse(self, results) -> DetectionResult:
        boxes: List[Tuple[int, int, int, int]] = []
        confidences: List[float] = []
        foot_points: List[Tuple[int, int]] = []
        track_ids: List[Optional[int]] = []

        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            return DetectionResult()

        b = results[0].boxes
        xyxy = b.xyxy.cpu().numpy()
        confs = b.conf.cpu().numpy()
        ids = b.id.cpu().numpy().astype(int) if getattr(b, "id", None) is not None else None

        for i, (box, conf) in enumerate(zip(xyxy, confs)):
            x1, y1, x2, y2 = map(int, box)
            boxes.append((x1, y1, x2, y2))
            confidences.append(float(conf))
            # 발목 좌표: 지상 접지점 추정에 쓰는 바운딩박스 하단 중앙
            foot_points.append((int((x1 + x2) / 2), y2))
            track_ids.append(int(ids[i]) if ids is not None else None)

        return DetectionResult(
            boxes=boxes,
            confidences=confidences,
            foot_points=foot_points,
            track_ids=track_ids,
            count=len(boxes),
        )

    # ─────────────────────────── 추론 ───────────────────────────
    def detect(self, frame: np.ndarray) -> DetectionResult:
        """프레임 단위 독립 검출. 프레임 간 ID 연속성은 없다."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return DetectionResult()

        results = self.model(
            frame,
            classes=[0],              # Person 만
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,
        )
        return self._parse(results)

    def track(self, frame: np.ndarray) -> DetectionResult:
        """ByteTrack 으로 동일 인물에 ID 를 유지하며 검출.

        persist=True 이므로 호출 간 추적 상태가 유지된다. 스트림이 끊겼거나
        전혀 다른 장면으로 전환됐다면 reset_tracker() 를 불러 상태를 비운다.
        """
        if frame is None or getattr(frame, "size", 0) == 0:
            return DetectionResult()

        results = self.model.track(
            frame,
            classes=[0],
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            imgsz=self.imgsz,
            device=self.device,
            tracker=self.tracker,
            persist=True,
            verbose=False,
        )
        return self._parse(results)

    def reset_tracker(self) -> None:
        """추적 상태 초기화. 스트림 재연결·장면 전환 후에 호출한다."""
        for predictor_attr in ("predictor",):
            predictor = getattr(self.model, predictor_attr, None)
            if predictor is not None and hasattr(predictor, "trackers"):
                for t in predictor.trackers:
                    if hasattr(t, "reset"):
                        t.reset()
