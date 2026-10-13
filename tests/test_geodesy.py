"""측지 계산 테스트 — 기체 기준 오프셋이 올바른 위경도가 되는지 검증."""
import math

import pytest

from flight.geodesy import (
    GeoPoint, bearing_deg, body_offset_to_ned, clamp_to_radius,
    distance_m, offset_point, target_from_body_offset,
)

# 연세대 신촌캠퍼스 부근
HOME = GeoPoint(37.5665, 126.9388, 0.0)


class TestBodyOffsetToNed:
    def test_heading_north_keeps_axes(self):
        n, e = body_offset_to_ned(forward_m=10, right_m=5, yaw_deg=0)
        assert n == pytest.approx(10.0)
        assert e == pytest.approx(5.0)

    def test_heading_east_rotates_axes(self):
        """기수가 동쪽이면 전방이 동, 우현이 남이 된다."""
        n, e = body_offset_to_ned(forward_m=10, right_m=5, yaw_deg=90)
        assert n == pytest.approx(-5.0, abs=1e-9)
        assert e == pytest.approx(10.0, abs=1e-9)

    def test_heading_south_inverts(self):
        n, e = body_offset_to_ned(forward_m=10, right_m=0, yaw_deg=180)
        assert n == pytest.approx(-10.0, abs=1e-9)

    def test_heading_west(self):
        n, e = body_offset_to_ned(forward_m=10, right_m=0, yaw_deg=270)
        assert e == pytest.approx(-10.0, abs=1e-9)

    def test_magnitude_is_preserved_under_rotation(self):
        for yaw in (0, 37, 90, 180, 263, 359):
            n, e = body_offset_to_ned(8, -6, yaw)
            assert math.hypot(n, e) == pytest.approx(10.0, abs=1e-9)


class TestOffsetPoint:
    def test_north_increases_latitude(self):
        p = offset_point(HOME, north_m=111.3195, east_m=0)
        assert p.lat == pytest.approx(HOME.lat + 0.001, abs=1e-6)
        assert p.lon == pytest.approx(HOME.lon, abs=1e-9)

    def test_east_increases_longitude(self):
        p = offset_point(HOME, north_m=0, east_m=100)
        assert p.lon > HOME.lon
        assert p.lat == pytest.approx(HOME.lat, abs=1e-12)

    def test_longitude_scales_with_latitude(self):
        """고위도일수록 같은 동쪽 거리가 더 큰 경도 변화를 만든다."""
        equator = offset_point(GeoPoint(0.0, 0.0), 0, 1000)
        high = offset_point(GeoPoint(60.0, 0.0), 0, 1000)
        assert high.lon > equator.lon * 1.9      # cos(60) = 0.5 이므로 약 2배

    def test_roundtrip_distance(self):
        p = offset_point(HOME, north_m=30, east_m=40)
        assert distance_m(HOME, p) == pytest.approx(50.0, rel=1e-4)

    def test_pole_is_rejected(self):
        with pytest.raises(ValueError):
            offset_point(GeoPoint(90.0, 0.0), 0, 100)

    def test_altitude_is_carried_or_overridden(self):
        assert offset_point(HOME, 10, 10).alt_m == 0.0
        assert offset_point(HOME, 10, 10, alt_m=12.0).alt_m == 12.0


class TestTargetFromBodyOffset:
    def test_forward_while_heading_north_goes_north(self):
        t = target_from_body_offset(HOME, yaw_deg=0, forward_m=50, right_m=0)
        assert t.lat > HOME.lat
        assert t.lon == pytest.approx(HOME.lon, abs=1e-9)

    def test_right_while_heading_north_goes_east(self):
        t = target_from_body_offset(HOME, yaw_deg=0, forward_m=0, right_m=50)
        assert t.lon > HOME.lon

    def test_matches_expected_bearing(self):
        """기수 45도에서 정면 100 m → 북동쪽 45도 방위에 100 m."""
        t = target_from_body_offset(HOME, yaw_deg=45, forward_m=100, right_m=0)
        assert distance_m(HOME, t) == pytest.approx(100.0, rel=1e-3)
        assert bearing_deg(HOME, t) == pytest.approx(45.0, abs=0.1)

    def test_vision_example_reproduces(self):
        """VISION.md 예시: forward -5.4, right -10.0, 기수 북 → 남서쪽."""
        t = target_from_body_offset(HOME, yaw_deg=0, forward_m=-5.4, right_m=-10.0)
        assert t.lat < HOME.lat and t.lon < HOME.lon
        assert distance_m(HOME, t) == pytest.approx(math.hypot(5.4, 10.0), rel=1e-3)

    def test_altitude_is_attached(self):
        t = target_from_body_offset(HOME, 0, 10, 10, alt_m=10.0)
        assert t.alt_m == 10.0


class TestBearing:
    def test_due_north(self):
        assert bearing_deg(HOME, offset_point(HOME, 100, 0)) == pytest.approx(0.0, abs=0.01)

    def test_due_east(self):
        assert bearing_deg(HOME, offset_point(HOME, 0, 100)) == pytest.approx(90.0, abs=0.01)

    def test_due_south_is_180(self):
        assert bearing_deg(HOME, offset_point(HOME, -100, 0)) == pytest.approx(180.0, abs=0.01)

    def test_due_west_is_270_not_negative(self):
        assert bearing_deg(HOME, offset_point(HOME, 0, -100)) == pytest.approx(270.0, abs=0.01)


class TestClampToRadius:
    def test_inside_radius_passes_through(self):
        t = offset_point(HOME, 30, 0)
        out, clamped = clamp_to_radius(HOME, t, max_radius_m=50)
        assert clamped is False
        assert out is t

    def test_outside_radius_is_cut_to_boundary(self):
        """안전 장치: 잘못된 타겟이 기체를 시야 밖으로 보내면 안 된다."""
        t = offset_point(HOME, 500, 0)
        out, clamped = clamp_to_radius(HOME, t, max_radius_m=50)
        assert clamped is True
        assert distance_m(HOME, out) == pytest.approx(50.0, rel=1e-3)

    def test_clamping_preserves_bearing(self):
        t = offset_point(HOME, 300, 400)          # 방위 약 36.87도
        out, _ = clamp_to_radius(HOME, t, max_radius_m=100)
        assert bearing_deg(HOME, out) == pytest.approx(bearing_deg(HOME, t), abs=0.1)

    def test_clamping_preserves_altitude(self):
        t = offset_point(HOME, 500, 0, alt_m=10.0)
        out, _ = clamp_to_radius(HOME, t, max_radius_m=50)
        assert out.alt_m == 10.0

    def test_zero_radius_is_rejected(self):
        with pytest.raises(ValueError):
            clamp_to_radius(HOME, HOME, max_radius_m=0)


class TestNedToBodyOffset:
    """body_offset_to_ned 의 역변환. 비전이 매 프레임 다시 재는 값과 같아야 한다."""

    def test_roundtrip_identity(self):
        from flight.geodesy import ned_to_body_offset
        for yaw in (0, 45, 90, 180, 237, 359):
            n, e = body_offset_to_ned(12.0, -7.0, yaw)
            f, r = ned_to_body_offset(n, e, yaw)
            assert f == pytest.approx(12.0, abs=1e-9)
            assert r == pytest.approx(-7.0, abs=1e-9)

    def test_heading_north_is_identity(self):
        from flight.geodesy import ned_to_body_offset
        f, r = ned_to_body_offset(north_m=10, east_m=5, yaw_deg=0)
        assert (f, r) == pytest.approx((10.0, 5.0))

    def test_offset_shrinks_as_vehicle_approaches(self):
        """접근하면 오프셋이 줄어야 한다. 줄지 않으면 목표가 영영 도망간다."""
        from flight.geodesy import ned_to_body_offset
        crowd = offset_point(HOME, 50, 0)
        far = ned_to_body_offset(distance_m(HOME, crowd), 0, 0)[0]
        halfway = offset_point(HOME, 25, 0)
        near = ned_to_body_offset(distance_m(halfway, crowd), 0, 0)[0]
        assert near < far
