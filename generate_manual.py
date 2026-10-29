"""Shepherdron 조립 설명서 도면 생성기.

조립하면서 보고 따라갈 수 있도록 2장으로 나눈다.
  1장 : 부품 배치 + 전원 계통 + 조립 순서
  2장 : 신호 결선 + 커넥터 핀맵 + 설정값

모든 커넥터 핀 배열은 KoA FC 공식 매뉴얼(koafc.com) 기준이다.
텍스트는 영문으로 써서 CJK 폰트 없이도 렌더링되게 한다.
"""
from __future__ import annotations

import math

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np

W, H = 2600, 1900
PAPER = "#FCFCFA"
INK, GREY, RULE = "#16202C", "#6B7A8C", "#B6C0CB"
V_MAIN = "#D1242F"      # 14.8 V
V_5 = "#0E8A45"         # 5 V
SIG = "#1257A6"
SER = "#7B2D8E"
PHASE = "#8A4B00"
AUD = "#B07A00"
WARN = "#B01020"


def new_sheet(title, subtitle, sheet_no):
    fig, ax = plt.subplots(figsize=(26, 19), dpi=130)
    ax.set_facecolor(PAPER); fig.patch.set_facecolor(PAPER)
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    ax.add_patch(patches.Rectangle((24, 24), W-48, H-48, fill=False, ec=INK, lw=2.4, zorder=2))
    ax.add_patch(patches.Rectangle((56, 56), W-112, H-112, fill=False, ec=INK, lw=1.0, zorder=2))
    ax.text(92, H-96, title, fontsize=25, fontweight="bold", color=INK, va="center", zorder=3)
    ax.text(92, H-132, subtitle, fontsize=12.5, color=GREY, va="center", zorder=3)
    ax.text(W-92, H-96, sheet_no, fontsize=13, color=GREY, ha="right", va="center", zorder=3)
    return fig, ax


def panel(ax, x, y, w, h, num, title, accent=INK):
    ax.add_patch(patches.Rectangle((x, y), w, h, fc="#FFFFFF", ec=INK, lw=1.6, zorder=5))
    ax.add_patch(patches.Rectangle((x, y+h-34), w, 34, fc=accent, ec=INK, lw=1.6, zorder=6))
    ax.add_patch(patches.Circle((x+26, y+h-17), 12, fc="#FFFFFF", ec=accent, lw=2, zorder=7))
    ax.text(x+26, y+h-17, str(num), fontsize=11.5, fontweight="bold", color=accent,
            ha="center", va="center", zorder=8)
    ax.text(x+50, y+h-17, title, fontsize=12.5, fontweight="bold", color="#FFFFFF",
            va="center", zorder=8)
    return x, y, w, h


def box(ax, x, y, w, h, ref, name, lines=(), accent=SIG, fs=9.0):
    ax.add_patch(patches.Rectangle((x, y), w, h, fc="#FFFFFF", ec=INK, lw=1.5, zorder=8))
    ax.add_patch(patches.Rectangle((x, y+h-24), w, 24, fc=accent, ec=INK, lw=1.5, zorder=9))
    ax.text(x+8, y+h-12, ref, fontsize=9.5, fontweight="bold", color="#FFFFFF",
            va="center", zorder=10)
    ax.text(x+w-8, y+h-12, name, fontsize=9.5, fontweight="bold", color="#FFFFFF",
            ha="right", va="center", zorder=10)
    yy = y + h - 40
    for ln in lines:
        ax.text(x+w/2, yy, ln, fontsize=fs, color=INK, ha="center", va="center", zorder=10)
        yy -= 15

def wire(ax, pts, col, lw=2.2, ls="-"):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=col, lw=lw, ls=ls, zorder=7,
            solid_capstyle="round", solid_joinstyle="round")

def tag(ax, x, y, text, col=INK, fs=8.4, ha="center", weight="normal", box_bg=True):
    ax.text(x, y, text, fontsize=fs, color=col, ha=ha, va="center", zorder=11,
            fontweight=weight,
            bbox=dict(boxstyle="square,pad=0.18", fc=PAPER, ec="none") if box_bg else None)

def connector(ax, x, y, pins, label, note="", pitch=27, accent=INK):
    """커넥터 핀 배열 그림. pins = [(이름, 색), ...] 왼쪽부터."""
    n = len(pins)
    w = n * pitch + 14
    ax.add_patch(patches.FancyBboxPatch((x, y), w, 34,
                 boxstyle="round,pad=1.5,rounding_size=4",
                 fc="#EEF2F7", ec=INK, lw=1.4, zorder=8))
    for i, (nm, c) in enumerate(pins):
        cx = x + 14 + i * pitch
        ax.add_patch(patches.Rectangle((cx-7, y+8), 14, 18, fc=c, ec=INK, lw=0.9, zorder=9))
        ax.text(cx, y + 44, nm, fontsize=7.6, color=INK, ha="center",
                va="bottom", rotation=90, zorder=9)
    ax.text(x, y - 13, label, fontsize=9.5, fontweight="bold", color=accent, zorder=9)
    if note:
        ax.text(x + w + 12, y + 17, note, fontsize=8.2, color=GREY, va="center", zorder=9)
    return w


# ══════════════════════════ SHEET 1 : POWER ══════════════════════════
def sheet1():
    fig, ax = new_sheet(
        "SHEPHERDRON  ASSEMBLY MANUAL",
        "Sheet 1 of 2  ·  Component layout and power wiring  ·  "
        "F450 / AirGear 355 / KoA FC H743 / 4S 14.8 V",
        "REV D  ·  2026-10-29")

    # ── 1. 부품 배치 (F450 상면도) ──
    px, py, pw, ph = 92, 980, 1120, 740
    panel(ax, px, py, pw, ph, 1, "COMPONENT LAYOUT  (F450, viewed from above)")
    cx, cy, r = px + 740, py + 360, 230
    ax.annotate("", xy=(cx, cy + r + 96), xytext=(cx, cy + 70),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=2.2), zorder=9)
    ax.text(cx + 16, cy + r + 76, "FWD", fontsize=11, fontweight="bold", color=INK, zorder=9)

    arms = [(1, 1, "M1", "CCW", "MF9545 R"), (-1, -1, "M2", "CCW", "MF9545 R"),
            (-1, 1, "M3", "CW", "MF9545"), (1, -1, "M4", "CW", "MF9545")]
    for sx, sy, ref, rot, prop in arms:
        mx, my = cx + sx*r*0.72, cy + sy*r*0.72
        ax.plot([cx, mx], [cy, my], color="#2A2A2A", lw=13, solid_capstyle="round", zorder=6)
        # ESC 는 암 중간에
        ex, ey = cx + sx*r*0.40, cy + sy*r*0.40
        ax.add_patch(patches.Rectangle((ex-34, ey-13), 68, 26, fc="#5A6676",
                                       ec=INK, lw=1.2, zorder=8))
        ax.text(ex, ey, f"ESC{ref[1]}", fontsize=7.8, color="#FFFFFF",
                ha="center", va="center", zorder=9)
        ax.add_patch(patches.Circle((mx, my), 42, fc="#FFFFFF", ec=PHASE, lw=2.4, zorder=9))
        ax.text(mx, my+9, ref, fontsize=11, fontweight="bold", color=INK,
                ha="center", va="center", zorder=10)
        ax.text(mx, my-11, rot, fontsize=8.4, color=PHASE, ha="center", va="center", zorder=10)
        ax.text(mx + sx*86, my + sy*34, prop, fontsize=8.6, fontweight="bold",
                color=INK, ha="center", va="center", zorder=10)
        t0 = np.linspace(0.3, 1.7*np.pi, 50) * (1 if rot == "CCW" else -1)
        ax.plot(mx + 56*np.cos(t0), my + 56*np.sin(t0), color=PHASE, lw=1.3, zorder=8)
        ax.annotate("", xy=(mx+56*np.cos(t0[-1]), my+56*np.sin(t0[-1])),
                    xytext=(mx+56*np.cos(t0[-5]), my+56*np.sin(t0[-5])),
                    arrowprops=dict(arrowstyle="-|>", color=PHASE, lw=1.3), zorder=9)

    # 중앙 스택
    ax.add_patch(patches.Rectangle((cx-62, cy-62), 124, 124, fc="#E8EDF3",
                                   ec=INK, lw=1.6, zorder=8))
    ax.text(cx, cy+34, "KoA FC", fontsize=10, fontweight="bold", color=INK,
            ha="center", va="center", zorder=9)
    ax.text(cx, cy+14, "top plate", fontsize=7.6, color=GREY, ha="center", zorder=9)
    ax.text(cx, cy-12, "PDB", fontsize=9.5, fontweight="bold", color=V_MAIN,
            ha="center", va="center", zorder=9)
    ax.text(cx, cy-32, "bottom plate", fontsize=7.6, color=GREY, ha="center", zorder=9)

    # 장착 위치 목록 (도면과 겹치지 않도록 왼쪽에 분리)
    ax.text(px+34, py+ph-72, "WHERE EACH PART GOES", fontsize=10.5,
            fontweight="bold", color=INK, zorder=9)
    места = [("BT1  battery", "bottom plate, under the PDB, strapped", "#4C4FB0"),
             ("PDB1", "F450 bottom plate (integrated)", V_MAIN),
             ("FC1  KoA FC", "top plate, 30.5 mm standoffs, ARROW FWD", SIG),
             ("ESC1-4", "on the arms, midway to the motors", "#5A6676"),
             ("PC1  Raspberry Pi", "top plate, heatsink fitted", "#A4206B"),
             ("U1  UBEC", "beside the PDB, short leads", V_5),
             ("RX1  receiver", "rear, away from the ESC leads", SER),
             ("MAG1  compass", "on a mast, far from power wiring", V_5),
             ("OF1  flow + range", "underside, facing DOWN, unobstructed", SIG),
             ("CAM1  camera", "front, tilted 45 deg DOWN", SIG)]
    for i, (nm, note, col) in enumerate(места):
        yy = py + ph - 112 - i*52
        ax.add_patch(patches.Rectangle((px+34, yy-14), 11, 32, fc=col, ec="none", zorder=9))
        ax.text(px+56, yy+9, nm, fontsize=9.2, fontweight="bold", color=INK, zorder=9)
        ax.text(px+56, yy-9, note, fontsize=8.0, color=GREY, zorder=9)

    # ── 2. 전원 계통 ──
    qx, qy, qw, qh = 1240, 980, 1268, 740
    panel(ax, qx, qy, qw, qh, 2, "POWER WIRING", accent=V_MAIN)

    box(ax, qx+40, qy+560, 280, 110, "BT1", "4S LiPo",
        ("14.8 V  2800 mAh  50C", "XT60  ·  approx 300 g"), accent="#4C4FB0")
    box(ax, qx+40, qy+380, 280, 110, "PDB1", "F450 bottom plate",
        ("star ground point", "470 uF / 25 V low-ESR"), accent=V_MAIN)
    box(ax, qx+480, qy+560, 300, 110, "ESC1-4", "AIR 20A  x4",
        ("20 A cont. / 30 A burst", "solder to PDB pads"), accent="#5A6676")
    box(ax, qx+480, qy+380, 300, 128, "FC1", "KoA FC H743",
        ("VBAT accepts up to 26 V", "5 V 2.5 A BEC built in",
         "NO power module needed"), accent=SIG)
    box(ax, qx+480, qy+190, 300, 110, "U1", "UBEC 5 V 5 A",
        ("in 5-30 V  out 5 V", "43 x 21 x 10 mm  10.4 g"), accent=V_5)
    box(ax, qx+930, qy+380, 290, 128, "", "FC 5 V BEC feeds",
        ("RX1  receiver", "MAG1  compass", "OF1  flow sensor"), accent=V_5)
    box(ax, qx+930, qy+170, 290, 150, "PC1", "Raspberry Pi 4",
        ("5 V / GND on J8-2, J8-6", "inline 3 A fuse",
         "LED1 and U2 share", "this 5 V rail"), accent="#A4206B")

    wire(ax, [(qx+180, qy+560), (qx+180, qy+490)], V_MAIN, 4.4)
    tag(ax, qx+196, qy+525, "XT60 cable  12 AWG 10 cm", V_MAIN, 8.4, ha="left")
    wire(ax, [(qx+320, qy+615), (qx+480, qy+615)], V_MAIN, 4.4)
    tag(ax, qx+400, qy+632, "14 AWG x4", V_MAIN, 8.2)
    wire(ax, [(qx+320, qy+435), (qx+400, qy+435), (qx+400, qy+444), (qx+480, qy+444)], V_MAIN, 3.2)
    tag(ax, qx+400, qy+466, "XT60 ext.  16 AWG 30 cm", V_MAIN, 8.2)
    wire(ax, [(qx+360, qy+435), (qx+360, qy+245), (qx+480, qy+245)], V_MAIN, 2.8)
    tag(ax, qx+372, qy+300, "18 AWG", V_MAIN, 8.2, ha="left")
    wire(ax, [(qx+780, qy+444), (qx+930, qy+444)], V_5, 2.8)
    tag(ax, qx+855, qy+462, "5 V from FC", V_5, 8.2)
    wire(ax, [(qx+780, qy+245), (qx+860, qy+245), (qx+860, qy+245), (qx+930, qy+245)], V_5, 2.8)
    tag(ax, qx+855, qy+263, "5 V  3 A", V_5, 8.2)

    # 접지 안내
    ax.add_patch(patches.Rectangle((qx+40, qy+190), 300, 140, fc="#FFF6F6",
                                   ec=WARN, lw=1.4, zorder=8))
    ax.text(qx+190, qy+306, "STAR GROUND", fontsize=10.5, fontweight="bold",
            color=WARN, ha="center", zorder=9)
    for i, ln in enumerate([
            "Every GND returns to ONE point",
            "on the PDB. Split returns inject",
            "switching noise into the PWM",
            "lines and cause random twitches."]):
        ax.text(qx+190, qy+282-i*21, ln, fontsize=8.4, color=INK, ha="center", zorder=9)

    ax.text(qx+40, qy+150, "Hover draw 11.7 A of 4S.  Peak on the 5 V rail 3.15 A of 5.00 A.",
            fontsize=8.8, color=GREY, zorder=9)
    ax.text(qx+40, qy+126,
            "A power module is OPTIONAL. Fit one only if you want current logging.",
            fontsize=8.8, color=GREY, zorder=9)
    ax.text(qx+40, qy+96,
            "USB on the FC is isolated from the BEC: with USB alone the receiver,",
            fontsize=8.8, color=WARN, zorder=9)
    ax.text(qx+40, qy+72,
            "compass and flow sensor get NO power. Connect the battery for bench tests.",
            fontsize=8.8, color=WARN, zorder=9)

    # ── 3. 조립 순서 ──
    sx_, sy_, sw_, sh_ = 92, 150, 2416, 790
    panel(ax, sx_, sy_, sw_, sh_, 3, "ASSEMBLY ORDER  (do not skip, do not reorder)")
    steps = [
        ("1", "Frame", ["Bolt the four arms to the F450 plates.",
                        "Fit the Tarot landing skid.",
                        "Check motor hole pattern vs arm (M3)."]),
        ("2", "Motors", ["Mount M1-M4 per the layout above.",
                         "Route the three phase wires inward.",
                         "DO NOT fit propellers yet."]),
        ("3", "ESC + PDB", ["Solder ESC power to the PDB pads, 14 AWG.",
                            "Fit the 470 uF cap across the PDB input.",
                            "Bond every GND to the star point."]),
        ("4", "FC", ["Mount KoA FC on 30.5 x 30.5 standoffs.",
                     "Arrow points FORWARD.",
                     "Use soft dampers against vibration."]),
        ("5", "Power", ["Battery -> PDB with the 12 AWG XT60 lead.",
                        "PDB -> FC POWER with the 16 AWG XT60 ext.",
                        "PDB -> UBEC -> Pi, with a 3 A inline fuse."]),
        ("6", "Signal", ["See Sheet 2 for every connector.",
                         "Keep signal wires away from ESC leads.",
                         "Compass on a mast, far from power."]),
        ("7", "First power", ["NO propellers. Battery + USB both on.",
                              "Check 5 V and 14.8 V rails with a meter.",
                              "Confirm the receiver binds and RC moves."]),
        ("8", "Motor test", ["Mission Planner motor test, one at a time.",
                             "Verify rotation against the layout.",
                             "Wrong way: swap any two phase wires."]),
        ("9", "Propellers", ["MF9545 R on M1, M2.  MF9545 on M3, M4.",
                             "Two people cross-check before tightening.",
                             "A wrong blade flips the aircraft on takeoff."]),
        ("10", "Firmware", ["Flash ArduCopter 4.x from Mission Planner.",
                            "Set the frame and serial parameters (Sheet 2).",
                            "Set EK3 sources for indoor flight (Sheet 2)."]),
        ("11", "Calibration", ["Accelerometer, then compass, then radio.",
                               "Compass away from power wires while calibrating.",
                               "ESC calibration if the motors start unevenly."]),
        ("12", "Ground check", ["Set the EKF origin on the GCS map (indoor).",
                                "Arm in STABILIZE, no propellers, confirm spin.",
                                "Only then move to a tethered hover test."]),
    ]
    colw = sw_ / 3
    for i, (no, title, lines) in enumerate(steps):
        col, row = i % 3, i // 3
        bx = sx_ + 28 + col * colw
        by = sy_ + sh_ - 128 - row * 222
        ax.add_patch(patches.Circle((bx+20, by+66), 19, fc=INK, ec=INK, zorder=9))
        ax.text(bx+20, by+66, no, fontsize=12, fontweight="bold", color="#FFFFFF",
                ha="center", va="center", zorder=10)
        ax.text(bx+52, by+68, title, fontsize=12.5, fontweight="bold", color=INK,
                va="center", zorder=9)
        for j, ln in enumerate(lines):
            ax.text(bx+52, by+34-j*24, ln, fontsize=9.4, color=INK, zorder=9)
        if no == "9":
            ax.text(bx+52, by-46, "This is the single most common build error.",
                    fontsize=9.0, color=WARN, fontstyle="italic", zorder=9)
        if no == "7":
            ax.text(bx+52, by-46, "If any rail is wrong, stop. Do not continue.",
                    fontsize=9.0, color=WARN, fontstyle="italic", zorder=9)

    plt.savefig("/Users/kennytang/shepherdron/manual_sheet1_power.png",
                facecolor=PAPER, bbox_inches="tight", pad_inches=0.16)
    plt.close(fig)
    print("sheet 1 saved")



# ══════════════════════════ SHEET 2 : SIGNAL ══════════════════════════
BLK, RED, YEL, WHT, BLU, GRN = "#1B1B1B", "#D1242F", "#E8B300", "#F2F2F2", "#1257A6", "#0E8A45"


def sheet2():
    fig, ax = new_sheet(
        "SHEPHERDRON  ASSEMBLY MANUAL",
        "Sheet 2 of 2  ·  Signal wiring, connector pinouts and parameters  ·  "
        "pinouts per koafc.com",
        "REV D  ·  2026-10-29")

    # ── 4. KoA FC 커넥터 핀아웃 ──
    ax_, ay, aw, ah = 92, 1010, 1180, 710
    panel(ax, ax_, ay, aw, ah, 4, "KoA FC CONNECTOR PINOUT", accent=SIG)
    ax.text(ax_+34, ay+ah-72,
            "Pin 1 is on the LEFT of each drawing, looking at the board with the arrow forward.",
            fontsize=8.8, color=GREY, zorder=9)

    conns = [
        (ay+ah-150, "POWER  6 pin", [("5V", RED), ("5V", RED), ("Curr", WHT),
                                     ("Vbat", RED), ("GND", BLK), ("GND", BLK)],
         "Vbat takes battery directly, up to 26 V"),
        (ay+ah-290, "PWM  10 pin", [("5V", RED), ("PWM1", WHT), ("PWM2", WHT), ("PWM3", WHT),
                                    ("PWM4", WHT), ("PWM5", WHT), ("PWM6", WHT), ("PWM7", WHT),
                                    ("PWM8/BUZ", YEL), ("GND", BLK)],
         "PWM1-4 to ESC1-4.  PWM8 drives a buzzer"),
        (ay+ah-430, "RC  4 pin", [("5V", RED), ("TX5", WHT), ("RX5/SBUS", BLU), ("GND", BLK)],
         "SBUS in on RX5.  5 V powers the receiver"),
        (ay+ah-570, "GPS  6 pin", [("5V", RED), ("TX1", WHT), ("RX1", WHT),
                                   ("SCL", GRN), ("SDA", GRN), ("GND", BLK)],
         "UART + I2C.  Compass uses SDA / SCL"),
    ]
    for yy, label, pins, note in conns:
        connector(ax, ax_+60, yy, pins, label, note, accent=SIG)

    ax.text(ax_+34, ay+56, "TELEM1 and TELEM2 are standard MAVLink serial ports.",
            fontsize=9.0, color=INK, zorder=9)
    ax.text(ax_+34, ay+32, "Micro SD (8 GB) is fitted for flight logs.",
            fontsize=9.0, color=INK, zorder=9)

    # ── 5. 신호 결선 ──
    bx, by, bw, bh = 1300, 1010, 1208, 710
    panel(ax, bx, by, bw, bh, 5, "SIGNAL WIRING", accent=SER)
    rows = [
        ("PWM 1-4", "ESC1-4 signal", "3-wire servo lead", SIG),
        ("PWM 8", "buzzer  (optional)", "2-wire", AUD),
        ("RC", "RX1  R86C V2", "SBUS, powered from FC 5 V", SER),
        ("GPS", "MAG1  compass", "I2C on SDA / SCL", V_5),
        ("TELEM1  SERIAL1", "OF1  flow + range", "UART, 5 V from FC", SIG),
        ("TELEM2  SERIAL2", "PC1  Raspberry Pi", "USB-TTL, 3.3 V logic, 921600", "#A4206B"),
    ]
    ax.text(bx+40, by+bh-74, "FROM  (KoA FC)", fontsize=9.6, fontweight="bold", color=GREY, zorder=9)
    ax.text(bx+360, by+bh-74, "TO", fontsize=9.6, fontweight="bold", color=GREY, zorder=9)
    ax.text(bx+700, by+bh-74, "CABLE", fontsize=9.6, fontweight="bold", color=GREY, zorder=9)
    ax.plot([bx+30, bx+bw-30], [by+bh-90, by+bh-90], color=RULE, lw=1.2, zorder=8)
    for i, (a, b, c, col) in enumerate(rows):
        yy = by+bh-126 - i*44
        ax.add_patch(patches.Rectangle((bx+30, yy-13), 10, 28, fc=col, ec="none", zorder=9))
        ax.text(bx+52, yy, a, fontsize=9.6, fontweight="bold", color=INK, va="center", zorder=9)
        ax.text(bx+360, yy, b, fontsize=9.6, color=INK, va="center", zorder=9)
        ax.text(bx+700, yy, c, fontsize=8.8, color=GREY, va="center", zorder=9)

    ax.add_patch(patches.Rectangle((bx+30, by+186), bw-60, 146, fc="#FFF6F6",
                                   ec=WARN, lw=1.4, zorder=8))
    ax.text(bx+50, by+306, "USB-TTL to TELEM2", fontsize=10.5, fontweight="bold",
            color=WARN, zorder=9)
    for i, ln in enumerate([
        "Use a 3.3 V logic cable. A 5 V cable can damage the FC UART.",
        "Leave the red 5 V conductor UNCONNECTED: the Pi and the FC each have",
        "their own supply, and joining them back-feeds one from the other.",
        "FC TX -> cable RX, FC RX -> cable TX.  GND to GND."]):
        ax.text(bx+50, by+276-i*26, ln, fontsize=9.0, color=INK, zorder=9)

    ax.text(bx+40, by+154, "Raspberry Pi GPIO  (see PAYLOAD.md and WIRING.md)",
            fontsize=9.6, fontweight="bold", color=INK, zorder=9)
    for i, (pin, fn) in enumerate([
            ("J8-19  GPIO10", "SPI0 MOSI  ->  74AHCT125  ->  WS2812B data"),
            ("J8-33  GPIO13", "PWM1  ->  74AHCT125  ->  payload driver"),
            ("J8-31  GPIO6", "direction  ->  74AHCT125  ->  payload driver"),
            ("J8-12/35/40", "I2S BCLK / LRCLK / DIN  ->  MAX98357A")]):
        ax.text(bx+56, by+122-i*27, pin, fontsize=8.8, fontweight="bold", color=INK, zorder=9)
        ax.text(bx+230, by+122-i*27, fn, fontsize=8.8, color=GREY, zorder=9)

    # ── 6. 파라미터 ──
    cx_, cy_, cw_, chh = 92, 150, 1180, 790
    panel(ax, cx_, cy_, cw_, chh, 6, "ARDUPILOT PARAMETERS", accent=INK)
    groups = [
        ("Frame and battery  (4S)", [
            ("FRAME_CLASS", "1", "multicopter"),
            ("FRAME_TYPE", "1", "quad X"),
            ("BATT_MONITOR", "3", "voltage only (4 with a power module)"),
            ("MOT_BAT_VOLT_MAX", "16.8", "4 x 4.2 V"),
            ("MOT_BAT_VOLT_MIN", "13.2", "4 x 3.3 V"),
            ("BATT_LOW_VOLT", "14.0", "3.5 V/cell"),
            ("BATT_CRT_VOLT", "13.2", "3.3 V/cell")]),
        ("Serial ports", [
            ("SERIAL2_PROTOCOL", "2", "MAVLink2 to the Pi  (TELEM2 = UART4)"),
            ("SERIAL2_BAUD", "921", "fall back to 115 if unstable"),
            ("SERIAL6_PROTOCOL", "23", "RC input  (RC port = UART5)"),
            ("SERIAL1_PROTOCOL", "--", "set per the flow sensor manual")]),
        ("Indoor, GPS denied", [
            ("EK3_SRC1_POSXY", "0", "no horizontal position source"),
            ("EK3_SRC1_VELXY", "5", "horizontal velocity from optical flow"),
            ("EK3_SRC1_POSZ", "1", "altitude from the barometer"),
            ("ARMING_CHECK", "--", "uncheck GPS, keep the rest"),
            ("FENCE_ENABLE", "1", "radius 20 m, alt 3.8 m  (see INDOOR.md)")]),
    ]
    yy = cy_ + chh - 80
    for gname, items in groups:
        ax.text(cx_+34, yy, gname, fontsize=10.5, fontweight="bold", color=SIG, zorder=9)
        yy -= 30
        for k, v, note in items:
            ax.text(cx_+50, yy, k, fontsize=9.0, fontfamily="monospace", color=INK, zorder=9)
            ax.text(cx_+330, yy, v, fontsize=9.0, fontfamily="monospace",
                    fontweight="bold", color=WARN, zorder=9)
            ax.text(cx_+420, yy, note, fontsize=8.6, color=GREY, zorder=9)
            yy -= 25
        yy -= 14
    ax.text(cx_+34, cy_+30, "EKF origin must be set by hand on the GCS map for indoor flight.",
            fontsize=9.0, color=WARN, zorder=9)

    # ── 7. 점검 ──
    dx, dy, dw, dh = 1300, 150, 1208, 790
    panel(ax, dx, dy, dw, dh, 7, "BEFORE FIRST FLIGHT", accent=WARN)
    checks = [
        "Every GND bonded to the PDB star point.",
        "470 uF capacitor across the PDB input.",
        "FC arrow points FORWARD.",
        "Motor rotation verified with NO propellers fitted.",
        "MF9545 R on M1 and M2, MF9545 on M3 and M4.",
        "Propeller nuts torqued, no play by hand.",
        "USB-TTL red 5 V conductor left unconnected.",
        "Receiver bound, all RC channels move the right way.",
        "Flight mode switch reachable without looking.",
        "Compass calibrated away from power wiring.",
        "Inline 3 A fuse on the Pi 5 V feed.",
        "LED brightness clamped in software (30 px white = 1.8 A).",
        "Propeller guards fitted for indoor flight.",
        "Battery strapped down, leads clear of the propellers.",
        "Fire extinguisher and LiPo bag on site.",
    ]
    for i, c in enumerate(checks):
        yy = dy + dh - 84 - i*43
        ax.add_patch(patches.Rectangle((dx+40, yy-11), 22, 22, fc="#FFFFFF",
                                       ec=INK, lw=1.4, zorder=9))
        ax.text(dx+78, yy, c, fontsize=9.6, color=INK, va="center", zorder=9)
    ax.text(dx+40, dy+40,
            "The pilot holds the transmitter at all times. Flipping the mode switch",
            fontsize=9.2, color=WARN, zorder=9)
    ax.text(dx+40, dy+18,
            "stands the mission down immediately and it will not take control back.",
            fontsize=9.2, color=WARN, zorder=9)

    plt.savefig("/Users/kennytang/shepherdron/manual_sheet2_signal.png",
                facecolor=PAPER, bbox_inches="tight", pad_inches=0.16)
    plt.close(fig)
    print("sheet 2 saved")


if __name__ == "__main__":
    sheet1()
    sheet2()
