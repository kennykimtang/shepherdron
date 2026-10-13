"""UDP 전송 — 지연이 짧고, 밀린 메시지는 버리는 편이 맞는 용도.

TCP 가 아닌 이유
    이 링크는 "가장 최신 관측"만 의미가 있다. TCP 는 끊긴 뒤 재연결하면서
    밀린 패킷을 순서대로 토해내는데, 그건 이미 지나간 군중 위치다.
    오래된 보고로 기체를 움직이느니 아무것도 없는 편이 안전하다.

안전 규칙
    · 수신 측은 stale_after_s 를 넘긴 보고를 없는 것으로 취급한다.
    · 순번이 역행한 패킷(지연 도착)은 버린다.
    · latest() 가 None 이면 GuidanceMission 은 마지막 타겟으로 계속 가다가
      이동 타임아웃에 걸려 RTL 한다. 이것이 설계된 열화 동작이다.
"""
from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Generic, Optional, Type, TypeVar

log = logging.getLogger("shepherdron.link")

T = TypeVar("T")

MAX_DATAGRAM = 65507


class Sender(Generic[T]):
    """단방향 UDP 송신기. 상대가 없어도 조용히 실패한다 (fire-and-forget)."""

    def __init__(self, host: str, port: int):
        self.addr = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 16)
        self.sent = 0
        self.errors = 0

    def send(self, message) -> bool:
        try:
            self._sock.sendto(message.to_json(), self.addr)
            self.sent += 1
            return True
        except OSError as exc:
            self.errors += 1
            if self.errors <= 3 or self.errors % 100 == 0:
                log.warning("send failed (%d회): %s", self.errors, exc)
            return False

    def close(self) -> None:
        self._sock.close()


class Receiver(Generic[T]):
    """백그라운드 수신기. 항상 최신 메시지 하나만 들고 있는다."""

    def __init__(
        self,
        message_type: Type[T],
        port: int,
        host: str = "0.0.0.0",
        stale_after_s: float = 2.0,
    ):
        self.message_type = message_type
        self.port = port
        self.host = host
        self.stale_after_s = stale_after_s

        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._latest: Optional[T] = None
        self._running = False

        self.received = 0
        self.dropped_old = 0        # 순번 역행
        self.dropped_bad = 0        # 파싱 실패

    def start(self) -> "Receiver[T]":
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(0.5)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("listening on %s:%d", self.host, self.port)
        return self

    def _loop(self) -> None:
        while self._running:
            try:
                raw, _ = self._sock.recvfrom(MAX_DATAGRAM)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                msg = self.message_type.from_json(raw, received_at=time.monotonic())
            except (ValueError, TypeError, KeyError) as exc:
                self.dropped_bad += 1
                if self.dropped_bad <= 3:
                    log.warning("malformed message: %s", exc)
                continue

            with self._lock:
                # UDP 는 순서를 보장하지 않는다. 늦게 도착한 옛 패킷은 버린다.
                if self._latest is not None and msg.seq <= self._latest.seq:
                    self.dropped_old += 1
                    continue
                self._latest = msg
                self.received += 1

    def latest(self, now: Optional[float] = None) -> Optional[T]:
        """신선한 최신 메시지. 없거나 오래됐으면 None."""
        with self._lock:
            msg = self._latest
        if msg is None:
            return None
        return msg if msg.age(now) <= self.stale_after_s else None

    def last_seen(self, now: Optional[float] = None) -> float:
        """마지막 수신 이후 경과 시간(초). 한 번도 못 받았으면 무한대."""
        with self._lock:
            msg = self._latest
        return float("inf") if msg is None else msg.age(now)

    @property
    def is_live(self) -> bool:
        return self.last_seen() <= self.stale_after_s

    def stop(self) -> None:
        self._running = False
        if self._sock is not None:
            self._sock.close()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        log.info("receiver stopped (received %d, dropped %d old / %d bad)",
                 self.received, self.dropped_old, self.dropped_bad)
