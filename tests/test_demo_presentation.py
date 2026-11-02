"""발표 시연기 테스트 — 자동 폴백과 관제 화면 합성."""
import numpy as np
import pytest

from vision.density_analyzer import DensityAnalyzer
from vision.density_field import DensityFieldEstimator
from vision.detector import DetectionResult
from vision.failover import FailoverSource
from vision.pipeline import PipelineResult, TargetFix
from vision.presentation import (
    EventLog,
    Layout,
    LevelFilter,
    PresentationRenderer,
    density_lut,
    derive_status,
    fit_into,
)
from vision.tactical import build_picture

SHAPE = (480, 640, 3)


# ══════════════ 폴백 소스 ══════════════
class FakeSource:
    """읽을 때마다 ok 를 돌려주는 가짜 소스. ok 를 바꿔 끊김을 흉내낸다."""

    def __init__(self, name, ok=True):
        self.name = name
        self.ok = ok
        self.reads = 0
        self.stopped = False

    def read(self):
        self.reads += 1
        if not self.ok:
            return False, None
        return True, np.full((8, 8, 3), 7, np.uint8)

    def stop(self):
        self.stopped = True


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def make(primary_ok=True, fallback="clip.mp4", grace=4.0, retry=10.0):
    made = {}
    clock = Clock()

    def opener(source, loop):
        src = FakeSource(source, ok=primary_ok if source == "0" else True)
        made.setdefault(source, []).append(src)
        return src

    fo = FailoverSource("0", fallback, grace_s=grace, retry_s=retry,
                        open_fn=opener, clock=clock).start()
    return fo, made, clock


def test_live_source_is_used_while_healthy():
    fo, made, clock = make(primary_ok=True)
    for _ in range(5):
        ok, frame = fo.read()
        assert ok and frame is not None
    assert not fo.on_fallback
    assert fo.active_label == "0"


def test_switches_to_clip_after_grace_period():
    fo, made, clock = make(primary_ok=False, grace=4.0)
    ok, _ = fo.read()
    assert not ok and not fo.on_fallback     # 유예 중에는 아직 버틴다

    clock.advance(4.1)
    fo.read()
    assert fo.on_fallback

    ok, frame = fo.read()
    assert ok and frame is not None          # 검은 화면이 아니라 녹화본
    assert fo.active_label == "clip.mp4"


def test_no_fallback_configured_never_switches():
    fo, _, clock = make(primary_ok=False, fallback=None)
    clock.advance(60.0)
    for _ in range(3):
        ok, _ = fo.read()
        assert not ok
    assert not fo.on_fallback


def test_recovers_to_live_when_source_returns():
    fo, made, clock = make(primary_ok=False, grace=1.0, retry=5.0)
    clock.advance(1.5)
    fo.read()
    assert fo.on_fallback

    # 재연결되면 정상 소스를 돌려주도록 바꾼다
    def healthy(source, loop):
        return FakeSource(source, ok=True)
    fo._open = healthy

    clock.advance(5.1)
    ok, frame = fo.read()
    assert ok and not fo.on_fallback


def test_manual_toggle_pins_the_choice():
    fo, _, clock = make(primary_ok=True)
    fo.toggle()
    assert fo.on_fallback
    clock.advance(999.0)
    fo.read()
    assert fo.on_fallback                    # 자동 복구가 끼어들지 않는다
    fo.toggle()
    assert not fo.on_fallback


def test_stop_releases_both_sources():
    fo, made, clock = make(primary_ok=False, grace=0.5)
    clock.advance(1.0)
    fo.read()
    fo.read()
    fo.stop()
    assert all(s.stopped for lst in made.values() for s in lst)


def test_read_survives_a_throwing_source():
    class Boom:
        def read(self):
            raise RuntimeError("usb unplugged")

        def stop(self):
            pass

    fo = FailoverSource("0", None, open_fn=lambda s, l: Boom())
    fo.start()
    assert fo.read() == (False, None)


# ══════════════ 렌더러 ══════════════
def detection(points, tracked=True):
    n = len(points)
    return DetectionResult(
        boxes=[(x - 20, y - 120, x + 20, y) for x, y in points],
        confidences=[0.9] * n, foot_points=list(points),
        track_ids=list(range(1, n + 1)) if tracked else [None] * n, count=n)


def result(points, alert=False, target=False, frame_index=0):
    det = detection(points)
    an = DensityAnalyzer().analyze(SHAPE, det)
    fr = DensityFieldEstimator().estimate(SHAPE, det)
    tgt = (TargetFix(pixel=fr.peak_point or (0, 0), yaw_offset_deg=3.0,
                     pitch_offset_deg=-10.0, forward_m=2.5, right_m=-1.0,
                     altitude_m=3.0) if target else None)
    return PipelineResult(frame_index=frame_index, detection=det, analysis=an,
                          alert_active=alert, raw_danger=alert,
                          smoothed_count=det.count, target=tgt, fps=12.0,
                          field=fr)


@pytest.fixture
def frame():
    return np.full(SHAPE, 40, np.uint8)


def test_render_produces_the_requested_canvas(frame):
    r = PresentationRenderer(layout=Layout(w=1280, h=720))
    out = r.render(frame, result([(100, 300), (140, 310)]))
    assert out.shape == (720, 1280, 3)
    assert out.dtype == np.uint8
    assert out.any()


def test_render_handles_an_empty_scene(frame):
    r = PresentationRenderer()
    out = r.render(frame, result([]))
    assert out.shape == (1080, 1920, 3)


def test_render_with_tactical_map_and_mission(frame):
    from flight.virtual_drone import DemoMission
    r = PresentationRenderer()
    res = result([(200, 400), (210, 405), (220, 410)], alert=True, target=True)
    pic = build_picture(res.detection, 640, 480)
    m = DemoMission()
    m.update(True, True, 3, pic.hotspot, now=0.0)
    out = r.render(frame, res, tactical=pic, mission=m)
    assert out.shape == (1080, 1920, 3)
    assert out.any()


def test_render_tolerates_a_portrait_source():
    r = PresentationRenderer()
    tall = np.full((640, 360, 3), 30, np.uint8)
    det = detection([(180, 500)])
    an = DensityAnalyzer().analyze(tall.shape, det)
    fr = DensityFieldEstimator().estimate(tall.shape, det)
    res = PipelineResult(frame_index=0, detection=det, analysis=an,
                         alert_active=False, raw_danger=False,
                         smoothed_count=1, fps=9.0, field=fr)
    assert r.render(tall, res).shape == (1080, 1920, 3)


def test_history_is_bounded(frame):
    r = PresentationRenderer(history=10)
    for i in range(40):
        r.render(frame, result([(100, 300)], frame_index=i))
    assert len(r.counts) == 10 and len(r.peaks) == 10 and len(r.levels) == 10


def test_status_tracks_the_alert(frame):
    assert derive_status(result([(100, 300)])) == "SAFE"
    assert derive_status(result([(100, 300)], alert=True)) == "DANGER"


def test_fit_into_preserves_aspect_ratio():
    img = np.zeros((100, 200, 3), np.uint8)
    out, ox, oy, s = fit_into(img, 400, 400)
    assert out.shape[:2] == (200, 400)
    assert oy == 100 and ox == 0
    assert s == pytest.approx(2.0)


def test_lut_runs_from_calm_to_alarm():
    lut = density_lut()
    assert lut.shape == (256, 3)
    assert int(lut[200][2]) > int(lut[10][2])      # BGR 이므로 index 2 가 R


def test_layout_panels_do_not_overlap():
    L = Layout()
    boxes = [L.video, L.readout, L.trend, L.tac, L.msn, L.log]
    for i, a in enumerate(boxes):
        assert a[2] > a[0] and a[3] > a[1]
        assert a[2] <= L.w and a[3] <= L.h
        for b in boxes[i + 1:]:
            overlap = (min(a[2], b[2]) - max(a[0], b[0]) > 0
                       and min(a[3], b[3]) - max(a[1], b[1]) > 0)
            assert not overlap


# ══════════════ 등급 히스테리시스 ══════════════
def test_level_filter_needs_sustained_change():
    f = LevelFilter(hold=3)
    assert f.update(3) == 0        # 한 프레임으로는 안 바뀐다
    assert f.update(3) == 0
    assert f.update(3) == 3        # 세 프레임 연속이면 받아들인다


def test_level_filter_ignores_a_single_spike():
    f = LevelFilter(hold=4)
    for _ in range(6):
        f.update(0)
    assert f.update(4) == 0
    assert f.update(0) == 0
    assert f.value == 0


def test_level_filter_resets_candidate_on_flapping():
    f = LevelFilter(hold=3)
    f.update(2); f.update(3); f.update(2)
    assert f.value == 0            # 후보가 계속 바뀌면 아무것도 확정되지 않는다


# ══════════════ 이벤트 로그 ══════════════
def test_log_records_level_changes():
    log = EventLog()
    log.observe(1, 1.2, "IDLE", "", False)
    assert log.items[-1].kind == "level"
    assert log.items[-1].level == 1


def test_log_records_mission_transitions():
    log = EventLog()
    log.observe(0, 0.0, "IDLE", "", False)
    n = len(log.items)
    log.observe(0, 0.0, "NAVIGATING", "과밀집 20명", False)
    assert len(log.items) == n + 1
    assert log.items[-1].kind == "mission"
    assert "과밀집" in log.items[-1].text


def test_log_does_not_repeat_a_steady_state():
    log = EventLog()
    log.observe(2, 2.5, "HOVERING", "도달", False)
    n = len(log.items)
    for _ in range(10):
        log.observe(2, 2.5, "HOVERING", "도달", False)
    assert len(log.items) == n


def test_log_notes_the_fallback_switch():
    log = EventLog()
    log.observe(0, 0.0, "IDLE", "", False)
    log.observe(0, 0.0, "IDLE", "", True)
    assert log.items[-1].kind == "warn"


def test_log_is_bounded():
    log = EventLog(maxlen=5)
    for i in range(20):
        log.add(f"event {i}")
    assert len(log.items) == 5
