"""Shepherdron — system interconnect wiring diagram (technical sheet).

Conventions
  · reference designators (BT1, PM1, U3, M1 …) key the wire schedule
  · conductors are tagged with a wire ID; gauge / connector live in the schedule
  · crossings that are NOT joined are drawn as hop arcs
  · GND returns use ground symbols, all bonded to the PDB1 star point
All text is English so the sheet renders without a CJK font.
"""
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

W, H = 2900, 2150
fig, ax = plt.subplots(figsize=(29.0, 21.5), dpi=130)
PAPER = "#FCFCFA"
ax.set_facecolor(PAPER); fig.patch.set_facecolor(PAPER)
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")

INK, GREY, RULE = "#16202C", "#6B7A8C", "#B6C0CB"
V11, V53, V50 = "#D1242F", "#E07B00", "#0E8A45"
GNDC, SIG, SER, PHASE, AUD = "#1B1B1B", "#1257A6", "#7B2D8E", "#8A4B00", "#B07A00"

# ───────────────────────────── sheet furniture ─────────────────────────────
ax.add_patch(patches.Rectangle((26, 26), W-52, H-52, fill=False, ec=INK, lw=2.4, zorder=2))
ax.add_patch(patches.Rectangle((62, 62), W-124, H-124, fill=False, ec=INK, lw=1.0, zorder=2))
for i, c in enumerate("ABCDEFGH"):
    x = 62 + (W-124)*(i+0.5)/8
    for y in (44, H-44):
        ax.text(x, y, c, fontsize=10, color=INK, ha="center", va="center", zorder=3)
    if i:
        xd = 62 + (W-124)*i/8
        for y0, y1 in ((26, 62), (H-62, H-26)):
            ax.plot([xd, xd], [y0, y1], color=INK, lw=1.0, zorder=3)
for j in range(6):
    y = 62 + (H-124)*(j+0.5)/6
    for x in (44, W-44):
        ax.text(x, y, str(6-j), fontsize=10, color=INK, ha="center", va="center", zorder=3)
    if j:
        yd = 62 + (H-124)*j/6
        for x0, x1 in ((26, 62), (W-62, W-26)):
            ax.plot([x0, x1], [yd, yd], color=INK, lw=1.0, zorder=3)

ax.text(100, 2048, "SHEPHERDRON   ·   SYSTEM INTERCONNECT WIRING DIAGRAM",
        fontsize=25, fontweight="bold", color=INK, va="center", zorder=3)
ax.text(100, 2012, "F450 quadrotor X   ·   4S 14.8 V   ·   KoA H743 / ArduCopter 4.x   ·   "
                   "Raspberry Pi 4 Model B companion computer",
        fontsize=12.5, color=GREY, va="center", zorder=3)

# ───────────────────────────── primitives ─────────────────────────────
def comp(x, y, w, h, ref, name, spec=(), accent=SIG):
    ax.add_patch(patches.Rectangle((x, y), w, h, fc="#FFFFFF", ec=INK, lw=1.7, zorder=6))
    ax.add_patch(patches.Rectangle((x, y+h-27), w, 27, fc=accent, ec=INK, lw=1.7, zorder=7))
    ax.text(x+10, y+h-13.5, ref, fontsize=10.5, fontweight="bold", color="#FFFFFF",
            va="center", zorder=8)
    ax.text(x+w-10, y+h-13.5, name, fontsize=10.5, fontweight="bold", color="#FFFFFF",
            ha="right", va="center", zorder=8)
    yy = y + h - 47
    for s in spec:
        ax.text(x+w/2, yy, s, fontsize=8.8, color=INK, ha="center", va="center", zorder=8)
        yy -= 16

def pin(x, y, col, label="", side="right", fs=8.2):
    ax.plot([x], [y], marker="s", ms=5.4, mfc=col, mec=INK, mew=0.8, zorder=9)
    if label:
        dx, ha = (10, "left") if side == "right" else (-10, "right")
        ax.text(x+dx, y, label, fontsize=fs, color=INK, ha=ha, va="center", zorder=9)

def wire(pts, col=SIG, lw=2.0, hops=()):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=col, lw=lw, zorder=5,
            solid_capstyle="round", solid_joinstyle="round")
    t = np.linspace(0, np.pi, 48)
    for hx, hy, orient in hops:
        if orient == "h":
            ax.plot([hx-16, hx+16], [hy, hy], color=PAPER, lw=lw+5, zorder=5.4)
            ax.plot(hx - 16*np.cos(t), hy + 16*np.sin(t), color=col, lw=lw, zorder=5.5)
        else:
            ax.plot([hx, hx], [hy-16, hy+16], color=PAPER, lw=lw+5, zorder=5.4)
            ax.plot(hx + 16*np.sin(t), hy - 16*np.cos(t), color=col, lw=lw, zorder=5.5)

def wid(x, y, text, col, ha="center", va="bottom"):
    ax.text(x, y, text, fontsize=8.6, fontweight="bold", color=col,
            ha=ha, va=va, zorder=10,
            bbox=dict(boxstyle="square,pad=0.14", fc=PAPER, ec="none"))

def ground(x, y, down=24):
    ax.plot([x, x], [y, y-down], color=GNDC, lw=1.9, zorder=5)
    for i, hw in enumerate((16, 10.5, 5)):
        ax.plot([x-hw, x+hw], [y-down-i*5.5, y-down-i*5.5], color=GNDC, lw=1.9, zorder=5)

def node(x, y, col):
    ax.plot([x], [y], marker="o", ms=7, color=col, zorder=10)

# ═══════════════ ZONE 1 · POWER + FLIGHT CONTROL + PROPULSION ═══════════════
ax.add_patch(patches.Rectangle((92, 1255), 2716, 735, fill=False, ec=RULE, lw=1.1,
                               ls=(0, (7, 5)), zorder=2))
ax.text(106, 1972, "1 · PROPULSION & FLIGHT CONTROL", fontsize=12, fontweight="bold",
        color=GREY, va="center", zorder=3)

comp(110, 1780, 250, 150, "BT1", "4S LiPo",
     ("14.8 V  2800 mAh  50C", "XT60  ·  approx 300 g", "140 A burst"), accent="#4C4FB0")
comp(460, 1780, 250, 150, "PM1", "Power module",
     ("in  14.8 V from BT1", "out 14.8 V to PDB1", "VERIFY: H743 may sense"), accent=V53)
comp(460, 1430, 250, 280, "PDB1", "F450 PDB",
     ("14.8 V distribution bus", "470 uF / 25 V low-ESR", "across the input pads",
      "", "★  STAR GROUND", "all returns bond here"), accent=V11)
node(600, 1430, GNDC); ground(600, 1430, 20)

comp(810, 1870, 200, 100, "OF1", "3901-L0X", ("INDOOR: no GPS", "flow = EK3_SRC1_VELXY 5"))
comp(1050, 1870, 200, 100, "TM1", "Telemetry", ("2.4 GHz air unit", "57 600 bps"), accent=V50)
comp(1290, 1870, 210, 100, "RX1", "MC6C RX", ("S.BUS receiver", "manual override"), accent=SER)

fcx, fcy, fcw, fch = 790, 1320, 710, 480
ax.add_patch(patches.Rectangle((fcx, fcy), fcw, fch, fc="#FFFFFF", ec=INK, lw=2.1, zorder=6))
ax.add_patch(patches.Rectangle((fcx, fcy+fch-31), fcw, 31, fc=INK, ec=INK, lw=2.1, zorder=7))
ax.text(fcx+12, fcy+fch-15.5, "FC1", fontsize=11.5, fontweight="bold", color="#FFFFFF",
        va="center", zorder=8)
ax.text(fcx+fcw-12, fcy+fch-15.5, "KoA H743   ·   ArduCopter 4.x",
        fontsize=11.5, fontweight="bold", color="#FFFFFF", ha="right", va="center", zorder=8)
ax.text(fcx+fcw/2, fcy+fch-56, "flight controller   ·   frame QUAD X",
        fontsize=9.5, color=GREY, ha="center", va="center", zorder=8)
ax.text(fcx+26, fcy+255,
        "PARAMETERS\n"
        "  FRAME_CLASS       1     multicopter\n"
        "  FRAME_TYPE        1     quad X\n"
        "  SERIAL2_PROTOCOL  2     MAVLink2\n"
        "  SERIAL2_BAUD      921   fallback 115\n"
        "  BRD_SAFETYENABLE  1\n"
        "  BATT_MONITOR      4     volt + current\n"
        "  MOT_BAT_VOLT_MAX  16.8   4S\n"
        "  MOT_BAT_VOLT_MIN  13.2   4S",
        fontsize=8.7, color=INK, va="top", family="monospace", zorder=8)
ground(1180, fcy+16, 0)

pin(fcx, 1700, V53, "POWER 6p", "right")
for xx, col in ((890, SIG), (1150, V50), (1390, SER)):
    pin(xx, fcy+fch, col)
pin(1300, fcy, SER)
ax.text(890, 1812, "flow + range", fontsize=8.2, color=INK, ha="center", va="bottom", zorder=9)
ax.text(1150, 1812, "TELEM1 6p", fontsize=8.2, color=INK, ha="center", va="bottom", zorder=9)
ax.text(1390, 1812, "RC IN 3p", fontsize=8.2, color=INK, ha="center", va="bottom", zorder=9)
ax.text(1316, 1332, "TELEM2 6p", fontsize=8.2, color=INK, va="bottom", zorder=9)
for i, yy in enumerate((1740, 1620, 1500, 1380)):
    pin(fcx+fcw, yy, V11, f"MAIN OUT {i+1}", "left")

esc_rows = [(1690, "ESC1", "M1", "front-right", "CCW", "T9545R"),
            (1570, "ESC2", "M2", "rear-left",   "CCW", "T9545R"),
            (1450, "ESC3", "M3", "front-left",  "CW",  "T9545"),
            (1330, "ESC4", "M4", "rear-right",  "CW",  "T9545")]
for y, eref, mref, pos, rot, prop in esc_rows:
    comp(1700, y, 270, 100, eref, "AIR 20A V2", ("3-4S  ·  AirGear 355 set",), accent="#5A6676")
    comp(2060, y, 420, 100, mref, f"AIR2213 920KV  ·  {pos}",
         (f"rotation {rot}      propeller {prop}",), accent=PHASE)

# ═══════════════════ ZONE 2 · COMPANION + MISSION PAYLOAD ═══════════════════
ax.add_patch(patches.Rectangle((92, 560), 2716, 670, fill=False, ec=RULE, lw=1.1,
                               ls=(0, (7, 5)), zorder=2))
ax.text(106, 1212, "2 · COMPANION & PAYLOAD", fontsize=12, fontweight="bold",
        color=GREY, va="center", zorder=3)

comp(170, 680, 290, 170, "U1", "UBEC 5V / 5A",
     ("in 14.8 V from PDB1", "out 5.00 V switching", "measured peak 3.15 A"), accent=V50)
comp(170, 900, 290, 180, "CAM1", "Camera 3 Wide",
     ("Sony IMX708  ·  12 MP", "102 deg H / 120 deg D", "focus 5 cm - inf",
      "200 mm FPC, CSI-2"))

px, py, pw, ph = 500, 700, 730, 530
ax.add_patch(patches.Rectangle((px, py), pw, ph, fc="#FFFFFF", ec=INK, lw=2.1, zorder=6))
ax.add_patch(patches.Rectangle((px, py+ph-31), pw, 31, fc="#A4206B", ec=INK, lw=2.1, zorder=7))
ax.text(px+12, py+ph-15.5, "PC1", fontsize=11.5, fontweight="bold", color="#FFFFFF",
        va="center", zorder=8)
ax.text(px+pw-12, py+ph-15.5, "RASPBERRY PI 4 MODEL B  ·  2 GB",
        fontsize=11.5, fontweight="bold", color="#FFFFFF", ha="right", va="center", zorder=8)
ax.text(px+170, py+ph-56,
        "companion computer\n"
        "   camera capture + MJPEG stream\n"
        "   MAVLink bridge to FC1\n"
        "   payload / LED / audio I/O\n"
        "   mission state machine\n\n"
        "VISION RUNS ON THE GROUND\n"
        "   laptop does YOLOv8n, sends\n"
        "   observations only over UDP\n"
        "   heatsink is enough, no fan",
        fontsize=8.8, color=INK, va="top", family="monospace", zorder=8)
pin(px, 790, V50, "J8-2 / J8-6\n5 V + GND", "right")
pin(px, 990, SIG, "CSI-2  camera", "right")
pin(700, py+ph, SER)
ax.text(716, 1244, "USB-A", fontsize=8.2, color=INK, va="bottom", zorder=9)

hx = px + pw
hdr = [(1090, "19", "GPIO10", "SPI0 MOSI", SER),
       (1000, "33", "GPIO13", "PWM1",      V53),
       (950,  "31", "GPIO6",  "direction", V53),
       (880,  "6",  "GND",    "",          GNDC),
       (800,  "12", "GPIO18", "I2S BCLK",  AUD),
       (770,  "35", "GPIO19", "I2S LRCLK", AUD),
       (740,  "40", "GPIO21", "I2S DIN",   AUD)]
ax.add_patch(patches.Rectangle((hx-132, 715), 132, 405, fc="#EEF2F7", ec=INK, lw=1.3, zorder=7))
ax.text(hx-66, 1104, "J8  ·  40-PIN HEADER", fontsize=8.2, fontweight="bold",
        color=INK, ha="center", va="center", zorder=9)
for y, p, bcm, fn, col in hdr:
    ax.add_patch(patches.Circle((hx-108, y), 11.5, fc=col, ec=INK, lw=1.0, zorder=9))
    ax.text(hx-108, y, p, fontsize=7.6, fontweight="bold", color="#FFFFFF",
            ha="center", va="center", zorder=10)
    ax.text(hx-88, y, bcm, fontsize=8.2, color=INK, va="center", zorder=9)
    if fn:
        ax.plot([hx-26, hx], [y, y], color=col, lw=2.0, zorder=5)
        pin(hx, y, col)
ground(hx-108, 868, 18)

comp(1340, 850, 230, 330, "U4", "74AHCT125",
     ("quad buffer", "3.3 V -> 5 V", "Vcc = 5.0 V", "", "A1 -> Y1   LED data",
      "A2 -> Y2   PWM", "A3 -> Y3   DIR", "", "REQUIRED, not", "optional - see note 4"),
     accent=SER)
comp(1700, 1055, 440, 135, "LED1", "WS2812B strip  ·  30 px",
     ("5 V addressable  ·  470 ohm series on DIN", "1000 uF bulk across 5 V / GND",
      "brightness clamped to 50 %  ->  0.90 A"), accent=SER)
comp(1700, 870, 340, 150, "U3", "Payload driver  TBD",
     ("mechanism undecided", "see issue #9", "winch servo recommended"), accent=V53)
comp(2210, 870, 420, 150, "M5", "Deployable structure  TBD",
     ("600 mm outdoor / 300 mm indoor", "telescopic mast or Kresling",
      "LIMIT SWITCH for stow detect"), accent=PHASE)
comp(1700, 660, 340, 150, "U2", "MAX98357A",
     ("I2S class-D amp", "3.2 W into 4 ohm", "3.3 V logic, no shifter"), accent=AUD)
comp(2210, 660, 340, 150, "LS1", "Speaker 3W 4ohm",
     ("evacuation voice prompt",), accent=AUD)

# ───────────────────────────── conductors ─────────────────────────────
wire([(360, 1855), (460, 1855)], V11, 4.2);            wid(410, 1866, "W01", V11)
wire([(710, 1700), (790, 1700)], V53, 2.6);            wid(750, 1711, "W02", V53)
wire([(585, 1780), (585, 1710)], V11, 4.2);            wid(597, 1745, "W03", V11, ha="left", va="center")
# W04 main bus to the ESCs (hops the W12 serial drop)
wire([(650, 1430), (650, 1305), (1832, 1305), (1832, 1330)], V11, 4.2,
     hops=[(1300, 1305, "h")])
for a, b in ((1430, 1450), (1550, 1570), (1670, 1690)):
    wire([(1832, a), (1832, b)], V11, 4.2)
wid(1000, 1316, "W04", V11)
for i, (y, *_r) in enumerate(esc_rows):
    cy = y + 50
    wire([(1500, cy), (1700, cy)], V11, 1.9);   wid(1600, cy+9, f"W{5+i:02d}", V11)
    wire([(1970, cy), (2060, cy)], PHASE, 3.0); wid(2015, cy+9, "3 ph", PHASE)
wire([(890, 1870), (890, 1800)], SIG, 2.0);      wid(866, 1838, "W09", SIG, ha="right", va="center")
wire([(1150, 1870), (1150, 1800)], V50, 2.0);    wid(1126, 1838, "W10", V50, ha="right", va="center")
wire([(1390, 1870), (1390, 1800)], SER, 2.0);    wid(1414, 1838, "W11", SER, ha="left", va="center")
# W12 FC TELEM2 <-> Pi USB
wire([(1300, 1320), (1300, 1270), (700, 1270), (700, 1230)], SER, 2.4)
wid(1000, 1281, "W12   MAVLink2 over USB-TTL, 3.3 V FTDI  ·  921 600 bps "
                "·  leave the 5 V conductor unterminated", SER)
# W13 / W14 main 11.1 V down to the payload bay
wire([(560, 1430), (560, 1270), (115, 1270), (115, 600), (1600, 600), (1600, 900),
      (1700, 900)], V11, 2.8, hops=[(1600, 630, "v"), (1600, 700, "v"), (1600, 760, "v")])
wire([(115, 800), (170, 800)], V11, 2.8); node(115, 800, V11)
wid(250, 1281, "W13", V11)
wid(820, 611, "W14   14.8 V to the payload driver  :  never take this from the 5 V rail", V11)
# W15 / W16 the 5 V clean rail
wire([(460, 790), (500, 790)], V50, 2.8);  wid(480, 801, "W15", V50)
wire([(480, 790), (480, 630), (2700, 630), (2700, 1215), (1455, 1215), (1455, 1180)], V50, 2.6)
node(480, 790, V50)
wire([(1900, 1215), (1900, 1190)], V50, 2.6); node(1900, 1215, V50)
wire([(1560, 630), (1560, 700), (1700, 700)], V50, 2.2); node(1560, 630, V50)
wid(1150, 641, "W16   5.0 V clean rail  ·  3.15 A peak of 5.00 A available", V50)
wid(1520, 712, "W17", V50)
# W18 camera
wire([(460, 990), (500, 990)], SIG, 2.0);  wid(480, 1001, "W18", SIG)
# header fan-out
wire([(hx, 1090), (1270, 1090), (1270, 1120), (1340, 1120)], SER, 2.0); wid(1282, 1106, "W19", SER, ha="left", va="center")
wire([(hx, 1000), (1340, 1000)], V53, 2.0);                            wid(1290, 1011, "W20", V53)
wire([(hx, 950),  (1340, 950)], V53, 2.0);                             wid(1290, 961, "W21", V53)
wire([(hx, 800), (1290, 800), (1290, 760), (1700, 760)], AUD, 2.4)
wid(1455, 770, "W22-24   I2S bundle 3-core  ·  BCLK / LRCLK / DIN", AUD)
wire([(hx, 770), (1290, 770)], AUD, 2.0)
wire([(hx, 740), (1290, 740), (1290, 760)], AUD, 2.0)
# shifter outputs
wire([(1570, 1120), (1700, 1120)], SER, 2.2);  wid(1635, 1131, "W25", SER)
wire([(1570, 1000), (1640, 1000), (1640, 960), (1700, 960)], V53, 2.2)
wire([(1570, 950),  (1620, 950),  (1620, 925), (1700, 925)], V53, 2.2)
wid(1618, 1034, "W26-27", V53)
# payload outputs
wire([(2040, 945), (2210, 945)], PHASE, 3.0);  wid(2125, 956, "W28", PHASE)
wire([(2040, 735), (2210, 735)], AUD, 2.6);    wid(2125, 746, "W29", AUD)
for gx, gy in ((300, 680), (1455, 850), (1790, 1055), (1790, 870), (1790, 660),
               (2330, 870), (2330, 660)):
    ground(gx, gy, 20)

# ═════════════════════ ZONE 3 · reference ═════════════════════
# legend strip
ly = 525
ax.text(110, ly, "LEGEND", fontsize=9.5, fontweight="bold", color=GREY, va="center", zorder=8)
cur = 200
for lbl, col, lw_ in (("14.8 V main", V11, 4.0), ("5.3 V FC rail", V53, 2.4),
                      ("5.0 V clean", V50, 2.4), ("signal", SIG, 2.0),
                      ("serial / data", SER, 2.0), ("3-phase", PHASE, 3.0),
                      ("I2S audio", AUD, 2.0)):
    ax.plot([cur, cur+36], [ly, ly], color=col, lw=lw_, zorder=8)
    ax.text(cur+44, ly, lbl, fontsize=8.6, color=INK, va="center", zorder=8)
    cur += 44 + len(lbl)*5.9 + 34
t = np.linspace(0, np.pi, 40)
ax.plot(cur + 18 - 18*np.cos(t), ly + 18*np.sin(t), color=GREY, lw=2.0, zorder=8)
ax.text(cur+48, ly, "hop  =  conductors cross, not joined", fontsize=8.6, color=INK,
        va="center", zorder=8)
ground(cur + 400, ly+10, 10)
ax.text(cur+424, ly-4, "GND, bonded to PDB1 star point", fontsize=8.6, color=INK,
        va="center", zorder=8)

# — DETAIL A : airframe plan —
ax.add_patch(patches.Rectangle((110, 95), 560, 390, fc="#FFFFFF", ec=INK, lw=1.6, zorder=6))
ax.add_patch(patches.Rectangle((110, 456), 560, 29, fc=INK, ec=INK, lw=1.6, zorder=7))
ax.text(122, 470.5, "DETAIL A", fontsize=10.5, fontweight="bold", color="#FFFFFF",
        va="center", zorder=8)
ax.text(658, 470.5, "MOTOR PLAN, VIEWED FROM ABOVE", fontsize=10.5, fontweight="bold",
        color="#FFFFFF", ha="right", va="center", zorder=8)
cx, cy, r = 390, 285, 100
ax.add_patch(patches.Rectangle((cx-30, cy-30), 60, 60, fc="#E8EDF3", ec=INK, lw=1.5, zorder=8))
ax.text(cx, cy, "FC1", fontsize=8.4, fontweight="bold", color=INK, ha="center",
        va="center", zorder=9)
ax.annotate("", xy=(cx, cy+r+54), xytext=(cx, cy+36),
            arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.8), zorder=9)
ax.text(cx+12, cy+r+44, "FWD", fontsize=9, fontweight="bold", color=INK, zorder=9)
for sx, sy, ref, rot, prop in ((1, 1, "M1", "CCW", "T9545R"), (-1, -1, "M2", "CCW", "T9545R"),
                               (-1, 1, "M3", "CW", "T9545"), (1, -1, "M4", "CW", "T9545")):
    mx, my = cx + sx*r, cy + sy*r
    ax.plot([cx, mx], [cy, my], color=INK, lw=5, solid_capstyle="round", zorder=7)
    ax.add_patch(patches.Circle((mx, my), 30, fc="#FFFFFF", ec=PHASE, lw=2.2, zorder=8))
    ax.text(mx, my+6, ref, fontsize=9.6, fontweight="bold", color=INK, ha="center",
            va="center", zorder=9)
    ax.text(mx, my-9, rot, fontsize=7.6, color=PHASE, ha="center", va="center", zorder=9)
    sgn = 1 if rot == "CCW" else -1
    tt = np.linspace(0.3, 1.7*np.pi, 60) * sgn
    ax.plot(mx + 42*np.cos(tt), my + 42*np.sin(tt), color=PHASE, lw=1.3, zorder=8)
    ax.annotate("", xy=(mx + 42*np.cos(tt[-1]), my + 42*np.sin(tt[-1])),
                xytext=(mx + 42*np.cos(tt[-5]), my + 42*np.sin(tt[-5])),
                arrowprops=dict(arrowstyle="-|>", color=PHASE, lw=1.3), zorder=9)
    ax.text(mx + sx*74, my + sy*20, prop, fontsize=8.6, fontweight="bold", color=INK,
            ha="center", va="center", zorder=9)
ax.text(390, 112, "T9545R is the reversed (pusher) blade.  A blade fitted to the wrong motor\n"
                  "flips the aircraft on takeoff.",
        fontsize=8.0, color="#B01020", ha="center", va="center", zorder=9)

# — wire schedule —
tx, ty, tw, th = 715, 95, 1200, 390
ax.add_patch(patches.Rectangle((tx, ty), tw, th, fc="#FFFFFF", ec=INK, lw=1.6, zorder=6))
ax.add_patch(patches.Rectangle((tx, ty+th-29), tw, 29, fc=INK, ec=INK, lw=1.6, zorder=7))
ax.text(tx+12, ty+th-14.5, "WIRE SCHEDULE", fontsize=10.5, fontweight="bold",
        color="#FFFFFF", va="center", zorder=8)
ax.text(tx+tw-12, ty+th-14.5, "23 conductors  ·  all GND returns bond to PDB1",
        fontsize=9, color="#FFFFFF", ha="right", va="center", zorder=8)
colx = [(tx+14, "ID"), (tx+84, "FROM"), (tx+255, "TO"), (tx+440, "NET"),
        (tx+576, "CONDUCTOR"), (tx+790, "NOTE")]
yy = ty + th - 46
for x_, lbl in colx:
    ax.text(x_, yy, lbl, fontsize=8.5, fontweight="bold", color=GREY, va="center", zorder=8)
ax.plot([tx+10, tx+tw-10], [yy-10, yy-10], color=RULE, lw=1.0, zorder=7)
rows = [
 ("W01","BT1 XT60","PM1 input","14.8 V","12 AWG silicone","main battery lead"),
 ("W03","PM1 output","PDB1 pad","14.8 V","12 AWG silicone","470 uF at the pad"),
 ("W04","PDB1 pad","ESC1-4 input","14.8 V","14 AWG x 4","11.1 A total at hover"),
 ("W02","PM1 6-pin","FC1 POWER","5.3 V","6p molex","feeds FC1 GPS1 TM1 RX1 only"),
 ("W05-08","FC1 MAIN 1-4","ESC1-4 signal","PWM","3p servo","motor order per DETAIL A"),
 ("W09","OF1 flow","FC1 UART/I2C","flow + range","per datasheet","INDOOR: replaces GPS"),
 ("W10","TM1","FC1 TELEM1","UART","6p","57 600 bps"),
 ("W11","RX1","FC1 RC IN","S.BUS","3p servo","manual override path"),
 ("W12","FC1 TELEM2","PC1 USB-A","MAVLink2","USB-TTL 3.3 V","do NOT land the 5 V wire"),
 ("W13","PDB1 pad","U1 input","14.8 V","16 AWG",""),
 ("W14","PDB1 pad","U3 Vcc","14.8 V","16 AWG","payload motive power"),
 ("W15","U1 output","PC1 J8-2 / J8-6","5.0 V","18 AWG","fit an inline 3 A fuse"),
 ("W16","U1 output","U4 Vcc, LED1 Vcc","5.0 V","18 AWG","1000 uF at LED1"),
 ("W17","5 V rail","U2 Vin","5.0 V","22 AWG",""),
 ("W18","CAM1","PC1 CSI-2","MIPI","15p FPC 200 mm","route clear of the ESC leads"),
 ("W19","PC1 J8-19","U4 A1","SPI0 MOSI","22 AWG","3.3 V in, 5 V out"),
 ("W20","PC1 J8-33","U4 A2","PWM1","22 AWG","actuator speed"),
 ("W21","PC1 J8-31","U4 A3","DIR","22 AWG","extend / retract"),
 ("W22-24","PC1 J8-12/35/40","U2 I2S","I2S","22 AWG x 3","3.3 V direct, no shifter"),
 ("W25","U4 Y1","LED1 DIN","5 V data","22 AWG","470 ohm in series"),
 ("W26-27","U4 Y2, Y3","U3 PWM, DIR","5 V TTL","22 AWG x 2","payload TBD #9"),
 ("W28","U3 output","M5","switched 14.8 V","18 AWG twisted","payload TBD #9"),
 ("W29","U2 output","LS1","audio","speaker pair",""),
]
yy -= 23
for i, r_ in enumerate(rows):
    if i % 2 == 0:
        ax.add_patch(patches.Rectangle((tx+8, yy-7), tw-16, 14.6, fc="#F2F5F9",
                                       ec="none", zorder=6.5))
    for (x_, _), v in zip(colx, r_):
        ax.text(x_, yy, v, fontsize=7.8, color=INK, va="center", zorder=8)
    yy -= 14.6

# — notes —
nx, ny, nw, nh = 1960, 275, 850, 210
ax.add_patch(patches.Rectangle((nx, ny), nw, nh, fc="#FFFFFF", ec=INK, lw=1.6, zorder=6))
ax.add_patch(patches.Rectangle((nx, ny+nh-29), nw, 29, fc="#B01020", ec=INK, lw=1.6, zorder=7))
ax.text(nx+12, ny+nh-14.5, "NOTES  —  READ BEFORE FIRST POWER-UP", fontsize=10.5,
        fontweight="bold", color="#FFFFFF", va="center", zorder=8)
notes = [
 "1.  Bond every GND to the PDB1 star point. Split returns inject switching noise into the PWM lines.",
 "2.  VERIFY: KoA H743 may have built-in voltage/current sensing. Check before buying PM1.",
 "3.  PC1 is fed through J8-2 / J8-6, which bypasses the board polyfuse. Fit an inline 3 A fuse.",
 "4.  3.3 V GPIO sits below the WS2812B VIH of 0.7 x VDD = 3.5 V and below the 5 V TTL",
 "      threshold. U4 is required on W25, W26 and W27.",
 "5.  GPIO18 is the I2S bit clock. It cannot also drive the LED strip or the actuator PWM, and",
 "      GPIO12 shares channel PWM0 with GPIO18, so it is unavailable too.",
 "6.  First spin-up with the propellers removed. Verify rotation against DETAIL A, then fit blades.",
 "7.  INDOOR: ceiling 4.22 m caps altitude at 3.4 m. A 600 mm structure reaches head height.",
 "8.  Clamp LED1 brightness in software. 30 px at full white draws 1.8 A and browns out PC1.",
]
yy = ny + nh - 48
for n in notes:
    ax.text(nx+14, yy, n, fontsize=8.0, color=INK, va="center", zorder=8)
    yy -= 16.4

# — title block / budget —
bx, by, bw, bh = 1960, 95, 850, 165
ax.add_patch(patches.Rectangle((bx, by), bw, bh, fc="#FFFFFF", ec=INK, lw=1.6, zorder=6))
ax.add_patch(patches.Rectangle((bx, by+bh-29), bw, 29, fc=INK, ec=INK, lw=1.6, zorder=7))
ax.text(bx+12, by+bh-14.5, "DESIGN BUDGET", fontsize=10.5, fontweight="bold",
        color="#FFFFFF", va="center", zorder=8)
ax.text(bx+bw-12, by+bh-14.5, "SHEET 1 OF 1   ·   REV C   ·   2026-10-16",
        fontsize=9, color="#FFFFFF", ha="right", va="center", zorder=8)
bud = [("All-up weight", "1 463 g", INK),
       ("Static thrust, 4 x T9545 at 14.8 V", "3 400 g", INK),
       ("Thrust to weight", "2.32 : 1        target 2.0 : 1", V50),
       ("Hover throttle  /  hover current", "43 %   /   11.1 A", INK),
       ("Endurance, 2800 mAh at 80 % DoD", "12.1 min       OK", V50),
       ("Indoor ceiling 4.22 m", "max altitude 3.4 m", AUD),
       ("5 V rail load", "3.15 A of 5.00 A        63 %", V50)]
yy = by + bh - 48
for k, v, c in bud:
    ax.text(bx+16, yy, k, fontsize=8.4, color=GREY, va="center", zorder=8)
    ax.text(bx+bw-16, yy, v, fontsize=8.4, fontweight="bold", color=c, ha="right",
            va="center", zorder=8)
    yy -= 17.5

plt.savefig("/Users/kennytang/shepherdron/shepherdron_wiring_diagram.png",
            facecolor=PAPER, bbox_inches="tight", pad_inches=0.16)
print("saved")
