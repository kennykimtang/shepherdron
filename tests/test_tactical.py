"""전술 지도 투영 · 유도 방향 테스트."""
import math

import pytest

from vision.detector import DetectionResult
from vision.tactical import (
    bearing_name,
    build_picture,
    evacuation_bearing,
    focal_px,
    ground_density,
    in_view,
    project,
)

W, H, HFOV = 1280, 720, 70.0


def person_at(right_m, forward_m):
    """바닥 좌표에 선 사람을 영상 박스로 역산한다."""
    f = focal_px(W, HFOV)
    h = f * 1.7 / forward_m
    x = W / 2 + right_m / forward_m * f
    y2 = 600
    return (int(x - h * 0.17), int(y2 - h), int(x + h * 0.17), y2), (int(x), y2)


def det(points):
    boxes, feet = zip(*[person_at(r, f) for r, f in points]) if points else ((), ())
    return DetectionResult(boxes=list(boxes), confidences=[0.9] * len(points),
                           foot_points=list(feet), track_ids=[None] * len(points),
                           count=len(points))


def test_projection_recovers_ground_position():
    pts = project(det([(1.5, 6.0), (-2.0, 4.0)]), W, H, HFOV)
    assert pts[0] == pytest.approx((1.5, 6.0), abs=0.15)
    assert pts[1] == pytest.approx((-2.0, 4.0), abs=0.15)


def test_center_of_frame_is_straight_ahead():
    (r, f), = project(det([(0.0, 5.0)]), W, H, HFOV)
    assert abs(r) < 0.05 and f == pytest.approx(5.0, abs=0.1)


def test_ground_density_of_lattice_matches_truth():
    pts = [(i * 0.7, 5 + j * 0.7) for i in range(-5, 6) for j in range(-5, 6)]
    assert ground_density((0.0, 5.0), pts, 0.75) == pytest.approx(1 / 0.49, rel=0.2)


def test_hotspot_is_the_dense_cluster():
    cluster = [(1.0 + 0.4 * (i % 3), 6.0 + 0.4 * (i // 3)) for i in range(9)]
    loose = [(-3.0, 4.0), (-2.5, 8.0)]
    pic = build_picture(det(cluster + loose), W, H, hfov_deg=HFOV)
    hx, hy = pic.hotspot
    assert 0.8 < hx < 2.2 and 5.8 < hy < 7.2


def test_evacuation_points_away_from_the_crowd():
    """오른쪽에 사람이 몰려 있으면 왼쪽으로 유도해야 한다."""
    crowd = [(0.5 + 0.45 * i, 6.0 + 0.45 * j) for i in range(5) for j in range(-2, 3)]
    ev = evacuation_bearing(crowd, (0.5, 6.0), 0.75, HFOV, 12.0)
    assert ev is not None
    assert 180 < ev.bearing_deg < 360            # 좌측 반구
    assert ev.density_there < ground_density((0.5, 6.0), crowd, 0.75)


def test_evacuation_never_points_out_of_view():
    crowd = [(0.0, 5.0 + 0.4 * k) for k in range(6)]
    ev = evacuation_bearing(crowd, (0.0, 6.0), 0.75, HFOV, 10.0)
    assert ev is not None
    assert in_view(ev.point, HFOV, 10.0)


def test_no_people_gives_an_empty_picture():
    pic = build_picture(det([]), W, H)
    assert pic.people == [] and pic.hotspot is None and pic.evacuation is None


@pytest.mark.parametrize("deg,name", [(0, "전방"), (90, "우측"), (180, "후방"),
                                      (270, "좌측"), (225, "좌후방"), (350, "전방")])
def test_bearing_names(deg, name):
    assert bearing_name(deg) == name


def test_in_view_rejects_behind_and_outside():
    assert not in_view((0.0, -1.0), HFOV, 10)
    assert not in_view((10.0, 2.0), HFOV, 20)
    assert not in_view((0.0, 15.0), HFOV, 10)
    assert in_view((0.0, 5.0), HFOV, 10)
