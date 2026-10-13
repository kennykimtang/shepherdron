"""비행 스택 통합 테스트 — 움직이는 가짜 기체로 임무 한 사이클을 끝까지 돌린다.

SITL 이 없어도 비전 오프셋 → GPS 변환 → 유도 → 도달 → 호버링 → 복귀 →
완료까지 전 구간이 이어지는지 확인한다.
"""
import pytest

import math

from flight.geodesy import (
    GeoPoint, bearing_deg, distance_m, ned_to_body_offset, offset_point,
    target_from_body_offset,
)
from flight.mavlink_controller import SafetyLimits, VehicleState
from flight.mission import GuidanceConfig, GuidanceMission, MissionState

HOME = GeoPoint(37.5665, 126.9388, 10.0)


class SimulatedVehicle:
    """목표를 향해 실제로 이동하는 가짜 기체."""

    def __init__(self, speed_ms: float = 5.0):
        self.state = VehicleState(
            connected=True, armed=True, mode="GUIDED",
            lat=HOME.lat, lon=HOME.lon, relative_alt_m=10.0, heading_deg=0.0,
            battery_remaining_pct=95, gps_fix_type=3, satellites=15,
        )
        self.limits = SafetyLimits()
        self.home = HOME
        self.speed = speed_ms
        self.commanded: list[GeoPoint] = []
        self.rtl_calls = 0
        self._rtl = False

    # ── MavlinkController 표면 ──
    def is_healthy(self, now=None):
        return True

    def preflight_check(self, require_gps=True, now=None):
        return []

    def set_mode(self, mode, timeout_s=5.0):
        self.state.mode = mode.upper()
        return True

    def goto(self, target, clamp=True):
        self.commanded.append(target)
        self._rtl = False
        return target

    def distance_to(self, point):
        return distance_m(self.state.position, point)

    def has_arrived(self, point, radius_m=2.0, altitude_tolerance_m=1.5):
        return self.distance_to(point) <= radius_m

    def return_to_launch(self):
        self.rtl_calls += 1
        self._rtl = True
        self.state.mode = "RTL"
        return True

    # ── 물리 ──
    def step(self, dt: float) -> None:
        """목표(또는 홈)를 향해 dt 초만큼 이동한다."""
        goal = self.home if self._rtl else (self.commanded[-1] if self.commanded else None)
        if goal is None:
            return
        pos = self.state.position
        d = distance_m(pos, goal)
        if d < 1e-6:
            if self._rtl:
                self.state.armed = False          # 착륙 후 자동 disarm
            return
        frac = min(1.0, self.speed * dt / d)
        self.state.lat += (goal.lat - pos.lat) * frac
        self.state.lon += (goal.lon - pos.lon) * frac


class _Target:
    def __init__(self, forward_m, right_m, altitude_m=10.0):
        self.forward_m, self.right_m, self.altitude_m = forward_m, right_m, altitude_m

    @property
    def has_ground_fix(self):
        return self.forward_m is not None


class _Alert:
    """비전이 내는 결과를 흉내낸다. 오프셋은 기체 기준이므로 매번 다시 잰다."""

    def __init__(self, crowd: GeoPoint):
        self.crowd = crowd
        self.alert_rising_edge = True
        self.alert_active = True
        self.smoothed_count = 14
        self.target = None

    def observe(self, veh) -> "_Alert":
        pos = veh.state.position
        if pos is None:
            self.target = None
            return self
        d = distance_m(pos, self.crowd)
        brg = math.radians(bearing_deg(pos, self.crowd))
        fwd, right = ned_to_body_offset(d * math.cos(brg), d * math.sin(brg),
                                        veh.state.heading_deg or 0.0)
        self.target = _Target(fwd, right)
        return self


# 홈에서 북동쪽 50 m 지점에 군중이 있다고 가정
CROWD = target_from_body_offset(HOME, 0.0, 40.0, 30.0)


@pytest.fixture
def alert():
    return _Alert(CROWD)


def run(mission, veh, alert, until, dt=0.5, start=0.0):
    """매 프레임 비전을 다시 관측하며 조건이 만족될 때까지 돌린다."""
    t = start
    for _ in range(int(600 / dt)):
        mission.update(alert.observe(veh), now=t)
        alert.alert_rising_edge = False
        veh.step(dt)
        if until(mission):
            return t
        t += dt
    raise AssertionError(f"조건 미달 — 마지막 상태 {mission.state}")


class TestFullMissionCycle:
    def test_vision_offset_reaches_the_right_place(self, alert):
        veh = SimulatedVehicle()
        m = GuidanceMission(veh, GuidanceConfig(cruise_altitude_m=10.0,
                                                arrival_radius_m=2.0,
                                                hover_duration_s=10.0))
        m.update(alert.observe(veh), now=0.0)
        assert distance_m(veh.commanded[0], CROWD) < 0.01
        assert distance_m(HOME, veh.commanded[0]) == pytest.approx(50.0, rel=1e-3)

    def test_runs_idle_to_idle(self, alert):
        veh = SimulatedVehicle(speed_ms=8.0)
        m = GuidanceMission(veh, GuidanceConfig(cruise_altitude_m=10.0,
                                                arrival_radius_m=2.0,
                                                hover_duration_s=5.0,
                                                mission_cooldown_s=30.0))
        run(m, veh, alert, lambda mi: mi.state is MissionState.HOVERING)
        t = run(m, veh, alert, lambda mi: mi.missions_completed == 1, start=100.0)
        assert m.state is MissionState.IDLE
        assert veh.rtl_calls >= 1
        assert distance_m(HOME, veh.state.position) < 2.0

    def test_arrival_hook_fires_once_per_mission(self, alert):
        veh = SimulatedVehicle(speed_ms=8.0)
        fired = []
        m = GuidanceMission(veh, GuidanceConfig(hover_duration_s=5.0),
                            on_arrived=lambda mi: fired.append(mi.target))
        run(m, veh, alert, lambda mi: mi.state is MissionState.HOVERING)
        assert len(fired) == 1

    def test_link_loss_midflight_returns_home(self, alert):
        veh = SimulatedVehicle(speed_ms=3.0)
        m = GuidanceMission(veh, GuidanceConfig())
        m.update(alert.observe(veh), now=0.0)
        alert.alert_rising_edge = False
        veh.step(1.0)
        veh.is_healthy = lambda now=None: False
        assert m.update(alert.observe(veh), now=1.0) is MissionState.FAILSAFE
        assert veh.rtl_calls == 1


class TestSafetyClamping:
    def test_runaway_vision_target_is_contained(self):
        """고도를 100배 틀리게 주면 오프셋이 폭주한다. 반경 제한이 받아내야 한다."""
        from flight.mavlink_controller import MavlinkController

        ctl = MavlinkController(dry_run=True, limits=SafetyLimits(max_radius_m=100.0))
        ctl.home = HOME
        ctl.state = VehicleState(connected=True, armed=True, mode="GUIDED",
                                 lat=HOME.lat, lon=HOME.lon, relative_alt_m=10.0,
                                 heading_deg=0.0, gps_fix_type=3, satellites=14,
                                 last_heartbeat=1.0)
        runaway = target_from_body_offset(HOME, 0.0, 4000.0, 3000.0, alt_m=10.0)
        sent = ctl.goto(runaway)
        assert distance_m(HOME, sent) == pytest.approx(100.0, rel=1e-3)
