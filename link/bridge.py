"""VisionReport(픽셀) → GuidanceMission 입력(미터) 변환.

노트북은 "화면 어디에서 보았는가"만 보낸다. 지상 거리로 바꾸려면 기체의
AGL 고도가 필요한데, 그건 Pi 만 안다. 그래서 환산은 여기, 기체 쪽에서 한다.

고도를 모르면 has_ground_fix 가 False 가 되고 GuidanceMission 은 비행 명령을
내지 않는다. 고도 없이 추정한 거리로 기체를 보내는 일은 없어야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from link.protocol import VisionReport
from vision.geometry import CameraModel


@dataclass
class MissionTarget:
    """GuidanceMission 이 기대하는 타겟 형태 (vision.TargetFix 와 호환)."""

    pixel: Tuple[int, int]
    yaw_offset_deg: float
    pitch_offset_deg: float
    forward_m: Optional[float] = None
    right_m: Optional[float] = None
    altitude_m: Optional[float] = None

    @property
    def has_ground_fix(self) -> bool:
        return self.forward_m is not None and self.right_m is not None


@dataclass
class MissionInput:
    """GuidanceMission.update() 가 받는 형태. PipelineResult 와 같은 표면."""

    alert_active: bool
    alert_rising_edge: bool
    smoothed_count: int
    target: Optional[MissionTarget]
    peak_density: Optional[float] = None
    link_age_s: float = 0.0


class VisionBridge:
    def __init__(self, camera: CameraModel):
        self.camera = camera

    def convert(
        self,
        report: Optional[VisionReport],
        altitude_m: Optional[float],
        now: Optional[float] = None,
    ) -> Optional[MissionInput]:
        """보고가 없거나 오래됐으면 None — 호출 측이 '관측 없음'으로 다룬다."""
        if report is None:
            return None

        target = None
        if report.has_target:
            # 카메라 기하는 실제 프레임 크기를 따라야 한다. 노트북이 다른 해상도로
            # 추론하면 초점거리가 틀려 방위각이 통째로 잘못 나온다.
            if (self.camera.width, self.camera.height) != (report.frame_w, report.frame_h):
                self.camera.width, self.camera.height = report.frame_w, report.frame_h

            px, py = report.target_px
            yaw, pitch = self.camera.pixel_to_angles(px, py)
            fwd = right = None
            if altitude_m and altitude_m > 0:
                off = self.camera.pixel_to_ground_offset(px, py, altitude_m)
                if off is not None:
                    fwd, right = off
            target = MissionTarget(pixel=(px, py), yaw_offset_deg=yaw,
                                   pitch_offset_deg=pitch, forward_m=fwd,
                                   right_m=right, altitude_m=altitude_m)

        return MissionInput(
            alert_active=report.alert_active,
            alert_rising_edge=report.alert_rising_edge,
            smoothed_count=report.count,
            target=target,
            peak_density=report.peak_density,
            link_age_s=report.age(now),
        )
