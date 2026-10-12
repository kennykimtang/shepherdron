"""시간축 안정화 테스트 — 한 프레임의 흔들림이 경보가 되지 않는지 확인한다."""
import pytest

from vision.stability import AlertDebouncer, RollingCounter, TargetSmoother


class TestRollingCounter:
    def test_single_spike_is_rejected(self):
        c = RollingCounter(window=5)
        for v in [4, 4, 4, 4]:
            c.update(v)
        assert c.update(99) == 4, "한 프레임 폭주값이 중앙값을 바꾸면 안 된다"

    def test_sustained_change_is_followed(self):
        c = RollingCounter(window=5)
        for v in [4] * 5:
            c.update(v)
        out = [c.update(20) for _ in range(5)]
        assert out[-1] == 20

    def test_window_must_be_positive(self):
        with pytest.raises(ValueError):
            RollingCounter(window=0)


class TestAlertDebouncer:
    def _feed(self, d, values, t0=0.0, dt=0.1):
        out = None
        for i, v in enumerate(values):
            out = d.update(v, now=t0 + i * dt)
        return out

    def test_isolated_spike_does_not_trigger(self):
        d = AlertDebouncer(window=10, on_ratio=0.6, off_ratio=0.25, min_on_s=1.0)
        assert self._feed(d, [False] * 9 + [True]) is False

    def test_sustained_danger_triggers(self):
        d = AlertDebouncer(window=10, on_ratio=0.6, off_ratio=0.25, min_on_s=1.0)
        assert self._feed(d, [True] * 10) is True

    def test_stays_on_during_min_hold(self):
        d = AlertDebouncer(window=10, on_ratio=0.6, off_ratio=0.25, min_on_s=5.0)
        self._feed(d, [True] * 10, t0=0.0)
        # 위험이 사라져도 min_on_s 안에는 유지되어야 한다
        assert self._feed(d, [False] * 10, t0=1.0) is True

    def test_clears_after_min_hold(self):
        d = AlertDebouncer(window=10, on_ratio=0.6, off_ratio=0.25, min_on_s=2.0)
        self._feed(d, [True] * 10, t0=0.0)
        self._feed(d, [False] * 10, t0=10.0)
        assert d.active is False

    def test_hysteresis_gap_prevents_flapping(self):
        """on 과 off 사이 구간에서는 상태가 바뀌지 않아야 한다."""
        d = AlertDebouncer(window=10, on_ratio=0.8, off_ratio=0.2, min_on_s=0.0)
        self._feed(d, [True] * 10, t0=0.0)          # ON
        assert d.active
        # 비율 0.5 — on(0.8) 미만이지만 off(0.2) 초과 → 그대로 ON 유지
        self._feed(d, [True, False] * 5, t0=5.0)
        assert d.active is True

    def test_invalid_ratios_rejected(self):
        with pytest.raises(ValueError):
            AlertDebouncer(on_ratio=0.2, off_ratio=0.6)

    def test_reset_clears_state(self):
        d = AlertDebouncer(window=4, on_ratio=0.5, off_ratio=0.25, min_on_s=0.0)
        self._feed(d, [True] * 4)
        d.reset()
        assert d.active is False and d.ratio == 0.0


class TestTargetSmoother:
    def test_first_point_passes_through(self):
        s = TargetSmoother(alpha=0.5)
        assert s.update((100, 200)) == (100.0, 200.0)

    def test_small_moves_are_damped(self):
        s = TargetSmoother(alpha=0.5, reset_distance=1000)
        s.update((100, 100))
        assert s.update((200, 100))[0] == pytest.approx(150.0)

    def test_large_jump_snaps_immediately(self):
        """군중이 다른 구역으로 옮겨가면 천천히 따라가서는 안 된다."""
        s = TargetSmoother(alpha=0.2, reset_distance=100)
        s.update((100, 100))
        assert s.update((900, 900)) == (900.0, 900.0)

    def test_none_holds_last_value(self):
        s = TargetSmoother()
        s.update((50, 60))
        assert s.update(None) == (50.0, 60.0)

    def test_none_before_any_point_is_none(self):
        assert TargetSmoother().update(None) is None
