"""적응형 커널 밀도추정(KDE) 기반 밀집도 — 3x3 격자의 한계를 대체한다.

격자 방식의 문제
    1. 해상도. 강의실 폭 10 m 를 3 칸으로 나누면 한 칸이 3.3 m 다.
       군중 압사는 1 m 규모에서 생기므로 격자가 그걸 못 본다.
    2. 경계. 군집이 셀 경계에 걸치면 양쪽으로 쪼개져 둘 다 안전으로 읽힌다.
    3. 잘게 쪼개도 해결이 안 된다. 칸마다 0~1 명이 되어 값이 더 튄다.

이 모듈의 방식
    사람마다 가우시안 커널을 깔고 모두 더해 연속적인 밀집도 장을 만든다.
    격자가 없으므로 경계 문제가 없고, 최대점이 곧 드론이 갈 좌표가 된다.
    균일한 군중에 대해 KDE 값은 실제 밀집도로 수렴한다(불편추정).

거리 환산
    캘리브레이션이 없어도 persons/m^2 를 낼 수 있다. 사람 키를 1.7 m 로 보면
    바운딩박스 높이가 그 사람까지의 축척(m/px)을 준다. 가까운 사람은 커널이
    넓고 먼 사람은 좁다 — 월드 좌표에서는 둘 다 같은 sigma 다.
    이는 발목점 투영이 이미 쓰고 있는 가정과 같다.

    지상 평면 캘리브레이션이 있으면 호모그래피로 실제 월드 좌표를 써서
    거리를 정확히 구한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from vision.detector import DetectionResult
from vision.geometry import GroundPlane

DEFAULT_SIGMA_M = 0.75          # 커널 폭. 군중 압사 관심 규모가 1~2 m 다
DEFAULT_PERSON_HEIGHT_M = 1.7


@dataclass
class PersonDensity:
    """한 사람의 위치에서 평가한 밀집도."""
    index: int
    point: Tuple[int, int]                   # 영상 좌표 (발목점)
    density: float                           # persons/m^2
    scale_m_per_px: float                    # 그 지점의 축척
    world: Optional[Tuple[float, float]] = None


@dataclass
class DensityFieldResult:
    peak_density: float = 0.0
    peak_point: Optional[Tuple[int, int]] = None
    mean_density: float = 0.0
    per_person: List[PersonDensity] = field(default_factory=list)
    heat: Optional[np.ndarray] = None        # (h, w) float32 표시용 저해상도 장
    heat_shape: Optional[Tuple[int, int]] = None
    calibrated: bool = False
    sigma_m: float = DEFAULT_SIGMA_M
    level: str = "SAFE"
    warn: float = 2.0
    danger: float = 4.0

    @property
    def unit(self) -> str:
        return "persons/m²"

    @property
    def source(self) -> str:
        return "캘리브레이션" if self.calibrated else "겉보기 크기 추정"

    @property
    def is_overcrowded(self) -> bool:
        return self.level == "DANGER"


def _box_heights(detection: DetectionResult) -> List[float]:
    return [max(1.0, float(y2 - y1)) for (_, y1, _, y2) in detection.boxes]


class DensityFieldEstimator:
    """발목점 집합에서 연속 밀집도 장을 만든다."""

    def __init__(
        self,
        sigma_m: float = DEFAULT_SIGMA_M,
        warn: float = 2.0,
        danger: float = 4.0,
        person_height_m: float = DEFAULT_PERSON_HEIGHT_M,
        field_width: int = 192,
        ground_plane: Optional[GroundPlane] = None,
    ):
        if sigma_m <= 0:
            raise ValueError("sigma_m 은 0 보다 커야 합니다")
        self.sigma_m = float(sigma_m)
        self.warn = float(warn)
        self.danger = float(danger)
        self.person_height_m = float(person_height_m)
        self.field_width = int(field_width)
        self.ground_plane = ground_plane

    def set_ground_plane(self, plane: Optional[GroundPlane]) -> None:
        self.ground_plane = plane

    @property
    def calibrated(self) -> bool:
        return self.ground_plane is not None and self.ground_plane.is_calibrated

    # ────────────────────── 메인 ──────────────────────
    def estimate(
        self,
        frame_shape: Tuple[int, ...],
        detection: DetectionResult,
        make_heat: bool = True,
    ) -> DensityFieldResult:
        h, w = frame_shape[:2]
        pts = list(detection.foot_points)
        res = DensityFieldResult(sigma_m=self.sigma_m, warn=self.warn,
                                 danger=self.danger, calibrated=self.calibrated)
        if not pts:
            if make_heat:
                res.heat, res.heat_shape = self._empty_heat(w, h)
            return res

        heights = _box_heights(detection)
        if len(heights) != len(pts):                 # 박스 없이 발목점만 온 경우
            heights = [max(1.0, h * 0.25)] * len(pts)

        # 각 지점의 축척 (m/px)
        scales = [self.person_height_m / hp for hp in heights]

        world: List[Optional[Tuple[float, float]]] = [None] * len(pts)
        if self.calibrated:
            projected = self.ground_plane.to_world(pts)
            world = [tuple(p) if p is not None else None for p in projected]

        # ── 각 사람 위치에서 밀집도 평가 (정확, O(N^2)) ──
        inv = 1.0 / (2.0 * math.pi * self.sigma_m ** 2)
        two_s2 = 2.0 * self.sigma_m ** 2
        per: List[PersonDensity] = []
        for i, (pi, si) in enumerate(zip(pts, scales)):
            total = 0.0
            for j, (pj, sj) in enumerate(zip(pts, scales)):
                d_m = self._distance_m(i, j, pi, pj, si, sj, world)
                if d_m is None:
                    continue
                total += inv * math.exp(-(d_m * d_m) / two_s2)
            per.append(PersonDensity(index=i, point=(int(pi[0]), int(pi[1])),
                                     density=total, scale_m_per_px=si,
                                     world=world[i]))

        res.per_person = per
        best = max(per, key=lambda p: p.density)
        res.peak_density = best.density
        res.peak_point = best.point
        res.mean_density = sum(p.density for p in per) / len(per)
        res.level = ("DANGER" if res.peak_density >= self.danger
                     else "WARNING" if res.peak_density >= self.warn
                     else "SAFE")

        if make_heat:
            res.heat, res.heat_shape = self._raster(w, h, pts, scales)
        return res

    # ────────────────────── 거리 ──────────────────────
    def _distance_m(self, i, j, pi, pj, si, sj, world) -> Optional[float]:
        if i == j:
            return 0.0
        wi, wj = world[i], world[j]
        if wi is not None and wj is not None:
            return math.hypot(wi[0] - wj[0], wi[1] - wj[1])
        # 겉보기 크기 추정 : 두 지점 축척의 평균을 쓴다
        d_px = math.hypot(pi[0] - pj[0], pi[1] - pj[1])
        return d_px * (si + sj) * 0.5

    # ────────────────────── 표시용 래스터 ──────────────────────
    def _field_size(self, w: int, h: int) -> Tuple[int, int]:
        fw = min(self.field_width, max(16, w))
        fh = max(9, int(round(h * fw / max(1, w))))
        return fw, fh

    def _empty_heat(self, w: int, h: int):
        fw, fh = self._field_size(w, h)
        return np.zeros((fh, fw), np.float32), (fh, fw)

    def _raster(self, w: int, h: int, pts, scales):
        """영상 좌표계 저해상도 장. 사람마다 가우시안 패치를 더한다."""
        fw, fh = self._field_size(w, h)
        k = fw / float(w)                                  # 영상 → 필드 배율
        heat = np.zeros((fh, fw), np.float32)
        inv = 1.0 / (2.0 * math.pi * self.sigma_m ** 2)
        two_s2 = 2.0 * self.sigma_m ** 2

        for (px, py), s in zip(pts, scales):
            # 월드 sigma 를 이 지점의 영상 픽셀로, 다시 필드 픽셀로
            sigma_px = self.sigma_m / max(s, 1e-6) * k
            sigma_px = float(np.clip(sigma_px, 1.0, max(fw, fh)))
            cx, cy = px * k, py * k
            rad = int(math.ceil(3.0 * sigma_px))
            x0, x1 = max(0, int(cx) - rad), min(fw, int(cx) + rad + 1)
            y0, y1 = max(0, int(cy) - rad), min(fh, int(cy) + rad + 1)
            if x0 >= x1 or y0 >= y1:
                continue
            ys = np.arange(y0, y1, dtype=np.float32) - cy
            xs = np.arange(x0, x1, dtype=np.float32) - cx
            # 필드 픽셀 거리 → 미터
            d2_m = ((ys[:, None] ** 2) + (xs[None, :] ** 2)) * (s / k) ** 2
            heat[y0:y1, x0:x1] += inv * np.exp(-d2_m / two_s2)
        return heat, (fh, fw)



# ─────────────────── 등급 (행안부 군중밀집 4단계) ───────────────────
# 상용 관제 시스템(인텔리빅스 등)이 쓰는 표기를 그대로 따른다.
LEVELS = [
    (0, "안전", "#2E9E4F"),
    (1, "관심", "#5B6BD6"),
    (2, "주의", "#E0B32A"),
    (3, "경계", "#E07B2A"),
    (4, "심각", "#D14437"),
]
DEFAULT_TIERS = (1.0, 2.0, 3.0, 4.0)        # 명/m^2 경계값


def level_of(density: float, tiers: Sequence[float] = DEFAULT_TIERS) -> int:
    return sum(1 for t in tiers if density >= t)


def level_name(idx: int) -> str:
    return LEVELS[min(idx, len(LEVELS) - 1)][1]


def level_color(idx: int) -> str:
    return LEVELS[min(idx, len(LEVELS) - 1)][2]


def level_tag(idx: int) -> str:
    return f"{idx}-{level_name(idx)}"


# ─────────────────── ROI (관심 영역) ───────────────────
@dataclass
class RoiReport:
    """운영자가 지정한 영역 하나에 대한 보고. 상용 관제 화면의 기본 단위."""
    name: str = "ROI 1"
    polygon: List[Tuple[int, int]] = field(default_factory=list)
    count: int = 0                     # 영역 안 인원
    area_m2: Optional[float] = None    # 영역의 실제 바닥 면적
    density: float = 0.0               # 인원 / 면적
    peak_density: float = 0.0          # 영역 안 국부 최대 (KDE)
    peak_point: Optional[Tuple[int, int]] = None
    level: int = 0
    area_estimated: bool = True        # 캘리브레이션 없이 추정했는가

    @property
    def tag(self) -> str:
        return level_tag(self.level)

    @property
    def color(self) -> str:
        return level_color(self.level)


def _scale_model(per_person: Sequence[PersonDensity]) -> Optional[Tuple[float, float]]:
    """영상 행(y) → 축척(m/px) 1차 모델. 지면이 평평하면 선형에 가깝다."""
    pts = [(p.point[1], p.scale_m_per_px) for p in per_person]
    if len(pts) < 2:
        return (0.0, pts[0][1]) if pts else None
    ys = np.array([y for y, _ in pts], np.float64)
    ss = np.array([s for _, s in pts], np.float64)
    if float(ys.max() - ys.min()) < 1e-6:
        return (0.0, float(ss.mean()))
    a, b = np.polyfit(ys, ss, 1)
    return float(a), float(b)


def roi_mask(frame_shape: Tuple[int, ...],
             polygon: Optional[Sequence[Tuple[int, int]]]) -> np.ndarray:
    h, w = frame_shape[:2]
    if not polygon or len(polygon) < 3:
        return np.ones((h, w), np.uint8)
    import cv2
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [np.array(polygon, np.int32)], 1)
    return m


def estimate_area_m2(frame_shape: Tuple[int, ...],
                     polygon: Optional[Sequence[Tuple[int, int]]],
                     per_person: Sequence[PersonDensity],
                     step: int = 8) -> Optional[float]:
    """영역의 바닥 면적(m^2). 검출된 사람들의 겉보기 크기로 축척을 역산한다.

    캘리브레이션이 없어도 '명/m^2' 를 낼 수 있게 하는 부분이다.
    사람이 하나도 없으면 축척을 모르므로 None 을 돌려준다.
    """
    model = _scale_model(per_person)
    if model is None:
        return None
    a, b = model
    h, w = frame_shape[:2]
    mask = roi_mask(frame_shape, polygon)
    ys = np.arange(0, h, step)
    sub = mask[::step, ::step]
    if not sub.any():
        return None
    scales = np.clip(a * ys + b, 1e-5, None)[:, None]        # (행, 1) m/px
    cell = (scales ** 2) * (step * step)                      # 한 샘플이 덮는 m^2
    return float((sub * cell[: sub.shape[0]]).sum())


def analyze_roi(
    field_result: DensityFieldResult,
    frame_shape: Tuple[int, ...],
    polygon: Optional[Sequence[Tuple[int, int]]] = None,
    name: str = "ROI 1",
    area_m2: Optional[float] = None,
    tiers: Sequence[float] = DEFAULT_TIERS,
) -> RoiReport:
    """영역 하나를 상용 관제 화면과 같은 방식으로 요약한다.

    density  = 인원 / 면적   (상용 시스템이 표시하는 '군중밀도')
    peak     = 영역 안 KDE 최대 (국부 밀집. 드론이 갈 지점을 정한다)
    level    = peak 기준 0-안전 ~ 4-심각
    """
    h, w = frame_shape[:2]
    poly = list(polygon) if polygon and len(polygon) >= 3 else [
        (0, 0), (w - 1, 0), (w - 1, h - 1), (0, h - 1)]
    mask = roi_mask(frame_shape, poly)

    inside = [p for p in field_result.per_person
              if 0 <= p.point[1] < h and 0 <= p.point[0] < w
              and mask[p.point[1], p.point[0]]]

    rep = RoiReport(name=name, polygon=[(int(x), int(y)) for x, y in poly],
                    count=len(inside))
    if area_m2 is not None:
        rep.area_m2, rep.area_estimated = float(area_m2), False
    else:
        rep.area_m2 = estimate_area_m2(frame_shape, poly,
                                       field_result.per_person)
        rep.area_estimated = True

    if rep.area_m2 and rep.area_m2 > 0:
        rep.density = rep.count / rep.area_m2
    if inside:
        best = max(inside, key=lambda p: p.density)
        rep.peak_density = best.density
        rep.peak_point = best.point
    # 등급은 국부 최대로 정한다. 압사는 평균이 아니라 한 지점에서 일어난다.
    # 넓은 영역의 평균(인원/면적)은 낮아도 한쪽 구석이 위험할 수 있다.
    rep.level = level_of(rep.peak_density if inside else rep.density, tiers)
    return rep
