"""페이로드 전개/수축 테스트.

핵심 안전 규칙: **구조물이 펼쳐진 채로 복귀·착륙하면 안 된다.**
600 mm 가 기체 아래로 나와 있으면 착륙 자체가 불가능하다.
"""
import pytest

from flight.geodesy import GeoPoint, distance_m
from flight.mavlink_controller import SafetyLimits, VehicleState
from flight.mission import GuidanceConfig, GuidanceMission, MissionState
from hardware.payload import NullPayload, PayloadState, SimulatedPayload

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
        self.rtl_at = []
        self.arrived = False
        self.healthy = True
        self.sent = []

    def is_healthy(self, now=None): return self.healthy
    def preflight_check(self, require_gps=True, now=None): return []
    def set_mode(self, mode, timeout_s=5.0):
        self.state.mode = mode.upper(); return True
    def goto(self, target, clamp=True):
        self.sent.append(target); return target
    def distance_to(self, p): return distance_m(self.state.position, p)
    def has_arrived(self, p, radius_m=2.0, altitude_tolerance_m=1.5):
        return self.arrived
    def return_to_launch(self):
        self.rtl_calls += 1; return True


class Alert:
    alert_rising_edge = True
    alert_active = True
    smoothed_count = 13

    class target:
        forward_m, right_m, altitude_m = 25.0, 0.0, 10.0
        has_ground_fix = True


QUIET = type("Q", (), {"alert_rising_edge": False, "alert_active": False,
                       "smoothed_count": 0, "target": None})()


def fly_to_hover(payload=None, **cfg):
    """경보 → 이동 → 도달까지 진행시킨 상태를 돌려준다."""
    ctl = FakeController()
    m = GuidanceMission(ctl, GuidanceConfig(hover_duration_s=10.0, **cfg),
                        payload=payload)
    m.update(Alert(), now=0.0)
    ctl.arrived = True
    m.update(QUIET, now=1.0)
    assert m.state is MissionState.HOVERING
    return m, ctl


class TestDeployOnArrival:
    def test_payload_deploys_when_the_target_is_reached(self):
        p = SimulatedPayload(deploy_duration_s=3.0)
        m, _ = fly_to_hover(p)
        assert p.state is PayloadState.DEPLOYING
        m.update(QUIET, now=5.0)
        assert p.state is PayloadState.DEPLOYED

    def test_arrival_hook_still_fires_alongside_the_payload(self):
        """LED·음성 같은 부가 동작은 여전히 콜백으로 받는다."""
        fired = []
        ctl = FakeController()
        p = SimulatedPayload()
        m = GuidanceMission(ctl, GuidanceConfig(), payload=p,
                            on_arrived=lambda mi: fired.append(mi.state))
        m.update(Alert(), now=0.0)
        ctl.arrived = True
        m.update(QUIET, now=1.0)
        assert fired == [MissionState.HOVERING]
        assert p.state is PayloadState.DEPLOYING


class TestNeverReturnWhileDeployed:
    """이 묶음이 이 작업의 존재 이유다."""

    def test_hover_end_goes_to_retracting_not_returning(self):
        p = SimulatedPayload(deploy_duration_s=2.0, retract_duration_s=8.0)
        m, ctl = fly_to_hover(p)
        m.update(QUIET, now=5.0)                      # 전개 완료
        assert m.update(QUIET, now=20.0) is MissionState.RETRACTING
        assert ctl.rtl_calls == 0, "접히기 전에 RTL 을 걸면 안 된다"

    def test_rtl_waits_for_the_structure_to_stow(self):
        p = SimulatedPayload(deploy_duration_s=2.0, retract_duration_s=8.0)
        m, ctl = fly_to_hover(p)
        m.update(QUIET, now=5.0)
        m.update(QUIET, now=20.0)                     # RETRACTING 진입
        for t in (22.0, 25.0, 27.0):                  # 아직 접히는 중
            assert m.update(QUIET, now=t) is MissionState.RETRACTING
            assert ctl.rtl_calls == 0
        assert m.update(QUIET, now=29.0) is MissionState.RETURNING
        assert ctl.rtl_calls == 1

    def test_mission_completes_after_landing(self):
        p = SimulatedPayload(deploy_duration_s=2.0, retract_duration_s=4.0)
        m, ctl = fly_to_hover(p)
        m.update(QUIET, now=5.0)
        m.update(QUIET, now=20.0)
        m.update(QUIET, now=25.0)
        assert m.state is MissionState.RETURNING
        ctl.state.armed = False
        assert m.update(QUIET, now=30.0) is MissionState.IDLE
        assert m.missions_completed == 1

    def test_stuck_payload_raises_failsafe(self):
        """접히지 않으면 조용히 복귀시키지 않는다. 운용자가 알아야 한다."""
        p = SimulatedPayload(deploy_duration_s=2.0, retract_duration_s=4.0,
                             fail_retract=True)
        m, ctl = fly_to_hover(p, retract_timeout_s=15.0)
        m.update(QUIET, now=5.0)
        m.update(QUIET, now=20.0)                     # RETRACTING 진입
        m.update(QUIET, now=25.0)                     # FAULT 로 떨어짐
        assert p.state is PayloadState.FAULT
        assert m.update(QUIET, now=40.0) is MissionState.FAILSAFE
        assert "수축 실패" in m.reason

    def test_failsafe_mid_flight_commands_a_retract(self):
        """링크가 끊겨도 구조물은 접어야 한다."""
        p = SimulatedPayload(deploy_duration_s=2.0)
        m, ctl = fly_to_hover(p)
        m.update(QUIET, now=5.0)
        assert p.state is PayloadState.DEPLOYED
        ctl.healthy = False
        m.update(QUIET, now=6.0)
        assert m.state is MissionState.FAILSAFE
        assert p.state is PayloadState.RETRACTING


class TestWithoutAPayload:
    """기구부가 완성되기 전에도 비행 로직은 그대로 돌아야 한다."""

    def test_null_payload_skips_the_retract_step(self):
        m, ctl = fly_to_hover(NullPayload())
        assert m.update(QUIET, now=20.0) is MissionState.RETURNING
        assert ctl.rtl_calls == 1

    def test_default_is_no_payload(self):
        m, ctl = fly_to_hover()
        assert isinstance(m.payload, NullPayload)
        assert m.update(QUIET, now=20.0) is MissionState.RETURNING


class TestSimulatedPayload:
    def test_starts_stowed(self):
        assert SimulatedPayload().is_stowed

    def test_deploy_is_not_instant(self):
        p = SimulatedPayload(deploy_duration_s=5.0)
        p.deploy(now=0.0)
        assert p.update(2.0) is PayloadState.DEPLOYING
        assert p.update(6.0) is PayloadState.DEPLOYED

    def test_retract_is_slower_than_deploy_by_default(self):
        p = SimulatedPayload()
        assert p.retract_duration_s > p.deploy_duration_s

    def test_repeated_deploy_does_not_restart_the_clock(self):
        p = SimulatedPayload(deploy_duration_s=4.0)
        p.deploy(now=0.0)
        p.deploy(now=3.0)
        assert p.update(5.0) is PayloadState.DEPLOYED

    def test_failed_deploy_reports_fault(self):
        p = SimulatedPayload(deploy_duration_s=2.0, fail_deploy=True)
        p.deploy(now=0.0)
        assert p.update(3.0) is PayloadState.FAULT
        assert not p.is_deployed and not p.is_stowed

    def test_retract_from_stowed_is_a_no_op(self):
        p = SimulatedPayload()
        p.retract(now=0.0)
        assert p.state is PayloadState.STOWED
