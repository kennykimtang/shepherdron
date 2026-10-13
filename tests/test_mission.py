"""유도 임무 상태기계 테스트 — 가짜 기체로 하드웨어 없이 전체 흐름을 검증한다."""
from dataclasses import dataclass
from typing import Optional

import pytest

from flight.geodesy import GeoPoint, distance_m
from flight.mavlink_controller import SafetyLimits, VehicleState
from flight.mission import GuidanceConfig, GuidanceMission, MissionState

HOME = GeoPoint(37.5665, 126.9388, 10.0)


# ─────────────────────────── 대역(fake) ───────────────────────────
@dataclass
class FakeTarget:
    forward_m: Optional[float] = 20.0
    right_m: Optional[float] = 0.0
    altitude_m: Optional[float] = 10.0

    @property
    def has_ground_fix(self) -> bool:
        return self.forward_m is not None and self.right_m is not None


@dataclass
class FakeResult:
    alert_rising_edge: bool = False
    alert_active: bool = True
    smoothed_count: int = 12
    target: Optional[FakeTarget] = None


class FakeController:
    """MavlinkController 와 같은 표면을 가진 테스트용 기체."""

    def __init__(self, **overrides):
        self.state = VehicleState(
            connected=True, armed=True, mode="GUIDED",
            lat=HOME.lat, lon=HOME.lon, relative_alt_m=10.0, heading_deg=0.0,
            battery_remaining_pct=90, gps_fix_type=3, satellites=14,
        )
        for k, v in overrides.items():
            setattr(self.state, k, v)
        self.limits = SafetyLimits()
        self.home = HOME
        self.healthy = True
        self.sent_targets: list[GeoPoint] = []
        self.rtl_calls = 0
        self.preflight_problems: list[str] = []
        self.arrived_at: Optional[GeoPoint] = None

    def is_healthy(self, now=None):
        return self.healthy

    def preflight_check(self, require_gps=True, now=None):
        return list(self.preflight_problems)

    def set_mode(self, mode, timeout_s=5.0):
        self.state.mode = mode.upper()
        return True

    def goto(self, target, clamp=True):
        self.sent_targets.append(target)
        return target

    def distance_to(self, point):
        pos = self.state.position
        return None if pos is None else distance_m(pos, point)

    def has_arrived(self, point, radius_m=2.0, altitude_tolerance_m=1.5):
        return self.arrived_at is not None and self.arrived_at is point

    def return_to_launch(self):
        self.rtl_calls += 1
        return True


def build(ctl=None, **cfg):
    ctl = ctl or FakeController()
    return GuidanceMission(ctl, GuidanceConfig(**cfg)), ctl


ALERT = FakeResult(alert_rising_edge=True, target=FakeTarget())
QUIET = FakeResult(alert_rising_edge=False, alert_active=False)


# ─────────────────────────── IDLE ───────────────────────────
class TestIdle:
    def test_stays_idle_without_alert(self):
        m, _ = build()
        assert m.update(QUIET, now=0.0) is MissionState.IDLE

    def test_alert_starts_navigation(self):
        m, ctl = build()
        assert m.update(ALERT, now=0.0) is MissionState.NAVIGATING
        assert len(ctl.sent_targets) == 1

    def test_target_is_20m_north_when_heading_north(self):
        m, ctl = build()
        m.update(ALERT, now=0.0)
        sent = ctl.sent_targets[0]
        assert distance_m(HOME, sent) == pytest.approx(20.0, rel=1e-3)
        assert sent.lat > HOME.lat

    def test_cruise_altitude_is_applied(self):
        m, ctl = build(cruise_altitude_m=15.0)
        m.update(ALERT, now=0.0)
        assert ctl.sent_targets[0].alt_m == 15.0

    def test_alert_without_ground_fix_is_ignored(self):
        """고도 미지정이면 미터 오프셋이 없다. 이때 비행 명령을 내면 안 된다."""
        m, ctl = build()
        bad = FakeResult(alert_rising_edge=True, target=FakeTarget(forward_m=None))
        assert m.update(bad, now=0.0) is MissionState.IDLE
        assert ctl.sent_targets == []

    def test_alert_without_target_is_ignored(self):
        m, ctl = build()
        assert m.update(FakeResult(alert_rising_edge=True), now=0.0) is MissionState.IDLE

    def test_preflight_failure_blocks_launch(self):
        m, ctl = build()
        ctl.preflight_problems = ["GPS fix 없음"]
        assert m.update(ALERT, now=0.0) is MissionState.IDLE
        assert ctl.sent_targets == []

    def test_missing_heading_blocks_launch(self):
        m, ctl = build(ctl=FakeController(heading_deg=None))
        assert m.update(ALERT, now=0.0) is MissionState.IDLE

    def test_guided_mode_is_entered(self):
        m, ctl = build(ctl=FakeController(mode="LOITER"))
        m.update(ALERT, now=0.0)
        assert ctl.state.mode == "GUIDED"


# ─────────────────────────── NAVIGATING ───────────────────────────
class TestNavigating:
    def test_arrival_moves_to_hovering(self):
        m, ctl = build()
        m.update(ALERT, now=0.0)
        ctl.arrived_at = m.target
        assert m.update(QUIET, now=5.0) is MissionState.HOVERING

    def test_arrival_fires_deploy_hook(self):
        """Phase 3 액추에이터 전개가 걸릴 지점."""
        fired = []
        ctl = FakeController()
        m = GuidanceMission(ctl, GuidanceConfig(), on_arrived=lambda mi: fired.append(mi.state))
        m.update(ALERT, now=0.0)
        ctl.arrived_at = m.target
        m.update(QUIET, now=5.0)
        assert fired == [MissionState.HOVERING]

    def test_timeout_returns_home(self):
        m, ctl = build(navigation_timeout_s=30.0)
        m.update(ALERT, now=0.0)
        assert m.update(QUIET, now=31.0) is MissionState.RETURNING
        assert ctl.rtl_calls == 1

    def test_crowd_movement_triggers_retarget(self):
        m, ctl = build(retarget_distance_m=5.0, retarget_min_interval_s=2.0)
        m.update(ALERT, now=0.0)
        moved = FakeResult(alert_active=True, target=FakeTarget(forward_m=20.0, right_m=30.0))
        m.update(moved, now=3.0)
        assert len(ctl.sent_targets) == 2

    def test_small_movement_does_not_retarget(self):
        """타겟이 조금 흔들릴 때마다 명령을 보내면 기체가 갈팡질팡한다."""
        m, ctl = build(retarget_distance_m=5.0, retarget_min_interval_s=2.0)
        m.update(ALERT, now=0.0)
        nudged = FakeResult(alert_active=True, target=FakeTarget(forward_m=21.0, right_m=1.0))
        m.update(nudged, now=3.0)
        assert len(ctl.sent_targets) == 1

    def test_retarget_respects_minimum_interval(self):
        m, ctl = build(retarget_distance_m=5.0, retarget_min_interval_s=5.0)
        m.update(ALERT, now=0.0)
        moved = FakeResult(alert_active=True, target=FakeTarget(forward_m=20.0, right_m=40.0))
        m.update(moved, now=1.0)                 # 간격 미달
        assert len(ctl.sent_targets) == 1
        m.update(moved, now=6.0)                 # 간격 충족
        assert len(ctl.sent_targets) == 2


# ─────────────────────────── HOVERING / RETURNING ───────────────────────────
class TestHoverAndReturn:
    def _reach_hover(self, **cfg):
        m, ctl = build(**cfg)
        m.update(ALERT, now=0.0)
        ctl.arrived_at = m.target
        m.update(QUIET, now=1.0)
        return m, ctl

    def test_holds_for_configured_duration(self):
        m, _ = self._reach_hover(hover_duration_s=30.0)
        assert m.update(QUIET, now=20.0) is MissionState.HOVERING

    def test_returns_after_duration(self):
        m, ctl = self._reach_hover(hover_duration_s=30.0)
        assert m.update(QUIET, now=40.0) is MissionState.RETURNING
        assert ctl.rtl_calls == 1

    def test_landing_completes_the_mission(self):
        m, ctl = self._reach_hover(hover_duration_s=10.0)
        m.update(QUIET, now=20.0)
        ctl.state.armed = False                  # 착륙 후 자동 disarm
        assert m.update(QUIET, now=60.0) is MissionState.IDLE
        assert m.missions_completed == 1

    def test_cooldown_blocks_immediate_relaunch(self):
        m, ctl = self._reach_hover(hover_duration_s=10.0, mission_cooldown_s=60.0)
        m.update(QUIET, now=20.0)
        ctl.state.armed = False
        m.update(QUIET, now=30.0)                # 완료, 쿨다운 시작
        ctl.state.armed = True
        assert m.update(ALERT, now=40.0) is MissionState.IDLE

    def test_relaunch_allowed_after_cooldown(self):
        m, ctl = self._reach_hover(hover_duration_s=10.0, mission_cooldown_s=60.0)
        m.update(QUIET, now=20.0)
        ctl.state.armed = False
        m.update(QUIET, now=30.0)
        ctl.state.armed = True
        ctl.arrived_at = None
        assert m.update(ALERT, now=95.0) is MissionState.NAVIGATING


# ─────────────────────────── 페일세이프 ───────────────────────────
class TestFailsafe:
    def test_link_loss_triggers_rtl(self):
        m, ctl = build()
        m.update(ALERT, now=0.0)
        ctl.healthy = False
        assert m.update(QUIET, now=1.0) is MissionState.FAILSAFE
        assert ctl.rtl_calls == 1

    def test_low_battery_triggers_rtl(self):
        m, ctl = build(min_battery_pct=30)
        m.update(ALERT, now=0.0)
        ctl.state.battery_remaining_pct = 20
        assert m.update(QUIET, now=1.0) is MissionState.FAILSAFE

    def test_failsafe_callback_receives_reason(self):
        seen = []
        ctl = FakeController()
        m = GuidanceMission(ctl, GuidanceConfig(),
                            on_failsafe=lambda mi, why: seen.append(why))
        m.update(ALERT, now=0.0)
        ctl.healthy = False
        m.update(QUIET, now=1.0)
        assert seen and "heartbeat" in seen[0]

    def test_failsafe_is_terminal(self):
        m, ctl = build()
        m.update(ALERT, now=0.0)
        ctl.healthy = False
        m.update(QUIET, now=1.0)
        ctl.healthy = True
        assert m.update(ALERT, now=10.0) is MissionState.FAILSAFE

    def test_idle_does_not_failsafe_on_link_loss(self):
        """지상 대기 중 링크가 없다고 RTL 을 걸 필요는 없다."""
        m, ctl = build()
        ctl.healthy = False
        assert m.update(QUIET, now=0.0) is MissionState.IDLE

    def test_manual_abort_returns_home(self):
        m, ctl = build()
        m.update(ALERT, now=0.0)
        m.abort("조종기 개입", now=5.0)
        assert m.state is MissionState.RETURNING
        assert ctl.rtl_calls == 1


class TestStatus:
    def test_status_reports_distance_to_target(self):
        m, ctl = build()
        m.update(ALERT, now=0.0)
        st = m.status(now=1.0)
        assert st.state is MissionState.NAVIGATING
        assert st.distance_m == pytest.approx(20.0, rel=1e-3)
