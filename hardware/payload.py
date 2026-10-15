"""페이로드(전개 구조물) 추상화.

기구 방식이 무엇이든 — 텔레스코픽 마스트든 Kresling 오리가미든, 서보 윈치든
DC 모터 + H브리지든 — 임무 쪽에서 보는 표면은 같아야 한다.

    deploy() → 펼친다
    retract() → 접는다
    update() → 현재 상태를 돌려준다 (폴링)

**왜 필요한가**
    600 mm 구조물을 내린 채로 복귀하면 착륙 자체가 안 된다. 임무가
    "접혔음을 확인한 뒤에" RTL 을 걸도록 하려면, 접혔는지 물어볼 대상이
    있어야 한다. 그게 이 인터페이스다.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol, runtime_checkable

log = logging.getLogger("shepherdron.payload")


class PayloadState(str, Enum):
    STOWED = "STOWED"            # 접힘 — 비행/착륙 가능
    DEPLOYING = "DEPLOYING"      # 펴는 중
    DEPLOYED = "DEPLOYED"        # 펼쳐짐 — 착륙 불가
    RETRACTING = "RETRACTING"    # 접는 중
    FAULT = "FAULT"              # 이상 — 상태를 신뢰할 수 없다


@runtime_checkable
class Payload(Protocol):
    def deploy(self) -> None: ...
    def retract(self) -> None: ...
    def update(self, now: Optional[float] = None) -> PayloadState: ...
    @property
    def state(self) -> PayloadState: ...
    @property
    def is_stowed(self) -> bool: ...
    @property
    def is_deployed(self) -> bool: ...


class NullPayload:
    """페이로드가 달려 있지 않은 기체. 항상 접힌 것으로 본다.

    기구부가 완성되기 전에도 비행 로직을 그대로 돌리기 위한 기본값이다.
    """

    def deploy(self) -> None:
        log.info("[payload 없음] deploy 요청 — 무시")

    def retract(self) -> None:
        log.info("[payload 없음] retract 요청 — 무시")

    def update(self, now: Optional[float] = None) -> PayloadState:
        return PayloadState.STOWED

    @property
    def state(self) -> PayloadState:
        return PayloadState.STOWED

    @property
    def is_stowed(self) -> bool:
        return True

    @property
    def is_deployed(self) -> bool:
        return False


@dataclass
class SimulatedPayload:
    """시간이 걸리는 가짜 페이로드. 테스트와 dry-run 용.

    실제 기구는 즉시 움직이지 않는다. 전개·수축에 수 초가 걸리고 실패할 수도
    있다. 그 시간성을 모사해야 임무 로직의 대기·타임아웃을 검증할 수 있다.
    """

    deploy_duration_s: float = 4.0
    retract_duration_s: float = 6.0     # 되감기는 보통 더 느리다
    fail_deploy: bool = False
    fail_retract: bool = False

    _state: PayloadState = field(default=PayloadState.STOWED, init=False)
    _started: Optional[float] = field(default=None, init=False)

    def deploy(self, now: Optional[float] = None) -> None:
        if self._state in (PayloadState.DEPLOYED, PayloadState.DEPLOYING):
            return
        self._state = PayloadState.DEPLOYING
        self._started = now if now is not None else time.monotonic()
        log.info("전개 시작")

    def retract(self, now: Optional[float] = None) -> None:
        if self._state in (PayloadState.STOWED, PayloadState.RETRACTING):
            return
        self._state = PayloadState.RETRACTING
        self._started = now if now is not None else time.monotonic()
        log.info("수축 시작")

    def update(self, now: Optional[float] = None) -> PayloadState:
        t = now if now is not None else time.monotonic()
        if self._started is None:
            return self._state

        elapsed = t - self._started
        if self._state is PayloadState.DEPLOYING and elapsed >= self.deploy_duration_s:
            self._state = PayloadState.FAULT if self.fail_deploy else PayloadState.DEPLOYED
            self._started = None
            log.info("전개 완료: %s", self._state.value)
        elif self._state is PayloadState.RETRACTING and elapsed >= self.retract_duration_s:
            self._state = PayloadState.FAULT if self.fail_retract else PayloadState.STOWED
            self._started = None
            log.info("수축 완료: %s", self._state.value)
        return self._state

    @property
    def state(self) -> PayloadState:
        return self._state

    @property
    def is_stowed(self) -> bool:
        return self._state is PayloadState.STOWED

    @property
    def is_deployed(self) -> bool:
        return self._state is PayloadState.DEPLOYED
