"""지상 평면 기하 테스트 — 모델 가중치 없이 순수 계산만 검증한다."""
import math

import pytest

from vision.geometry import CameraModel, GroundPlane, ground_plane_from_altitude


def square_plane():
    """화면 사각형 400x200 px 가 실제 4m x 3m 에 대응하는 단순 케이스."""
    img = [(100, 100), (500, 100), (500, 300), (100, 300)]
    world = [(0.0, 3.0), (4.0, 3.0), (4.0, 0.0), (0.0, 0.0)]
    return GroundPlane.from_points(img, world)


class TestGroundPlane:
    def test_corner_mapping_is_exact(self):
        gp = square_plane()
        got = gp.to_world(gp.image_points)
        for g, w in zip(got, gp.world_points):
            assert g == pytest.approx(w, abs=1e-6)

    def test_reference_rectangle_area(self):
        gp = square_plane()
        assert gp.polygon_area_m2([(100, 100), (500, 100), (500, 300), (100, 300)]) \
            == pytest.approx(12.0, rel=1e-6)

    def test_half_rectangle_is_half_area(self):
        gp = square_plane()
        assert gp.polygon_area_m2([(100, 100), (300, 100), (300, 300), (100, 300)]) \
            == pytest.approx(6.0, rel=1e-6)

    def test_roundtrip_through_json(self, tmp_path):
        gp = square_plane()
        p = tmp_path / "plane.json"
        gp.save(p)
        back = GroundPlane.load(p)
        assert back.to_world([(300, 200)])[0] == pytest.approx(
            gp.to_world([(300, 200)])[0], abs=1e-9)

    def test_needs_four_points(self):
        with pytest.raises(ValueError):
            GroundPlane.from_points([(0, 0), (1, 1)], [(0, 0), (1, 1)])

    def test_mismatched_lengths_rejected(self):
        with pytest.raises(ValueError):
            GroundPlane.from_points([(0, 0)] * 4, [(0, 0)] * 3)


class TestCameraModel:
    def test_focal_length_from_fov(self):
        cam = CameraModel(width=1280, height=720, hfov_deg=90.0, vfov_deg=90.0)
        # 90도 화각이면 초점거리 = 폭의 절반
        assert cam.fx == pytest.approx(640.0, rel=1e-9)

    def test_image_centre_has_no_angular_offset(self):
        cam = CameraModel(width=1280, height=720)
        assert cam.pixel_to_angles(640, 360) == pytest.approx((0.0, 0.0), abs=1e-9)

    def test_nadir_centre_is_directly_below(self):
        cam = CameraModel(width=1280, height=720, pitch_deg=90.0)
        fwd, right = cam.pixel_to_ground_offset(640, 360, 10.0)
        assert fwd == pytest.approx(0.0, abs=1e-6)
        assert right == pytest.approx(0.0, abs=1e-6)

    def test_nadir_bottom_of_frame_is_behind_the_aircraft(self):
        cam = CameraModel(width=1280, height=720, pitch_deg=90.0)
        fwd, _ = cam.pixel_to_ground_offset(640, 719, 10.0)
        assert fwd < 0, "화면 하단은 기체 뒤쪽 지면이어야 한다"

    def test_offset_scales_linearly_with_altitude(self):
        cam = CameraModel(width=1280, height=720, pitch_deg=90.0)
        a = cam.pixel_to_ground_offset(1000, 360, 10.0)
        b = cam.pixel_to_ground_offset(1000, 360, 20.0)
        assert b[1] == pytest.approx(2 * a[1], rel=1e-9)

    def test_above_horizon_returns_none(self):
        # 20도만 숙이면 화면 상단(화각 절반 33.5도 위)은 하늘을 본다
        cam = CameraModel(width=1280, height=720, pitch_deg=20.0)
        assert cam.pixel_to_ground_offset(640, 0, 10.0) is None

    def test_zero_altitude_is_rejected(self):
        cam = CameraModel(width=1280, height=720)
        assert cam.pixel_to_ground_offset(640, 360, 0.0) is None

    def test_nadir_footprint_matches_fov_geometry(self):
        cam = CameraModel(width=1280, height=720, hfov_deg=90.0, vfov_deg=90.0,
                          pitch_deg=90.0)
        # 90도 화각, 고도 10m -> 한 변 20m
        assert cam.ground_footprint_m2(10.0) == pytest.approx(400.0, rel=1e-9)

    def test_tilted_camera_has_no_simple_footprint(self):
        cam = CameraModel(width=1280, height=720, pitch_deg=45.0)
        assert cam.ground_footprint_m2(10.0) is None


class TestSyntheticPlane:
    def test_matches_camera_model_offsets(self):
        cam = CameraModel(width=1280, height=720, pitch_deg=90.0)
        gp = ground_plane_from_altitude(cam, 12.0)
        assert gp is not None
        px, py = 700, 500
        via_plane = gp.to_world([(px, py)])[0]
        fwd, right = cam.pixel_to_ground_offset(px, py, 12.0)
        assert via_plane[0] == pytest.approx(right, abs=1e-6)
        assert via_plane[1] == pytest.approx(fwd, abs=1e-6)


class TestObliqueCameraDefaults:
    """기본 카메라 각도는 45도(비스듬)다.

    수직 하향(90도)은 두 가지가 깨진다.
      1. 사람이 어깨너비(0.5m)만 보여 10m 고도에서 6.5px — 검출 불가
      2. 발목 좌표(박스 하단 중앙)가 실제 지상 위치와 맞지 않는다
    """

    def test_default_is_oblique_not_nadir(self):
        assert CameraModel(width=640, height=480).pitch_deg == 45.0

    def test_oblique_sees_the_whole_person(self):
        """비스듬히 보면 전신(1.7m), 수직이면 어깨너비(0.5m)만 보인다."""
        oblique = CameraModel(width=640, height=480, pitch_deg=45.0)
        nadir = CameraModel(width=640, height=480, pitch_deg=90.0)
        assert oblique.apparent_px(14.1) > 3 * nadir.apparent_px(14.1)

    def test_oblique_reaches_much_further(self):
        oblique = CameraModel(width=640, height=480, pitch_deg=45.0)
        nadir = CameraModel(width=640, height=480, pitch_deg=90.0)
        assert oblique.max_detection_range_m() > 3 * nadir.max_detection_range_m()

    def test_detection_range_scales_with_input_size(self):
        small = CameraModel(width=320, height=240, pitch_deg=45.0)
        big = CameraModel(width=640, height=480, pitch_deg=45.0)
        assert big.max_detection_range_m() == pytest.approx(
            2 * small.max_detection_range_m(), rel=1e-6)

    def test_smaller_min_pixels_claims_more_range(self):
        lenient = CameraModel(width=640, height=480, min_detect_px=6)
        strict = CameraModel(width=640, height=480, min_detect_px=24)
        assert lenient.max_detection_range_m() == pytest.approx(
            4 * strict.max_detection_range_m(), rel=1e-6)

    def test_top_of_frame_is_further_than_bottom(self):
        cam = CameraModel(width=640, height=480, pitch_deg=45.0)
        assert cam.slant_range_at(80, 10.0) > cam.slant_range_at(400, 10.0)

    def test_slant_range_never_closer_than_the_altitude(self):
        cam = CameraModel(width=640, height=480, pitch_deg=45.0)
        for py in (0, 120, 240, 360, 479):
            r = cam.slant_range_at(py, 10.0)
            if r is not None:
                assert r >= 10.0 - 1e-6

    def test_above_horizon_has_no_range(self):
        cam = CameraModel(width=640, height=480, pitch_deg=20.0)
        assert cam.slant_range_at(0, 10.0) is None

    def test_zero_altitude_has_no_range(self):
        assert CameraModel(width=640, height=480).slant_range_at(240, 0.0) is None
