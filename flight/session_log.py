"""세션 로그 — 무슨 일이 있었는지 나중에 재구성할 수 있게 남긴다.

Pixhawk 는 자체 SD 에 비행 로그를 쓴다. 하지만 **왜 그렇게 비행했는지**는
거기 없다. 군중을 몇 명으로 봤는지, 어느 셀이 위험이었는지, 경보가 왜
켜졌는지는 이쪽에서 남겨야 한다.

용도
  · 비행 후 원인 분석 — "왜 그때 거기로 갔지?"
  · 최종 보고서·발표 근거 (#14)
  · 임계치 튜닝 — 실제 현장 수치를 보고 조정

형식은 JSONL(한 줄 한 사건)이다. 중간에 전원이 끊겨도 그때까지 쓴 줄은
살아 있고, 사람이 읽을 수도 grep 할 수도 있다.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TextIO

log = logging.getLogger("shepherdron.session")


@dataclass
class SessionLog:
    """한 번의 비행(또는 실행)에 대한 기록."""

    directory: str = "logs"
    prefix: str = "session"
    flush_every: int = 1          # 전원이 끊겨도 남도록 기본은 매 줄 flush

    path: Optional[Path] = field(default=None, init=False)
    _fh: Optional[TextIO] = field(default=None, init=False, repr=False)
    _n: int = field(default=0, init=False)
    _t0: float = field(default=0.0, init=False)

    def __enter__(self) -> "SessionLog":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> "SessionLog":
        d = Path(self.directory)
        d.mkdir(parents=True, exist_ok=True)
        self.path = d / f"{self.prefix}_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        self._fh = self.path.open("a", encoding="utf-8")
        self._t0 = time.monotonic()
        log.info("session log -> %s", self.path)
        self.event("session_start", at=datetime.now().isoformat(timespec="seconds"))
        return self

    def event(self, kind: str, **data: Any) -> None:
        """사건 한 줄. 실패해도 비행을 멈추지 않는다."""
        if self._fh is None:
            return
        rec = {"t": round(time.monotonic() - self._t0, 3), "kind": kind, **data}
        try:
            self._fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            self._n += 1
            if self.flush_every and self._n % self.flush_every == 0:
                self._fh.flush()
        except OSError as exc:      # 디스크가 차도 임무는 계속되어야 한다
            log.warning("session log write failed: %s", exc)

    # ── 편의 기록기 ──
    def mission_state(self, old: str, new: str, reason: str = "") -> None:
        self.event("mission_state", **{"from": old, "to": new, "reason": reason})

    def vision(self, report) -> None:
        self.event("vision",
                   seq=getattr(report, "seq", None),
                   count=getattr(report, "count", None),
                   alert=getattr(report, "alert_active", None),
                   density=getattr(report, "peak_density", None),
                   cell=getattr(report, "busiest_cell", None),
                   target_px=getattr(report, "target_px", None),
                   fps=getattr(report, "fps", None))

    def target(self, point, forward_m=None, right_m=None, clamped=False) -> None:
        self.event("target", lat=getattr(point, "lat", None),
                   lon=getattr(point, "lon", None),
                   alt_m=getattr(point, "alt_m", None),
                   forward_m=forward_m, right_m=right_m, clamped=clamped)

    def vehicle(self, state, payload_state: str = "", link_age_s=None) -> None:
        self.event("vehicle", mode=state.mode, armed=state.armed,
                   lat=state.lat, lon=state.lon, alt_m=state.relative_alt_m,
                   heading=state.heading_deg, battery=state.battery_remaining_pct,
                   sats=state.satellites, payload=payload_state,
                   link_age_s=link_age_s)

    def warning(self, message: str, **data: Any) -> None:
        self.event("warning", message=message, **data)

    def close(self) -> None:
        if self._fh is None:
            return
        self.event("session_end", events=self._n)
        self._fh.flush()
        self._fh.close()
        self._fh = None
        log.info("session log closed (%d events) -> %s", self._n, self.path)


class NullSessionLog:
    """기록하지 않는 구현. 로그를 끄고 싶을 때."""

    path = None

    def __enter__(self): return self
    def __exit__(self, *exc): pass
    def open(self): return self
    def event(self, kind: str, **data: Any) -> None: pass
    def mission_state(self, old: str, new: str, reason: str = "") -> None: pass
    def vision(self, report) -> None: pass
    def target(self, point, **kw) -> None: pass
    def vehicle(self, state, **kw) -> None: pass
    def warning(self, message: str, **data: Any) -> None: pass
    def close(self) -> None: pass
