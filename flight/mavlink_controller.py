"""MAVLink 비행 제어 — Pixhawk 연결, 모드 전환, 유도 비행.

이 모듈은 실제 기체를 움직인다. 비전 모듈의 판단이 틀렸거나 GPS 가 흔들려도
기체가 시야 밖으로 날아가지 않도록 모든 명령 앞에 가드를 둔다.

안전 설계
  · dry_run      실제 전송 없이 로그만 남긴다. SITL 연결 전 로직 검증용
  · 사전 점검    GPS fix / 위성 수 / 배터리 / heartbeat 를 보고 거부
  · 모드 검증    전환 명령을 보내고 실제로 바뀌었는지 확인한다
  · 반경 제한    goto 목표를 홈 반경 안으로 잘라낸다 (geodesy.clamp_to_radius)
  · 고도 제한    min/max 고도를 벗어나는 명령은 거부
  · heartbeat    끊기면 is_healthy() 가 False. 호출 측이 RTL 을 결정한다
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

from flight.geodesy import GeoPoint, clamp_to_radius, distance_m

log = logging.getLogger("shepherdron.flight")

# SET_POSITION_TARGET_GLOBAL_INT 의 type_mask — 위치만 쓰고 속도/가속도/yaw 는 무시
_IGNORE_VX, _IGNORE_VY, _IGNORE_VZ = 1 << 3, 1 << 4, 1 << 5
_IGNORE_AFX, _IGNORE_AFY, _IGNORE_AFZ = 1 << 6, 1 << 7, 1 << 8
_IGNORE_YAW, _IGNORE_YAW_RATE = 1 << 10, 1 << 11
POSITION_ONLY_MASK = (_IGNORE_VX | _IGNORE_VY | _IGNORE_VZ
                      | _IGNORE_AFX | _IGNORE_AFY | _IGNORE_AFZ
                      | _IGNORE_YAW | _IGNORE_YAW_RATE)          # 0b110111111000


@dataclass
class VehicleState:
    """기체 상태 스냅샷."""

    connected: bool = False
    armed: bool = False
    mode: str = "UNKNOWN"
    lat: Optional[float] = None
    lon: Optional[float] = None
    relative_alt_m: Optional[float] = None
    heading_deg: Optional[float] = None
    groundspeed_ms: Optional[float] = None
    battery_voltage: Optional[float] = None
    battery_remaining_pct: Optional[int] = None
    gps_fix_type: int = 0                 # 0-1 없음, 2 2D, 3 3D, 4+ DGPS/RTK
    satellites: int = 0
    last_heartbeat: float = 0.0

    @property
    def position(self) -> Optional[GeoPoint]:
        if self.lat is None or self.lon is None:
            return None
        return GeoPoint(self.lat, self.lon, self.relative_alt_m)

    @property
    def has_gps_fix(self) -> bool:
        return self.gps_fix_type >= 3

    def heartbeat_age(self, now: Optional[float] = None) -> float:
        if self.last_heartbeat == 0.0:
            return math.inf
        return (now if now is not None else time.monotonic()) - self.last_heartbeat


@dataclass
class SafetyLimits:
    """비행 범위 제한. 기본값은 교내 시연 규모를 가정한다."""

    max_radius_m: float = 100.0        # 홈에서 벗어날 수 있는 최대 수평 거리
    min_altitude_m: float = 3.0        # 이보다 낮게는 유도 비행하지 않는다
    max_altitude_m: float = 30.0       # 국내 드론 비행 고도 제한(150 m) 훨씬 아래로 보수적
    min_battery_pct: int = 25          # 이 아래로 떨어지면 신규 임무 거부
    min_satellites: int = 8
    heartbeat_timeout_s: float = 3.0

    def validate(self) -> list[str]:
        """제한값 정합성 점검. 비행 전에 호출한다."""
        p: list[str] = []
        if self.max_radius_m <= 0:
            p.append(f"max_radius_m={self.max_radius_m} 는 0보다 커야 합니다")
        if self.min_altitude_m >= self.max_altitude_m:
            p.append(f"min_altitude_m({self.min_altitude_m}) >= "
                     f"max_altitude_m({self.max_altitude_m}) — 모든 고도가 거부됩니다")
        if self.min_altitude_m <= 0:
            p.append(f"min_altitude_m={self.min_altitude_m} 는 0보다 커야 합니다")
        if self.heartbeat_timeout_s <= 0:
            p.append(f"heartbeat_timeout_s={self.heartbeat_timeout_s} 는 0보다 커야 합니다")
        if not 0 <= self.min_battery_pct <= 100:
            p.append(f"min_battery_pct={self.min_battery_pct} 는 0~100 이어야 합니다")
        return p


class PreflightError(RuntimeError):
    """사전 점검 실패. 기체를 움직여서는 안 되는 상태."""


class MavlinkController:
    def __init__(
        self,
        connection_string: str = "udp:127.0.0.1:14550",
        baud: int = 921600,
        limits: Optional[SafetyLimits] = None,
        dry_run: bool = False,
        source_system: int = 255,
    ):
        self.connection_string = connection_string
        self.baud = baud
        self.limits = limits or SafetyLimits()
        self.dry_run = dry_run
        self.source_system = source_system

        self.conn = None
        self.state = VehicleState()
        self.home: Optional[GeoPoint] = None
        self._target_system = 1
        self._target_component = 1

    # ─────────────────────────── 연결 ───────────────────────────
    def connect(self, timeout_s: float = 30.0) -> bool:
        """연결하고 첫 heartbeat 를 기다린다."""
        from pymavlink import mavutil

        log.info("connecting to %s", self.connection_string)
        kwargs = {"source_system": self.source_system}
        if self.connection_string.startswith(("/dev/", "com", "COM")):
            kwargs["baud"] = self.baud
        self.conn = mavutil.mavlink_connection(self.connection_string, **kwargs)

        hb = self.conn.wait_heartbeat(timeout=timeout_s)
        if hb is None:
            log.error("no heartbeat within %.0f s", timeout_s)
            return False

        self._target_system = self.conn.target_system
        self._target_component = self.conn.target_component
        self.state.connected = True
        self.state.last_heartbeat = time.monotonic()
        log.info("connected to system %d component %d",
                 self._target_system, self._target_component)
        self.request_data_streams()
        return True

    def request_data_streams(self, rate_hz: int = 4) -> None:
        """위치·상태 메시지를 주기적으로 받도록 요청한다."""
        if self.conn is None:
            return
        from pymavlink import mavutil
        self.conn.mav.request_data_stream_send(
            self._target_system, self._target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL, rate_hz, 1)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        self.state.connected = False
        log.info("connection closed")

    # ─────────────────────────── 상태 갱신 ───────────────────────────
    def update(self, max_messages: int = 40) -> VehicleState:
        """수신 큐를 비우며 상태를 갱신한다. 메인 루프에서 매 주기 호출한다."""
        if self.conn is None:
            return self.state

        for _ in range(max_messages):
            msg = self.conn.recv_match(blocking=False)
            if msg is None:
                break
            self._apply(msg)
        return self.state

    def _apply(self, msg) -> None:
        t = msg.get_type()
        s = self.state

        if t == "HEARTBEAT":
            from pymavlink import mavutil
            s.last_heartbeat = time.monotonic()
            s.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            s.mode = self.conn.flightmode if self.conn else "UNKNOWN"
        elif t == "GLOBAL_POSITION_INT":
            s.lat = msg.lat / 1e7
            s.lon = msg.lon / 1e7
            s.relative_alt_m = msg.relative_alt / 1000.0
            s.heading_deg = msg.hdg / 100.0 if msg.hdg != 65535 else s.heading_deg
        elif t == "GPS_RAW_INT":
            s.gps_fix_type = msg.fix_type
            s.satellites = msg.satellites_visible
        elif t == "SYS_STATUS":
            s.battery_voltage = msg.voltage_battery / 1000.0
            s.battery_remaining_pct = (msg.battery_remaining
                                       if msg.battery_remaining >= 0 else None)
        elif t == "VFR_HUD":
            s.groundspeed_ms = msg.groundspeed
        elif t == "HOME_POSITION":
            self.home = GeoPoint(msg.latitude / 1e7, msg.longitude / 1e7, 0.0)

    def is_healthy(self, now: Optional[float] = None) -> bool:
        """링크가 살아 있는가. False 면 호출 측이 페일세이프를 결정해야 한다."""
        return (self.state.connected
                and self.state.heartbeat_age(now) < self.limits.heartbeat_timeout_s)

    # ─────────────────────────── 사전 점검 ───────────────────────────
    def preflight_check(self, require_gps: bool = True,
                        now: Optional[float] = None) -> list[str]:
        """비행 전 점검. 문제 목록을 돌려준다. 비어 있으면 정상."""
        s, lim = self.state, self.limits
        problems: list[str] = []

        if not s.connected:
            problems.append("기체에 연결되지 않음")
        if not self.is_healthy(now):
            problems.append(f"heartbeat 끊김 ({s.heartbeat_age(now):.1f}s)")
        if require_gps:
            if not s.has_gps_fix:
                problems.append(f"GPS fix 없음 (fix_type={s.gps_fix_type})")
            if s.satellites < lim.min_satellites:
                problems.append(f"위성 부족 ({s.satellites} < {lim.min_satellites})")
            if s.position is None:
                problems.append("위치 정보 없음")
        if (s.battery_remaining_pct is not None
                and s.battery_remaining_pct < lim.min_battery_pct):
            problems.append(f"배터리 부족 ({s.battery_remaining_pct}% "
                            f"< {lim.min_battery_pct}%)")
        return problems

    def assert_ready(self, require_gps: bool = True,
                     now: Optional[float] = None) -> None:
        problems = self.preflight_check(require_gps, now)
        if problems:
            raise PreflightError("사전 점검 실패: " + "; ".join(problems))

    # ─────────────────────────── 명령 ───────────────────────────
    def _send_command_long(self, command: int, *params: float) -> None:
        if self.dry_run:
            log.info("[dry-run] COMMAND_LONG %s %s", command, params)
            return
        p = list(params) + [0.0] * (7 - len(params))
        self.conn.mav.command_long_send(
            self._target_system, self._target_component, command, 0, *p[:7])

    def set_mode(self, mode: str, timeout_s: float = 5.0) -> bool:
        """비행 모드를 바꾸고 **실제로 바뀌었는지 확인한다**.

        명령이 무시되는 경우가 흔하므로 전송만 하고 넘어가서는 안 된다.
        """
        mode = mode.upper()
        if self.dry_run:
            log.info("[dry-run] set_mode %s", mode)
            self.state.mode = mode
            return True

        mapping = self.conn.mode_mapping() or {}
        if mode not in mapping:
            log.error("unknown mode %s (available: %s)", mode, sorted(mapping))
            return False

        self.conn.set_mode(mapping[mode])
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.update()
            if self.state.mode == mode:
                log.info("mode -> %s", mode)
                return True
            time.sleep(0.1)

        log.error("mode change to %s not confirmed (still %s)", mode, self.state.mode)
        return False

    def arm(self, timeout_s: float = 10.0, require_gps: bool = True) -> bool:
        self.assert_ready(require_gps)
        from pymavlink import mavutil

        log.info("arming")
        self._send_command_long(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
        if self.dry_run:
            self.state.armed = True
            return True

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.update()
            if self.state.armed:
                log.info("armed")
                return True
            time.sleep(0.2)
        log.error("arm not confirmed within %.0f s", timeout_s)
        return False

    def disarm(self, force: bool = False) -> None:
        from pymavlink import mavutil
        log.info("disarming%s", " (forced)" if force else "")
        self._send_command_long(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                                0, 21196 if force else 0)
        if self.dry_run:
            self.state.armed = False

    def takeoff(self, altitude_m: float, timeout_s: float = 60.0) -> bool:
        """GUIDED 모드에서 지정 고도까지 상승. 도달하면 True."""
        lim = self.limits
        if not (lim.min_altitude_m <= altitude_m <= lim.max_altitude_m):
            log.error("takeoff altitude %.1f m outside [%.1f, %.1f]",
                      altitude_m, lim.min_altitude_m, lim.max_altitude_m)
            return False
        if not self.state.armed:
            log.error("cannot take off while disarmed")
            return False

        from pymavlink import mavutil
        log.info("takeoff to %.1f m", altitude_m)
        self._send_command_long(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                                0, 0, 0, 0, 0, 0, altitude_m)
        if self.dry_run:
            self.state.relative_alt_m = altitude_m
            return True

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.update()
            alt = self.state.relative_alt_m
            if alt is not None and alt >= altitude_m * 0.95:
                log.info("reached %.1f m", alt)
                return True
            time.sleep(0.3)
        log.error("takeoff altitude not reached within %.0f s", timeout_s)
        return False

    def goto(self, target: GeoPoint, clamp: bool = True) -> Optional[GeoPoint]:
        """GUIDED 모드로 목표 지점 이동. 실제로 보낸 좌표를 돌려준다.

        안전 제한에 걸리면 None 을 돌려주고 아무것도 보내지 않는다.
        """
        lim = self.limits

        if self.state.mode != "GUIDED":
            log.error("goto refused: mode is %s, not GUIDED", self.state.mode)
            return None
        if not self.state.armed:
            log.error("goto refused: disarmed")
            return None

        alt = target.alt_m
        if alt is None:
            log.error("goto refused: target has no altitude")
            return None
        if not (lim.min_altitude_m <= alt <= lim.max_altitude_m):
            log.error("goto refused: altitude %.1f m outside [%.1f, %.1f]",
                      alt, lim.min_altitude_m, lim.max_altitude_m)
            return None

        origin = self.home or self.state.position
        if clamp and origin is not None:
            target, was_clamped = clamp_to_radius(origin, target, lim.max_radius_m)
            if was_clamped:
                log.warning("target clamped to %.0f m radius -> %s",
                            lim.max_radius_m, target)

        if self.dry_run:
            log.info("[dry-run] goto %s", target)
            return target

        from pymavlink import mavutil
        self.conn.mav.set_position_target_global_int_send(
            0,                                   # time_boot_ms
            self._target_system, self._target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            POSITION_ONLY_MASK,
            int(target.lat * 1e7), int(target.lon * 1e7), float(alt),
            0, 0, 0,                             # velocity
            0, 0, 0,                             # acceleration
            0, 0,                                # yaw, yaw_rate
        )
        log.info("goto %s", target)
        return target

    def distance_to(self, point: GeoPoint) -> Optional[float]:
        pos = self.state.position
        return None if pos is None else distance_m(pos, point)

    def has_arrived(self, point: GeoPoint, radius_m: float = 2.0,
                    altitude_tolerance_m: float = 1.5) -> bool:
        """목표 지점에 도달했는가. 수평·수직을 모두 본다."""
        d = self.distance_to(point)
        if d is None or d > radius_m:
            return False
        if point.alt_m is not None and self.state.relative_alt_m is not None:
            if abs(self.state.relative_alt_m - point.alt_m) > altitude_tolerance_m:
                return False
        return True

    def return_to_launch(self) -> bool:
        log.warning("RTL")
        return self.set_mode("RTL")

    def land(self) -> bool:
        log.warning("LAND")
        return self.set_mode("LAND")
