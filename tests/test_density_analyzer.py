"""밀집도 분석 테스트 — 원근 보정 유무에 따른 판정 차이를 검증한다."""
import pytest

from vision.density_analyzer import DensityAnalyzer
from vision.detector import DetectionResult
from vision.geometry import GroundPlane

SHAPE = (480, 640, 3)


def detection(foot_points, track_ids=None):
    n = len(foot_points)
    return DetectionResult(
        boxes=[(x - 10, y - 40, x + 10, y) for x, y in foot_points],
        confidences=[0.9] * n,
        foot_points=list(foot_points),
        track_ids=list(track_ids) if track_ids else [None] * n,
        count=n,
    )


def uniform_plane(m_per_px=0.02):
    """화면 전체가 균일 축척인 가상 평면. 1 px = m_per_px m."""
    w, h = 640, 480
    img = [(0, 0), (w, 0), (w, h), (0, h)]
    world = [(0.0, h * m_per_px), (w * m_per_px, h * m_per_px),
             (w * m_per_px, 0.0), (0.0, 0.0)]
    return GroundPlane.from_points(img, world)


class TestUncalibrated:
    def test_counts_map_to_cells(self):
        a = DensityAnalyzer(grid_rows=3, grid_cols=3, danger_threshold=4)
        r = a.analyze(SHAPE, detection([(320, 240)] * 3))
        assert r.total_persons == 3
        assert r.calibrated is False
        assert r.metric == "persons/cell"
        centre = next(c for c in r.grid_cells if (c.row, c.col) == (1, 1))
        assert centre.count == 3

    def test_cell_threshold_triggers(self):
        a = DensityAnalyzer(danger_threshold=4, total_threshold=99)
        r = a.analyze(SHAPE, detection([(320, 240)] * 4))
        assert r.is_overcrowded is True
        assert any("count 4" in s for s in r.alarm_reasons)

    def test_total_threshold_triggers_even_when_spread_out(self):
        a = DensityAnalyzer(grid_rows=3, grid_cols=3,
                            danger_threshold=99, total_threshold=6)
        pts = [(80, 80), (320, 80), (560, 80), (80, 400), (320, 400), (560, 400)]
        r = a.analyze(SHAPE, detection(pts))
        assert r.is_overcrowded is True
        assert any("Total count" in s for s in r.alarm_reasons)

    def test_empty_frame_has_no_target(self):
        a = DensityAnalyzer()
        r = a.analyze(SHAPE, DetectionResult())
        assert r.max_dense_cell is None
        assert r.target_point is None
        assert r.is_overcrowded is False

    def test_out_of_bounds_footpoints_are_clipped(self):
        a = DensityAnalyzer()
        r = a.analyze(SHAPE, detection([(-50, -50), (9999, 9999)]))
        assert sum(c.count for c in r.grid_cells) == 2

    def test_track_ids_are_grouped_per_cell(self):
        a = DensityAnalyzer()
        r = a.analyze(SHAPE, detection([(320, 240), (330, 250)], track_ids=[7, 9]))
        centre = next(c for c in r.grid_cells if (c.row, c.col) == (1, 1))
        assert sorted(centre.track_ids) == [7, 9]


class TestCalibrated:
    def test_density_is_count_over_ground_area(self):
        # 1 px = 0.02 m 이면 셀(213x160 px) 면적은 약 4.26 x 3.2 = 13.6 m^2
        a = DensityAnalyzer(ground_plane=uniform_plane(0.02))
        r = a.analyze(SHAPE, detection([(320, 240)] * 10))
        assert r.calibrated is True
        assert r.metric == "persons/m^2"
        centre = next(c for c in r.grid_cells if (c.row, c.col) == (1, 1))
        assert centre.area_m2 == pytest.approx(13.65, rel=0.02)
        assert centre.density == pytest.approx(10 / 13.65, rel=0.02)

    def test_same_count_different_scale_gives_different_verdict(self):
        """원근 보정의 핵심: 같은 인원수라도 지면 면적이 다르면 판정이 달라야 한다."""
        people = detection([(320, 240)] * 8)

        # 중앙 셀은 213 x 160 px.
        #   0.05 m/px -> 10.65 x 8.00 m = 85.2 m^2 -> 0.09 p/m^2  (여유)
        #   0.005 m/px ->  1.07 x 0.80 m = 0.85 m^2 -> 9.4 p/m^2  (압착 위험)
        wide = DensityAnalyzer(ground_plane=uniform_plane(0.05),
                               density_danger=4.0, total_threshold=99)
        tight = DensityAnalyzer(ground_plane=uniform_plane(0.005),
                                density_danger=4.0, total_threshold=99)

        assert wide.analyze(SHAPE, people).is_overcrowded is False
        assert tight.analyze(SHAPE, people).is_overcrowded is True

    def test_uncalibrated_cannot_distinguish_those_two(self):
        """대조군: 보정이 없으면 위 두 상황이 완전히 동일하게 보인다."""
        people = detection([(320, 240)] * 8)
        a = DensityAnalyzer(danger_threshold=4, total_threshold=99)
        assert a.analyze(SHAPE, people).is_overcrowded is True   # 지면 넓이와 무관

    def test_peak_density_reported(self):
        a = DensityAnalyzer(ground_plane=uniform_plane(0.02))
        r = a.analyze(SHAPE, detection([(320, 240)] * 10))
        assert r.peak_density == pytest.approx(10 / 13.65, rel=0.02)

    def test_set_ground_plane_switches_mode_and_clears_cache(self):
        a = DensityAnalyzer()
        assert a.analyze(SHAPE, detection([(320, 240)])).calibrated is False
        a.set_ground_plane(uniform_plane(0.02))
        assert a.analyze(SHAPE, detection([(320, 240)])).calibrated is True


class TestTargeting:
    def test_target_is_centroid_of_feet_not_cell_centre(self):
        a = DensityAnalyzer(grid_rows=3, grid_cols=3)
        # 중앙 셀은 x 213..426, y 160..320 이고 중심은 (320, 240).
        # 사람들을 셀 왼쪽 위에 몰아두면 타겟도 그쪽으로 당겨져야 한다.
        r = a.analyze(SHAPE, detection([(230, 180), (240, 190), (250, 170)]))
        assert r.target_point is not None
        assert r.target_point[0] < 300 and r.target_point[1] < 230

    def test_busiest_cell_wins(self):
        a = DensityAnalyzer(grid_rows=3, grid_cols=3)
        pts = [(80, 80)] + [(560, 400)] * 5
        r = a.analyze(SHAPE, detection(pts))
        assert (r.max_dense_cell.row, r.max_dense_cell.col) == (2, 2)


class TestDetectionRange:
    """멀어서 못 본 구역을 '안전'이라고 보고하면 안 된다.

    비스듬한 카메라에서 화면 위쪽 셀은 수십 미터 밖이라 사람이 몇 픽셀밖에
    안 된다. 면적은 정확히 계산되므로 '검출 0명'이 '밀집도 0 = 안전'으로
    보고되는데, 이건 거짓 음성이다.
    """

    def _analyzer(self, px=320, **kw):
        from vision.geometry import CameraModel
        cam = CameraModel(width=px, height=int(px * 0.75), pitch_deg=45.0, **kw)
        return DensityAnalyzer(grid_rows=3, grid_cols=3, camera=cam), cam

    def test_far_empty_cell_is_unknown_not_empty(self):
        a, cam = self._analyzer()
        r = a.analyze((240, 320, 3), DetectionResult(), altitude_m=10.0)
        top = next(c for c in r.grid_cells if (c.row, c.col) == (0, 1))
        assert top.in_detection_range is False
        assert top.status == "UNKNOWN", "보이지 않는 구역을 EMPTY 로 보고하면 안 된다"

    def test_near_empty_cell_is_genuinely_empty(self):
        a, _ = self._analyzer()
        r = a.analyze((240, 320, 3), DetectionResult(), altitude_m=10.0)
        bottom = next(c for c in r.grid_cells if (c.row, c.col) == (2, 1))
        assert bottom.in_detection_range is True
        assert bottom.status == "EMPTY"

    def test_detections_in_a_far_cell_are_still_trusted(self):
        """멀어도 실제로 보였다면 그 관측은 유효하다. 보류할 이유가 없다."""
        a, _ = self._analyzer()
        r = a.analyze((240, 320, 3), detection([(160, 20)] * 6), altitude_m=10.0)
        top = next(c for c in r.grid_cells if (c.row, c.col) == (0, 1))
        assert top.count == 6
        assert top.status != "UNKNOWN"

    def test_higher_resolution_extends_the_trusted_range(self):
        a, _ = self._analyzer(px=640)
        r = a.analyze((480, 640, 3), DetectionResult(), altitude_m=10.0)
        top = next(c for c in r.grid_cells if (c.row, c.col) == (0, 1))
        assert top.in_detection_range is True, "640px 면 상단 행도 검출 범위 안"

    def test_without_altitude_nothing_is_flagged(self):
        """고도를 모르면 거리를 모른다. 추측해서 구역을 버리지 않는다."""
        a, _ = self._analyzer()
        r = a.analyze((240, 320, 3), DetectionResult(), altitude_m=None)
        assert all(c.in_detection_range for c in r.grid_cells)

    def test_without_a_camera_nothing_is_flagged(self):
        a = DensityAnalyzer(grid_rows=3, grid_cols=3)
        r = a.analyze((240, 320, 3), DetectionResult(), altitude_m=10.0)
        assert all(c.in_detection_range for c in r.grid_cells)

    def test_cell_range_increases_toward_the_top_of_frame(self):
        a, _ = self._analyzer()
        r = a.analyze((240, 320, 3), DetectionResult(), altitude_m=10.0)
        col = sorted((c for c in r.grid_cells if c.col == 1), key=lambda c: c.row)
        assert col[0].slant_range_m > col[1].slant_range_m > col[2].slant_range_m
