"""CrowdPipeline — 검출·추적·밀집도·안정화·타겟 산출을 한 루프로 묶는다.

main.py 가 얇아지고, 같은 로직을 테스트와 라즈베리파이 실행기에서
그대로 재사용할 수 있게 하는 것이 목적이다.

흐름
    frame
      └─ PersonDetector.track()        동일 인물 ID 유지
           └─ DensityAnalyzer.analyze()  원근 보정 persons/m^2
                └─ AlertDebouncer        N-of-M 히스테리시스
                     └─ TargetSmoother   타겟 좌표 평활
                          └─ CameraModel 픽셀 → 기체 기준 전방/우측 오프셋
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

from vision.density_analyzer import DensityAnalysisResult, DensityAnalyzer
from vision.detector import DetectionResult, PersonDetector
from vision.geometry import CameraModel, GroundPlane
from vision.stability import AlertDebouncer, RollingCounter, TargetSmoother


@dataclass
class TargetFix:
    """비행 모듈로 넘길 타겟. 픽셀 → 각도 → 기체 기준 지상 오프셋."""

    pixel: Tuple[int, int]
    yaw_offset_deg: float                      # 광축 기준 좌우 편차 (우측 +)
    pitch_offset_deg: float                    # 광축 기준 상하 편차 (아래 +)
    forward_m: Optional[float] = None          # 기수 방향 거리
    right_m: Optional[float] = None            # 우현 방향 거리
    altitude_m: Optional[float] = None         # 계산에 사용한 AGL 고도

    @property
    def has_ground_fix(self) -> bool:
        return self.forward_m is not None and self.right_m is not None


@dataclass
class PipelineResult:
    frame_index: int
    detection: DetectionResult
    analysis: DensityAnalysisResult
    alert_active: bool                         # 히스테리시스를 통과한 최종 경보
    raw_danger: bool                           # 이번 프레임만 본 판정
    smoothed_count: int
    target: Optional[TargetFix] = None
    fps: float = 0.0
    alert_rising_edge: bool = False            # 이번 프레임에 경보가 켜졌는가

    @property
    def unique_track_ids(self) -> int:
        return len({t for t in self.detection.track_ids if t is not None})


class CrowdPipeline:
    def __init__(
        self,
        detector: PersonDetector,
        analyzer: DensityAnalyzer,
        camera: Optional[CameraModel] = None,
        use_tracking: bool = True,
        debouncer: Optional[AlertDebouncer] = None,
        counter: Optional[RollingCounter] = None,
        smoother: Optional[TargetSmoother] = None,
        altitude_m: Optional[float] = None,
    ):
        self.detector = detector
        self.analyzer = analyzer
        self.camera = camera
        self.use_tracking = use_tracking
        self.debouncer = debouncer or AlertDebouncer()
        self.counter = counter or RollingCounter()
        self.smoother = smoother or TargetSmoother()
        self.altitude_m = altitude_m

        self._frame_index = 0
        self._prev_t: Optional[float] = None
        self._was_active = False

    # ─────────────────────── 런타임 갱신 ───────────────────────
    def set_altitude(self, altitude_m: Optional[float]) -> None:
        """비행 중 기압계/GPS 고도를 주기적으로 넣어 준다."""
        self.altitude_m = altitude_m

    def set_ground_plane(self, plane: Optional[GroundPlane]) -> None:
        self.analyzer.set_ground_plane(plane)

    def reset(self) -> None:
        """스트림 재연결·장면 전환 시 시간축 상태를 비운다."""
        self.detector.reset_tracker()
        self.debouncer.reset()
        self.counter.reset()
        self.smoother.reset()
        self._prev_t = None
        self._was_active = False

    # ───────────────────────── 메인 루프 ─────────────────────────
    def process(self, frame: np.ndarray, now: Optional[float] = None) -> PipelineResult:
        t = now if now is not None else time.monotonic()

        # 카메라 기하는 실제 프레임 크기를 따라야 한다. 설정값(capture_width 등)은
        # 요청 해상도일 뿐이고, 스트림이 다른 크기를 줄 수 있다. 어긋난 채로 두면
        # 초점거리가 틀려 타겟 방위각이 통째로 잘못 나온다.
        if self.camera is not None:
            fh, fw = frame.shape[:2]
            if (self.camera.width, self.camera.height) != (fw, fh):
                self.camera.width, self.camera.height = fw, fh

        fps = 0.0
        if self._prev_t is not None and t > self._prev_t:
            fps = 1.0 / (t - self._prev_t)
        self._prev_t = t

        detection = (self.detector.track(frame) if self.use_tracking
                     else self.detector.detect(frame))
        analysis = self.analyzer.analyze(frame.shape, detection,
                                         altitude_m=self.altitude_m)

        raw = analysis.is_overcrowded
        active = self.debouncer.update(raw, now=t)
        rising = active and not self._was_active
        self._was_active = active
        smoothed = self.counter.update(detection.count)

        target = None
        smoothed_px = self.smoother.update(analysis.target_point)
        if active and smoothed_px is not None:
            px, py = int(smoothed_px[0]), int(smoothed_px[1])
            if self.camera is not None:
                yaw, pitch = self.camera.pixel_to_angles(px, py)
                fwd = right = None
                if self.altitude_m:
                    off = self.camera.pixel_to_ground_offset(px, py, self.altitude_m)
                    if off is not None:
                        fwd, right = off
                target = TargetFix(pixel=(px, py), yaw_offset_deg=yaw,
                                   pitch_offset_deg=pitch, forward_m=fwd,
                                   right_m=right, altitude_m=self.altitude_m)
            else:
                target = TargetFix(pixel=(px, py), yaw_offset_deg=0.0,
                                   pitch_offset_deg=0.0)

        self._frame_index += 1
        return PipelineResult(
            frame_index=self._frame_index - 1,
            detection=detection,
            analysis=analysis,
            alert_active=active,
            raw_danger=raw,
            smoothed_count=smoothed,
            target=target,
            fps=fps,
            alert_rising_edge=rising,
        )

    def render(self, frame: np.ndarray, result: PipelineResult, **flags) -> np.ndarray:
        return self.analyzer.draw_visualization(
            frame=frame,
            detection=result.detection,
            analysis=result.analysis,
            fps=result.fps,
            alert_active=result.alert_active,
            smoothed_count=result.smoothed_count,
            target_override=result.target.pixel if result.target else None,
            **flags,
        )
