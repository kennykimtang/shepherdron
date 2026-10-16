"""현장 투입 전 점검 — 설정 정합성과 세션 기록.

잘못된 설정은 조용히 잘못된 판단을 만든다. 예외도 안 나고 그냥 틀린다.
그리고 사고가 나면 왜 그랬는지 재구성할 수단이 있어야 한다.
"""
import json
from pathlib import Path

import pytest

from config import ConfigError, VisionConfig, assert_valid, summary, validate
from flight.mavlink_controller import SafetyLimits, VehicleState
from flight.session_log import NullSessionLog, SessionLog


class TestConfigValidation:
    def test_defaults_are_flyable(self):
        assert validate(VisionConfig()) == []

    def test_inverted_density_thresholds_are_caught(self):
        """경고가 위험보다 높으면 WARNING 단계가 영영 나오지 않는다."""
        c = VisionConfig()
        c.density_warn, c.density_danger = 5.0, 2.0
        assert any("DENSITY_WARN" in p for p in validate(c))

    def test_inverted_grid_thresholds_are_caught(self):
        c = VisionConfig()
        c.grid_warning_threshold, c.grid_danger_threshold = 9, 3
        assert any("GRID_WARN" in p for p in validate(c))

    @pytest.mark.parametrize("pitch", [0.0, -10.0, 120.0])
    def test_impossible_camera_pitch_is_caught(self, pitch):
        c = VisionConfig()
        c.camera_pitch_deg = pitch
        assert any("CAMERA_PITCH_DEG" in p for p in validate(c))

    def test_nadir_is_allowed_though_discouraged(self):
        c = VisionConfig()
        c.camera_pitch_deg = 90.0
        assert validate(c) == []

    def test_zero_fov_is_caught(self):
        """화각이 0이면 모든 거리 계산이 무한대가 된다."""
        c = VisionConfig()
        c.hfov_deg = 0.0
        assert any("화각" in p for p in validate(c))

    def test_imgsz_must_be_a_multiple_of_32(self):
        c = VisionConfig()
        c.imgsz = 500
        assert any("YOLO_IMGSZ" in p for p in validate(c))

    def test_too_short_alert_window_is_caught(self):
        """창이 짧으면 한 프레임 오검출이 그대로 비행 명령이 된다."""
        c = VisionConfig()
        c.alert_window = 2
        assert any("ALERT_WINDOW" in p for p in validate(c))

    def test_inverted_hysteresis_is_caught(self):
        c = VisionConfig()
        c.alert_on_ratio, c.alert_off_ratio = 0.2, 0.8
        assert any("히스테리시스" in p for p in validate(c))

    def test_tiny_min_detect_px_is_caught(self):
        c = VisionConfig()
        c.min_detect_px = 1
        assert any("MIN_DETECT_PX" in p for p in validate(c))

    def test_assert_valid_raises_with_every_reason(self):
        c = VisionConfig()
        c.imgsz, c.camera_pitch_deg = 500, 0.0
        with pytest.raises(ConfigError) as exc:
            assert_valid(c)
        assert "YOLO_IMGSZ" in str(exc.value) and "CAMERA_PITCH_DEG" in str(exc.value)

    def test_summary_lists_every_field(self):
        text = summary(VisionConfig())
        for key in ("camera_pitch_deg", "imgsz", "density_danger", "alert_window"):
            assert key in text


class TestSafetyLimitValidation:
    def test_defaults_are_sane(self):
        assert SafetyLimits().validate() == []

    def test_inverted_altitude_band_is_caught(self):
        """모든 고도가 거부되어 goto 가 영영 나가지 않는다."""
        assert any("min_altitude_m" in p
                   for p in SafetyLimits(min_altitude_m=50, max_altitude_m=10).validate())

    def test_zero_radius_is_caught(self):
        assert any("max_radius_m" in p for p in SafetyLimits(max_radius_m=0).validate())

    def test_impossible_battery_threshold_is_caught(self):
        assert any("min_battery_pct" in p
                   for p in SafetyLimits(min_battery_pct=150).validate())


class TestSessionLog:
    def test_writes_one_json_object_per_line(self, tmp_path):
        with SessionLog(directory=str(tmp_path)) as s:
            s.mission_state("IDLE", "NAVIGATING", "과밀집 13명")
            s.warning("타겟 반경 밖", requested_m=430)
            path = s.path
        lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
        records = [json.loads(ln) for ln in lines]
        kinds = [r["kind"] for r in records]
        assert kinds == ["session_start", "mission_state", "warning", "session_end"]

    def test_korean_text_is_readable_not_escaped(self):
        with SessionLog(directory="/tmp/shepherdron_test_log") as s:
            s.warning("관측 끊김")
            path = s.path
        assert "관측 끊김" in Path(path).read_text(encoding="utf-8")
        Path(path).unlink()

    def test_records_survive_a_crash_mid_session(self, tmp_path):
        """전원이 끊겨도 그때까지 쓴 줄은 남아야 한다 — close 없이 읽는다."""
        s = SessionLog(directory=str(tmp_path)).open()
        s.mission_state("IDLE", "NAVIGATING")
        assert "NAVIGATING" in Path(s.path).read_text(encoding="utf-8")

    def test_vehicle_snapshot_captures_what_matters(self, tmp_path):
        with SessionLog(directory=str(tmp_path)) as s:
            s.vehicle(VehicleState(mode="GUIDED", armed=True, lat=37.5, lon=127.0,
                                   relative_alt_m=10.0, battery_remaining_pct=80,
                                   satellites=15),
                      payload_state="DEPLOYED", link_age_s=0.2)
            path = s.path
        rec = [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines()
               if json.loads(ln)["kind"] == "vehicle"][0]
        assert rec["mode"] == "GUIDED" and rec["payload"] == "DEPLOYED"
        assert rec["battery"] == 80 and rec["link_age_s"] == 0.2

    def test_timestamps_are_relative_and_monotonic(self, tmp_path):
        with SessionLog(directory=str(tmp_path)) as s:
            for i in range(4):
                s.event("tick", i=i)
            path = s.path
        ts = [json.loads(ln)["t"] for ln in
              Path(path).read_text(encoding="utf-8").splitlines()]
        assert ts[0] == 0.0
        assert all(b >= a for a, b in zip(ts, ts[1:]))

    def test_writing_before_open_is_a_no_op(self):
        SessionLog().event("ignored")      # 예외가 나면 안 된다

    def test_null_log_satisfies_the_same_surface(self, tmp_path):
        n = NullSessionLog()
        with n:
            n.mission_state("A", "B")
            n.vision(None)
            n.vehicle(VehicleState())
            n.warning("x")
        assert n.path is None
