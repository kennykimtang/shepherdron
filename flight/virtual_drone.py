"""가상 기체 — 실제 GuidanceMission 을 하드웨어 없이 시연 화면에서 돌린다.

시연에서 보여 주고 싶은 것은 '드론이 날아가는 그림'이 아니라 Shepherdron 의
실제 임무 로직이다. 그래서 상태기계를 흉내 내지 않고, flight/mission.py 의
GuidanceMission 을 그대로 쓰고 컨트롤러 자리에 이 가상 기체를 끼운다.

  비전 경보 ──→ GuidanceMission (실제 코드) ──→ VirtualDrone (가상)
                 대기 → 출동 → 안내 → 회수 → 복귀

실내(무GPS) 상대 이동 모드로 동작한다. 기수는 카메라 광축과 같다고 두므로
'기체 기준 오프셋' = '카메라 기준 바닥 좌표 차이' 다. 원점(이륙 지점)은 카메라.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Tuple

from flight.mavlink_controller import VehicleState
from flight.mission import GuidanceConfig, GuidanceMission, MissionState
from hardware.payload import SimulatedPayload

Point = Tuple[float, float]          # (우측 m, 전방 m)

# 시연에 맞게 시간을 줄인 설정. 로직은 실제와 같다.
DEMO_CONFIG = GuidanceConfig(
    cruise_altitude_m=3.0,
    use_body_offset=True,
    arrival_radius_m=0.8,
    hover_duration_s=10.0,
    navigation_timeout_s=60.0,
    retarget_distance_m=1.5,
    retarget_min_interval_s=1.0,
    mission_cooldown_s=15.0,
    min_battery_pct=20,
    retract_timeout_s=15.0,
)

STATE_KO = {
    MissionState.IDLE: "대기",
    MissionState.NAVIGATING: "출동",
    MissionState.HOVERING: "안내",
    MissionState.RETRACTING: "회수",
    MissionState.RETURNING: "복귀",
    MissionState.STANDBY: "수동",
    MissionState.FAILSAFE: "이상",
}
TRACK = [MissionState.IDLE, MissionState.NAVIGATING, MissionState.HOVERING,
         MissionState.RETRACTING, MissionState.RETURNING]


class VirtualDrone:
    """GuidanceMission 이 부르는 컨트롤러 메서드만 갖춘 운동학 모형."""

    def __init__(self, cruise_alt_m: float = 3.0, speed_mps: float = 1.6,
                 climb_mps: float = 1.0):
        self.state = VehicleState(
            connected=True, armed=False, mode="LOITER", relative_alt_m=0.0,
            heading_deg=0.0, groundspeed_ms=0.0, battery_remaining_pct=100,
        )
        self.home: Point = (0.0, 0.0)
        self.pos = [0.0, 0.0]
        self.goal: Optional[Point] = None
        self.cruise_alt = cruise_alt_m
        self.speed = speed_mps
        self.climb = climb_mps
        self.trail: Deque[Point] = deque(maxlen=600)
        self._rtl = False
        self._batt = 100.0

    # ── GuidanceMission 이 쓰는 표면 ─────────────────────
    def is_healthy(self, now=None) -> bool:
        return True

    def preflight_check(self, require_gps=None, now=None):
        return []

    def set_mode(self, mode: str, timeout_s: float = 5.0) -> bool:
        self.state.mode = mode.upper()
        return True

    def goto_body_offset(self, forward_m: float, right_m: float,
                         down_m: float = 0.0):
        self.goal = (self.pos[0] + right_m, self.pos[1] + forward_m)
        self.state.armed = True
        self._rtl = False
        return (forward_m, right_m)

    def return_to_launch(self) -> bool:
        self.goal = self.home
        self._rtl = True
        self.state.mode = "RTL"
        return True

    def distance_to(self, point):
        return None

    def has_arrived(self, *_, **__) -> bool:
        return False

    # ── 시뮬레이션 ───────────────────────────────────────
    @property
    def position(self) -> Point:
        return (self.pos[0], self.pos[1])

    @property
    def flying(self) -> bool:
        return bool(self.state.armed)

    def step(self, dt: float) -> None:
        dt = max(0.0, min(dt, 0.5))
        if not self.state.armed:
            self.state.groundspeed_ms = 0.0
            return
        alt = self.state.relative_alt_m or 0.0
        at_home = math.hypot(self.pos[0] - self.home[0],
                             self.pos[1] - self.home[1]) < 0.15

        # 고도 : 이륙 시 상승, 복귀 후 하강·착륙
        if self._rtl and at_home:
            alt = max(0.0, alt - self.climb * dt)
            if alt <= 0.02:
                self.state.armed = False
                self.state.mode = "LAND"
                self._rtl = False
                self.goal = None
        else:
            alt = min(self.cruise_alt, alt + self.climb * dt)
        self.state.relative_alt_m = alt

        # 수평 이동 : 고도를 어느 정도 확보한 뒤에만
        v = 0.0
        if self.goal is not None and alt > 0.5 * self.cruise_alt:
            dx, dy = self.goal[0] - self.pos[0], self.goal[1] - self.pos[1]
            d = math.hypot(dx, dy)
            if d > 1e-3:
                stepd = min(d, self.speed * dt)
                self.pos[0] += dx / d * stepd
                self.pos[1] += dy / d * stepd
                v = stepd / dt if dt > 0 else 0.0
                self.state.heading_deg = (math.degrees(math.atan2(dx, dy)) + 360) % 360
        self.state.groundspeed_ms = v
        self._batt = max(0.0, self._batt - 0.06 * dt)
        self.state.battery_remaining_pct = int(round(self._batt))
        self.trail.append(self.position)


@dataclass
class _RelTarget:
    forward_m: float
    right_m: float

    @property
    def has_ground_fix(self) -> bool:
        return True


@dataclass
class _Obs:
    """GuidanceMission.update() 가 읽는 필드만 가진 관측."""
    alert_rising_edge: bool
    alert_active: bool
    smoothed_count: int
    target: Optional[_RelTarget]


class DemoMission:
    """비전 관측을 받아 가상 기체 위에서 실제 임무 로직을 돌린다."""

    def __init__(self, config: GuidanceConfig = DEMO_CONFIG):
        self.drone = VirtualDrone(cruise_alt_m=config.cruise_altitude_m)
        self.payload = SimulatedPayload(deploy_duration_s=3.0, retract_duration_s=4.0)
        self.mission = GuidanceMission(self.drone, config, payload=self.payload)
        self.goal_ground: Optional[Point] = None
        self._last: Optional[float] = None
        self._manual = False

    @property
    def state(self) -> MissionState:
        return self.mission.state

    @property
    def state_ko(self) -> str:
        return STATE_KO.get(self.mission.state, self.mission.state.value)

    @property
    def reason(self) -> str:
        return self.mission.reason

    def dispatch(self) -> None:
        """운용자 수동 출동. 다음 update 에서 경보 상승으로 취급한다."""
        self._manual = True

    def update(self, alert_rising: bool, alert_active: bool, count: int,
               hotspot: Optional[Point], now: Optional[float] = None) -> MissionState:
        t = now if now is not None else time.monotonic()
        dt = 0.0 if self._last is None else t - self._last
        self._last = t
        self.drone.step(dt)

        target = None
        if hotspot is not None:
            px, py = self.drone.position
            target = _RelTarget(forward_m=hotspot[1] - py, right_m=hotspot[0] - px)
            self.goal_ground = hotspot

        rising = alert_rising or self._manual
        active = alert_active or self._manual
        self._manual = False
        self.mission.update(_Obs(rising, active, count, target), now=t)
        return self.mission.state
