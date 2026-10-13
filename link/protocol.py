"""지상-기체 링크 프로토콜.

구조 결정 (2026-10-13)
    노트북 = 지각(perception).  영상을 받아 YOLO 를 돌리고 "무엇을 보았는가" 만 보낸다.
    라즈베리파이 = 판단 + 구동.  상태기계와 페일세이프를 가지고 기체를 움직인다.

**링크는 관측만 나르고 명령은 나르지 않는다.**
    노트북이 오작동하거나 링크가 탈취돼도 최악의 결과는 "잘못된 군중 위치 보고"이며,
    그것은 MavlinkController 의 반경 제한이 막는다. arm/takeoff/goto 같은 비행 명령은
    링크를 통해 들어올 수 없다.

왜 미터가 아니라 픽셀을 보내는가
    지상 오프셋(미터)을 구하려면 기체의 AGL 고도가 필요하다. 노트북이 미터를 보내려면
    먼저 고도를 받아와야 하므로 왕복 의존이 생기고, 텔레메트리가 늦으면 타겟이 틀어진다.
    노트북은 "화면 어디에서 보았는가"(픽셀)만 보내고, 고도를 아는 Pi 가 미터로 환산한다.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Tuple

PROTOCOL_VERSION = 1


@dataclass
class Message:
    """링크 메시지 공통 베이스.

    udp.Receiver 는 모든 메시지가 seq 와 age() 를 갖는다고 가정한다.
    (최신 판별과 신선도 판별에 둘 다 필요하다.)
    """

    seq: int

    # 수신 측에서 채운다. 두 기기의 시계가 동기화돼 있다고 가정하지 않기 위해
    # 송신 시각이 아니라 로컬 도착 시각을 쓴다.
    received_at: Optional[float] = field(default=None, compare=False)

    def age(self, now: Optional[float] = None) -> float:
        """수신 후 경과 시간(초). 받은 적이 없으면 무한대."""
        if self.received_at is None:
            return float("inf")
        return (now if now is not None else time.monotonic()) - self.received_at

    def to_json(self) -> bytes:
        d = asdict(self)
        d.pop("received_at", None)
        return json.dumps(d, separators=(",", ":")).encode("utf-8")

    @classmethod
    def _parse(cls, raw: bytes) -> dict:
        d: dict[str, Any] = json.loads(raw.decode("utf-8"))
        if d.get("version") != PROTOCOL_VERSION:
            raise ValueError(f"프로토콜 버전 불일치: {d.get('version')} != {PROTOCOL_VERSION}")
        d.pop("received_at", None)
        return d


@dataclass
class VisionReport(Message):
    """노트북 → Pi. 한 프레임의 지각 결과."""

    alert_active: bool = False
    alert_rising_edge: bool = False
    count: int = 0                                  # 평활된 인원수
    raw_count: int = 0
    peak_density: Optional[float] = None            # persons/m^2 (캘리브레이션 시)
    calibrated: bool = False

    target_px: Optional[Tuple[int, int]] = None     # 타겟 화면 좌표
    frame_w: int = 0
    frame_h: int = 0

    busiest_cell: Optional[Tuple[int, int]] = None  # (row, col) — 로그/HUD 용
    fps: float = 0.0
    version: int = PROTOCOL_VERSION

    @property
    def has_target(self) -> bool:
        return self.target_px is not None and self.frame_w > 0 and self.frame_h > 0

    @classmethod
    def from_json(cls, raw: bytes, received_at: Optional[float] = None) -> "VisionReport":
        d = cls._parse(raw)
        for key in ("target_px", "busiest_cell"):
            if d.get(key) is not None:
                d[key] = tuple(d[key])
        r = cls(**d)
        r.received_at = received_at if received_at is not None else time.monotonic()
        return r

    @classmethod
    def from_pipeline(cls, seq: int, result, frame_shape) -> "VisionReport":
        """CrowdPipeline.process() 결과를 그대로 보고로 바꾼다."""
        a = result.analysis
        h, w = frame_shape[:2]
        px = result.target.pixel if result.target else a.target_point
        cell = ((a.max_dense_cell.row, a.max_dense_cell.col)
                if a.max_dense_cell else None)
        return cls(
            seq=seq,
            alert_active=result.alert_active,
            alert_rising_edge=result.alert_rising_edge,
            count=result.smoothed_count,
            raw_count=a.total_persons,
            peak_density=a.peak_density,
            calibrated=a.calibrated,
            target_px=(int(px[0]), int(px[1])) if px else None,
            frame_w=w, frame_h=h,
            busiest_cell=cell,
            fps=round(result.fps, 1),
        )


@dataclass
class TelemetryReport(Message):
    """Pi → 노트북. 지상 HUD 와 기록용. 비행 판단에는 쓰이지 않는다."""

    mission_state: str = "IDLE"
    mode: str = "UNKNOWN"
    armed: bool = False
    lat: Optional[float] = None
    lon: Optional[float] = None
    relative_alt_m: Optional[float] = None
    heading_deg: Optional[float] = None
    battery_pct: Optional[int] = None
    satellites: int = 0
    vision_age_s: Optional[float] = None       # Pi 가 본 링크 지연
    version: int = PROTOCOL_VERSION

    @classmethod
    def from_json(cls, raw: bytes, received_at: Optional[float] = None) -> "TelemetryReport":
        r = cls(**cls._parse(raw))
        r.received_at = received_at if received_at is not None else time.monotonic()
        return r
