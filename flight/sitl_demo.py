"""SITL 데모 — 가상 기체로 유도 임무 전체를 끝까지 돌려본다.

하드웨어 없이 Phase 2 완료 기준("타겟 좌표로 10 m 고도 이동 후 호버링")을
검증하기 위한 실행기다. 비전 대신 가짜 과밀집 경보를 주입한다.

사용법
    터미널 1:  ./scripts/run_sitl.sh
    터미널 2:  python -m flight.sitl_demo
               python -m flight.sitl_demo --forward 40 --right -25
"""
from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from typing import Optional

from flight.geodesy import distance_m
from flight.mavlink_controller import MavlinkController, SafetyLimits
from flight.mission import GuidanceConfig, GuidanceMission, MissionState


@dataclass
class _Target:
    forward_m: float
    right_m: float
    altitude_m: float = 10.0

    @property
    def has_ground_fix(self) -> bool:
        return True


@dataclass
class _Alert:
    """CrowdPipeline.process() 반환값을 흉내낸 가짜 경보."""

    target: _Target
    alert_rising_edge: bool = False
    alert_active: bool = True
    smoothed_count: int = 12


def parse_args():
    p = argparse.ArgumentParser(description="Shepherdron SITL guidance demo")
    p.add_argument("--connect", default="udp:127.0.0.1:14550")
    p.add_argument("--forward", type=float, default=30.0, help="가짜 타겟 전방 거리(m)")
    p.add_argument("--right", type=float, default=20.0, help="가짜 타겟 우현 거리(m)")
    p.add_argument("--altitude", type=float, default=10.0, help="순항 고도(m)")
    p.add_argument("--hover", type=float, default=15.0, help="호버링 유지 시간(s)")
    p.add_argument("--timeout", type=float, default=240.0, help="전체 제한 시간(s)")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(name)-20s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    log = logging.getLogger("shepherdron.sitl")
    a = parse_args()

    ctl = MavlinkController(a.connect, limits=SafetyLimits(max_radius_m=150.0))
    if not ctl.connect(timeout_s=30.0):
        log.error("SITL 에 연결하지 못했습니다. ./scripts/run_sitl.sh 가 떠 있나요?")
        return 1

    log.info("기체 상태를 기다립니다 (GPS fix)…")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        ctl.update()
        if ctl.state.has_gps_fix and ctl.state.position is not None:
            break
        time.sleep(0.5)

    problems = ctl.preflight_check()
    if problems:
        log.error("사전 점검 실패: %s", "; ".join(problems))
        return 1
    log.info("위치 %s  위성 %d  배터리 %s%%", ctl.state.position,
             ctl.state.satellites, ctl.state.battery_remaining_pct)

    if not ctl.set_mode("GUIDED"):
        return 1
    if not ctl.arm():
        return 1
    if not ctl.takeoff(a.altitude):
        return 1

    home = ctl.state.position
    log.info("이륙 완료. 가짜 과밀집 경보를 주입합니다 "
             "(전방 %.0f m, 우현 %.0f m)", a.forward, a.right)

    mission = GuidanceMission(
        ctl,
        GuidanceConfig(cruise_altitude_m=a.altitude, hover_duration_s=a.hover,
                       arrival_radius_m=3.0),
        on_arrived=lambda m: log.info("🎯 목표 도달 — [PHASE 3] 액추에이터 전개 지점"),
        on_complete=lambda m: log.info("✅ 임무 완료 (총 %d회)", m.missions_completed),
        on_failsafe=lambda m, why: log.error("⚠️  페일세이프: %s", why),
    )

    alert = _Alert(_Target(a.forward, a.right, a.altitude), alert_rising_edge=True)
    end = time.monotonic() + a.timeout
    last_log = 0.0

    try:
        while time.monotonic() < end:
            ctl.update()
            state = mission.update(alert)
            alert.alert_rising_edge = False          # 상승 에지는 1회만

            now = time.monotonic()
            if now - last_log >= 2.0:
                st = mission.status()
                d = f"{st.distance_m:6.1f} m" if st.distance_m is not None else "   —  "
                log.info("%-11s dist %s  alt %5.1f m  mode %-8s %s",
                         state.value, d, ctl.state.relative_alt_m or 0.0,
                         ctl.state.mode, "ARMED" if ctl.state.armed else "disarmed")
                last_log = now

            if state is MissionState.IDLE and mission.missions_completed:
                log.info("데모 종료 — 홈에서 %.1f m",
                         distance_m(home, ctl.state.position) if ctl.state.position else -1)
                return 0
            if state is MissionState.FAILSAFE:
                return 1
            time.sleep(0.2)

        log.error("제한 시간 초과")
        return 1
    except KeyboardInterrupt:
        log.warning("중단 — RTL")
        ctl.return_to_launch()
        return 1
    finally:
        ctl.close()


if __name__ == "__main__":
    raise SystemExit(main())
