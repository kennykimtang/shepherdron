"""시간축 안정화 — 한 프레임의 흔들림이 드론 명령이 되지 않게 막는다.

검출기는 프레임마다 독립적으로 동작하므로, 사람이 잠깐 가려지거나
모션 블러가 끼면 인원수가 출렁인다. 그 값을 그대로 쓰면 경보가
수십 번 켜졌다 꺼지고, 그만큼 비행 명령도 요동친다.

여기서는 두 가지를 제공한다.
  · AlertDebouncer : N-of-M 다수결 + 최소 유지시간 (히스테리시스)
  · RollingCounter : 인원수 중앙값 평활화 (튀는 값 제거)
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional


@dataclass
class RollingCounter:
    """최근 N 프레임 인원수의 중앙값. 평균과 달리 한 프레임 폭주에 둔감하다."""

    window: int = 9

    _buf: Deque[int] = field(default_factory=deque, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.window < 1:
            raise ValueError("window 는 1 이상이어야 합니다.")
        self._buf = deque(maxlen=self.window)

    def update(self, value: int) -> int:
        self._buf.append(int(value))
        ordered = sorted(self._buf)
        return ordered[len(ordered) // 2]

    @property
    def filled(self) -> bool:
        return len(self._buf) == self.window

    def reset(self) -> None:
        self._buf.clear()


@dataclass
class AlertDebouncer:
    """과밀집 경보의 켜짐/꺼짐을 히스테리시스로 제어한다.

    on_ratio  : 최근 window 프레임 중 이 비율 이상이 위험이어야 경보 ON
    off_ratio : 최근 window 프레임 중 이 비율 이하로 떨어져야 경보 OFF
                (on 보다 낮게 잡아 경계선에서 깜빡이는 것을 막는다)
    min_on_s  : 한번 켜진 경보가 최소한 유지되는 시간(초).
                드론이 목표 지점으로 출발한 직후 경보가 꺼져 회항하는 것을 막는다.
    """

    window: int = 15
    on_ratio: float = 0.6
    off_ratio: float = 0.25
    min_on_s: float = 5.0

    _buf: Deque[bool] = field(default_factory=deque, init=False, repr=False)
    _active: bool = field(default=False, init=False)
    _since: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if not 0.0 < self.off_ratio <= self.on_ratio <= 1.0:
            raise ValueError("0 < off_ratio <= on_ratio <= 1 이어야 합니다.")
        self._buf = deque(maxlen=self.window)

    @property
    def active(self) -> bool:
        return self._active

    @property
    def ratio(self) -> float:
        return (sum(self._buf) / len(self._buf)) if self._buf else 0.0

    def held_for(self, now: Optional[float] = None) -> float:
        """경보가 현재 상태를 유지한 시간(초)."""
        if self._since == 0.0:
            return 0.0
        return (now if now is not None else time.monotonic()) - self._since

    def update(self, raw_danger: bool, now: Optional[float] = None) -> bool:
        """프레임 단위 위험 판정을 넣고, 안정화된 경보 상태를 돌려받는다."""
        t = now if now is not None else time.monotonic()
        self._buf.append(bool(raw_danger))
        r = self.ratio

        if not self._active:
            if r >= self.on_ratio:
                self._active = True
                self._since = t
        else:
            if r <= self.off_ratio and (t - self._since) >= self.min_on_s:
                self._active = False
                self._since = t
        return self._active

    def reset(self) -> None:
        self._buf.clear()
        self._active = False
        self._since = 0.0


@dataclass
class TargetSmoother:
    """타겟 지점(화면 좌표)의 지수 평활. 드론이 좌우로 흔들리며 쫓는 것을 막는다."""

    alpha: float = 0.35            # 0에 가까울수록 더 부드럽고 더 느리다
    reset_distance: float = 240.0  # 이보다 멀리 점프하면 새 타겟으로 간주하고 즉시 추종

    _x: Optional[float] = field(default=None, init=False)
    _y: Optional[float] = field(default=None, init=False)

    def update(self, point: Optional[tuple]) -> Optional[tuple]:
        if point is None:
            return (self._x, self._y) if self._x is not None else None
        px, py = float(point[0]), float(point[1])
        if self._x is None:
            self._x, self._y = px, py
        else:
            jump = ((px - self._x) ** 2 + (py - self._y) ** 2) ** 0.5
            if jump > self.reset_distance:
                self._x, self._y = px, py          # 다른 구역으로 이동 — 즉시 전환
            else:
                self._x += self.alpha * (px - self._x)
                self._y += self.alpha * (py - self._y)
        return (self._x, self._y)

    def reset(self) -> None:
        self._x = self._y = None
