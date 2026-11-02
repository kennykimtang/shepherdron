"""KDE 밀집도 장 테스트.

핵심 성질을 검증한다.
  - 균일한 군중에 대해 KDE 값이 실제 밀집도로 수렴한다 (불편추정)
  - 격자와 달리 셀 경계에 걸친 군집도 하나로 잡는다
  - 겉보기 크기로 거리를 환산하므로 원근이 보정된다
"""
import math

import pytest

from vision.density_analyzer import DensityAnalyzer
from vision.density_field import (
    DEFAULT_TIERS,
    DensityFieldEstimator,
    analyze_roi,
    estimate_area_m2,
    level_of,
    level_tag,
)
from vision.detector import DetectionResult

SHAPE = (720, 1280, 3)
PERSON_H_M = 1.7


def lattice(n_side, spacing_m, cx, cy, box_h_px=200):
    """현실 간격 spacing_m 로 정렬된 n_side x n_side 군중."""
    px_per_m = box_h_px / PERSON_H_M
    step = spacing_m * px_per_m
    boxes, feet = [], []
    off = (n_side - 1) / 2
    for i in range(n_side):
        for j in range(n_side):
            fx = cx + (j - off) * step
            fy = cy + (i - off) * step
            boxes.append((int(fx - 30), int(fy - box_h_px), int(fx + 30), int(fy)))
            feet.append((int(fx), int(fy)))
    return DetectionResult(boxes=boxes, confidences=[0.9] * len(feet),
                           foot_points=feet, track_ids=[None] * len(feet),
                           count=len(feet))


@pytest.mark.parametrize("spacing_m", [0.7, 1.0, 1.5])
def test_uniform_crowd_recovers_true_density(spacing_m):
    """넓고 균일한 군중의 중심에서 KDE 는 1/간격^2 로 수렴해야 한다."""
    det = lattice(9, spacing_m, 640, 400)
    res = DensityFieldEstimator(sigma_m=0.75).estimate(SHAPE, det)
    true_density = 1.0 / (spacing_m ** 2)
    assert res.peak_density == pytest.approx(true_density, rel=0.25)


def test_isolated_person_is_not_dense():
    det = lattice(1, 1.0, 640, 400)
    res = DensityFieldEstimator(sigma_m=0.75).estimate(SHAPE, det)
    # 혼자 서 있는 사람은 위험이 아니다
    assert res.peak_density < 1.0
    assert res.level == "SAFE"


def test_denser_crowd_scores_higher():
    loose = DensityFieldEstimator().estimate(SHAPE, lattice(7, 1.5, 640, 400))
    tight = DensityFieldEstimator().estimate(SHAPE, lattice(7, 0.5, 640, 400))
    assert tight.peak_density > loose.peak_density * 3


def test_perspective_is_corrected():
    """같은 현실 간격이면 화면 어디에 있든 밀집도가 비슷해야 한다."""
    near = DensityFieldEstimator().estimate(
        SHAPE, lattice(5, 0.8, 640, 650, box_h_px=300))
    far = DensityFieldEstimator().estimate(
        SHAPE, lattice(5, 0.8, 640, 330, box_h_px=80))
    assert near.peak_density == pytest.approx(far.peak_density, rel=0.2)


def test_cluster_on_grid_boundary_is_not_split():
    """3x3 격자의 경계 한가운데 선 군집 — 격자는 놓치고 KDE 는 잡는다."""
    h, w = SHAPE[:2]
    det = lattice(4, 0.45, w / 3, h / 3, box_h_px=200)   # 셀 모서리 교차점

    grid = DensityAnalyzer(grid_rows=3, grid_cols=3).analyze(SHAPE, det)
    per_cell = max(c.count for c in grid.grid_cells)
    assert per_cell < det.count          # 격자는 군집을 쪼갠다

    field = DensityFieldEstimator().estimate(SHAPE, det)
    assert field.peak_density > 2.0      # KDE 는 통째로 본다


def test_peak_point_sits_on_the_crowd():
    det = lattice(5, 0.5, 950, 520)
    res = DensityFieldEstimator().estimate(SHAPE, det)
    assert res.peak_point is not None
    px, py = res.peak_point
    assert 800 < px < 1100 and 380 < py < 660


def test_empty_frame_is_safe():
    det = DetectionResult(count=0)
    res = DensityFieldEstimator().estimate(SHAPE, det)
    assert res.peak_density == 0.0
    assert res.peak_point is None
    assert res.level == "SAFE"
    assert not res.is_overcrowded


def test_levels_follow_thresholds():
    est = DensityFieldEstimator(warn=2.0, danger=4.0)
    assert est.estimate(SHAPE, lattice(7, 2.0, 640, 400)).level == "SAFE"
    assert est.estimate(SHAPE, lattice(9, 0.45, 640, 400)).level == "DANGER"


def test_sigma_must_be_positive():
    with pytest.raises(ValueError):
        DensityFieldEstimator(sigma_m=0.0)


def test_heat_raster_matches_requested_width():
    det = lattice(3, 1.0, 640, 400)
    res = DensityFieldEstimator(field_width=128).estimate(SHAPE, det)
    assert res.heat is not None
    fh, fw = res.heat.shape
    assert fw == 128
    assert fh == pytest.approx(128 * SHAPE[0] / SHAPE[1], abs=1)


def test_heat_can_be_skipped():
    res = DensityFieldEstimator().estimate(SHAPE, lattice(3, 1.0, 640, 400),
                                           make_heat=False)
    assert res.heat is None
    assert res.peak_density > 0


# ── ROI · 면적 · 등급 ──────────────────────────────────────
def test_area_is_estimated_without_calibration():
    """겉보기 크기만으로 영역 면적을 복원한다. 1.0 m 간격 9x9 = 약 64 m²."""
    det = lattice(9, 1.0, 640, 400)
    res = DensityFieldEstimator().estimate(SHAPE, det)
    poly = [(300, 200), (980, 200), (980, 600), (300, 600)]
    area = estimate_area_m2(SHAPE, poly, res.per_person)
    assert area is not None and area > 0
    # 같은 영역을 반으로 줄이면 면적도 대략 반이 된다
    half = estimate_area_m2(SHAPE, [(300, 200), (640, 200), (640, 600), (300, 600)],
                            res.per_person)
    assert half == pytest.approx(area / 2, rel=0.2)


def test_area_is_unknown_without_any_person():
    det = DetectionResult(count=0)
    res = DensityFieldEstimator().estimate(SHAPE, det)
    assert estimate_area_m2(SHAPE, None, res.per_person) is None


def test_roi_counts_only_people_inside():
    det = lattice(5, 0.8, 300, 400)                 # 좌측에 군집
    res = DensityFieldEstimator().estimate(SHAPE, det)
    left = analyze_roi(res, SHAPE, [(0, 0), (640, 0), (640, 719), (0, 719)])
    right = analyze_roi(res, SHAPE, [(640, 0), (1279, 0), (1279, 719), (640, 719)])
    assert left.count == det.count
    assert right.count == 0


def test_roi_density_is_persons_over_area():
    det = lattice(5, 1.0, 640, 400)
    res = DensityFieldEstimator().estimate(SHAPE, det)
    roi = analyze_roi(res, SHAPE, None, area_m2=100.0)
    assert roi.area_m2 == 100.0
    assert not roi.area_estimated
    assert roi.count == det.count            # 전원이 화면 안
    assert roi.density == pytest.approx(roi.count / 100.0)


def test_roi_ignores_detections_outside_the_frame():
    det = lattice(9, 1.2, 640, 400)          # 일부가 화면 밖으로 나간다
    res = DensityFieldEstimator().estimate(SHAPE, det)
    roi = analyze_roi(res, SHAPE, None, area_m2=100.0)
    assert roi.count < det.count


def test_roi_level_follows_local_peak_not_average():
    """넓은 영역 한구석의 군집도 등급에 반영돼야 한다. 평균은 희석된다."""
    det = lattice(6, 0.45, 1000, 560)               # 구석에 빽빽한 군집
    res = DensityFieldEstimator().estimate(SHAPE, det)
    roi = analyze_roi(res, SHAPE, None, area_m2=400.0)
    assert roi.density < 1.0                        # 평균은 한가해 보인다
    assert roi.peak_density >= 3.0
    assert roi.level >= 3                           # 그래도 경계 이상


def test_roi_defaults_to_the_whole_frame():
    det = lattice(4, 1.0, 640, 400)
    res = DensityFieldEstimator().estimate(SHAPE, det)
    roi = analyze_roi(res, SHAPE, None)
    assert roi.count == det.count
    assert len(roi.polygon) == 4


def test_empty_roi_is_level_zero():
    res = DensityFieldEstimator().estimate(SHAPE, DetectionResult(count=0))
    roi = analyze_roi(res, SHAPE, None)
    assert roi.count == 0 and roi.level == 0 and roi.peak_density == 0.0


@pytest.mark.parametrize("density,expected", [
    (0.4, 0), (1.2, 1), (2.5, 2), (3.4, 3), (6.0, 4)])
def test_level_tiers(density, expected):
    assert level_of(density, DEFAULT_TIERS) == expected


def test_level_tag_format():
    assert level_tag(0) == "0-안전"
    assert level_tag(4) == "4-심각"
