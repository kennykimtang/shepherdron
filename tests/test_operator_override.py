"""조종사 수동 개입 테스트.

README 는 "언제든 스위치 올려 수동 착륙 가능"을 약속한다. 그런데 임무가
자동으로 RTL 을 걸면 조종권을 도로 뺏어간다. 그러면 수동 개입 장치가
무용지물이 된다. 이 묶음이 그 약속을 코드로 고정한다.
"""
import pytest

from flight.geodesy import GeoPoint, distance_m
from flight.mavlink_controller import SafetyLimits, VehicleState
from flight.mission import GuidanceConfig, GuidanceMission, MissionState
from hardware.payload import PayloadState, SimulatedPayload

HOME = GeoPoint(37.5665, 126.9388, 10.0)


class FakeController:
    def __init__(self):
        self.state = VehicleState(
            connected=True, armed=True, mode="GUIDED",
            lat=HOME.lat, lon=HOME.lon, relative_alt_m=10.0, heading_deg=0.0,
            battery_remaining_pct=90, gps_fix_type=3, satellites=14)
        self.limits = SafetyLimits()
        self.home = HOME
        self.rtl_calls = 0
        self.goto_calls = 0
        self.mode_sets = []
        self.arrived = False
        self.healthy = True

    def is_healthy(self, now=None): return self.healthy
    def preflight_check(self, require_gps=True, now=None): return []
    def set_mode(self, mode, timeout_s=5.0):
        self.mode_sets.append(mode)
        self.state.mode = mode.upper()
        return True
    def goto(self, target, clamp=True):
        self.goto_calls += 1
        return target
    def distance_to(self, p): return distance_m(self.state.position, p)
    def has_arrived(self, p, radius_m=2.0, altitude_tolerance_m=1.5):
        return self.arrived
    def return_to_launch(self):
        self.rtl_calls += 1
        self.state.mode = "RTL"
        return True

    @property
    def commands_issued(self) -> int:
        return self.rtl_calls + self.goto_calls + len(self.mode_sets)


class Alert:
    alert_rising_edge = True
    alert_active = True
    smoothed_count = 13

    class target:
        forward_m, right_m, altitude_m = 25.0, 0.0, 10.0
        has_ground_fix = True


QUIET = type("Q", (), {"alert_rising_edge": False, "alert_active": False,
                       "smoothed_count": 0, "target": None})()


def airborne(payload=None, **cfg):
    ctl = FakeController()
    m = GuidanceMission(ctl, GuidanceConfig(hover_duration_s=10.0, **cfg),
                        payload=payload)
    m.update(Alert(), now=0.0)
    assert m.state is MissionState.NAVIGATING
    return m, ctl


class TestDetection:
    @pytest.mark.parametrize("mode", ["STABILIZE", "LOITER", "ALT_HOLD",
                                      "POSHOLD", "ACRO"])
    def test_any_manual_mode_stands_the_mission_down(self, mode):
        m, ctl = airborne()
        ctl.state.mode = mode
        assert m.update(QUIET, now=5.0) is MissionState.STANDBY

    def test_stand_down_from_hovering(self):
        m, ctl = airborne()
        ctl.arrived = True
        m.update(QUIET, now=1.0)
        assert m.state is MissionState.HOVERING
        ctl.state.mode = "LOITER"
        assert m.update(QUIET, now=2.0) is MissionState.STANDBY

    def test_stand_down_while_retracting(self):
        p = SimulatedPayload(deploy_duration_s=1.0, retract_duration_s=20.0)
        m, ctl = airborne(p)
        ctl.arrived = True
        m.update(QUIET, now=1.0)
        m.update(QUIET, now=3.0)
        m.update(QUIET, now=15.0)
        assert m.state is MissionState.RETRACTING
        ctl.state.mode = "STABILIZE"
        assert m.update(QUIET, now=16.0) is MissionState.STANDBY

    def test_rtl_is_expected_while_returning_not_an_override(self):
        """임무 자신이 건 RTL 을 조종사 개입으로 오인하면 안 된다."""
        m, ctl = airborne()
        ctl.arrived = True
        m.update(QUIET, now=1.0)
        m.update(QUIET, now=20.0)
        assert m.state is MissionState.RETURNING
        assert ctl.state.mode == "RTL"
        assert m.update(QUIET, now=21.0) is MissionState.RETURNING

    def test_operator_override_during_rtl_is_detected(self):
        m, ctl = airborne()
        ctl.arrived = True
        m.update(QUIET, now=1.0)
        m.update(QUIET, now=20.0)
        ctl.state.mode = "STABILIZE"
        assert m.update(QUIET, now=21.0) is MissionState.STANDBY

    def test_unknown_mode_does_not_trigger(self):
        """아직 모드를 못 읽은 상태를 개입으로 오인하면 안 된다."""
        m, ctl = airborne()
        ctl.state.mode = "UNKNOWN"
        assert m.update(QUIET, now=5.0) is MissionState.NAVIGATING


class TestNoCommandsWhileOperatorFlies:
    """핵심: STANDBY 에서는 비행 명령을 하나도 내지 않는다."""

    def test_no_rtl_is_issued(self):
        m, ctl = airborne()
        ctl.state.mode = "STABILIZE"
        m.update(QUIET, now=5.0)
        before = ctl.rtl_calls
        for t in (10.0, 30.0, 60.0, 120.0):
            m.update(Alert(), now=t)
        assert ctl.rtl_calls == before, "조종사가 조종 중인데 RTL 을 걸면 안 된다"

    def test_no_goto_is_issued(self):
        m, ctl = airborne()
        ctl.state.mode = "LOITER"
        m.update(QUIET, now=5.0)
        before = ctl.goto_calls
        for t in (10.0, 20.0, 30.0):
            m.update(Alert(), now=t)
        assert ctl.goto_calls == before

    def test_no_mode_change_is_forced(self):
        m, ctl = airborne()
        ctl.state.mode = "STABILIZE"
        m.update(QUIET, now=5.0)
        before = len(ctl.mode_sets)
        for t in (10.0, 20.0):
            m.update(Alert(), now=t)
        assert len(ctl.mode_sets) == before, "GUIDED 로 되돌리려 하면 안 된다"

    def test_a_new_alert_cannot_restart_the_mission(self):
        m, ctl = airborne()
        ctl.state.mode = "STABILIZE"
        m.update(QUIET, now=5.0)
        assert m.update(Alert(), now=30.0) is MissionState.STANDBY

    def test_link_loss_does_not_trigger_rtl_in_standby(self):
        """조종사가 조종 중이면 링크가 끊겨도 자동화가 끼어들지 않는다."""
        m, ctl = airborne()
        ctl.state.mode = "STABILIZE"
        m.update(QUIET, now=5.0)
        ctl.healthy = False
        before = ctl.rtl_calls
        assert m.update(None, now=10.0) is MissionState.STANDBY
        assert ctl.rtl_calls == before

    def test_low_battery_does_not_trigger_rtl_in_standby(self):
        m, ctl = airborne()
        ctl.state.mode = "STABILIZE"
        m.update(QUIET, now=5.0)
        ctl.state.battery_remaining_pct = 5
        before = ctl.rtl_calls
        assert m.update(QUIET, now=10.0) is MissionState.STANDBY
        assert ctl.rtl_calls == before


class TestPayloadInStandby:
    def test_deployed_structure_is_retracted_for_landing(self):
        """수축은 비행 제어와 충돌하지 않는다. 조종사가 착륙할 수 있어야 한다."""
        p = SimulatedPayload(deploy_duration_s=1.0)
        m, ctl = airborne(p)
        ctl.arrived = True
        m.update(QUIET, now=1.0)
        m.update(QUIET, now=3.0)
        assert p.state is PayloadState.DEPLOYED
        ctl.state.mode = "LOITER"
        m.update(QUIET, now=4.0)
        assert p.state is PayloadState.RETRACTING


class TestRecovery:
    def test_landing_returns_to_idle(self):
        m, ctl = airborne()
        ctl.state.mode = "STABILIZE"
        m.update(QUIET, now=5.0)
        ctl.state.armed = False
        assert m.update(QUIET, now=10.0) is MissionState.IDLE

    def test_cooldown_applies_after_an_operator_landing(self):
        m, ctl = airborne(mission_cooldown_s=60.0)
        ctl.state.mode = "STABILIZE"
        m.update(QUIET, now=5.0)
        ctl.state.armed = False
        m.update(QUIET, now=10.0)
        ctl.state.armed = True
        ctl.state.mode = "GUIDED"
        assert m.update(Alert(), now=20.0) is MissionState.IDLE

    def test_mission_does_not_auto_resume_on_return_to_guided(self):
        """조종사가 GUIDED 로 되돌려도 임무가 멋대로 재개되면 놀란다."""
        m, ctl = airborne()
        ctl.state.mode = "STABILIZE"
        m.update(QUIET, now=5.0)
        ctl.state.mode = "GUIDED"
        assert m.update(QUIET, now=10.0) is MissionState.STANDBY
