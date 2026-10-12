"""파이프라인 통합 테스트 — 가짜 검출기를 넣어 모델 없이 전체 흐름을 검증한다."""
import numpy as np
import pytest

from vision.density_analyzer import DensityAnalyzer
from vision.detector import DetectionResult
from vision.geometry import CameraModel
from vision.pipeline import CrowdPipeline
from vision.stability import AlertDebouncer, RollingCounter, TargetSmoother

FRAME = np.zeros((480, 640, 3), dtype=np.uint8)


class FakeDetector:
    """스크립트대로 검출 결과를 돌려주는 대역. 실제 가중치가 필요 없다."""

    def __init__(self, script):
        self.script = list(script)
        self.i = 0
        self.resets = 0

    def _result(self):
        pts = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        n = len(pts)
        return DetectionResult(
            boxes=[(x - 8, y - 32, x + 8, y) for x, y in pts],
            confidences=[0.9] * n,
            foot_points=list(pts),
            track_ids=list(range(1, n + 1)),
            count=n,
        )

    def track(self, frame):
        return self._result()

    def detect(self, frame):
        return self._result()

    def reset_tracker(self):
        self.resets += 1


def build(script, **kw):
    analyzer = DensityAnalyzer(grid_rows=3, grid_cols=3,
                              danger_threshold=kw.pop("danger", 4),
                              total_threshold=kw.pop("total", 99))
    return CrowdPipeline(
        detector=FakeDetector(script),
        analyzer=analyzer,
        camera=CameraModel(width=640, height=480, pitch_deg=90.0),
        debouncer=AlertDebouncer(window=10, on_ratio=0.6, off_ratio=0.2, min_on_s=0.0),
        counter=RollingCounter(window=5),
        smoother=TargetSmoother(alpha=1.0),
        **kw,
    )


CROWD = [(320, 240)] * 5
EMPTY = []


class TestAlertBehaviour:
    def test_single_crowded_frame_does_not_alert(self):
        p = build([EMPTY] * 9 + [CROWD])
        last = None
        for i in range(10):
            last = p.process(FRAME, now=i * 0.1)
        assert last.raw_danger is True, "그 프레임 자체는 위험이 맞다"
        assert last.alert_active is False, "그러나 경보로 올라가면 안 된다"

    def test_sustained_crowd_alerts(self):
        p = build([CROWD])
        for i in range(10):
            r = p.process(FRAME, now=i * 0.1)
        assert r.alert_active is True

    def test_rising_edge_fires_exactly_once(self):
        p = build([CROWD])
        edges = [p.process(FRAME, now=i * 0.1).alert_rising_edge for i in range(20)]
        assert sum(edges) == 1

    def test_count_is_median_smoothed(self):
        p = build([CROWD, CROWD, [(320, 240)] * 40, CROWD, CROWD])
        for i in range(5):
            r = p.process(FRAME, now=i * 0.1)
        assert r.detection.count == 5
        assert r.smoothed_count == 5, "한 프레임 40명 폭주가 평활값을 흔들면 안 된다"


class TestTargeting:
    def test_no_target_while_calm(self):
        p = build([EMPTY])
        r = p.process(FRAME, now=0.0)
        assert r.target is None

    def test_target_present_once_alerting(self):
        p = build([CROWD])
        for i in range(10):
            r = p.process(FRAME, now=i * 0.1)
        assert r.target is not None
        assert r.target.pixel == pytest.approx((320, 240), abs=2)

    def test_angular_offset_is_zero_at_image_centre(self):
        p = build([CROWD])
        for i in range(10):
            r = p.process(FRAME, now=i * 0.1)
        assert r.target.yaw_offset_deg == pytest.approx(0.0, abs=0.5)

    def test_no_ground_fix_without_altitude(self):
        p = build([CROWD])
        for i in range(10):
            r = p.process(FRAME, now=i * 0.1)
        assert r.target.has_ground_fix is False

    def test_ground_fix_once_altitude_known(self):
        p = build([CROWD], altitude_m=10.0)
        for i in range(10):
            r = p.process(FRAME, now=i * 0.1)
        assert r.target.has_ground_fix is True
        assert r.target.forward_m == pytest.approx(0.0, abs=0.2)
        assert r.target.right_m == pytest.approx(0.0, abs=0.2)

    def test_offset_sign_matches_crowd_position(self):
        """군중이 화면 오른쪽에 있으면 우현(+) 오프셋이 나와야 한다."""
        p = build([[(600, 240)] * 5], altitude_m=10.0)
        for i in range(10):
            r = p.process(FRAME, now=i * 0.1)
        assert r.target.right_m > 0

    def test_altitude_can_be_updated_in_flight(self):
        p = build([CROWD])
        for i in range(10):
            p.process(FRAME, now=i * 0.1)
        p.set_altitude(25.0)
        r = p.process(FRAME, now=2.0)
        assert r.target.altitude_m == 25.0


class TestCameraGeometrySync:
    def test_camera_adapts_to_actual_frame_size(self):
        """설정 해상도와 실제 프레임 크기가 다르면 방위각이 통째로 틀어진다."""
        p = build([CROWD])
        p.camera = CameraModel(width=1920, height=1080, pitch_deg=90.0)
        p.process(FRAME, now=0.0)          # FRAME 은 640x480
        assert (p.camera.width, p.camera.height) == (640, 480)

    def test_centre_target_stays_on_axis_after_resize(self):
        p = build([CROWD])
        p.camera = CameraModel(width=1920, height=1080, pitch_deg=90.0)
        for i in range(10):
            r = p.process(FRAME, now=i * 0.1)
        assert r.target.yaw_offset_deg == pytest.approx(0.0, abs=0.5)


class TestLifecycle:
    def test_frame_index_increments(self):
        p = build([EMPTY])
        assert [p.process(FRAME, now=i).frame_index for i in range(3)] == [0, 1, 2]

    def test_fps_computed_after_first_frame(self):
        p = build([EMPTY])
        assert p.process(FRAME, now=0.0).fps == 0.0
        assert p.process(FRAME, now=0.5).fps == pytest.approx(2.0)

    def test_reset_clears_tracker_and_filters(self):
        p = build([CROWD])
        for i in range(10):
            p.process(FRAME, now=i * 0.1)
        assert p.debouncer.active is True
        p.reset()
        assert p.debouncer.active is False
        assert p.detector.resets == 1

    def test_detect_only_mode_skips_tracking(self):
        p = build([CROWD])
        p.use_tracking = False
        r = p.process(FRAME, now=0.0)
        assert r.detection.count == 5

    def test_unique_track_ids_counted(self):
        p = build([CROWD])
        assert p.process(FRAME, now=0.0).unique_track_ids == 5
