"""발표용 소스 관리자 — 라이브가 끊기면 녹화본으로 자동 전환한다.

발표장에서 웹캠이 안 잡히거나 USB 가 빠지면 검은 화면이 뜬다. 그 순간
발표가 끝난다. 그래서 1차 소스가 grace_s 동안 프레임을 못 주면 예비
클립으로 갈아타고, 그 뒤로도 주기적으로 1차 복구를 시도한다.

시계와 소스 생성 함수를 주입받아 테스트에서 실제 카메라 없이 검증한다.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Tuple

import numpy as np


def _default_open(source, loop: bool):
    from vision.stream_handler import StreamHandler
    return StreamHandler(source=source, loop_files=loop).start()


class FailoverSource:
    def __init__(
        self,
        primary: str,
        fallback: Optional[str] = None,
        grace_s: float = 4.0,
        retry_s: float = 10.0,
        open_fn: Callable = _default_open,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.primary_name = str(primary)
        self.fallback_name = str(fallback) if fallback else None
        self.grace_s = float(grace_s)
        self.retry_s = float(retry_s)
        self._open = open_fn
        self._now = clock

        self._primary = None
        self._fallback = None
        self.on_fallback = False
        self._last_ok = None          # 1차에서 마지막으로 프레임을 받은 시각
        self._last_retry = 0.0
        self._pinned = False          # 사용자가 수동으로 고정했는가

    # ── 수명주기 ──────────────────────────────────────
    def start(self) -> "FailoverSource":
        self._primary = self._open(self.primary_name, False)
        self._last_ok = self._now()
        self._last_retry = self._now()
        return self

    def stop(self) -> None:
        for s in (self._primary, self._fallback):
            if s is not None:
                try:
                    s.stop()
                except Exception:
                    pass
        self._primary = self._fallback = None

    # ── 상태 ──────────────────────────────────────────
    @property
    def active_label(self) -> str:
        return (self.fallback_name or "?") if self.on_fallback else self.primary_name

    def listing(self):
        """좌측 채널 목록용 (이름, 활성) 쌍."""
        items = [(self.primary_name, not self.on_fallback)]
        if self.fallback_name:
            items.append((self.fallback_name, self.on_fallback))
        return items

    @property
    def has_fallback(self) -> bool:
        return self.fallback_name is not None

    # ── 수동 전환 ──────────────────────────────────────
    def toggle(self) -> None:
        """발표자가 직접 라이브 ↔ 녹화본을 바꾼다. 이후 자동 복구는 멈춘다."""
        if not self.has_fallback:
            return
        self.on_fallback = not self.on_fallback
        self._pinned = True
        if self.on_fallback:
            self._ensure_fallback()
        else:
            self._reopen_primary()

    # ── 내부 ──────────────────────────────────────────
    def _ensure_fallback(self):
        if self._fallback is None and self.fallback_name:
            self._fallback = self._open(self.fallback_name, True)
        return self._fallback

    def _reopen_primary(self):
        if self._primary is not None:
            try:
                self._primary.stop()
            except Exception:
                pass
        self._primary = self._open(self.primary_name, False)
        self._last_ok = self._now()

    # ── 읽기 ──────────────────────────────────────────
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        now = self._now()

        if not self.on_fallback:
            ok, frame = self._try(self._primary)
            if ok:
                self._last_ok = now
                return True, frame
            if (self.has_fallback and not self._pinned
                    and self._last_ok is not None
                    and now - self._last_ok >= self.grace_s):
                self.on_fallback = True
                self._ensure_fallback()
                self._last_retry = now
            return False, None

        # 녹화본 재생 중 — 주기적으로 라이브 복구를 시도한다
        if not self._pinned and now - self._last_retry >= self.retry_s:
            self._last_retry = now
            self._reopen_primary()
            ok, frame = self._try(self._primary)
            if ok:
                self.on_fallback = False
                self._last_ok = now
                return True, frame

        return self._try(self._ensure_fallback())

    @staticmethod
    def _try(src) -> Tuple[bool, Optional[np.ndarray]]:
        if src is None:
            return False, None
        try:
            ok, frame = src.read()
        except Exception:
            return False, None
        return (True, frame) if ok and frame is not None else (False, None)
