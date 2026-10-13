"""지상-기체 링크 테스트.

가장 중요한 검증: **링크가 끊겼을 때 오래된 관측으로 기체를 움직이지 않는가.**
"""
import time

import pytest

from link.bridge import VisionBridge
from link.protocol import PROTOCOL_VERSION, TelemetryReport, VisionReport
from link.udp import Receiver, Sender
from vision.geometry import CameraModel


def report(seq=1, **kw):
    kw.setdefault("target_px", (320, 240))
    kw.setdefault("frame_w", 640)
    kw.setdefault("frame_h", 480)
    return VisionReport(seq=seq, **kw)


class TestProtocol:
    def test_roundtrip_preserves_fields(self):
        r = report(seq=7, alert_active=True, count=12, peak_density=3.4,
                   calibrated=True, busiest_cell=(1, 2))
        back = VisionReport.from_json(r.to_json(), received_at=0.0)
        assert back.seq == 7 and back.count == 12
        assert back.peak_density == 3.4 and back.busiest_cell == (1, 2)
        assert back.target_px == (320, 240)

    def test_tuples_survive_json(self):
        back = VisionReport.from_json(report().to_json(), received_at=0.0)
        assert isinstance(back.target_px, tuple)

    def test_version_mismatch_is_rejected(self):
        raw = report().to_json().replace(
            f'"version":{PROTOCOL_VERSION}'.encode(), b'"version":99')
        with pytest.raises(ValueError):
            VisionReport.from_json(raw)

    def test_age_uses_local_arrival_not_sender_clock(self):
        """송신 측 시계를 믿지 않는다 — NTP 동기화 없이도 맞아야 한다."""
        r = VisionReport.from_json(report().to_json(), received_at=100.0)
        assert r.age(102.5) == pytest.approx(2.5)

    def test_age_is_infinite_before_arrival(self):
        assert report().age() == float("inf")

    def test_missing_target_is_flagged(self):
        assert VisionReport(seq=1).has_target is False
        assert report().has_target is True

    def test_telemetry_roundtrip(self):
        t = TelemetryReport(seq=3, mission_state="NAVIGATING", armed=True,
                            relative_alt_m=10.5, battery_pct=78)
        back = TelemetryReport.from_json(t.to_json(), received_at=0.0)
        assert back.mission_state == "NAVIGATING" and back.battery_pct == 78

    def test_wire_format_stays_small(self):
        """프레임마다 보내므로 작아야 한다."""
        assert len(report(alert_active=True, count=20, peak_density=4.1).to_json()) < 400


class TestFromPipeline:
    def test_maps_pipeline_result(self):
        class Cell:
            row, col = 2, 1

        class Analysis:
            total_persons = 11
            peak_density = 4.2
            calibrated = True
            max_dense_cell = Cell()
            target_point = (100, 200)

        class Target:
            pixel = (300, 400)

        class Result:
            analysis = Analysis()
            target = Target()
            alert_active = True
            alert_rising_edge = True
            smoothed_count = 10
            fps = 23.456

        r = VisionReport.from_pipeline(5, Result(), (480, 640, 3))
        assert r.seq == 5 and r.count == 10 and r.raw_count == 11
        assert r.target_px == (300, 400)          # TargetFix 를 우선
        assert (r.frame_w, r.frame_h) == (640, 480)
        assert r.busiest_cell == (2, 1)
        assert r.fps == 23.5

    def test_falls_back_to_analysis_target_point(self):
        class Analysis:
            total_persons = 3
            peak_density = None
            calibrated = False
            max_dense_cell = None
            target_point = (50, 60)

        class Result:
            analysis = Analysis()
            target = None
            alert_active = False
            alert_rising_edge = False
            smoothed_count = 3
            fps = 10.0

        assert VisionReport.from_pipeline(1, Result(), (480, 640, 3)).target_px == (50, 60)


class TestBridge:
    def setup_method(self):
        self.bridge = VisionBridge(CameraModel(width=640, height=480, pitch_deg=90.0))

    def _fresh(self, **kw):
        r = report(**kw)
        r.received_at = 100.0
        return r

    def test_no_report_means_no_input(self):
        assert self.bridge.convert(None, altitude_m=10.0) is None

    def test_centre_target_at_nadir_is_directly_below(self):
        mi = self.bridge.convert(self._fresh(), altitude_m=10.0, now=100.0)
        assert mi.target.has_ground_fix
        assert mi.target.forward_m == pytest.approx(0.0, abs=1e-6)
        assert mi.target.right_m == pytest.approx(0.0, abs=1e-6)

    def test_without_altitude_there_is_no_ground_fix(self):
        """고도를 모르면 거리를 모른다. 추정해서 기체를 보내면 안 된다."""
        mi = self.bridge.convert(self._fresh(), altitude_m=None, now=100.0)
        assert mi.target.has_ground_fix is False

    def test_zero_altitude_is_treated_as_unknown(self):
        mi = self.bridge.convert(self._fresh(), altitude_m=0.0, now=100.0)
        assert mi.target.has_ground_fix is False

    def test_right_of_frame_maps_to_starboard(self):
        mi = self.bridge.convert(self._fresh(target_px=(600, 240)),
                                 altitude_m=10.0, now=100.0)
        assert mi.target.right_m > 0

    def test_bottom_of_frame_maps_behind_at_nadir(self):
        mi = self.bridge.convert(self._fresh(target_px=(320, 460)),
                                 altitude_m=10.0, now=100.0)
        assert mi.target.forward_m < 0

    def test_camera_adopts_reported_frame_size(self):
        """지상국이 다른 해상도로 추론하면 초점거리가 틀려 방위각이 통째로 잘못된다."""
        self.bridge.convert(self._fresh(frame_w=1920, frame_h=1080,
                                        target_px=(960, 540)),
                            altitude_m=10.0, now=100.0)
        assert (self.bridge.camera.width, self.bridge.camera.height) == (1920, 1080)

    def test_report_without_target_still_carries_the_alert(self):
        r = VisionReport(seq=1, alert_active=True, count=9)
        r.received_at = 100.0
        mi = self.bridge.convert(r, altitude_m=10.0, now=100.0)
        assert mi.target is None and mi.alert_active is True

    def test_link_age_is_passed_through(self):
        mi = self.bridge.convert(self._fresh(), altitude_m=10.0, now=101.5)
        assert mi.link_age_s == pytest.approx(1.5)


class TestUdpTransport:
    def setup_method(self):
        self.rx = Receiver(VisionReport, port=47699, host="127.0.0.1",
                           stale_after_s=0.6).start()
        self.tx = Sender("127.0.0.1", 47699)

    def teardown_method(self):
        self.rx.stop(); self.tx.close()

    def _settle(self, s=0.25):
        time.sleep(s)

    def test_latest_message_wins(self):
        for i in range(1, 4):
            self.tx.send(report(seq=i, count=i * 10))
        self._settle()
        assert self.rx.latest().count == 30

    def test_late_arriving_old_packet_is_dropped(self):
        """UDP 는 순서를 보장하지 않는다. 뒤늦게 온 옛 관측을 쓰면 안 된다."""
        self.tx.send(report(seq=5, count=50))
        self._settle()
        self.tx.send(report(seq=2, count=999))
        self._settle()
        assert self.rx.latest().count == 50
        assert self.rx.dropped_old == 1

    def test_stale_message_is_withheld(self):
        """링크가 끊기면 오래된 관측을 내주지 않는다 — 이게 안전의 핵심."""
        self.tx.send(report(seq=1))
        self._settle()
        assert self.rx.latest() is not None
        time.sleep(0.7)
        assert self.rx.latest() is None
        assert self.rx.is_live is False

    def test_malformed_datagram_does_not_kill_the_receiver(self):
        self.tx._sock.sendto(b"not json at all", self.tx.addr)
        self._settle()
        self.tx.send(report(seq=1, count=7))
        self._settle()
        assert self.rx.latest().count == 7
        assert self.rx.dropped_bad == 1

    def test_last_seen_is_infinite_before_first_message(self):
        assert self.rx.last_seen() == float("inf")

    def test_sender_tolerates_no_listener(self):
        dead = Sender("127.0.0.1", 47698)
        assert dead.send(report()) is True       # UDP 는 상대 부재를 모른다
        dead.close()


class TestMessageContract:
    """udp.Receiver 는 모든 메시지가 seq 와 age() 를 갖는다고 가정한다.

    TelemetryReport 에 age() 가 없어 지상국이 텔레메트리를 받는 순간
    죽은 적이 있다. 두 메시지 모두 계약을 지키는지 확인한다.
    """

    @pytest.mark.parametrize("cls", [VisionReport, TelemetryReport])
    def test_has_seq_and_age(self, cls):
        m = cls.from_json(cls(seq=4).to_json(), received_at=10.0)
        assert m.seq == 4
        assert m.age(12.5) == pytest.approx(2.5)
        assert cls(seq=1).age() == float("inf")

    @pytest.mark.parametrize("cls", [VisionReport, TelemetryReport])
    def test_survives_the_receiver_path(self, cls):
        rx = Receiver(cls, port=47696, host="127.0.0.1", stale_after_s=5.0).start()
        tx = Sender("127.0.0.1", 47696)
        try:
            tx.send(cls(seq=11))
            time.sleep(0.25)
            assert rx.latest() is not None and rx.latest().seq == 11
        finally:
            rx.stop(); tx.close()
