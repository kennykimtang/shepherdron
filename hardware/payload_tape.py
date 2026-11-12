"""줄자 붐 전개장치 드라이버 — DRV8833 + 홀 센서 2개.

왜 엔코더가 없는가
    오가는 위치가 둘(수납 · 전개)뿐이라 중간 위치를 알 필요가 없다. 끝에서
    멈추는 일은 홀 센서가 하고, 센서가 안 걸리면 시간 초과로 멈춘다.

왜 멈출 때 브레이크를 거는가
    줄자 스프링이 날을 되감으려 한다. 모터를 코스트(양쪽 LOW)로 두면 전개
    상태가 유지되지 않는다. 멈출 때는 DRV8833 의 두 입력을 모두 올려 브레이크를
    건다. 웜기어가 자기 잠금을 하더라도 브레이크가 이중 안전이다.

**안전 규칙** — `is_stowed` 는 수납 센서가 실제로 눌렸을 때만 참이다.
    시간으로 추정하지 않는다. 이 값이 거짓으로 참이 되면 구조물이 펼쳐진 채
    착륙한다. 임무 쪽(flight/mission.py)이 이 값 하나로 RTL 가부를 정한다.

하드웨어는 백엔드로 분리했다. 노트북에서는 FakeBackend 로 UI 와 상태기계를
그대로 돌려 보고, 기체에서는 GpiozeroBackend 를 쓴다.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from .payload import PayloadState

log = logging.getLogger("shepherdron.payload.tape")

Clock = Callable[[], float]


@dataclass(frozen=True)
class TapeBoomConfig:
    """핀 번호는 BCM 기준. 배선 문서의 Pi J8 핀 배정과 같아야 한다."""

    in1_pin: int = 13          # 물리 33 — DRV8833 IN1
    in2_pin: int = 6           # 물리 31 — DRV8833 IN2
    stowed_pin: int = 16       # 물리 36 — S1 수납 감지 (A3144, 자석 근접 시 LOW)
    deployed_pin: int = 20     # 물리 38 — S2 전개 감지

    duty: float = 0.85         # 정상 구동 듀티
    creep_duty: float = 0.45   # 원점 복귀 등 느린 구동
    ramp_s: float = 0.35       # 소프트 스타트. 돌입 전류를 줄인다
    deploy_timeout_s: float = 8.0
    retract_timeout_s: float = 10.0    # 되감기는 스프링을 이기므로 더 준다
    debounce_s: float = 0.03

    invert: bool = False       # 모터 두 선이 반대로 붙었으면 True

    def __post_init__(self):
        if not 0.0 < self.duty <= 1.0:
            raise ValueError("duty 는 0 초과 1 이하")
        if self.deploy_timeout_s <= 0 or self.retract_timeout_s <= 0:
            raise ValueError("시간 초과는 양수")


class Backend(Protocol):
    """모터 한 축과 리미트 스위치 두 개."""

    def drive(self, duty: float) -> None:
        """duty > 0 전개 방향, < 0 수축 방향, 0 이면 브레이크."""

    def stowed(self) -> bool: ...
    def deployed(self) -> bool: ...
    def close(self) -> None: ...


class TapeBoomPayload:
    """hardware.payload.Payload 프로토콜 구현.

    update() 를 주기적으로(권장 20 Hz 이상) 불러야 끝에서 멈춘다. 호출이
    끊기면 모터가 계속 돈다 — 벤치 서비스와 임무 루프 모두 루프 안에서 부른다.
    """

    def __init__(self, backend: Backend, config: Optional[TapeBoomConfig] = None,
                 clock: Clock = time.monotonic):
        self.cfg = config or TapeBoomConfig()
        self._b = backend
        self._clock = clock
        self._state = PayloadState.FAULT
        self._started: Optional[float] = None
        self._target_duty = 0.0
        self._applied = 0.0
        self._fault_reason = "위치 불명 — 수축으로 원점 복귀"
        # 첫 읽기는 디바운스를 거치지 않는다. 켜자마자 실제 위치를 알아야 한다.
        self._raw = self._stable = (bool(backend.stowed()), bool(backend.deployed()))
        self._changed_at = clock()
        self._b.drive(0.0)                 # 켜질 때 브레이크. 부팅 중 움직이지 않게
        self.update()                      # 센서를 읽어 현재 상태를 정한다

    # ── 명령 ────────────────────────────────────────────────
    def deploy(self) -> None:
        if self._state in (PayloadState.DEPLOYED, PayloadState.DEPLOYING):
            return
        if self._stable[1]:                # 이미 전개 센서가 눌려 있다
            self._settle(PayloadState.DEPLOYED)
            return
        self._start(PayloadState.DEPLOYING, +self.cfg.duty)

    def retract(self) -> None:
        """수축은 FAULT 상태에서도 받는다. 원점으로 돌아가는 유일한 길이다."""
        if self._state in (PayloadState.STOWED, PayloadState.RETRACTING):
            return
        if self._stable[0]:
            self._settle(PayloadState.STOWED)
            return
        duty = self.cfg.creep_duty if self._state is PayloadState.FAULT else self.cfg.duty
        self._start(PayloadState.RETRACTING, -duty)

    def stop(self, reason: str = "수동 정지") -> None:
        """비상 정지. 끝에 도달하지 않았으므로 위치를 신뢰할 수 없다."""
        moving = self._state in (PayloadState.DEPLOYING, PayloadState.RETRACTING)
        self._brake()
        if moving:
            self._fault(reason)

    # ── 폴링 ────────────────────────────────────────────────
    def update(self, now: Optional[float] = None) -> PayloadState:
        t = self._clock() if now is None else now
        stowed, deployed = self._read(t)

        if stowed and deployed:            # 둘 다 눌릴 수는 없다
            self._brake()
            return self._fault("센서 둘 다 활성 — 배선 확인")

        if self._state in (PayloadState.DEPLOYING, PayloadState.RETRACTING):
            done = deployed if self._state is PayloadState.DEPLOYING else stowed
            if done:
                self._brake()
                return self._settle(PayloadState.DEPLOYED if self._state
                                    is PayloadState.DEPLOYING else PayloadState.STOWED)
            limit = (self.cfg.deploy_timeout_s if self._state is PayloadState.DEPLOYING
                     else self.cfg.retract_timeout_s)
            if self._started is not None and t - self._started >= limit:
                self._brake()
                return self._fault(f"{limit:.0f} 초 안에 끝에 닿지 않음")
            self._ramp(t)
        else:
            # 정지 중에는 센서가 상태를 결정한다. 외력으로 밀렸으면 바로 드러난다.
            if stowed:
                self._state = PayloadState.STOWED
            elif deployed:
                self._state = PayloadState.DEPLOYED
            elif self._state in (PayloadState.STOWED, PayloadState.DEPLOYED):
                self._fault("센서가 떨어졌다 — 위치 불명")
        return self._state

    # ── 상태 ────────────────────────────────────────────────
    @property
    def state(self) -> PayloadState:
        return self._state

    @property
    def is_stowed(self) -> bool:
        return self._state is PayloadState.STOWED

    @property
    def is_deployed(self) -> bool:
        return self._state is PayloadState.DEPLOYED

    @property
    def fault_reason(self) -> str:
        return self._fault_reason if self._state is PayloadState.FAULT else ""

    def snapshot(self) -> dict:
        return {
            "state": self._state.value,
            "stowed_switch": self._stable[0],
            "deployed_switch": self._stable[1],
            "duty": round(self._applied, 3),
            "fault": self.fault_reason,
        }

    def close(self) -> None:
        self._brake()
        self._b.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── 내부 ────────────────────────────────────────────────
    def _read(self, t: float) -> tuple[bool, bool]:
        raw = (bool(self._b.stowed()), bool(self._b.deployed()))
        if raw != self._raw:
            self._raw = raw
            self._changed_at = t
        elif raw != self._stable and t - self._changed_at >= self.cfg.debounce_s:
            self._stable = raw
        return self._stable

    def _start(self, state: PayloadState, duty: float) -> None:
        self._state = state
        self._started = self._clock()
        self._target_duty = -duty if self.cfg.invert else duty
        self._applied = 0.0
        self._b.drive(0.0)
        log.info("%s 시작", "전개" if duty > 0 else "수축")

    def _ramp(self, t: float) -> None:
        if self._started is None:
            return
        k = 1.0 if self.cfg.ramp_s <= 0 else min(1.0, (t - self._started) / self.cfg.ramp_s)
        duty = self._target_duty * k
        if abs(duty - self._applied) > 1e-3:
            self._applied = duty
            self._b.drive(duty)

    def _brake(self) -> None:
        self._target_duty = self._applied = 0.0
        self._started = None
        self._b.drive(0.0)

    def _settle(self, state: PayloadState) -> PayloadState:
        self._brake()
        self._state = state
        self._fault_reason = ""
        log.info("%s 완료", state.value)
        return state

    def _fault(self, reason: str) -> PayloadState:
        if self._state is not PayloadState.FAULT or self._fault_reason != reason:
            log.error("페이로드 이상: %s", reason)
        self._state = PayloadState.FAULT
        self._fault_reason = reason
        return self._state


# ── 백엔드 ──────────────────────────────────────────────────
class FakeBackend:
    """하드웨어 없이 돌리는 백엔드. 노트북에서 UI 와 상태기계를 검증한다."""

    def __init__(self, travel_s: float = 3.0, clock: Clock = time.monotonic,
                 position: float = 0.0, jam_at: Optional[float] = None):
        self.travel_s = travel_s
        self.jam_at = jam_at            # 이 위치에서 걸려 더 안 간다 (잼 모사)
        self._pos = position
        self._duty = 0.0
        self._clock = clock
        self._t = clock()

    @property
    def position(self) -> float:
        self._advance()
        return self._pos

    def _advance(self) -> None:
        t = self._clock()
        dt, self._t = t - self._t, t
        if self._duty and dt > 0:
            self._pos = min(1.0, max(0.0, self._pos + self._duty * dt / self.travel_s))
            if self.jam_at is not None and self._duty > 0:
                self._pos = min(self._pos, self.jam_at)

    def drive(self, duty: float) -> None:
        self._advance()
        self._duty = max(-1.0, min(1.0, duty))

    def stowed(self) -> bool:
        self._advance()
        return self._pos <= 0.02

    def deployed(self) -> bool:
        self._advance()
        return self._pos >= 0.98

    def close(self) -> None:
        self.drive(0.0)


class GpiozeroBackend:
    """라즈베리파이. `sudo apt install python3-gpiozero python3-lgpio`

    DRV8833 는 IN1/IN2 양쪽에 PWM 을 넣는다. 한쪽만 PWM 이고 다른 쪽이 HIGH 면
    느린 감쇠(slow decay)가 되어 저속에서 토크가 들쭉날쭉하다. gpiozero 의
    Motor(pwm=True) 가 양쪽 PWM 을 만들어 준다.
    """

    def __init__(self, cfg: TapeBoomConfig):
        from gpiozero import DigitalInputDevice, Motor      # Pi 에서만 import

        self._m = Motor(forward=cfg.in1_pin, backward=cfg.in2_pin, pwm=True)
        # A3144 는 오픈 컬렉터. 자석이 붙으면 LOW -> pull_up 에서 is_active 가 참.
        self._s1 = DigitalInputDevice(cfg.stowed_pin, pull_up=True)
        self._s2 = DigitalInputDevice(cfg.deployed_pin, pull_up=True)

    def drive(self, duty: float) -> None:
        if duty > 0:
            self._m.forward(min(1.0, duty))
        elif duty < 0:
            self._m.backward(min(1.0, -duty))
        else:
            # 양쪽 HIGH = 브레이크. gpiozero 에는 전용 메서드가 없어 직접 올린다.
            self._m.forward_device.value = 1
            self._m.backward_device.value = 1

    def stowed(self) -> bool:
        return bool(self._s1.is_active)

    def deployed(self) -> bool:
        return bool(self._s2.is_active)

    def close(self) -> None:
        self._m.stop()
        self._m.close()
        self._s1.close()
        self._s2.close()


def build(fake: bool = False, config: Optional[TapeBoomConfig] = None,
          **fake_kw) -> TapeBoomPayload:
    """노트북이면 fake=True, 기체면 False."""
    cfg = config or TapeBoomConfig()
    backend: Backend = FakeBackend(**fake_kw) if fake else GpiozeroBackend(cfg)
    return TapeBoomPayload(backend, cfg)
