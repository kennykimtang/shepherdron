"""전술 지도 — 카메라가 본 사람들을 위에서 내려다본 바닥 좌표로 옮긴다.

상용 군중계수기는 '몇 명이 얼마나 붐비는가'에서 멈춘다. Shepherdron 은
그 다음을 해야 한다. 드론을 어디로 보내고, 사람들을 어느 쪽으로 유도할지.
그러려면 영상 좌표가 아니라 바닥 좌표(미터)가 필요하다.

투영 (캘리브레이션 불필요)
    사람 키를 1.7 m 로 두면 바운딩박스 높이 h 픽셀이 거리를 준다.
        거리   = fy · 1.7 / h
        좌우   = (x - cx) / fx · 거리
    밀집도 추정이 쓰는 겉보기 크기 가정과 같다. 카메라가 기울어 있으면
    이 거리는 사선거리이므로 실제 바닥 거리보다 약간 길게 나온다.

유도 방향
    핫스팟 둘레 반경 r 의 원 위에서 밀집도를 재고, 가장 덜 붐비는 쪽을
    고른다. 단 카메라가 보지 못하는 곳(시야 밖, 관측 거리 너머)은 후보에서
    뺀다. '비어 보이는 것'과 '실제로 비어 있는 것'은 다르기 때문이다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from vision.detector import DetectionResult

PERSON_H_M = 1.7
Point = Tuple[float, float]          # (우측 m, 전방 m) — 카메라 원점


@dataclass
class GroundPerson:
    right_m: float
    forward_m: float
    density: float = 0.0             # 그 자리의 밀집도 (명/m²)


@dataclass
class Evacuation:
    bearing_deg: float               # 0 = 전방(카메라에서 멀어지는 쪽), 시계방향 +
    density_there: float             # 유도 방향 끝의 밀집도
    point: Point                     # 유도 방향 끝 지점
    name: str = ""


@dataclass
class TacticalPicture:
    people: List[GroundPerson] = field(default_factory=list)
    hotspot: Optional[Point] = None
    hotspot_density: float = 0.0
    evacuation: Optional[Evacuation] = None
    hfov_deg: float = 70.0
    max_range_m: float = 0.0


def focal_px(width: int, hfov_deg: float) -> float:
    return (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)


def project(detection: DetectionResult, width: int, height: int,
            hfov_deg: float = 70.0, person_h_m: float = PERSON_H_M) -> List[Point]:
    """발목점 → 바닥 좌표 (우측 m, 전방 m)."""
    f = focal_px(width, hfov_deg)
    cx = width / 2.0
    out: List[Point] = []
    for (fx_, _fy), (_x1, y1, _x2, y2) in zip(detection.foot_points, detection.boxes):
        h = max(1.0, float(y2 - y1))
        rng = f * person_h_m / h
        out.append(((fx_ - cx) / f * rng, rng))
    return out


def ground_density(q: Point, pts: Sequence[Point], sigma_m: float) -> float:
    inv = 1.0 / (2.0 * math.pi * sigma_m * sigma_m)
    two = 2.0 * sigma_m * sigma_m
    return sum(inv * math.exp(-((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) / two)
               for p in pts)


BEARING_KO = ["전방", "우전방", "우측", "우후방", "후방", "좌후방", "좌측", "좌전방"]


def bearing_name(deg: float) -> str:
    return BEARING_KO[int(((deg % 360) + 22.5) // 45) % 8]


def in_view(q: Point, hfov_deg: float, max_range_m: float,
            margin_deg: float = 2.0) -> bool:
    r, f = q
    if f <= 0.3:
        return False
    if math.degrees(abs(math.atan2(r, f))) > hfov_deg / 2.0 - margin_deg:
        return False
    return math.hypot(r, f) <= max_range_m


def evacuation_bearing(pts: Sequence[Point], hotspot: Point, sigma_m: float,
                       hfov_deg: float, max_range_m: float,
                       radius_m: float = 2.5, step_deg: float = 15.0
                       ) -> Optional[Evacuation]:
    """핫스팟에서 가장 덜 붐비는, 그리고 관측되는 방향."""
    best: Optional[Evacuation] = None
    n = int(round(360.0 / step_deg))
    for k in range(n):
        th = k * step_deg
        q = (hotspot[0] + radius_m * math.sin(math.radians(th)),
             hotspot[1] + radius_m * math.cos(math.radians(th)))
        if not in_view(q, hfov_deg, max_range_m):
            continue
        d = ground_density(q, pts, sigma_m)
        if best is None or d < best.density_there - 1e-9:
            best = Evacuation(th, d, q, bearing_name(th))
    return best


def build_picture(detection: DetectionResult, width: int, height: int,
                  sigma_m: float = 0.75, hfov_deg: float = 70.0,
                  person_h_m: float = PERSON_H_M) -> TacticalPicture:
    pts = project(detection, width, height, hfov_deg, person_h_m)
    pic = TacticalPicture(hfov_deg=hfov_deg)
    if not pts:
        return pic
    pic.people = [GroundPerson(r, f, ground_density((r, f), pts, sigma_m))
                  for r, f in pts]
    pic.max_range_m = max(math.hypot(p.right_m, p.forward_m) for p in pic.people) * 1.15
    top = max(pic.people, key=lambda p: p.density)
    pic.hotspot = (top.right_m, top.forward_m)
    pic.hotspot_density = top.density
    pic.evacuation = evacuation_bearing(pts, pic.hotspot, sigma_m, hfov_deg,
                                        pic.max_range_m)
    return pic
