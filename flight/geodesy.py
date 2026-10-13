"""측지 계산 — 기체 기준 오프셋을 위경도로 바꾼다.

비전 모듈은 "기수 방향 +5.4 m, 우현 +10.0 m" 같은 **기체 기준** 오프셋을 낸다.
여기에 기체의 현재 위치와 기수 방위(yaw)를 합쳐 실제 GPS 좌표로 만든다.

좌표 약속
    body frame : X 전방(기수 방향), Y 우현
    NED        : N 북쪽, E 동쪽
    yaw        : 북쪽 기준 시계방향 각도 (0 = 북, 90 = 동)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

# WGS84 장반경. 100 m 안팎 거리에서 구면 근사 오차는 1 cm 미만이라 충분하다.
EARTH_RADIUS_M = 6378137.0


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float
    alt_m: Optional[float] = None       # AGL 상대고도

    def __str__(self) -> str:
        a = f", {self.alt_m:.1f} m AGL" if self.alt_m is not None else ""
        return f"({self.lat:.7f}, {self.lon:.7f}{a})"


def body_offset_to_ned(forward_m: float, right_m: float, yaw_deg: float) -> Tuple[float, float]:
    """기체 기준 오프셋 → 북/동 오프셋.

    기수가 북(yaw=0)을 향하면 전방은 그대로 북, 우현은 동이다.
    기수가 동(yaw=90)을 향하면 전방이 동, 우현이 남이 된다.
    """
    y = math.radians(yaw_deg)
    north = forward_m * math.cos(y) - right_m * math.sin(y)
    east = forward_m * math.sin(y) + right_m * math.cos(y)
    return north, east


def ned_to_body_offset(north_m: float, east_m: float, yaw_deg: float) -> Tuple[float, float]:
    """북/동 오프셋 → 기체 기준 오프셋. body_offset_to_ned 의 역변환.

    비전이 보는 것과 같은 값을 만들 때 쓴다 — 기체가 목표에 접근하면
    오프셋이 줄어드는 것이 정상이다. 고정 오프셋을 계속 재사용하면
    목표가 함께 도망가므로 영영 도달하지 못한다.
    """
    y = math.radians(yaw_deg)
    forward = north_m * math.cos(y) + east_m * math.sin(y)
    right = -north_m * math.sin(y) + east_m * math.cos(y)
    return forward, right


def offset_point(origin: GeoPoint, north_m: float, east_m: float,
                 alt_m: Optional[float] = None) -> GeoPoint:
    """기준점에서 북/동으로 이동한 지점의 위경도."""
    dlat = math.degrees(north_m / EARTH_RADIUS_M)
    # 경도 1도의 실제 거리는 위도가 높을수록 짧아진다
    coslat = math.cos(math.radians(origin.lat))
    if abs(coslat) < 1e-12:                       # 극점 — 경도가 정의되지 않는다
        raise ValueError("극점 근처에서는 동서 오프셋을 계산할 수 없습니다.")
    dlon = math.degrees(east_m / (EARTH_RADIUS_M * coslat))
    return GeoPoint(origin.lat + dlat, origin.lon + dlon,
                    alt_m if alt_m is not None else origin.alt_m)


def target_from_body_offset(
    origin: GeoPoint,
    yaw_deg: float,
    forward_m: float,
    right_m: float,
    alt_m: Optional[float] = None,
) -> GeoPoint:
    """비전 타겟(기체 기준 미터) → GPS 좌표. Phase 2 가 쓰는 주 진입점."""
    north, east = body_offset_to_ned(forward_m, right_m, yaw_deg)
    return offset_point(origin, north, east, alt_m)


def distance_m(a: GeoPoint, b: GeoPoint) -> float:
    """두 지점 사이 수평 거리(m). 하버사인."""
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(a: GeoPoint, b: GeoPoint) -> float:
    """a 에서 b 를 바라보는 방위각(도). 북 기준 시계방향 0~360."""
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dl = math.radians(b.lon - a.lon)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def clamp_to_radius(
    origin: GeoPoint, target: GeoPoint, max_radius_m: float
) -> Tuple[GeoPoint, bool]:
    """타겟을 기준점 반경 안으로 제한한다.

    **안전 장치다.** 비전이 잘못된 타겟을 내거나 고도가 틀리면 오프셋이
    수백 미터로 튈 수 있다. 그대로 비행 명령이 되면 기체가 시야 밖으로
    날아간다. 반경을 넘으면 같은 방위의 경계선 지점으로 잘라낸다.

    반환: (제한된 타겟, 잘렸는지 여부)
    """
    if max_radius_m <= 0:
        raise ValueError("max_radius_m 은 0보다 커야 합니다.")

    d = distance_m(origin, target)
    if d <= max_radius_m:
        return target, False

    brg = math.radians(bearing_deg(origin, target))
    north = max_radius_m * math.cos(brg)
    east = max_radius_m * math.sin(brg)
    return offset_point(origin, north, east, target.alt_m), True
