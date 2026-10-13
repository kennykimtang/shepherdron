"""분리 구조 통합 테스트 — 지상 지각 ↔ 기체 판단.

이 구조의 핵심 위험은 하나다: **비행 중 Wi-Fi 가 끊기면 어떻게 되는가.**
상태기계를 기체에 둔 이유가 여기서 검증된다.
"""
import pytest

from flight.geodesy import GeoPoint, distance_m
from flight.mavlink_controller import SafetyLimits, VehicleState
from flight.mission import GuidanceConfig, GuidanceMission, MissionState
from link.bridge import VisionBridge
from link.protocol import VisionReport
from vision.geometry import CameraModel

HOME = GeoPoint(37.5665, 126.9388, 10.0)


class FakeController:
    def __init__(self):
        self.state = VehicleState(
            connected=True, armed=True, mode="GUIDED",
            lat=HOME.lat, lon=HOME.lon, relative_alt_m=10.0, heading_deg=0.0,
            battery_remaining_pct=90, gps_fix_type=3, satellites=14)
        self.limits = SafetyLimits()
        self.home = HOME
        self.sent = []
        self.rtl_calls = 0
        self.arrived = False

    def is_healthy(self, now=None): return True
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


def build():
    ctl = FakeController()
    bridge = VisionBridge(CameraModel(width=640, height=480, pitch_deg=90.0))
    mission = GuidanceMission(ctl, GuidanceConfig(
        cruise_altitude_m=10.0, navigation_timeout_s=30.0, hover_duration_s=10.0))
    return ctl, bridge, mission


def observation(seq, t, **kw):
    """지상국이 보낸 관측이 기체에 막 도착한 상태."""
    kw.setdefault("target_px", (600, 240))        # 화면 오른쪽 = 우현
    kw.setdefault("frame_w", 640)
    kw.setdefault("frame_h", 480)
    kw.setdefault("alert_active", True)
    r = VisionReport(seq=seq, count=14, **kw)
    r.received_at = t
    return r


class TestGroundToAirPath:
    def test_ground_observation_becomes_a_flight_target(self):
        ctl, bridge, mission = build()
        mi = bridge.convert(observation(1, 0.0, alert_rising_edge=True),
                            ctl.state.relative_alt_m, now=0.0)
        assert mission.update(mi, now=0.0) is MissionState.NAVIGATING
        assert len(ctl.sent) == 1
        assert distance_m(HOME, ctl.sent[0]) > 1.0

    def test_pixel_offset_resolves_to_the_correct_side(self):
        """화면 오른쪽 군중 → 기체 우현(동쪽, 기수 북 기준)으로 가야 한다."""
        ctl, bridge, mission = build()
        mi = bridge.convert(observation(1, 0.0, alert_rising_edge=True),
                            ctl.state.relative_alt_m, now=0.0)
        mission.update(mi, now=0.0)
        assert ctl.sent[0].lon > HOME.lon

    def test_altitude_comes_from_the_aircraft_not_the_ground_station(self):
        """지상국은 고도를 모른다. 기체가 자기 고도로 환산해야 한다."""
        ctl, bridge, mission = build()
        obs = observation(1, 0.0, alert_rising_edge=True)

        ctl.state.relative_alt_m = 10.0
        near = bridge.convert(obs, ctl.state.relative_alt_m, now=0.0)
        ctl.state.relative_alt_m = 30.0
        far = bridge.convert(obs, ctl.state.relative_alt_m, now=0.0)

        assert abs(far.target.right_m) == pytest.approx(3 * abs(near.target.right_m),
                                                        rel=1e-6)


class TestLinkLoss:
    """이 구조를 택한 이유가 여기서 증명된다."""

    def _airborne(self):
        ctl, bridge, mission = build()
        mi = bridge.convert(observation(1, 0.0, alert_rising_edge=True),
                            ctl.state.relative_alt_m, now=0.0)
        mission.update(mi, now=0.0)
        assert mission.state is MissionState.NAVIGATING
        return ctl, bridge, mission

    def test_mission_continues_without_fresh_observations(self):
        """관측이 끊겨도 기체는 마지막 타겟으로 계속 간다."""
        ctl, bridge, mission = self._airborne()
        for t in (1.0, 5.0, 10.0):
            assert mission.update(None, now=t) is MissionState.NAVIGATING

    def test_arrival_still_works_with_the_link_down(self):
        """도달 판정은 기체의 GPS 로 한다 — 지상국이 없어도 된다."""
        ctl, bridge, mission = self._airborne()
        mission.update(None, now=5.0)
        ctl.arrived = True
        assert mission.update(None, now=6.0) is MissionState.HOVERING

    def test_payload_deploys_with_the_link_down(self):
        ctl = FakeController()
        bridge = VisionBridge(CameraModel(width=640, height=480, pitch_deg=90.0))
        fired = []
        mission = GuidanceMission(ctl, GuidanceConfig(cruise_altitude_m=10.0),
                                  on_arrived=lambda m: fired.append(True))
        mission.update(bridge.convert(observation(1, 0.0, alert_rising_edge=True),
                                      10.0, now=0.0), now=0.0)
        ctl.arrived = True
        mission.update(None, now=5.0)
        assert fired == [True]

    def test_timeout_returns_home_if_the_link_never_recovers(self):
        """영영 못 받으면 이동 타임아웃에 걸려 스스로 복귀한다."""
        ctl, bridge, mission = self._airborne()
        assert mission.update(None, now=31.0) is MissionState.RETURNING
        assert ctl.rtl_calls == 1

    def test_stale_observation_is_never_acted_on(self):
        """오래된 관측은 수신기가 내주지 않는다 — bridge 에 None 이 온다."""
        from link.udp import Receiver
        rx = Receiver(VisionReport, port=47697, host="127.0.0.1", stale_after_s=1.0)
        rx._latest = observation(9, 0.0)
        assert rx.latest(now=0.5) is not None
        assert rx.latest(now=3.0) is None

    def test_recovered_link_resumes_retargeting(self):
        ctl, bridge, mission = self._airborne()
        mission.update(None, now=5.0)
        moved = observation(2, 10.0, target_px=(40, 440))   # 군중이 반대편으로
        mission.update(bridge.convert(moved, ctl.state.relative_alt_m, now=10.0),
                       now=10.0)
        assert len(ctl.sent) == 2


class TestLinkCarriesNoCommands:
    """링크는 관측만 나른다. 비행 명령은 들어올 수 없다."""

    def test_vision_report_has_no_command_fields(self):
        fields = set(VisionReport(seq=1).__dict__)
        forbidden = {"arm", "takeoff", "goto", "mode", "disarm", "rtl", "land",
                     "lat", "lon", "command"}
        assert fields & forbidden == set()

    def test_above_horizon_pixel_yields_no_command_at_all(self):
        """지평선 위를 가리키는 픽셀은 지상 교점이 없다. 거리를 지어내지 않는다."""
        bridge = VisionBridge(CameraModel(width=640, height=480, pitch_deg=20.0))
        mi = bridge.convert(observation(1, 0.0, target_px=(320, 5)),
                            altitude_m=10.0, now=0.0)
        assert mi.target.has_ground_fix is False

    def test_a_runaway_report_is_bounded_by_the_radius_clamp(self):
        """지상국이 오작동해도 최악은 '잘못된 군중 위치'이고 반경이 막는다."""
        from flight.geodesy import target_from_body_offset
        from flight.mavlink_controller import MavlinkController

        ctl = MavlinkController(dry_run=True, limits=SafetyLimits(max_radius_m=100.0))
        ctl.home = HOME
        ctl.state = VehicleState(connected=True, armed=True, mode="GUIDED",
                                 lat=HOME.lat, lon=HOME.lon, relative_alt_m=30.0,
                                 heading_deg=0.0, gps_fix_type=3, satellites=14,
                                 last_heartbeat=1.0)
        # 30 m 고도에서 화면 최상단을 가리키면 140 m 앞 지면으로 환산된다
        bridge = VisionBridge(CameraModel(width=640, height=480, pitch_deg=45.0))
        mi = bridge.convert(observation(1, 0.0, target_px=(320, 5)),
                            altitude_m=30.0, now=0.0)
        runaway = target_from_body_offset(HOME, 0.0, mi.target.forward_m,
                                          mi.target.right_m, alt_m=10.0)
        assert distance_m(HOME, runaway) > 100          # 실제로 폭주하는 입력
        assert distance_m(HOME, ctl.goto(runaway)) == pytest.approx(100.0, rel=1e-3)
