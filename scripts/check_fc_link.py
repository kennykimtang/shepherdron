#!/usr/bin/env python3
"""FC ↔ 라즈베리파이 MAVLink 링크 점검 — 기체(Pi)에서 실행한다.

    python3 scripts/check_fc_link.py

왜 따로 만드는가
    "연결이 안 된다" 는 원인이 최소 다섯 가지다. 배선 두 가닥 중 어느 쪽인지,
    Pi 설정인지, FC 파라미터인지, 보드레이트인지. 한 번에 갈라 주지 않으면
    배선을 다 뜯어 보게 된다.

진단의 핵심은 **수신과 송신을 따로 본다**는 것이다.
    HEARTBEAT 가 들어오면  → FC TX → Pi RX (물리 10번) 는 정상
    파라미터 응답이 오면   → Pi TX → FC RX (물리 8번) 도 정상
    둘은 서로 다른 전선이라 한쪽만 되는 경우가 흔하다.
"""
from __future__ import annotations

import argparse
import glob
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BAUDS = (921600, 115200, 57600)
OK, NO, WARN = "  OK  ", " 문제 ", " 주의 "


def line(tag: str, text: str, detail: str = "") -> None:
    print(f"[{tag}] {text}" + (f"\n         {detail}" if detail else ""))


# ── 1단계 : Pi 환경 ──────────────────────────────────────────
def read_first(paths) -> tuple[str, str]:
    for p in paths:
        f = pathlib.Path(p)
        if f.exists():
            try:
                return p, f.read_text(errors="replace")
            except OSError:
                pass
    return "", ""


def check_pi_config() -> bool:
    """config.txt · cmdline.txt · 장치 파일. 치명적 문제가 있으면 False."""
    ok = True
    cfg_path, cfg = read_first(["/boot/firmware/config.txt", "/boot/config.txt"])
    if not cfg:
        line(WARN, "config.txt 를 못 찾았다 — 라즈베리파이가 맞는가?")
    else:
        act = [ln.strip() for ln in cfg.splitlines()
               if ln.strip() and not ln.strip().startswith("#")]
        if any("disable-bt" in ln for ln in act):
            line(OK, f"dtoverlay=disable-bt 있음 ({cfg_path})")
        else:
            ok = False
            line(NO, "dtoverlay=disable-bt 가 없다",
                 f"{cfg_path} 끝에 한 줄 넣고 재부팅:  dtoverlay=disable-bt\n"
                 "         없으면 mini-UART 에 물려 921600 bps 에서 바이트를 흘린다.")
        if any(ln.startswith("enable_uart") and ln.endswith("1") for ln in act):
            line(OK, "enable_uart=1 있음")
        else:
            line(WARN, "enable_uart=1 이 없다 — disable-bt 만으로도 보통 되지만 넣어 두면 확실하다")

    _, cmd = read_first(["/boot/firmware/cmdline.txt", "/boot/cmdline.txt"])
    if cmd:
        bad = [t for t in cmd.split() if t.startswith("console=") and "tty1" not in t]
        if bad:
            ok = False
            line(NO, f"시리얼 로그인 콘솔이 켜져 있다: {' '.join(bad)}",
                 "sudo raspi-config → Interface Options → Serial Port\n"
                 "         로그인 셸 : 아니오   하드웨어 시리얼 : 예")
        else:
            line(OK, "시리얼 로그인 콘솔 꺼져 있음")
    return ok


def resolve_device(dev: str) -> str:
    if os.path.exists(dev):
        tgt = os.path.realpath(dev)
        line(OK, f"장치 있음: {dev}" + (f" → {tgt}" if tgt != dev else ""))
        if not os.access(dev, os.R_OK | os.W_OK):
            line(WARN, "권한 없음 — sudo usermod -aG dialout $USER 후 재로그인")
        return dev
    line(NO, f"{dev} 가 없다", f"있는 포트: {', '.join(sorted(glob.glob('/dev/tty[AUS]*'))) or '없음'}")
    return ""


# ── 2 · 3단계 : 수신 ─────────────────────────────────────────
def sniff(dev: str, baud: int, seconds: float) -> int:
    """원시 바이트 수. MAVLink 파싱 전에 전선부터 확인한다."""
    try:
        import serial
    except ImportError:
        return -1
    try:
        with serial.Serial(dev, baud, timeout=0.2) as s:
            end, n = time.monotonic() + seconds, 0
            while time.monotonic() < end:
                n += len(s.read(4096))
            return n
    except Exception as e:
        line(NO, f"포트를 열 수 없다: {e}")
        return -2


def heartbeat(dev: str, baud: int, seconds: float):
    from pymavlink import mavutil
    conn = None
    try:
        conn = mavutil.mavlink_connection(dev, baud=baud)
        hb = conn.wait_heartbeat(timeout=seconds)
        return (conn, hb) if hb else (conn, None)
    except Exception as e:
        line(NO, f"MAVLink 연결 실패: {e}")
        if conn:
            conn.close()
        return None, None


def param_roundtrip(conn, name: str, seconds: float = 4.0):
    """Pi → FC 방향 확인. 보내고 답이 와야 송신 전선이 살아 있다."""
    from pymavlink import mavutil      # noqa: F401
    conn.mav.param_request_read_send(conn.target_system, conn.target_component,
                                     name.encode(), -1)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        m = conn.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
        if m and m.param_id.strip("\x00") == name:
            return m.param_value
    return None


# ── 진단 ────────────────────────────────────────────────────
def diagnose(raw_bytes: int, got_hb: bool, got_param: bool) -> list[str]:
    """순수 함수 — 테스트 대상. 관측 결과를 사람 말로 바꾼다."""
    if raw_bytes == 0:
        return [
            "FC 에서 **아무 바이트도** 안 온다. 수신 쪽부터 본다.",
            "1. 배선 : FC TELEM2 2번(TX) → Pi 물리 10번(GPIO15 RXD). 같은 이름끼리 꽂지 않았는가",
            "2. FC 파라미터 : SERIAL2_PROTOCOL = 2 (MAVLink2) 인가",
            "3. GND : FC TELEM2 6번 ↔ Pi 물리 6번이 이어져 있는가",
            "4. FC 에 전원이 들어와 있는가 (USB 만으로도 TELEM2 는 동작한다)",
        ]
    if not got_hb:
        return [
            "바이트는 오는데 MAVLink 로 안 읽힌다. **보드레이트 불일치**가 가장 흔하다.",
            "1. FC 의 SERIAL2_BAUD 와 이 스크립트의 --baud 가 같은가",
            "2. dtoverlay=disable-bt 가 빠지면 mini-UART 라 921600 에서 깨진다",
            "3. SERIAL2_PROTOCOL 이 2 가 아닌 다른 값(예: 이미 다른 용도)일 수 있다",
        ]
    if not got_param:
        return [
            "수신은 되는데 **송신이 안 간다**. 전선 한 가닥만 문제다.",
            "1. 배선 : Pi 물리 8번(GPIO14 TXD) → FC TELEM2 3번(RX)",
            "2. 이 방향만 끊겨도 HEARTBEAT 는 계속 보이므로 '연결된 것처럼' 보인다",
            "3. 듀폰 핀이 커넥터에 덜 들어갔는지 확인 (가장 흔한 원인)",
        ]
    return ["양방향 모두 정상. 링크 준비 완료."]


def main() -> int:
    ap = argparse.ArgumentParser(description="FC ↔ Pi MAVLink 링크 점검")
    ap.add_argument("--device", default="/dev/ttyAMA0")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--scan", action="store_true", help="보드레이트를 차례로 시도")
    ap.add_argument("--seconds", type=float, default=5.0)
    a = ap.parse_args()

    print("=" * 62)
    print(" FC ↔ 라즈베리파이 링크 점검")
    print("=" * 62)

    print("\n[1단계] Pi 설정")
    check_pi_config()
    dev = resolve_device(a.device)
    if not dev:
        return 1

    bauds = BAUDS if a.scan else (a.baud,)
    raw, used = 0, a.baud
    print("\n[2단계] 전선 — 원시 바이트가 들어오는가")
    for b in bauds:
        n = sniff(dev, b, min(2.0, a.seconds))
        if n == -1:
            line(WARN, "pyserial 없음 — 건너뜀 (pip install pyserial)")
            raw = -1
            break
        if n == -2:
            return 1
        line(OK if n else NO, f"{b:>7} bps : {n} 바이트")
        if n:
            raw, used = n, b
            break

    print("\n[3단계] MAVLink HEARTBEAT")
    conn, hb = heartbeat(dev, used, a.seconds)
    if hb:
        from pymavlink import mavutil
        ap_name = mavutil.mavlink.enums["MAV_AUTOPILOT"][hb.autopilot].name
        line(OK, f"수신 — system {conn.target_system}, {ap_name}")
        if "ARDUPILOT" not in ap_name:
            line(WARN, "ArduPilot 이 아니다. PX4 가 올라가 있으면 flight/ 코드가 안 맞는다")
    else:
        line(NO, f"{a.seconds:.0f} 초 안에 HEARTBEAT 없음")

    got_param = False
    if hb:
        print("\n[4단계] 송신 — 보낸 요청에 답이 오는가")
        v = param_roundtrip(conn, "SERIAL2_BAUD")
        if v is None:
            line(NO, "SERIAL2_BAUD 응답 없음")
        else:
            got_param = True
            line(OK, f"SERIAL2_BAUD = {int(v)}  (921 = 921600 bps)")
            if int(v) * 1000 != used and int(v) != used:
                line(WARN, f"FC 설정({int(v)})과 지금 쓰는 속도({used})가 다르다")
    if conn:
        conn.close()

    print("\n" + "=" * 62)
    for s in diagnose(raw if raw >= 0 else 1, bool(hb), got_param):
        print(" " + s)
    print("=" * 62)
    return 0 if (hb and got_param) else 2


if __name__ == "__main__":
    raise SystemExit(main())
