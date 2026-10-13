"""기체 온보드 에이전트 — 판단과 구동을 담당한다.

역할
    · 지상국의 관측(VisionReport)을 받는다
    · 자기 고도로 픽셀 → 지상 미터를 환산한다
    · GuidanceMission 상태기계를 돌려 Pixhawk 에 비행 명령을 낸다
    · 도달하면 페이로드(액추에이터·LED·음성)를 전개한다
    · 텔레메트리를 지상국으로 돌려보낸다

**링크가 끊겨도 기체는 혼자 안전하게 동작한다.**
    관측이 끊기면 마지막 타겟까지 간 뒤 이동 타임아웃에 걸려 RTL 한다.
    상태기계와 페일세이프가 전부 여기 있기 때문이다.

사용법
    python shepherdron_pi.py --fc /dev/ttyUSB0
    python shepherdron_pi.py --fc udp:127.0.0.1:14550 --dry-run    # SITL/로컬 검증
"""
from __future__ import annotations

import argparse
import logging
import time

from config import VisionConfig
from flight.mavlink_controller import MavlinkController, SafetyLimits
from flight.mission import GuidanceConfig, GuidanceMission, MissionState
from link import Receiver, Sender, TelemetryReport, VisionBridge, VisionReport
from vision.geometry import CameraModel

log = logging.getLogger("shepherdron.pi")


def parse_args():
    p = argparse.ArgumentParser(description="Shepherdron onboard agent (decision + actuation)")
    p.add_argument("--fc", default="/dev/ttyUSB0", help="비행제어기 연결 (시리얼 또는 udp:...)")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--ground", default="", help="지상국 주소 (비우면 수신한 곳으로 회신 안 함)")
    p.add_argument("--vision-port", type=int, default=47600)
    p.add_argument("--telemetry-port", type=int, default=47601)
    p.add_argument("--altitude", type=float, default=10.0, help="순항 고도(m)")
    p.add_argument("--max-radius", type=float, default=100.0, help="홈 기준 최대 반경(m)")
    p.add_argument("--hover", type=float, default=30.0, help="안내 유지 시간(s)")
    p.add_argument("--stale-after", type=float, default=2.0,
                   help="이 시간이 지난 관측은 없는 것으로 본다(s)")
    p.add_argument("--dry-run", action="store_true", help="실제 전송 없이 로그만")
    return p.parse_args()


def deploy_payload(mission: GuidanceMission) -> None:
    """도달 시 호출. Phase 3 기구부가 여기에 붙는다 (#8, #10, #11)."""
    log.info("🎯 목표 도달 — 페이로드 전개")
    log.info("   [#8]  액추에이터 전개   GPIO13 PWM + GPIO6 DIR")
    log.info("   [#10] LED 방향 유도     GPIO10 SPI0")
    log.info("   [#11] 음성 안내         I2S GPIO18/19/21")
    # from hardware.actuator import deploy; deploy()
    # from hardware.indicators import guide_pattern, announce; ...


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(name)-18s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    a = parse_args()
    cfg = VisionConfig()

    print("=" * 70)
    print("  🛰️  SHEPHERDRON — 기체 온보드 에이전트 (판단 + 구동)")
    print("=" * 70)
    print(f"  * 비행제어기    : {a.fc}")
    print(f"  * 관측 수신     : 0.0.0.0:{a.vision_port}  (stale > {a.stale_after}s 무시)")
    print(f"  * 순항 고도     : {a.altitude:.0f} m   반경 제한 {a.max_radius:.0f} m")
    print(f"  * 모드          : {'DRY-RUN (명령 미전송)' if a.dry_run else '실제 비행'}")
    print("=" * 70)

    ctl = MavlinkController(a.fc, baud=a.baud, dry_run=a.dry_run,
                            limits=SafetyLimits(max_radius_m=a.max_radius))
    if not ctl.connect(timeout_s=30.0):
        log.error("비행제어기에 연결하지 못했습니다")
        return 1

    bridge = VisionBridge(CameraModel(
        width=cfg.capture_width, height=cfg.capture_height,
        hfov_deg=cfg.hfov_deg, vfov_deg=cfg.vfov_deg,
        pitch_deg=cfg.camera_pitch_deg))

    mission = GuidanceMission(
        ctl,
        GuidanceConfig(cruise_altitude_m=a.altitude, hover_duration_s=a.hover),
        on_arrived=deploy_payload,
        on_complete=lambda m: log.info("✅ 임무 완료 (누적 %d회)", m.missions_completed),
        on_failsafe=lambda m, why: log.error("⚠️  페일세이프: %s", why),
    )

    rx = Receiver(VisionReport, port=a.vision_port, stale_after_s=a.stale_after).start()
    tx = Sender(a.ground, a.telemetry_port) if a.ground else None

    seq = 0
    last_telem = 0.0
    warned_link = False

    try:
        while True:
            ctl.update()
            report = rx.latest()

            # 관측이 끊겨도 상태기계는 계속 돈다 — 타임아웃/페일세이프가 여기 있다
            if report is None and not warned_link and mission.state is not MissionState.IDLE:
                log.warning("관측 끊김 (%.1fs) — 마지막 타겟으로 계속, "
                            "이동 타임아웃 시 RTL", rx.last_seen())
                warned_link = True
            elif report is not None:
                warned_link = False

            mission_input = bridge.convert(report, ctl.state.relative_alt_m)
            mission.update(mission_input)

            now = time.monotonic()
            if tx is not None and now - last_telem >= 0.5:
                seq += 1
                s = ctl.state
                tx.send(TelemetryReport(
                    seq=seq, mission_state=mission.state.value, mode=s.mode,
                    armed=s.armed, lat=s.lat, lon=s.lon,
                    relative_alt_m=s.relative_alt_m, heading_deg=s.heading_deg,
                    battery_pct=s.battery_remaining_pct, satellites=s.satellites,
                    vision_age_s=round(rx.last_seen(), 2) if rx.received else None,
                ))
                last_telem = now

            time.sleep(0.05)

    except KeyboardInterrupt:
        log.warning("중단 — 비행 중이면 RTL")
        if mission.state not in (MissionState.IDLE, MissionState.FAILSAFE):
            mission.abort("운용자 중단")
        return 0
    finally:
        rx.stop()
        if tx is not None:
            tx.close()
        ctl.close()


if __name__ == "__main__":
    raise SystemExit(main())
