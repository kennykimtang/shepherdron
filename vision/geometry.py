"""지상 평면 기하 — 픽셀 좌표를 실제 거리로 환산한다.

이 모듈이 필요한 이유:
  카메라는 비스듬히 지면을 보므로, 화면 위쪽 1픽셀과 아래쪽 1픽셀이
  덮는 실제 지면 면적이 다르다. 원근 보정 없이 "셀당 인원수"를 세면
  멀리 있는 군중은 과대평가되고 가까운 군중은 과소평가된다.
  밀집도(persons/m^2)를 제대로 내려면 지면 평면으로 투영해야 한다.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

Point = Tuple[float, float]


def _shoelace(poly: Sequence[Point]) -> float:
    """다각형 넓이 (신발끈 공식). 꼭짓점 순서와 무관하게 양수를 반환."""
    n = len(poly)
    acc = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        acc += x1 * y2 - x2 * y1
    return abs(acc) * 0.5


@dataclass
class GroundPlane:
    """영상 평면 ↔ 지상 평면 호모그래피.

    지면이 평평하다고 가정한다. 영상 속 네 점과 그에 대응하는 실제
    지면 좌표(미터)를 주면 둘 사이의 사영 변환을 구한다.

    실측 방법
      1. 촬영 지점 지면에 사각형을 표시하고 네 변의 길이를 잰다.
      2. 그 네 모서리의 화면 픽셀 좌표를 읽는다 (scripts/calibrate_ground.py).
      3. image_points / world_points 를 같은 순서로 넘긴다.
    """

    H: np.ndarray          # 3x3, image -> world(metre)
    image_points: List[Point]
    world_points: List[Point]
    label: str = ""

    # ─────────────────────────── 생성 ───────────────────────────
    @classmethod
    def from_points(
        cls,
        image_points: Sequence[Point],
        world_points: Sequence[Point],
        label: str = "",
    ) -> "GroundPlane":
        if len(image_points) != len(world_points):
            raise ValueError("image_points 와 world_points 의 개수가 다릅니다.")
        if len(image_points) < 4:
            raise ValueError("호모그래피를 구하려면 대응점이 최소 4쌍 필요합니다.")

        src = np.asarray(image_points, dtype=np.float64).reshape(-1, 1, 2)
        dst = np.asarray(world_points, dtype=np.float64).reshape(-1, 1, 2)

        import cv2  # 지연 임포트: 기하 계산만 쓰는 테스트에서는 불필요

        if len(image_points) == 4:
            H = cv2.getPerspectiveTransform(src.astype(np.float32), dst.astype(np.float32))
            H = H.astype(np.float64)
        else:
            H, _ = cv2.findHomography(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
            if H is None:
                raise ValueError("호모그래피 추정에 실패했습니다. 대응점을 다시 확인하세요.")
        return cls(H=H, image_points=[tuple(p) for p in image_points],
                   world_points=[tuple(p) for p in world_points], label=label)

    # ─────────────────────────── 직렬화 ───────────────────────────
    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "image_points": [list(p) for p in self.image_points],
            "world_points": [list(p) for p in self.world_points],
            "H": self.H.tolist(),
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "GroundPlane":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            H=np.asarray(d["H"], dtype=np.float64),
            image_points=[tuple(p) for p in d["image_points"]],
            world_points=[tuple(p) for p in d["world_points"]],
            label=d.get("label", ""),
        )

    # ─────────────────────────── 투영 ───────────────────────────
    def to_world(self, points: Iterable[Point]) -> List[Optional[Point]]:
        """픽셀 좌표 목록을 지상 좌표(미터)로 변환.

        지평선 위(또는 그 너머)의 점은 지면과 만나지 않으므로 None 을 돌려준다.
        """
        out: List[Optional[Point]] = []
        for x, y in points:
            v = self.H @ np.array([x, y, 1.0])
            w = v[2]
            if abs(w) < 1e-9:
                out.append(None)          # 지평선 — 지면 교점 없음
                continue
            out.append((float(v[0] / w), float(v[1] / w)))
        return out

    def polygon_area_m2(self, poly: Sequence[Point]) -> Optional[float]:
        """영상 속 다각형이 덮는 실제 지면 면적(m^2).

        꼭짓점 중 하나라도 지평선 너머면 None (면적 무한대 또는 정의 불가).
        """
        world = self.to_world(poly)
        if any(p is None for p in world):
            return None
        area = _shoelace([p for p in world if p is not None])
        if not math.isfinite(area) or area <= 0:
            return None
        return area

    def is_calibrated(self) -> bool:
        return self.H is not None and self.H.shape == (3, 3)


@dataclass
class CameraModel:
    """핀홀 카메라 + 고정 짐벌 각도. 픽셀 → 기체 기준 지상 오프셋.

    Phase 2 (MAVLink) 가 쓸 수 있는 형태로 타겟 좌표를 내보내기 위한 것.
    DensityAnalyzer 가 내는 타겟 셀 중심(픽셀)을 "기수 기준 전방 X m,
    우측 Y m" 로 바꿔 주면, 비행 모듈이 기체 yaw 만 더해 GPS 좌표를 만든다.

    좌표계: X 전방, Y 우측, Z 하방 (기체 기준).
    """

    width: int
    height: int
    hfov_deg: float = 102.0        # Camera Module 3 Wide 수평 화각
    vfov_deg: float = 67.0         # 〃 수직 화각
    pitch_deg: float = 90.0        # 수평선 기준 하향각. 90 = 완전 수직(나디르)

    @property
    def fx(self) -> float:
        return (self.width / 2.0) / math.tan(math.radians(self.hfov_deg) / 2.0)

    @property
    def fy(self) -> float:
        return (self.height / 2.0) / math.tan(math.radians(self.vfov_deg) / 2.0)

    def pixel_to_angles(self, px: float, py: float) -> Tuple[float, float]:
        """광축 기준 (수평 편차, 수직 편차) 각도. 단위 도(degree).

        오른쪽이 +yaw, 아래쪽이 +pitch.
        """
        cx, cy = self.width / 2.0, self.height / 2.0
        yaw = math.degrees(math.atan2(px - cx, self.fx))
        pitch = math.degrees(math.atan2(py - cy, self.fy))
        return yaw, pitch

    def pixel_to_ground_offset(
        self, px: float, py: float, altitude_m: float
    ) -> Optional[Tuple[float, float]]:
        """고도 altitude_m 에서 픽셀이 가리키는 지점의 기체 기준 오프셋(m).

        반환: (전방 +m, 우측 +m). 광선이 지면과 만나지 않으면 None.
        """
        if altitude_m <= 0:
            return None

        cx, cy = self.width / 2.0, self.height / 2.0
        x = (px - cx) / self.fx          # 카메라 우측
        y = (py - cy) / self.fy          # 카메라 하단
        th = math.radians(self.pitch_deg)

        # 카메라 축을 기체 축으로 회전 (X 전방, Y 우측, Z 하방)
        dx = math.cos(th) - y * math.sin(th)    # 전방 성분
        dy = x                                   # 우측 성분
        dz = math.sin(th) + y * math.cos(th)    # 하방 성분

        if dz <= 1e-9:
            return None                          # 지평선 위 — 지면 교점 없음

        t = altitude_m / dz
        return (float(t * dx), float(t * dy))

    def ground_footprint_m2(self, altitude_m: float) -> Optional[float]:
        """나디르 기준 화면 전체가 덮는 지면 면적(m^2). 참고용 개략치."""
        if self.pitch_deg < 85.0:
            return None                          # 기울어지면 사다리꼴 — 단순식 불가
        w = 2 * altitude_m * math.tan(math.radians(self.hfov_deg) / 2.0)
        h = 2 * altitude_m * math.tan(math.radians(self.vfov_deg) / 2.0)
        return float(w * h)


def ground_plane_from_altitude(
    camera: CameraModel, altitude_m: float
) -> Optional[GroundPlane]:
    """캘리브레이션 없이, 알려진 고도로부터 지상 평면을 합성한다.

    현장에서 사각형을 재서 캘리브레이션할 수 없는 비행 중에 쓴다.
    고도(기압계/GPS)와 짐벌 각도만 있으면 되므로 실용적이지만,
    지면이 평평하고 고도가 정확하다는 가정에 전적으로 의존한다.
    """
    w, h = camera.width, camera.height
    # 지면과 확실히 만나는 하단 영역의 네 점을 쓴다
    img_pts = [(w * 0.1, h * 0.55), (w * 0.9, h * 0.55),
               (w * 0.9, h * 0.95), (w * 0.1, h * 0.95)]
    world_pts: List[Point] = []
    for px, py in img_pts:
        off = camera.pixel_to_ground_offset(px, py, altitude_m)
        if off is None:
            return None
        fwd, right = off
        world_pts.append((right, fwd))           # (동/우, 북/전) 평면
    return GroundPlane.from_points(img_pts, world_pts,
                                   label=f"synthetic@{altitude_m:.1f}m")
