"""실내 시연 프로파일 테스트.

실내는 전제가 다르다. GPS 가 없고, 천장이 4.2 m 이고, 사람이 가까이 있다.
야외 기본값을 그대로 쓰면 arm 조차 되지 않거나, 되더라도 위험하다.
"""
import math

import pytest

from flight.mavlink_controller import MavlinkController, SafetyLimits, VehicleState
from flight.mission import GuidanceConfig, GuidanceMission, MissionState
from hardware.payload import SimulatedPayload


def indoor_controller(**limits):
    c = MavlinkController(dry_run=True, limits=SafetyLimits.indoor(**limits))
    c.state = VehicleState(connected=True, armed=True, mode="GUIDED",
                           relative_alt_m=2.0, heading_deg=0.0,
                           battery_remaining_pct=80, gps_fix_type=0,
                           satellites=0, last_heartbeat=1.0)
    return c


class TestIndoorLimits:
    def test_ceiling_sets_the_altitude_ceiling(self):
        """천장효과를 피하려면 로터 지름의 3배(0.7m) 이상 떨어져야 한다."""
        lim = SafetyLimits.indoor(ceiling_m=4.22)
        assert lim.max_altitude_m == pytest.approx(3.4, abs=0.05)

    def test_lower_ceiling_lowers_the_limit(self):
        assert (SafetyLimits.indoor(ceiling_m=3.0).max_altitude_m
                < SafetyLimits.indoor(ceiling_m=4.5).max_altitude_m)

    def test_gps_is_not_required(self):
        assert SafetyLimits.indoor().require_gps is False
        assert SafetyLimits().require_gps is True

    def test_step_is_limited_for_a_small_room(self):
        assert SafetyLimits.indoor().max_step_m < SafetyLimits().max_step_m

    def test_more_battery_margin_indoors(self):
        """실내는 비상 착륙지가 없다."""
        assert SafetyLimits.indoor().min_battery_pct > SafetyLimits().min_battery_pct

    def test_indoor_defaults_pass_validation(self):
        assert SafetyLimits.indoor().validate() == []

    def test_step_larger_than_radius_is_caught(self):
        assert any("max_step_m" in p
                   for p in SafetyLimits(max_radius_m=5, max_step_m=20).validate())

    def test_overrides_are_honoured(self):
        assert SafetyLimits.indoor(max_step_m=2.0).max_step_m == 2.0


class TestPreflightWithoutGps:
    def test_indoor_preflight_ignores_missing_gps(self):
        """야외 기본값이면 GPS fix 가 없어 arm 조차 되지 않는다."""
        assert indoor_controller().preflight_check(now=2.0) == []

    def test_outdoor_preflight_still_demands_gps(self):
        c = indoor_controller()
        c.limits = SafetyLimits()
        assert any("GPS" in p for p in c.preflight_check(now=2.0))

    def test_explicit_argument_overrides_the_profile(self):
        assert any("GPS" in p
                   for p in indoor_controller().preflight_check(require_gps=True, now=2.0))


class TestBodyOffsetCommand:
    def test_relative_move_is_accepted(self):
        sent = indoor_controller().goto_body_offset(3.0, 1.0)
        assert sent == pytest.approx((3.0, 1.0, 0.0))

    def test_long_move_is_clamped_to_max_step(self):
        """좁은 실내에서 한 번에 멀리 보내지 않는다."""
        c = indoor_controller()
        fwd, right, _ = c.goto_body_offset(30.0, 0.0)
        assert math.hypot(fwd, right) == pytest.approx(c.limits.max_step_m, rel=1e-6)

    def test_clamping_preserves_direction(self):
        fwd, right, _ = indoor_controller().goto_body_offset(30.0, 40.0)
        assert fwd / right == pytest.approx(30.0 / 40.0, rel=1e-6)

    def test_refused_outside_guided(self):
        c = indoor_controller()
        c.state.mode = "LOITER"
        assert c.goto_body_offset(1.0, 0.0) is None

    def test_refused_while_disarmed(self):
        c = indoor_controller()
        c.state.armed = False
        assert c.goto_body_offset(1.0, 0.0) is None

    def test_climbing_through_the_ceiling_is_refused(self):
        c = indoor_controller(ceiling_m=4.22)        # 최대 3.4 m
        c.state.relative_alt_m = 3.0
        assert c.goto_body_offset(1.0, 0.0, down_m=-2.0) is None   # 5.0 m 가 된다

    def test_descending_below_the_floor_limit_is_refused(self):
        c = indoor_controller()
        c.state.relative_alt_m = 1.2
        assert c.goto_body_offset(1.0, 0.0, down_m=1.0) is None     # 0.2 m 가 된다

    def test_level_move_keeps_altitude(self):
        assert indoor_controller().goto_body_offset(2.0, 0.0)[2] == 0.0


class Alert:
    alert_rising_edge = True
    alert_active = True
    smoothed_count = 11

    def __init__(self, fwd=4.0, right=1.0):
        self.target = type("T", (), {"forward_m": fwd, "right_m": right,
                                     "altitude_m": 2.0, "has_ground_fix": True})()


QUIET = type("Q", (), {"alert_rising_edge": False, "alert_active": False,
                       "smoothed_count": 0, "target": None})()


def step(mission, ctl, result, now):
    """실제 루프는 매 주기 ctl.update() 로 heartbeat 를 갱신한다. 그것을 모사한다."""
    ctl.state.last_heartbeat = now
    return mission.update(result, now=now)


class TestIndoorMission:
    def _mission(self, **cfg):
        ctl = indoor_controller()
        cfg.setdefault("use_body_offset", True)
        cfg.setdefault("arrival_radius_m", 1.0)
        cfg.setdefault("hover_duration_s", 5.0)
        return GuidanceMission(ctl, GuidanceConfig(**cfg)), ctl

    def test_alert_issues_a_relative_move_not_a_gps_goto(self):
        m, ctl = self._mission()
        assert step(m, ctl, Alert(), 0.0) is MissionState.NAVIGATING
        assert m.target.forward_m == pytest.approx(4.0)
        assert m.target.right_m == pytest.approx(1.0)

    def test_mission_runs_without_any_gps_fix(self):
        m, ctl = self._mission()
        assert ctl.state.gps_fix_type == 0 and ctl.state.lat is None
        assert step(m, ctl, Alert(), 0.0) is MissionState.NAVIGATING

    def test_arrival_is_judged_by_remaining_offset(self):
        """실내에는 절대 좌표가 없다. 남은 거리가 곧 오차다."""
        m, ctl = self._mission()
        step(m, ctl, Alert(fwd=4.0), 0.0)
        assert step(m, ctl, Alert(fwd=0.3, right=0.2), 3.0) is MissionState.HOVERING

    def test_no_arrival_claimed_without_an_observation(self):
        """관측이 끊기면 도달했다고 단정하지 않는다."""
        m, ctl = self._mission()
        step(m, ctl, Alert(), 0.0)
        assert step(m, ctl, None, 3.0) is MissionState.NAVIGATING

    def test_still_far_keeps_navigating(self):
        m, ctl = self._mission()
        step(m, ctl, Alert(fwd=5.0), 0.0)
        assert step(m, ctl, Alert(fwd=3.0), 1.0) is MissionState.NAVIGATING

    def test_retarget_uses_remaining_distance(self):
        m, ctl = self._mission(retarget_distance_m=2.0, retarget_min_interval_s=1.0)
        step(m, ctl, Alert(fwd=6.0), 0.0)
        step(m, ctl, Alert(fwd=5.0, right=2.0), 2.0)
        # 새 관측 방향으로 다시 발행되되, max_step_m 으로 길이가 잘린다
        assert m.target.forward_m / m.target.right_m == pytest.approx(5.0 / 2.0, rel=1e-6)
        assert math.hypot(m.target.forward_m, m.target.right_m) == pytest.approx(
            ctl.limits.max_step_m, rel=1e-6)

    def test_payload_still_retracts_before_returning(self):
        p = SimulatedPayload(deploy_duration_s=1.0, retract_duration_s=3.0)
        ctl = indoor_controller()
        m = GuidanceMission(ctl, GuidanceConfig(use_body_offset=True,
                                                arrival_radius_m=1.0,
                                                hover_duration_s=3.0),
                            payload=p)
        step(m, ctl, Alert(fwd=0.2, right=0.0), 0.0)
        step(m, ctl, Alert(fwd=0.2, right=0.0), 1.0)
        step(m, ctl, Alert(fwd=0.2, right=0.0), 3.0)
        assert step(m, ctl, QUIET, 10.0) is MissionState.RETRACTING

    def test_status_reports_remaining_distance(self):
        m, ctl = self._mission()
        step(m, ctl, Alert(fwd=3.0, right=4.0), 0.0)
        assert m.status(now=1.0).distance_m == pytest.approx(5.0)
