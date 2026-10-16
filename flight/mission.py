"""유도 임무 상태기계 — 비전 판단을 비행 명령으로 잇는다.

CrowdPipeline 이 내는 PipelineResult 를 받아 기체를 과밀집 지점으로 보내고,
도달하면 전개 훅을 호출한 뒤 복귀시킨다.

    IDLE ─경보─> NAVIGATING ─도달─> HOVERING ─유지시간─> RETRACTING ─접힘─> RETURNING
      ^              │                 │                    │                 │
      └──────────────┴─────────────────┴────────────────────┴─────────────────┘
                         실패/페일세이프 시 FAILSAFE

**RETRACTING 은 생략할 수 없다.** 600 mm 구조물을 내린 채로 복귀하면 착륙
자체가 안 된다. 접혔음을 확인하기 전에는 RTL 을 걸지 않는다.

**조종사가 우선이다.** 비행 모드가 임무가 기대하는 값에서 벗어나면 — 즉
조종기로 수동 전환하면 — 즉시 STANDBY 로 물러나 비행 명령을 일체 내지
않는다. 조종권을 되찾아가는 자동화는 수동 개입 장치를 무용지물로 만든다.

설계 원칙
  · 상태 전이는 전부 명시적이다. "아마 도착했겠지" 로 다음 단계로 넘어가지 않는다.
  · 링크 끊김·배터리 부족은 어느 상태에서든 FAILSAFE 로 간다.
  · 군중이 이동하면 재조준하되, 명령 폭주를 막기 위해 최소 간격을 둔다.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from flight.geodesy import GeoPoint, distance_m, target_from_body_offset
from flight.mavlink_controller import MavlinkController
from hardware.payload import NullPayload, Payload, PayloadState

log = logging.getLogger("shepherdron.mission")


class MissionState(str, Enum):
    IDLE = "IDLE"                 # 대기 — 경보를 기다린다
    NAVIGATING = "NAVIGATING"     # 과밀집 지점으로 이동 중
    HOVERING = "HOVERING"         # 도달, 안내 수행 중
    RETRACTING = "RETRACTING"     # 구조물 접는 중 — 접히기 전에는 복귀하지 않는다
    RETURNING = "RETURNING"       # 복귀 중
    STANDBY = "STANDBY"           # 조종사가 수동 전환 — 임무는 일체 명령하지 않는다
    FAILSAFE = "FAILSAFE"         # 이상 — 더 이상 임무를 수행하지 않는다


@dataclass
class GuidanceConfig:
    cruise_altitude_m: float = 10.0       # 유도 비행 고도 (ROADMAP 완료 기준)
    arrival_radius_m: float = 2.0         # 이 안에 들면 도달로 본다
    hover_duration_s: float = 30.0        # 안내를 유지하는 시간
    navigation_timeout_s: float = 90.0    # 이 시간 안에 못 가면 포기하고 복귀
    retarget_distance_m: float = 5.0      # 타겟이 이만큼 움직이면 재조준
    retarget_min_interval_s: float = 2.0  # 재조준 명령 최소 간격
    mission_cooldown_s: float = 60.0      # 임무 종료 후 새 경보를 무시하는 시간
    min_battery_pct: int = 30             # 이 아래면 새 임무를 시작하지 않는다
    retract_timeout_s: float = 25.0       # 이 안에 못 접으면 이상으로 본다


@dataclass
class MissionStatus:
    state: MissionState = MissionState.IDLE
    target: Optional[GeoPoint] = None
    distance_m: Optional[float] = None
    elapsed_s: float = 0.0
    reason: str = ""
    missions_completed: int = 0


# 각 임무 상태에서 기체가 있어야 할 비행 모드.
# 여기서 벗어나면 조종사가 개입한 것으로 본다.
EXPECTED_MODES = {
    MissionState.NAVIGATING: {"GUIDED"},
    MissionState.HOVERING: {"GUIDED"},
    MissionState.RETRACTING: {"GUIDED"},
    MissionState.RETURNING: {"RTL", "LAND", "GUIDED", "AUTO"},
}


class GuidanceMission:
    def __init__(
        self,
        controller: MavlinkController,
        config: Optional[GuidanceConfig] = None,
        payload: Optional[Payload] = None,
        on_arrived: Optional[Callable[["GuidanceMission"], None]] = None,
        on_complete: Optional[Callable[["GuidanceMission"], None]] = None,
        on_failsafe: Optional[Callable[["GuidanceMission", str], None]] = None,
    ):
        self.ctl = controller
        self.cfg = config or GuidanceConfig()
        # 페이로드를 주지 않으면 "달려 있지 않은 기체"로 본다 — 기구부가
        # 완성되기 전에도 비행 로직을 그대로 돌릴 수 있어야 한다.
        self.payload: Payload = payload or NullPayload()
        self.on_arrived = on_arrived          # Phase 3: 액추에이터 전개 + LED/음성
        self.on_complete = on_complete
        self.on_failsafe = on_failsafe

        self.state = MissionState.IDLE
        self.target: Optional[GeoPoint] = None
        self.reason = ""
        self.missions_completed = 0

        # 0.0 은 유효한 시각이므로 sentinel 로 쓰면 안 된다 (falsy 검사 금지)
        self._entered_at: Optional[float] = None
        self._last_goto_at: Optional[float] = None
        self._cooldown_until = 0.0

    # ─────────────────────────── 상태 전이 ───────────────────────────
    def _enter(self, state: MissionState, now: float, reason: str = "") -> None:
        if state == self.state:
            return
        log.info("state %s -> %s%s", self.state.value, state.value,
                 f"  ({reason})" if reason else "")
        self.state = state
        self._entered_at = now
        self.reason = reason

    def _fail(self, now: float, reason: str) -> None:
        self._enter(MissionState.FAILSAFE, now, reason)
        log.error("failsafe: %s", reason)
        # 접힘을 기다릴 여유는 없지만, 명령은 걸어 두는 편이 낫다
        if not self.payload.is_stowed:
            log.error("페이로드가 전개 상태다 — 수축 명령 후 RTL. "
                      "착륙 전 운용자 확인 필요")
            self._payload_retract(now)
        self.ctl.return_to_launch()
        if self.on_failsafe:
            self.on_failsafe(self, reason)

    def _operator_has_control(self) -> bool:
        """조종사가 수동 모드로 전환했는가.

        GUIDED 에서는 스틱 입력이 무시되므로, 조종사가 개입하려면 조종기의
        모드 스위치를 올려야 한다. 따라서 비행 모드가 바뀐 것이 곧 개입 신호다.
        """
        expected = EXPECTED_MODES.get(self.state)
        if expected is None:                   # IDLE / STANDBY / FAILSAFE
            return False
        mode = self.ctl.state.mode
        if not mode or mode == "UNKNOWN":      # 아직 모드를 못 읽었다
            return False
        return mode not in expected

    def _stand_down(self, now: float) -> None:
        """조종권을 넘기고 물러난다. 비행 명령은 일체 내지 않는다."""
        mode = self.ctl.state.mode
        self._enter(MissionState.STANDBY, now, f"조종사 수동 전환 ({mode})")
        log.warning("조종사가 %s 로 전환 — 임무 중단. 비행 명령을 내지 않는다", mode)
        # 구조물 수축은 비행 제어와 충돌하지 않으므로 접어 둔다 (착륙 대비)
        if not self.payload.is_stowed:
            log.warning("구조물이 전개 상태 — 수축 명령만 건다")
            self._payload_retract(now)

    def _standby(self, result, t: float) -> None:
        """조종사가 조종 중. 착륙(disarm)하면 대기 상태로 돌아간다."""
        if not self.ctl.state.armed:
            self._cooldown_until = t + self.cfg.mission_cooldown_s
            self.target = None
            self._enter(MissionState.IDLE, t, "조종사 착륙 — 대기 복귀")

    def _payload_call(self, action: str, now: float) -> None:
        fn = getattr(self.payload, action)
        try:
            fn(now=now)
        except TypeError:
            fn()

    def _payload_deploy(self, now: float) -> None:
        self._payload_call("deploy", now)

    def _payload_retract(self, now: float) -> None:
        self._payload_call("retract", now)

    def elapsed(self, now: float) -> float:
        return 0.0 if self._entered_at is None else now - self._entered_at

    def status(self, now: Optional[float] = None) -> MissionStatus:
        t = now if now is not None else time.monotonic()
        d = self.ctl.distance_to(self.target) if self.target else None
        return MissionStatus(self.state, self.target, d, self.elapsed(t),
                             self.reason, self.missions_completed)

    # ─────────────────────────── 메인 루프 ───────────────────────────
    def update(self, result=None, now: Optional[float] = None) -> MissionState:
        """매 프레임 호출한다. result 는 CrowdPipeline.process() 의 반환값."""
        t = now if now is not None else time.monotonic()
        self.payload.update(t)

        # 조종사 개입이 최우선이다. 링크·배터리보다 먼저 본다.
        if self._operator_has_control():
            self._stand_down(t)
            return self.state

        # 어느 상태에서든 링크와 배터리를 먼저 본다
        if self.state not in (MissionState.IDLE, MissionState.FAILSAFE,
                              MissionState.STANDBY):
            if not self.ctl.is_healthy(t):
                self._fail(t, "heartbeat 끊김")
                return self.state
            pct = self.ctl.state.battery_remaining_pct
            if pct is not None and pct < self.cfg.min_battery_pct:
                self._fail(t, f"배터리 {pct}%")
                return self.state

        handler = {
            MissionState.IDLE: self._idle,
            MissionState.NAVIGATING: self._navigating,
            MissionState.HOVERING: self._hovering,
            MissionState.RETRACTING: self._retracting,
            MissionState.RETURNING: self._returning,
            MissionState.STANDBY: self._standby,
            MissionState.FAILSAFE: lambda *_: None,
        }[self.state]
        handler(result, t)
        return self.state

    # ─────────────────────────── 각 상태 ───────────────────────────
    def _idle(self, result, t: float) -> None:
        if result is None or not result.alert_rising_edge:
            return
        if t < self._cooldown_until:
            log.info("alert ignored: cooldown %.0f s remaining", self._cooldown_until - t)
            return

        target = self._resolve_target(result)
        if target is None:
            return

        problems = self.ctl.preflight_check(now=t)
        if problems:
            log.warning("alert ignored: %s", "; ".join(problems))
            return
        if self.ctl.state.mode != "GUIDED" and not self.ctl.set_mode("GUIDED"):
            log.error("alert ignored: could not enter GUIDED")
            return

        sent = self.ctl.goto(target)
        if sent is None:
            log.error("alert ignored: goto refused")
            return

        self.target = sent
        self._last_goto_at = t
        self._enter(MissionState.NAVIGATING, t, f"과밀집 {result.smoothed_count}명")

    def _navigating(self, result, t: float) -> None:
        if self.elapsed(t) > self.cfg.navigation_timeout_s:
            self._enter(MissionState.RETURNING, t, "이동 시간 초과")
            self.ctl.return_to_launch()
            return

        # 군중이 움직였으면 재조준한다 (명령 폭주는 최소 간격으로 막는다)
        if result is not None and result.alert_active:
            new_target = self._resolve_target(result)
            if (new_target is not None and self.target is not None
                    and self._last_goto_at is not None
                    and t - self._last_goto_at >= self.cfg.retarget_min_interval_s
                    and distance_m(self.target, new_target) >= self.cfg.retarget_distance_m):
                sent = self.ctl.goto(new_target)
                if sent is not None:
                    log.info("retargeting: crowd moved %.1f m",
                             distance_m(self.target, sent))
                    self.target = sent
                    self._last_goto_at = t

        if self.target is not None and self.ctl.has_arrived(
                self.target, self.cfg.arrival_radius_m):
            self._enter(MissionState.HOVERING, t, "목표 도달")
            self._payload_deploy(t)
            if self.on_arrived:
                self.on_arrived(self)       # LED·음성 등 부가 동작

    def _hovering(self, result, t: float) -> None:
        if self.elapsed(t) < self.cfg.hover_duration_s:
            return
        # 이미 접혀 있으면(페이로드 미장착 등) 한 단계를 건너뛴다
        if self.payload.is_stowed:
            self._enter(MissionState.RETURNING, t, "안내 종료")
            self.ctl.return_to_launch()
            return
        self._enter(MissionState.RETRACTING, t, "안내 종료 — 구조물 수축")
        self._payload_retract(t)

    def _retracting(self, result, t: float) -> None:
        """접힘을 확인하기 전에는 복귀하지 않는다."""
        if self.payload.is_stowed:
            self._enter(MissionState.RETURNING, t, "수축 완료")
            self.ctl.return_to_launch()
            return
        if self.elapsed(t) > self.cfg.retract_timeout_s:
            # 접히지 않으면 어디에 내려도 구조물이 파손되거나 기체가 전복된다.
            # 그래도 공중에 머무는 것보다는 홈으로 보내는 편이 낫다.
            self._fail(t, f"페이로드 수축 실패 ({self.payload.state.value}) "
                          f"— 착륙 전 운용자 개입 필요")

    def _returning(self, result, t: float) -> None:
        # RTL 은 비행제어기가 수행한다. 착륙(disarm)을 확인하면 임무 종료.
        if not self.ctl.state.armed:
            self.missions_completed += 1
            self._cooldown_until = t + self.cfg.mission_cooldown_s
            self.target = None
            self._enter(MissionState.IDLE, t, "임무 완료")
            if self.on_complete:
                self.on_complete(self)

    # ─────────────────────────── 타겟 해석 ───────────────────────────
    def _resolve_target(self, result) -> Optional[GeoPoint]:
        """비전 결과의 기체 기준 오프셋을 GPS 좌표로 바꾼다."""
        target = getattr(result, "target", None)
        if target is None or not target.has_ground_fix:
            log.warning("target rejected: 지상 오프셋 없음 (고도 미지정?)")
            return None

        pos = self.ctl.state.position
        yaw = self.ctl.state.heading_deg
        if pos is None or yaw is None:
            log.warning("target rejected: 기체 위치/기수 정보 없음")
            return None

        return target_from_body_offset(
            pos, yaw, target.forward_m, target.right_m,
            alt_m=self.cfg.cruise_altitude_m)

    def abort(self, reason: str = "수동 중단", now: Optional[float] = None) -> None:
        """외부에서 임무를 중단시킨다 (조종기 개입 등)."""
        t = now if now is not None else time.monotonic()
        self._enter(MissionState.RETURNING, t, reason)
        self.ctl.return_to_launch()
