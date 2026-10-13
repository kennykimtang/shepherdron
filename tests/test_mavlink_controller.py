"""MAVLink 컨트롤러 안전 가드 테스트.

dry_run 모드를 쓰므로 실제 연결도 SITL 도 필요 없다.
여기서 검증하는 건 "잘못된 명령을 거부하는가" 다.
"""
import math

import pytest

from flight.geodesy import GeoPoint, distance_m, offset_point
from flight.mavlink_controller import (
    POSITION_ONLY_MASK, MavlinkController, PreflightError, SafetyLimits, VehicleState,
)

HOME = GeoPoint(37.5665, 126.9388, 0.0)


def ready_controller(**limits) -> MavlinkController:
    c = MavlinkController(dry_run=True, limits=SafetyLimits(**limits))
    c.home = HOME
    c.state = VehicleState(
        connected=True, armed=True, mode="GUIDED",
        lat=HOME.lat, lon=HOME.lon, relative_alt_m=10.0, heading_deg=0.0,
        battery_remaining_pct=90, gps_fix_type=3, satellites=14,
        last_heartbeat=1.0,
    )
    return c


class TestPositionMask:
    def test_mask_matches_ardupilot_documented_value(self):
        assert POSITION_ONLY_MASK == 0b110111111000


class TestVehicleState:
    def test_position_is_none_without_fix(self):
        assert VehicleState().position is None

    def test_heartbeat_age_is_infinite_before_first_beat(self):
        assert VehicleState().heartbeat_age() == math.inf

    def test_gps_fix_requires_3d(self):
        assert VehicleState(gps_fix_type=2).has_gps_fix is False
        assert VehicleState(gps_fix_type=3).has_gps_fix is True


class TestPreflight:
    def test_healthy_vehicle_passes(self):
        c = ready_controller()
        assert c.preflight_check(now=2.0) == []

    def test_disconnected_is_caught(self):
        c = ready_controller()
        c.state.connected = False
        assert any("연결" in p for p in c.preflight_check(now=2.0))

    def test_no_gps_fix_is_caught(self):
        c = ready_controller()
        c.state.gps_fix_type = 1
        assert any("GPS" in p for p in c.preflight_check(now=2.0))

    def test_too_few_satellites_is_caught(self):
        c = ready_controller(min_satellites=10)
        c.state.satellites = 6
        assert any("위성" in p for p in c.preflight_check(now=2.0))

    def test_low_battery_is_caught(self):
        c = ready_controller(min_battery_pct=25)
        c.state.battery_remaining_pct = 15
        assert any("배터리" in p for p in c.preflight_check(now=2.0))

    def test_gps_can_be_waived_for_bench_testing(self):
        c = ready_controller()
        c.state.gps_fix_type = 0
        c.state.lat = c.state.lon = None
        assert c.preflight_check(require_gps=False, now=2.0) == []

    def test_assert_ready_raises_with_all_reasons(self):
        c = ready_controller()
        c.state.gps_fix_type = 0
        c.state.battery_remaining_pct = 5
        with pytest.raises(PreflightError) as exc:
            c.assert_ready(now=2.0)
        assert "GPS" in str(exc.value) and "배터리" in str(exc.value)


class TestGotoGuards:
    def test_accepts_a_valid_target(self):
        c = ready_controller()
        sent = c.goto(offset_point(HOME, 30, 0, alt_m=10.0))
        assert sent is not None

    def test_refuses_outside_guided(self):
        c = ready_controller()
        c.state.mode = "LOITER"
        assert c.goto(offset_point(HOME, 30, 0, alt_m=10.0)) is None

    def test_refuses_while_disarmed(self):
        c = ready_controller()
        c.state.armed = False
        assert c.goto(offset_point(HOME, 30, 0, alt_m=10.0)) is None

    def test_refuses_target_without_altitude(self):
        c = ready_controller()
        assert c.goto(GeoPoint(HOME.lat, HOME.lon, None)) is None

    def test_refuses_altitude_above_limit(self):
        c = ready_controller(max_altitude_m=30.0)
        assert c.goto(offset_point(HOME, 10, 0, alt_m=120.0)) is None

    def test_refuses_altitude_below_limit(self):
        c = ready_controller(min_altitude_m=3.0)
        assert c.goto(offset_point(HOME, 10, 0, alt_m=1.0)) is None

    def test_clamps_a_runaway_target(self):
        """비전이 틀린 타겟을 내도 기체가 시야 밖으로 날아가면 안 된다."""
        c = ready_controller(max_radius_m=100.0)
        sent = c.goto(offset_point(HOME, 800, 0, alt_m=10.0))
        assert sent is not None
        assert distance_m(HOME, sent) == pytest.approx(100.0, rel=1e-3)

    def test_clamp_can_be_disabled_explicitly(self):
        c = ready_controller(max_radius_m=100.0)
        far = offset_point(HOME, 800, 0, alt_m=10.0)
        assert distance_m(HOME, c.goto(far, clamp=False)) == pytest.approx(800.0, rel=1e-3)

    def test_clamps_relative_to_home_not_current_position(self):
        """기체가 멀리 떠내려가도 반경 기준점은 홈이어야 한다."""
        c = ready_controller(max_radius_m=100.0)
        drifted = offset_point(HOME, 90, 0)
        c.state.lat, c.state.lon = drifted.lat, drifted.lon
        sent = c.goto(offset_point(HOME, 500, 0, alt_m=10.0))
        assert distance_m(HOME, sent) == pytest.approx(100.0, rel=1e-3)


class TestTakeoffGuards:
    def test_refuses_while_disarmed(self):
        c = ready_controller()
        c.state.armed = False
        assert c.takeoff(10.0) is False

    def test_refuses_altitude_outside_limits(self):
        c = ready_controller(min_altitude_m=3.0, max_altitude_m=30.0)
        assert c.takeoff(50.0) is False
        assert c.takeoff(1.0) is False

    def test_accepts_altitude_in_range(self):
        assert ready_controller().takeoff(10.0) is True


class TestArrival:
    def test_not_arrived_when_far(self):
        c = ready_controller()
        assert c.has_arrived(offset_point(HOME, 50, 0, alt_m=10.0), radius_m=2.0) is False

    def test_arrived_when_within_radius_and_altitude(self):
        c = ready_controller()
        assert c.has_arrived(offset_point(HOME, 1, 0, alt_m=10.0), radius_m=2.0) is True

    def test_horizontal_arrival_is_not_enough(self):
        """수평으로 도착해도 고도가 틀리면 아직 도달이 아니다."""
        c = ready_controller()
        assert c.has_arrived(offset_point(HOME, 1, 0, alt_m=25.0),
                             radius_m=2.0, altitude_tolerance_m=1.5) is False


class TestHealth:
    def test_fresh_heartbeat_is_healthy(self):
        c = ready_controller(heartbeat_timeout_s=3.0)
        assert c.is_healthy(now=2.0) is True

    def test_stale_heartbeat_is_unhealthy(self):
        c = ready_controller(heartbeat_timeout_s=3.0)
        assert c.is_healthy(now=10.0) is False

    def test_disconnected_is_unhealthy(self):
        c = ready_controller()
        c.state.connected = False
        assert c.is_healthy(now=1.0) is False
