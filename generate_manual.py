"""Shepherdron 조립 설명서 도면 생성기 (v2).

실제 부품 모양을 그리고 케이블로 이어 붙이는 설명서 형식.
부품 치수와 커넥터 위치는 KoA FC 공식 매뉴얼(koafc.com) 및
T-MOTOR AirGear 355 사양 기준.

텍스트는 영문으로 써서 CJK 폰트 없이도 렌더링된다.
"""
from __future__ import annotations

import math
import pathlib

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.path import Path as MPath

# ── 한글 폰트 등록 (Pretendard) ──────────────────────────────
import matplotlib.font_manager as fm

_FONT_DIR = pathlib.Path.home() / "Library" / "Fonts"
for _f in ("Pretendard-Regular.otf", "Pretendard-Medium.otf",
           "Pretendard-SemiBold.otf", "Pretendard-Bold.otf",
           "Pretendard-ExtraBold.otf"):
    _p = _FONT_DIR / _f
    if _p.exists():
        fm.fontManager.addfont(str(_p))
plt.rcParams["font.family"] = "Pretendard"
plt.rcParams["axes.unicode_minus"] = False

PAPER = "#FBFAF7"
INK, GREY, RULE = "#141C26", "#6E7D8C", "#C3CCD6"
RED, BLK, WHT, YEL, BLU, GRN, ORG = (
    "#D1242F", "#242424", "#F4F4F4", "#E8B300", "#1257A6", "#0E8A45", "#E07B00")
PCB = "#17352B"          # 기판 녹색
PCB_DK = "#0E241C"
GOLD = "#C9A227"
WARN = "#B01020"


# ───────────────────────── 시트 ─────────────────────────
def new_sheet(w, h, title, subtitle, corner):
    fig, ax = plt.subplots(figsize=(w/100, h/100), dpi=150)
    ax.set_facecolor(PAPER); fig.patch.set_facecolor(PAPER)
    ax.set_xlim(0, w); ax.set_ylim(0, h); ax.axis("off")
    ax.add_patch(patches.Rectangle((22, 22), w-44, h-44, fill=False, ec=INK, lw=2.6, zorder=2))
    ax.add_patch(patches.Rectangle((22, h-128), w-44, 106, fc=INK, ec=INK, zorder=3))
    ax.text(56, h-62, title, fontsize=26, fontweight="bold", color="#FFFFFF",
            va="center", zorder=4)
    ax.text(56, h-98, subtitle, fontsize=12.5, color="#A9B6C4", va="center", zorder=4)
    ax.text(w-56, h-75, corner, fontsize=12, color="#A9B6C4", ha="right",
            va="center", zorder=4)
    return fig, ax


def panel(ax, x, y, w, h, num, title, accent=INK, fc="#FFFFFF"):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=10",
                 fc=fc, ec=RULE, lw=1.6, zorder=4))
    ax.add_patch(patches.Circle((x+34, y+h-32), 19, fc=accent, ec="none", zorder=6))
    ax.text(x+34, y+h-32, str(num), fontsize=14, fontweight="bold", color="#FFFFFF",
            ha="center", va="center", zorder=7)
    ax.text(x+66, y+h-32, title, fontsize=14.5, fontweight="bold", color=INK,
            va="center", zorder=6)
    ax.plot([x+20, x+w-20], [y+h-58, y+h-58], color=RULE, lw=1.2, zorder=6)


def note(ax, x, y, w, h, title, lines, col=WARN):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=7",
                 fc="#FFF5F5" if col == WARN else "#F2F8FF", ec=col, lw=1.6, zorder=8))
    ax.add_patch(patches.Circle((x+26, y+h-26), 12, fc=col, ec="none", zorder=9))
    ax.text(x+26, y+h-26, "!", fontsize=12, fontweight="bold", color="#FFFFFF",
            ha="center", va="center", zorder=10)
    ax.text(x+48, y+h-26, title, fontsize=11, fontweight="bold", color=col,
            va="center", zorder=9)
    for i, ln in enumerate(lines):
        ax.text(x+22, y+h-56-i*23, ln, fontsize=9.6, color=INK, zorder=9)


# ───────────────────────── 부품 그림 ─────────────────────────
def jst(ax, x, y, n, label="", vertical=False, col="#E8E4D8", fs=7.4,
        side="top", s=1.0):
    """JST-GH 커넥터. n핀."""
    pitch, pw = 7.5*s, 5.2*s
    w = n * pitch + 7*s
    d = 17*s
    if vertical:
        ax.add_patch(patches.Rectangle((x, y), d, w, fc=col, ec=INK, lw=1.1, zorder=12))
        for i in range(n):
            ax.add_patch(patches.Rectangle((x+4*s, y+5*s+i*pitch), 9*s, pw*0.7,
                                           fc="#9A9A9A", ec="none", zorder=13))
    else:
        ax.add_patch(patches.Rectangle((x, y), w, d, fc=col, ec=INK, lw=1.1, zorder=12))
        for i in range(n):
            ax.add_patch(patches.Rectangle((x+5*s+i*pitch, y+4*s), pw*0.7, 9*s,
                                           fc="#9A9A9A", ec="none", zorder=13))
    if label:
        if side == "top":
            ax.text(x + w/2, y + d + 6*s, label, fontsize=fs, fontweight="bold",
                    color=INK, ha="center", va="bottom", zorder=13)
        else:
            ax.text(x + w/2, y - 7*s, label, fontsize=fs, fontweight="bold",
                    color=INK, ha="center", va="top", zorder=13)
    return w


def board(ax, x, y, w, h, holes=True, dark=False):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=6",
                 fc=PCB_DK if dark else PCB, ec="#0A1A14", lw=1.6, zorder=10))
    if holes:
        for hx, hy in ((x+14, y+14), (x+w-14, y+14), (x+14, y+h-14), (x+w-14, y+h-14)):
            ax.add_patch(patches.Circle((hx, hy), 6.5, fc=PAPER, ec=GOLD, lw=1.6, zorder=11))


def wires(ax, pts, cols, spread=5, lw=3.0):
    """여러 가닥 케이블. cols 순서대로 나란히."""
    xs, ys = zip(*pts)
    n = len(cols)
    for i, c in enumerate(cols):
        off = (i - (n-1)/2) * spread
        # 수평 우세 구간은 y 로, 수직 우세 구간은 x 로 오프셋
        ox = [0.0]*len(pts); oy = [0.0]*len(pts)
        for k in range(len(pts)):
            a = pts[max(0, k-1)]; b = pts[min(len(pts)-1, k+1)]
            if abs(b[0]-a[0]) >= abs(b[1]-a[1]):
                oy[k] = off
            else:
                ox[k] = off
        ax.plot([p[0]+ox[k] for k, p in enumerate(pts)],
                [p[1]+oy[k] for k, p in enumerate(pts)],
                color=c, lw=lw, zorder=9, solid_capstyle="round",
                solid_joinstyle="round")


def cable(ax, pts, col, lw=4.5, label="", lx=None, ly=None, fs=9.0, dash=None):
    xs, ys = zip(*pts)
    kw = {"dashes": dash} if dash else {}
    ax.plot(xs, ys, color=col, lw=lw, zorder=9, solid_capstyle="round",
            solid_joinstyle="round", **kw)
    if label:
        mx = lx if lx is not None else (xs[len(xs)//2])
        my = ly if ly is not None else (ys[len(ys)//2])
        ax.text(mx, my, label, fontsize=fs, fontweight="bold", color=col,
                ha="center", va="center", zorder=14,
                bbox=dict(boxstyle="round,pad=0.26", fc=PAPER, ec=col, lw=1.0))


def callout(ax, x, y, n, col=INK, r=15):
    ax.add_patch(patches.Circle((x, y), r, fc=col, ec="#FFFFFF", lw=2, zorder=16))
    ax.text(x, y, str(n), fontsize=11, fontweight="bold", color="#FFFFFF",
            ha="center", va="center", zorder=17)


def caption(ax, x, y, text, fs=10, col=INK, weight="bold", ha="center"):
    ax.text(x, y, text, fontsize=fs, fontweight=weight, color=col,
            ha=ha, va="center", zorder=15)


# ═══════════════════════ 부품 일러스트 ═══════════════════════
def _poly(ax, pts, fc, ec=INK, lw=1.4, z=10, alpha=1.0):
    ax.add_patch(patches.Polygon(pts, closed=True, fc=fc, ec=ec, lw=lw,
                                 zorder=z, alpha=alpha))


def _arm(ax, cx, cy, ang, length, width, col, inner=16):
    a = math.radians(ang)
    ux, uy = math.cos(a), math.sin(a)
    px, py = -uy, ux
    p1 = (cx + ux*inner + px*width/2, cy + uy*inner + py*width/2)
    p2 = (cx + ux*length + px*width/2, cy + uy*length + py*width/2)
    p3 = (cx + ux*length - px*width/2, cy + uy*length - py*width/2)
    p4 = (cx + ux*inner - px*width/2, cy + uy*inner - py*width/2)
    _poly(ax, [p1, p2, p3, p4], col, z=8)
    return (cx + ux*length, cy + uy*length)


def dr_motor(ax, cx, cy, s=1.0, wires_dir=None, label=True, num=None):
    """AIR2213 KV1000 아웃러너 상면도."""
    R = 26*s
    ax.add_patch(patches.Circle((cx, cy), R, fc="#2F3640", ec=INK, lw=1.6, zorder=11))
    ax.add_patch(patches.Circle((cx, cy), R*0.74, fc="#4A5560", ec="#2F3640",
                                lw=1.2, zorder=12))
    for k in range(6):
        a = math.radians(k*60 + 15)
        ax.add_patch(patches.Circle((cx + math.cos(a)*R*0.52,
                                     cy + math.sin(a)*R*0.52), R*0.12,
                                    fc="#1A1F26", ec="none", zorder=13))
    ax.add_patch(patches.Circle((cx, cy), R*0.2, fc=GOLD, ec="#8A6E1B",
                                lw=1.0, zorder=14))
    tips = []
    if wires_dir is not None:
        a = math.radians(wires_dir)
        for i in range(3):
            off = (i-1)*R*0.30
            x0 = cx + math.cos(a)*R*0.9 - math.sin(a)*off
            y0 = cy + math.sin(a)*R*0.9 + math.cos(a)*off
            x1 = cx + math.cos(a)*(R+30*s) - math.sin(a)*off
            y1 = cy + math.sin(a)*(R+30*s) + math.cos(a)*off
            ax.plot([x0, x1], [y0, y1], color="#6A3A00", lw=2.6*s,
                    zorder=10, solid_capstyle="round")
            tips.append((x1, y1))
    if num is not None:
        callout(ax, cx, cy, num, col=INK, r=13*s)
    if label:
        caption(ax, cx, cy - R - 16*s, "AIR2213 KV1000", fs=8.2)
    return tips


def dr_prop(ax, cx, cy, s=1.0, ang=0.0, cw=True):
    """MF9545 폴딩 프로펠러."""
    for sgn in (1, -1):
        a = math.radians(ang) + (0 if sgn > 0 else math.pi)
        L, W = 56*s, 9*s
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        pts = [(cx + ux*9 + px*W*0.5, cy + uy*9 + py*W*0.5),
               (cx + ux*L*0.6 + px*W*1.15, cy + uy*L*0.6 + py*W*1.15),
               (cx + ux*L + px*W*0.35, cy + uy*L + py*W*0.35),
               (cx + ux*L - px*W*0.3, cy + uy*L - py*W*0.3),
               (cx + ux*L*0.5 - px*W*0.8, cy + uy*L*0.5 - py*W*0.8),
               (cx + ux*9 - px*W*0.5, cy + uy*9 - py*W*0.5)]
        _poly(ax, pts, "#30343B", ec="#15181C", lw=1.0, z=16)
    ax.add_patch(patches.Circle((cx, cy), 9*s, fc="#5A6270", ec=INK, lw=1.2, zorder=17))
    # 회전 방향 화살표 (거의 한 바퀴)
    r = 74*s
    a0, a1 = (125, -145) if cw else (55, 325)
    th = np.radians(np.linspace(a0, a1, 90))
    ax.plot(cx + r*np.cos(th), cy + r*np.sin(th), color="#8A96A4", lw=2.4,
            zorder=9, solid_capstyle="round")
    ax.annotate("", xy=(cx + r*math.cos(th[-1]), cy + r*math.sin(th[-1])),
                xytext=(cx + r*math.cos(th[-4]), cy + r*math.sin(th[-4])),
                arrowprops=dict(arrowstyle="-|>,head_width=0.38,head_length=0.7",
                                color="#8A96A4", lw=2.4), zorder=9)
    ax.text(cx, cy + r + 20*s, "CW (시계)" if cw else "CCW (반시계)",
            fontsize=9.6, fontweight="bold", color="#5A6672",
            ha="center", va="center", zorder=15)


def dr_esc(ax, x, y, s=1.0, label="AIR 20A ESC"):
    """AIR 20A ESC. 반환: {"in":[+,-], "out":[상1,상2,상3]} 결선점."""
    w, h = 86*s, 34*s
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=4",
                 fc="#262B33", ec=INK, lw=1.5, zorder=11))
    ax.add_patch(patches.Rectangle((x+8*s, y+h*0.56), w-16*s, h*0.30,
                                   fc="#3A424D", ec="none", zorder=12))
    ax.text(x + w/2, y + h*0.28, "20A", fontsize=8.5*s, fontweight="bold",
            color="#C8D0DA", ha="center", va="center", zorder=13)
    ins, outs = [], []
    for i, c in enumerate((RED, BLK)):
        yy = y + h*0.5 + (0.5 - i) * h*0.44
        ax.plot([x-26*s, x], [yy, yy], color=c, lw=3.2*s, zorder=10,
                solid_capstyle="round")
        ins.append((x - 26*s, yy))
    for k in range(3):
        yy = y + h*0.5 + (1 - k) * h*0.30
        ax.plot([x+w, x+w+26*s], [yy, yy], color="#6A3A00", lw=2.8*s, zorder=10,
                solid_capstyle="round")
        outs.append((x + w + 26*s, yy))
    if label:
        caption(ax, x + w/2, y - 13*s, label, fs=8.4)
    return {"in": ins, "out": outs}


def dr_fc(ax, x, y, s=1.0, detail=True, front_labels=True):
    """KoA FC H743. 전면(POWER/PWM/RC/GPS) · 후면(TELEM1/TELEM2).

    반환: 커넥터 이름 -> 케이블 출구 좌표.
    """
    w, h = 300*s, 210*s
    board(ax, x, y, w, h)
    ax.text(x + w/2, y + h*0.64, "KoA FC", fontsize=15*s, fontweight="bold",
            color="#CFE3D8", ha="center", va="center", zorder=12)
    ax.text(x + w/2, y + h*0.52, "STM32H743", fontsize=9*s, color="#7FA893",
            ha="center", va="center", zorder=12)
    ax.add_patch(patches.Rectangle((x+w*0.40, y+h*0.26), w*0.20, h*0.15,
                 fc="#0A1A14", ec="#2E5A48", lw=1.0, zorder=12))
    ax.text(x+w*0.50, y+h*0.335, "IMU", fontsize=7.4*s, color="#7FA893",
            ha="center", va="center", zorder=13)
    ports = {}
    jh = 17*s
    # ── 전면(하단): POWER(8) PWM(10) RC(5) GPS(6) ──────────
    front = [("POWER", 6, RED), ("PWM", 10, YEL), ("RC", 4, BLU), ("GPS", 6, GRN)]
    widths = [n*7.5*s + 7*s for _, n, _ in front]
    gap = (w - 16*s - sum(widths)) / (len(front) - 1)
    cx = x + 8*s
    for (name, n, col), cw_ in zip(front, widths):
        jst(ax, cx, y - jh, n, "", col="#E8E4D8", s=s)
        if front_labels:
            ax.text(cx + cw_/2, y - jh - 7*s, name, fontsize=8.0*s,
                    fontweight="bold", color=col, ha="center", va="top", zorder=13)
            ax.text(cx + cw_/2, y - jh - 22*s, f"{n}핀", fontsize=6.8*s,
                    color=GREY, ha="center", va="top", zorder=13)
        ports[name] = (cx + cw_/2, y - jh)
        cx += cw_ + gap
    # ── 후면(상단): TELEM2 / TELEM1 ───────────────────────
    cx = x + w - 10*s
    for name, n, col in (("TELEM2", 6, ORG), ("TELEM1", 6, "#9A5BD1")):
        cw_ = n*7.5*s + 7*s
        cx -= cw_
        jst(ax, cx, y + h, n, "", col="#E8E4D8", s=s)
        ax.text(cx + cw_/2, y + h + jh + 7*s, name, fontsize=8.0*s,
                fontweight="bold", color=col, ha="center", va="bottom", zorder=13)
        ports[name] = (cx + cw_/2, y + h + jh)
        cx -= 18*s
    # ── 좌측: I2C(4) ──────────────────────────────────────
    iy = y + h*0.52
    jst(ax, x - jh, iy, 4, "", vertical=True, col="#E8E4D8", s=s)
    ax.text(x - jh - 8*s, iy + (4*7.5*s+7*s)/2, "I2C", fontsize=8.0*s,
            fontweight="bold", color="#1AA6A6", ha="right", va="center", zorder=13)
    ports["I2C"] = (x - jh, iy + (4*7.5*s+7*s)/2)
    # ── 우측: USB-C + microSD ─────────────────────────────
    uy = y + h*0.68
    ax.add_patch(patches.FancyBboxPatch((x + w - 2*s, uy), 16*s, 26*s,
                 boxstyle="round,pad=0,rounding_size=5",
                 fc="#8C949E", ec=INK, lw=1.1, zorder=12))
    ax.text(x + w + 22*s, uy + 13*s, "USB-C", fontsize=7.6*s, color=GREY,
            ha="left", va="center", zorder=13)
    ports["USB"] = (x + w + 14*s, uy + 13*s)
    sy = y + h*0.22
    ax.add_patch(patches.Rectangle((x + w - 2*s, sy), 14*s, 30*s,
                 fc="#A8AEB6", ec=INK, lw=1.0, zorder=12))
    ax.text(x + w + 20*s, sy + 15*s, "microSD", fontsize=7.6*s, color=GREY,
            ha="left", va="center", zorder=13)
    if detail:
        caption(ax, x + w/2, y + h + jh + 46*s,
                "KoA FC H743  ·  36x36mm  ·  30.5mm 마운트", fs=9.2, col=GREY)
    return ports


def dr_pi(ax, x, y, s=1.0, labels=True):
    """Raspberry Pi 4 상면도. 반환: 핀헤더/CSI/USB 좌표."""
    w, h = 300*s, 198*s
    board(ax, x, y, w, h, dark=True)
    # 40핀 GPIO 헤더
    hx, hy = x + 24*s, y + h - 30*s
    hw, hh = w - 60*s, 20*s
    ax.add_patch(patches.Rectangle((hx, hy), hw, hh, fc="#14181C", ec=INK,
                                   lw=1.2, zorder=12))
    for i in range(20):
        for r in range(2):
            ax.add_patch(patches.Rectangle(
                (hx + 5*s + i*(hw - 10*s)/20, hy + 4*s + r*8*s),
                3.4*s, 4.2*s, fc=GOLD, ec="none", zorder=13))
    if labels:
        ax.text(hx, hy + hh + 9*s, "40핀 GPIO 헤더", fontsize=9.0,
                fontweight="bold", color=INK, ha="left", va="bottom", zorder=13)
    # SoC
    ax.add_patch(patches.Rectangle((x + w*0.33, y + h*0.40), 54*s, 54*s,
                 fc="#1C2A33", ec="#3A5A68", lw=1.2, zorder=12))
    ax.text(x + w*0.33 + 27*s, y + h*0.40 + 27*s, "BCM\n2711",
            fontsize=6.8*s, color="#7FA893", ha="center", va="center",
            zorder=13, linespacing=1.4)
    # USB x4 (우측)
    for i in range(2):
        ax.add_patch(patches.Rectangle((x + w - 4*s, y + 26*s + i*54*s),
                     18*s, 44*s, fc="#8C949E", ec=INK, lw=1.0, zorder=12))
    if labels:
        ax.text(x + w + 20*s, y + 76*s, "USB", fontsize=7.4*s, color=GREY,
                ha="left", va="center", zorder=13)
    # Ethernet
    ax.add_patch(patches.Rectangle((x + w - 4*s, y + h - 76*s), 20*s, 40*s,
                 fc="#5A6270", ec=INK, lw=1.0, zorder=12))
    # USB-C 전원 (좌하)
    ax.add_patch(patches.FancyBboxPatch((x - 14*s, y + 22*s), 16*s, 22*s,
                 boxstyle="round,pad=0,rounding_size=5",
                 fc="#8C949E", ec=INK, lw=1.0, zorder=12))
    if labels:
        ax.text(x - 22*s, y + 33*s, "USB-C\n전원", fontsize=8.0, color=GREY,
                ha="right", va="center", zorder=13, linespacing=1.4)
    # CSI 카메라 (좌상)
    ax.add_patch(patches.Rectangle((x + 8*s, y + h*0.52), 11*s, 46*s,
                 fc="#D8D2C2", ec=INK, lw=1.0, zorder=12))
    if labels:
        ax.text(x + 26*s, y + h*0.52 + 23*s, "CSI", fontsize=8.4,
                fontweight="bold", color="#A9D4BD", ha="left", va="center",
                zorder=13)
        caption(ax, x + w/2, y - 16, "Raspberry Pi 4", fs=9.6, col=GREY)
    return {"gpio": (hx, hy + hh/2), "gpio_w": hw, "gpio_x": hx,
            "usbc": (x - 14*s, y + 33*s), "csi": (x + 13*s, y + h*0.52 + 23*s),
            "usb": (x + w + 14*s, y + 76*s)}


def dr_battery(ax, x, y, s=1.0):
    w, h = 210*s, 96*s
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=8",
                 fc="#1E2A38", ec=INK, lw=1.8, zorder=11))
    for i in range(4):
        ax.plot([x + 16 + i*(w-32)/4]*2, [y+8, y+h-8], color="#2E3C4C", lw=1.0,
                zorder=12)
    ax.text(x + w/2, y + h*0.66, "4S  14.8V", fontsize=13*s, fontweight="bold",
            color="#E8EDF3", ha="center", va="center", zorder=13)
    ax.text(x + w/2, y + h*0.34, "2800mAh  50C", fontsize=9*s, color="#8FA3B8",
            ha="center", va="center", zorder=13)
    # XT60 수 커넥터
    cxx = x + w + 10*s
    for i, c in enumerate((RED, BLK)):
        ax.plot([x+w-6*s, cxx+6*s], [y+h*(0.64-i*0.28)]*2, color=c, lw=4.2,
                zorder=10, solid_capstyle="round")
    ax.add_patch(patches.Polygon([(cxx, y+h*0.24), (cxx+44*s, y+h*0.24),
                                  (cxx+52*s, y+h*0.5), (cxx+44*s, y+h*0.76),
                                  (cxx, y+h*0.76)], closed=True,
                 fc="#E8C33A", ec=INK, lw=1.4, zorder=12))
    ax.text(cxx+24*s, y+h*0.5, "XT60", fontsize=8.0*s, fontweight="bold",
            color=INK, ha="center", va="center", zorder=13)
    for i, c in enumerate((RED, BLK)):
        ax.plot([cxx+52*s, cxx+92*s], [y+h*(0.64-i*0.28)]*2, color=c, lw=4.2,
                zorder=10, solid_capstyle="round")
    caption(ax, x + w/2, y - 16*s, "PT-B2800N-FX50", fs=9.2, col=GREY)
    return {"+": (cxx + 92*s, y + h*0.64),
            "-": (cxx + 92*s, y + h*0.36)}


def dr_rx(ax, x, y, s=1.0):
    """R86C V2 수신기: 소형 기판 + 안테나 2 + 서보 헤더."""
    w, h = 96*s, 48*s
    board(ax, x, y, w, h, holes=False)
    ax.text(x + w/2, y + h*0.60, "R86C V2", fontsize=8.6*s, fontweight="bold",
            color="#CFE3D8", ha="center", va="center", zorder=12)
    ax.text(x + w/2, y + h*0.30, "CC2500 / D16", fontsize=6.8*s, color="#7FA893",
            ha="center", va="center", zorder=12)
    for i, ang in enumerate((150, 210)):
        a = math.radians(ang)
        ax.plot([x, x + math.cos(a)*54*s], [y+h*(0.72-i*0.44),
                y + h*(0.72-i*0.44) + math.sin(a)*22*s],
                color="#9A6A3A", lw=2.2, zorder=10, solid_capstyle="round")
    ax.text(x - 44*s, y + h/2, "안테나 x2", fontsize=6.8*s, color=GREY,
            ha="center", va="center", zorder=13)
    jst(ax, x + w - 34*s, y + h, 3, "SBUS", col="#E8E4D8", fs=6.8*s, s=s)
    caption(ax, x + w/2, y - 14*s, "조종기 수신기", fs=8.6, col=GREY)
    return (x + w - 34*s + (3*7.5*s+7*s)/2, y + h + 17*s)


def dr_gps(ax, x, y, s=1.0):
    """M10 GPS + 나침반 퍽 + 마스트."""
    R = 40*s
    ax.add_patch(patches.Rectangle((x - 4*s, y - 46*s), 8*s, 46*s, fc="#3A424D",
                 ec=INK, lw=1.0, zorder=10))
    ax.add_patch(patches.Circle((x, y + R*0.1), R, fc="#20262E", ec=INK,
                                lw=1.6, zorder=11))
    ax.add_patch(patches.Rectangle((x - R*0.6, y - R*0.35), R*1.2, R*1.0,
                 fc="#D8D2C2", ec="#8A8578", lw=1.2, zorder=12))
    ax.text(x, y + R*0.15, "GPS", fontsize=8.2*s, fontweight="bold", color=INK,
            ha="center", va="center", zorder=13)
    # 방향 화살표 (전방 표시)
    ax.annotate("", xy=(x, y + R + 18*s), xytext=(x, y + R*0.75),
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=2.0), zorder=14)
    ax.text(x + 8*s, y + R + 12*s, "전방", fontsize=7.2*s, fontweight="bold",
            color=RED, ha="left", va="center", zorder=14)
    ax.plot([x + 2*s, x + R*0.5 + 10*s], [y - 40*s, y - 49*s],
            color="#5A6270", lw=2.6, zorder=10, solid_capstyle="round")
    jst(ax, x + R*0.5, y - 58*s, 6, "", col="#E8E4D8", s=s)
    caption(ax, x, y - 80*s, "GPS + 나침반", fs=8.6, col=GREY)
    return (x + R*0.5 + (6*7.5*s+7*s)/2, y - 58*s)


def dr_flow(ax, x, y, s=1.0):
    """광류 센서 + 거리계 (하향)."""
    w, h = 74*s, 58*s
    board(ax, x, y, w, h, holes=False)
    ax.add_patch(patches.Circle((x + w*0.32, y + h*0.45), 11*s, fc="#101418",
                 ec="#4A5560", lw=1.4, zorder=12))
    ax.add_patch(patches.Circle((x + w*0.32, y + h*0.45), 5*s, fc="#2A6AD6",
                 ec="none", zorder=13))
    ax.add_patch(patches.Circle((x + w*0.70, y + h*0.45), 8*s, fc="#2A0A0A",
                 ec="#6A2020", lw=1.2, zorder=12))
    ax.text(x + w*0.32, y + h*0.80, "광류", fontsize=6.4*s, color="#A9D4BD",
            ha="center", va="center", zorder=13)
    ax.text(x + w*0.70, y + h*0.80, "ToF", fontsize=6.4*s, color="#A9D4BD",
            ha="center", va="center", zorder=13)
    jst(ax, x + w/2 - 20*s, y + h, 4, "", col="#E8E4D8", s=s)
    caption(ax, x + w/2, y - 14*s, "광류 + 거리계", fs=8.6, col=GREY)
    return (x + w/2 - 20*s + (4*7.5*s+7*s)/2, y + h + 17*s)


def dr_ubec(ax, x, y, s=1.0, labels=True):
    """5V 5A UBEC: 수축 블록, 입력 2선, 출력 2선."""
    w, h = 90*s, 40*s
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=4",
                 fc="#1C2026", ec=INK, lw=1.5, zorder=11))
    ax.text(x + w/2, y + h*0.62, "UBEC", fontsize=9.6*s, fontweight="bold",
            color="#E8EDF3", ha="center", va="center", zorder=12)
    ax.text(x + w/2, y + h*0.28, "5V / 5A", fontsize=7.8*s, color="#8FA3B8",
            ha="center", va="center", zorder=12)
    for i, c in enumerate((RED, BLK)):
        ax.plot([x-30, x], [y + h*(0.68-i*0.36)]*2, color=c, lw=3.4, zorder=10,
                solid_capstyle="round")
        ax.plot([x+w, x+w+30], [y + h*(0.68-i*0.36)]*2, color=c, lw=3.0,
                zorder=10, solid_capstyle="round")
    if labels:
        ax.text(x - 36, y + h/2, "IN\n14.8V", fontsize=6.8*s, color=GREY,
                ha="right", va="center", zorder=13, linespacing=1.4)
        ax.text(x + w + 36, y + h/2, "OUT\n5V", fontsize=6.8*s, color=GREY,
                ha="left", va="center", zorder=13, linespacing=1.4)
    return (x - 30, y + h/2), (x + w + 30, y + h/2)


def dr_pdb(ax, x, y, s=1.0, labels=True):
    """전원 분배 지점: F450 하단판 PDB."""
    w, h = 150*s, 110*s
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=6",
                 fc="#8A1414", ec=INK, lw=1.6, zorder=11))
    if labels:
        ax.text(x + w/2, y + h - 18*s, "전원 분배", fontsize=9.6*s,
                fontweight="bold", color="#FFE8E8", ha="center",
                va="center", zorder=13)
        ax.text(x + w/2, y + h - 33*s, "F450 하단판 PDB", fontsize=7.0*s,
                color="#F0B8B8", ha="center", va="center", zorder=13)
    pads = []
    for r in range(2):
        for c in range(4):
            px_ = x + 24*s + c*(w - 48*s)/3
            py_ = y + 22*s + r*30*s
            ax.add_patch(patches.Circle((px_, py_), 8.5*s,
                         fc=RED if r == 1 else "#2A2A2A",
                         ec=GOLD, lw=1.4, zorder=13))
            pads.append((px_, py_))
    ax.text(x - 10*s, y + 52*s, "+", fontsize=12*s, fontweight="bold", color=RED,
            ha="right", va="center", zorder=13)
    ax.text(x - 10*s, y + 22*s, "-", fontsize=14*s, fontweight="bold", color=INK,
            ha="right", va="center", zorder=13)
    return pads


def dr_camera(ax, x, y, s=1.0):
    """Camera Module 3 Wide + 리본 케이블."""
    w, h = 62*s, 62*s
    board(ax, x, y, w, h, holes=False)
    ax.add_patch(patches.Circle((x + w/2, y + h*0.55), 17*s, fc="#14181C",
                 ec="#4A5560", lw=1.6, zorder=12))
    ax.add_patch(patches.Circle((x + w/2, y + h*0.55), 10*s, fc="#1E3A5A",
                 ec="none", zorder=13))
    ax.add_patch(patches.Circle((x + w/2 - 3*s, y + h*0.55 + 3*s), 3.4*s,
                 fc="#9AC8E8", ec="none", zorder=14))
    ax.add_patch(patches.Rectangle((x + w*0.2, y - 9*s), w*0.6, 10*s, fc="#D8D2C2",
                 ec="#8A8578", lw=1.0, zorder=10))
    caption(ax, x + w/2, y - 24*s, "Camera Module 3 Wide", fs=8.0, col=GREY)
    return (x + w/2, y - 9*s)


def dr_tx(ax, x, y, s=1.0):
    """RadioMaster Pocket 조종기."""
    w, h = 150*s, 108*s
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=12",
                 fc="#23272E", ec=INK, lw=1.8, zorder=11))
    ax.add_patch(patches.Rectangle((x + w*0.33, y + h*0.56), w*0.34, h*0.30,
                 fc="#4A6A8A", ec=INK, lw=1.1, zorder=12))
    for sgn in (0, 1):
        ccx = x + w*(0.17 + sgn*0.66)
        ax.add_patch(patches.Circle((ccx, y + h*0.40), 19, fc="#161A20",
                     ec="#3A424D", lw=1.4, zorder=12))
        ax.add_patch(patches.Circle((ccx, y + h*0.40), 8, fc="#5A6270",
                     ec=INK, lw=1.0, zorder=13))
    caption(ax, x + w/2, y - 14, "RadioMaster Pocket (CC2500)", fs=8.4, col=GREY)


def dr_f450(ax, cx, cy, s=1.0, motor_nums=True):
    """F450 X 배치 상면도. 반환: 모터 중심 좌표 리스트 (M1..M4)."""
    L, W = 150*s, 30*s
    ends = {}
    # ArduPilot X 배치: M1=전우, M2=후좌, M3=전좌, M4=후우
    spec = [(45, "M1", "#C8252B", False), (225, "M2", "#E8E4DC", False),
            (135, "M3", "#C8252B", True), (315, "M4", "#E8E4DC", True)]
    for ang, name, col, cw in spec:
        ends[name] = (_arm(ax, cx, cy, ang, L, W, col), cw)
    # 하단판 / 상단판
    ax.add_patch(patches.FancyBboxPatch((cx-52*s, cy-52*s), 104*s, 104*s,
                 boxstyle="round,pad=0,rounding_size=12",
                 fc="#8A1414", ec=INK, lw=1.6, zorder=9))
    ax.add_patch(patches.FancyBboxPatch((cx-44*s, cy-44*s), 88*s, 88*s,
                 boxstyle="round,pad=0,rounding_size=10",
                 fc="#A81A1A", ec=INK, lw=1.4, zorder=10))
    ax.text(cx, cy, "F450", fontsize=11*s, fontweight="bold", color="#FFE0E0",
            ha="center", va="center", zorder=11)
    # 전방 화살표
    ax.annotate("", xy=(cx, cy + L + 46*s), xytext=(cx, cy + L*0.78),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=2.6), zorder=14)
    ax.text(cx + 12, cy + L + 36*s, "전방", fontsize=10*s, fontweight="bold",
            color=INK, ha="left", va="center", zorder=14)
    return ends


import contextlib


@contextlib.contextmanager
def no_caption():
    """일러스트 자체 캡션을 끄고 타일 캡션만 쓴다."""
    global caption
    _old = caption
    caption = lambda *a, **k: None          # noqa: E731
    try:
        yield
    finally:
        caption = _old


def tile(ax, x, y, w, h, ref, qty, name, spec, mount, draw, have=True):
    """부품 식별 타일."""
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=9",
                 fc="#FFFFFF", ec=RULE, lw=1.5, zorder=4))
    # 상태 띠
    stat_c = GRN if have else ORG
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=9",
                 fc="none", ec=stat_c, lw=0.0, zorder=4))
    ax.add_patch(patches.Rectangle((x, y + h - 36), w, 36, fc="#F2F5F8",
                 ec="none", zorder=5))
    ax.plot([x, x + w], [y + h - 36]*2, color=RULE, lw=1.2, zorder=6)
    ax.add_patch(patches.FancyBboxPatch((x + 12, y + h - 29), 34, 22,
                 boxstyle="round,pad=0,rounding_size=5",
                 fc=INK, ec="none", zorder=6))
    ax.text(x + 29, y + h - 18, ref, fontsize=10, fontweight="bold",
            color="#FFFFFF", ha="center", va="center", zorder=7)
    ax.text(x + 56, y + h - 18, name, fontsize=11.4, fontweight="bold",
            color=INK, va="center", zorder=7)
    ax.add_patch(patches.FancyBboxPatch((x + w - 58, y + h - 29), 46, 22,
                 boxstyle="round,pad=0,rounding_size=5",
                 fc=stat_c, ec="none", zorder=6))
    ax.text(x + w - 35, y + h - 18, qty, fontsize=10, fontweight="bold",
            color="#FFFFFF", ha="center", va="center", zorder=7)
    # 일러스트
    with no_caption():
        draw(ax)
    # 하단 정보
    ax.plot([x + 14, x + w - 14], [y + 62]*2, color="#E4E9EE", lw=1.2, zorder=6)
    ax.text(x + 16, y + 44, spec, fontsize=9.0, color=INK, va="center", zorder=7)
    ax.text(x + 16, y + 22, "장착 : " + mount, fontsize=8.6, color=GREY,
            va="center", zorder=7)


def sheet1():
    w, h = 1760, 1580
    fig, ax = new_sheet(w, h, "1. 부품 식별",
                        "조립 전에 모든 부품이 있는지 이 표로 먼저 확인한다",
                        "Shepherdron  ·  1/4")
    cols, rows = 4, 3
    gx, gy = 44, 76
    tw = (w - 2*gx - (cols-1)*18) / cols
    th = (h - 150 - gy - (rows-1)*18) / rows
    C = 0.53                                  # 일러스트 영역 중심 비율

    def pos(i):
        r, c = divmod(i, cols)
        return gx + c*(tw+18), h - 150 - (r+1)*th - r*18

    items = [
        ("A1", "x1", "F450 프레임", "휠베이스 450mm · 암 4개", "기체 본체",
         lambda a, X, Y: dr_f450(a, X+tw/2, Y+th*0.50, s=0.82), True),
        ("A2", "x4", "AIR2213 모터", "KV1000 · 14.8V · 아웃러너", "암 끝단 4곳",
         lambda a, X, Y: dr_motor(a, X+tw/2, Y+th*0.58, s=2.2, wires_dir=270), True),
        ("A3", "x4", "AIR 20A ESC", "20A · BLHeli_S · 2-4S", "암 하단",
         lambda a, X, Y: dr_esc(a, X+tw/2-82, Y+th*C-32, s=1.9, label=None), True),
        ("A4", "x4", "MF9545 프로펠러", "9.5x4.5 폴딩 · CW 2 / CCW 2", "모터 축",
         lambda a, X, Y: dr_prop(a, X+tw/2, Y+th*0.50, s=1.40, cw=True), True),
        ("B1", "x1", "KoA FC H743", "STM32H743 · 36x36mm", "상단판 중앙",
         lambda a, X, Y: dr_fc(a, X+tw/2-138, Y+th*0.34, s=0.92, detail=False), True),
        ("B2", "x2", "4S 배터리", "14.8V 2800mAh 50C", "하단판 하면",
         lambda a, X, Y: dr_battery(a, X+tw/2-196, Y+th*C-50, s=1.05), True),
        ("B3", "x1", "조종기", "RadioMaster Pocket · CC2500", "조종자 휴대",
         lambda a, X, Y: dr_tx(a, X+tw/2-139, Y+th*C-100, s=1.85), True),
        ("B4", "x1", "수신기", "R86C V2 · D16 · SBUS 출력", "상단판 후방",
         lambda a, X, Y: dr_rx(a, X+tw/2-56, Y+th*C-43, s=1.8), True),
        ("C1", "x1", "Raspberry Pi 4", "4GB · 임무 컴퓨터", "상단판 위 스탠드오프",
         lambda a, X, Y: dr_pi(a, X+tw/2-138, Y+th*C-91, s=0.92), True),
        ("C2", "x1", "카메라", "Camera Module 3 Wide · 102도", "전방 하향 45도",
         lambda a, X, Y: dr_camera(a, X+tw/2-81, Y+th*C-70, s=2.6), False),
        ("C3", "x1", "GPS + 나침반", "M10 · 외장 나침반 필수", "마스트 상단",
         lambda a, X, Y: dr_gps(a, X+tw/2, Y+th*C, s=1.6), False),
        ("C4", "x1", "광류 + 거리계", "실내 위치 유지용", "하단판 하면 하향",
         lambda a, X, Y: dr_flow(a, X+tw/2-85, Y+th*C-67, s=2.3), False),
    ]
    for i, (ref, qty, name, spec, mount, dfn, have) in enumerate(items):
        X, Y = pos(i)
        tile(ax, X, Y, tw, th, ref, qty, name, spec, mount,
             lambda a, X=X, Y=Y, dfn=dfn: dfn(a, X, Y), have=have)

    ly = 44
    ax.add_patch(patches.Circle((gx + 10, ly), 8, fc=GRN, ec="none", zorder=6))
    ax.text(gx + 26, ly, "구매 완료 / 보유", fontsize=10.5, color=INK,
            va="center", zorder=6)
    ax.add_patch(patches.Circle((gx + 230, ly), 8, fc=ORG, ec="none", zorder=6))
    ax.text(gx + 246, ly, "구매 예정 (미보유)", fontsize=10.5, color=INK,
            va="center", zorder=6)
    ax.text(w - gx, ly, "부품 번호(A1 등)는 2~4장의 배선도에서 그대로 쓴다",
            fontsize=10, color=GREY, ha="right", va="center", zorder=6)
    fig.savefig("manual_1_parts.png", facecolor=PAPER,
                bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    print("manual_1_parts.png")


def table(ax, x, y, w, head, rows, widths, fs=9.4, rh=30):
    """배선 표. widths 는 비율."""
    tot = sum(widths)
    xs, acc = [], x
    for ww in widths:
        xs.append(acc); acc += w*ww/tot
    ax.add_patch(patches.Rectangle((x, y + len(rows)*rh), w, rh,
                 fc=INK, ec="none", zorder=6))
    for cx, hd in zip(xs, head):
        ax.text(cx + 10, y + len(rows)*rh + rh/2, hd, fontsize=fs,
                fontweight="bold", color="#FFFFFF", va="center", zorder=7)
    for i, row in enumerate(rows):
        ry = y + (len(rows)-1-i)*rh
        if i % 2 == 0:
            ax.add_patch(patches.Rectangle((x, ry), w, rh, fc="#F4F7FA",
                         ec="none", zorder=5))
        for j, (cx, cell) in enumerate(zip(xs, row)):
            col, txt = (cell if isinstance(cell, tuple) else (INK, cell))
            ax.text(cx + 10, ry + rh/2, txt, fontsize=fs,
                    fontweight="bold" if j == 0 else "normal",
                    color=col, va="center", zorder=7)
        ax.plot([x, x+w], [ry]*2, color="#E1E7ED", lw=1.0, zorder=6)
    ax.add_patch(patches.Rectangle((x, y), w, len(rows)*rh + rh, fill=False,
                 ec=RULE, lw=1.4, zorder=7))


def sheet2():
    w, h = 1760, 1770
    fig, ax = new_sheet(w, h, "2. 전원 배선",
                        "배터리에서 각 부품까지. 연결 전에 극성을 반드시 두 번 확인한다",
                        "Shepherdron  ·  2/4")
    GX, GW = 44, w - 88

    # ═══ 패널 1 : 동력 전원 ═══════════════════════════════
    ay = 860
    panel(ax, GX, ay, GW, 760, 1,
          "동력 전원 : 배터리 → 전원 분배 → ESC 4개 → 모터 4개", accent=RED)

    bt = dr_battery(ax, GX + 60, ay + 560, s=0.90)
    callout(ax, GX + 60 + 95, ay + 560 + 110, 1, col=RED)

    px, py = GX + 460, ay + 500
    dr_pdb(ax, px, py, s=1.0)
    PR, PB = py + 52, py + 22            # + / - 패드 행
    callout(ax, px + 75, py + 128, 2, col=RED)

    cable(ax, [bt["+"], (bt["+"][0] + 34, bt["+"][1]),
               (bt["+"][0] + 34, PR), (px, PR)], RED, lw=5.0)
    cable(ax, [bt["-"], (bt["-"][0] + 62, bt["-"][1]),
               (bt["-"][0] + 62, PB), (px, PB)], BLK, lw=5.0)

    # ── ESC 4조 + 모터 4개 ──
    ex, mx = GX + 850, GX + 1180
    busr, busb = GX + 740, GX + 770          # +/- 버스 수직 경로
    cable(ax, [(px + 150, PR), (busr, PR)], RED, lw=4.4)
    cable(ax, [(px + 150, PB), (busb, PB)], BLK, lw=4.4)
    info = [("M1", "전방 우", "CCW"), ("M3", "전방 좌", "CW"),
            ("M2", "후방 좌", "CCW"), ("M4", "후방 우", "CW")]
    ys = [ay + 560, ay + 410, ay + 260, ay + 110]
    cable(ax, [(busr, PR), (busr, ys[-1] + 21)], RED, lw=4.4)
    cable(ax, [(busb, PB), (busb, ys[-1] + 4)], BLK, lw=4.4)
    for (mid, place, rot), ey in zip(info, ys):
        e = dr_esc(ax, ex, ey, s=1.25, label=None)
        ax.text(ex + 54, ey + 58, f"ESC · {mid}", fontsize=10.6,
                fontweight="bold", color=INK, ha="center", zorder=15)
        cable(ax, [(busr, e["in"][0][1]), e["in"][0]], RED, lw=3.4)
        cable(ax, [(busb, e["in"][1][1]), e["in"][1]], BLK, lw=3.4)
        tips = dr_motor(ax, mx, ey + 21, s=1.45, wires_dir=180, label=False)
        for a_, b_ in zip(e["out"], tips):
            cable(ax, [a_, ((a_[0] + b_[0]) / 2, a_[1]),
                       ((a_[0] + b_[0]) / 2, b_[1]), b_], "#6A3A00", lw=2.8)
        ax.text(mx + 72, ey + 32, mid, fontsize=13, fontweight="bold",
                color=INK, ha="left", va="center", zorder=15)
        ax.text(mx + 72, ey + 10, f"{place} · {rot}", fontsize=9.8,
                color=GREY, ha="left", va="center", zorder=15)
    callout(ax, ex + 54, ys[0] + 92, 3, col=RED)
    callout(ax, (ex + 109 + mx - 56) / 2, ys[0] + 56, 4, col="#6A3A00")

    # ── 모터 번호 참조도 ──
    ix, iy = GX + 250, ay + 250
    ax.add_patch(patches.FancyBboxPatch((GX + 40, ay + 40), 430, 420,
                 boxstyle="round,pad=0,rounding_size=8",
                 fc="#F7F9FB", ec=RULE, lw=1.3, zorder=3))
    ax.text(GX + 60, ay + 430, "모터 번호 · ArduPilot X 배치",
            fontsize=11.4, fontweight="bold", color=INK, zorder=6)
    ends = dr_f450(ax, ix, iy, s=0.72)
    for name, ((exx, eyy), cw_) in ends.items():
        dr_motor(ax, exx, eyy, s=0.70, label=False)
        ax.add_patch(patches.Circle((exx, eyy), 15, fc="#FFFFFF", ec=INK,
                                    lw=1.8, zorder=18))
        ax.text(exx, eyy, name[1], fontsize=11, fontweight="bold", color=INK,
                ha="center", va="center", zorder=19)
        ax.text(exx, eyy - 34, "CW" if cw_ else "CCW", fontsize=8.6,
                fontweight="bold", color=GREY, ha="center", va="center", zorder=18)
    ax.text(GX + 60, ay + 62,
            "ESC 신호선은 PWM 1~4번을 M1~M4 순서대로 꽂는다 (3장 참조)",
            fontsize=9.4, color=GREY, zorder=6)

    # ═══ 패널 2 : 전자부 전원 ═════════════════════════════
    by, bh = 420, 420
    panel(ax, GX, by, GW, bh, 2,
          "전자부 전원 : 전원 분배 → FC / UBEC → Raspberry Pi", accent=GRN)

    BUS_R, BUS_B = by + 48, by + 24          # 패널 아래쪽 +/- 간선

    qx, qy = GX + 60, by + 130
    dr_pdb(ax, qx, qy, s=0.82)
    ax.text(qx + 61, qy - 20, "전원 분배 (패널 1)", fontsize=9.8,
            color=GREY, ha="center", zorder=16)
    # 분배판 → 간선
    cable(ax, [(qx + 123, qy + 43), (qx + 170, qy + 43),
               (qx + 170, BUS_R), (GW + GX - 120, BUS_R)], RED, lw=4.4)
    cable(ax, [(qx + 123, qy + 18), (qx + 148, qy + 18),
               (qx + 148, BUS_B), (GW + GX - 120, BUS_B)], BLK, lw=4.4)
    ax.text(GX + 36, BUS_R, "+", fontsize=15, fontweight="bold", color=RED,
            ha="center", va="center", zorder=16)
    ax.text(GX + 36, BUS_B, "-", fontsize=17, fontweight="bold", color=INK,
            ha="center", va="center", zorder=16)

    # ── KoA FC ──
    fx, fy = GX + 420, by + 170
    ports = dr_fc(ax, fx, fy, s=0.60, detail=False, front_labels=False)
    ax.text(fx + 90, fy + 126 + 46, "KoA FC H743", fontsize=11.0,
            fontweight="bold", color=INK, ha="center", zorder=17)
    pwx = ports["POWER"][0]
    cable(ax, [(pwx + 7, BUS_R), (pwx + 7, ports["POWER"][1])], RED, lw=4.2)
    cable(ax, [(pwx - 7, BUS_B), (pwx - 7, ports["POWER"][1])], BLK, lw=4.2)
    ax.text(pwx - 34, ports["POWER"][1] - 16, "POWER", fontsize=9.6,
            fontweight="bold", color=RED, ha="right", va="center", zorder=17)
    ax.text(pwx - 34, ports["POWER"][1] - 36, "6핀 · Vbat/GND", fontsize=8.6,
            color=GREY, ha="right", va="center", zorder=17)
    callout(ax, pwx + 42, (BUS_R + ports["POWER"][1]) / 2, 5, col=RED)

    # ── UBEC ──
    ux, uy = GX + 880, by + 190
    uin, uout = dr_ubec(ax, ux, uy, s=1.0, labels=False)
    ax.text(ux + 45, uy + 58, "UBEC 5V 5A", fontsize=10.8,
            fontweight="bold", color=INK, ha="center", zorder=17)
    cable(ax, [(ux - 62, BUS_R), (ux - 62, uin[1] + 7), (uin[0], uin[1] + 7)],
          RED, lw=4.2)
    cable(ax, [(ux - 90, BUS_B), (ux - 90, uin[1] - 7), (uin[0], uin[1] - 7)],
          BLK, lw=4.2)
    ax.text(ux - 24, uy - 22, "입력 14.8V", fontsize=8.8, color=GREY,
            ha="center", va="center", zorder=17)
    ax.text(ux + 114, uy - 22, "출력 5V", fontsize=8.8, color=GRN,
            ha="center", va="center", zorder=17)
    callout(ax, ux - 62, uin[1] + 66, 6, col=RED)

    # ── Raspberry Pi ──
    pix, piy = GX + 1240, by + 150
    pi = dr_pi(ax, pix, piy, s=0.62, labels=False)
    ax.text(pix + 93, piy - 20, "Raspberry Pi 4", fontsize=10.6,
            fontweight="bold", color=INK, ha="center", zorder=17)
    cable(ax, [uout, (uout[0] + 52, uout[1]),
               (uout[0] + 52, pi["usbc"][1]), pi["usbc"]], GRN, lw=4.6,
          label="5V", lx=uout[0] + 52, ly=(uout[1] + pi["usbc"][1]) / 2)
    ax.text(pi["usbc"][0] - 16, pi["usbc"][1] - 30, "USB-C", fontsize=8.8,
            color=GREY, ha="center", va="center", zorder=17)
    callout(ax, pi["usbc"][0] - 70, pi["usbc"][1], 7, col=GRN)

    note(ax, GX + 20, 320, GW - 40, 78, "FC 내장 BEC로 Pi를 급전하지 말 것",
         ["KoA FC의 5V 출력은 2.5A뿐이고 Pi 4는 최대 3A를 요구한다. "
          "반드시 별도 UBEC로 Pi에 급전하고, UBEC 접지와 FC 접지는 전원 분배판 한 점에서 만나게 한다."])

    # ═══ 배선 표 ═════════════════════════════════════════
    head = ["#", "구간", "전선", "색 / 극성", "확인 사항"]
    trows = [
        ["1", "배터리 XT60 → 전원 분배", "14 AWG", (RED, "빨강 + / 검정 -"),
         "XT60 암수 방향 확인. 역결선하면 FC가 즉시 손상된다"],
        ["2", "전원 분배판 패드", "납땜", (RED, "+ 상단 / - 하단"),
         "납땜 후 멀티미터 저항 모드로 +/- 단락 여부를 측정한다"],
        ["3", "전원 분배 → ESC 4개", "16 AWG", (RED, "빨강 + / 검정 -"),
         "4개 모두 같은 극성. 납땜부는 수축튜브로 절연한다"],
        ["4", "ESC → 모터 4개", "3상 3선", ("#6A3A00", "순서 무관"),
         "모터가 반대로 돌면 3선 중 아무 2선만 바꿔 끼운다"],
        ["5", "전원 분배 → FC POWER", "6핀 몰렉스", (RED, "Vbat / GND"),
         "KoA FC는 VBAT 26V까지 직결. 별도 파워모듈이 필요 없다"],
        ["6", "전원 분배 → UBEC 입력", "20 AWG", (RED, "빨강 + / 검정 -"),
         "입력단에서 14.8V가 나오는지 먼저 측정한다"],
        ["7", "UBEC 출력 → Pi USB-C", "5V 5A", (GRN, "5V / GND"),
         "Pi에 꽂기 전 무부하 출력이 5.0~5.2V인지 측정한다"],
    ]
    table(ax, GX, 58, GW, head, trows, [0.04, 0.22, 0.10, 0.15, 0.49])

    fig.savefig("manual_2_power.png", facecolor=PAPER,
                bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    print("manual_2_power.png")


# ═══════════════════════ 3장 : 신호 배선 ═══════════════════════
P5V, PGND, PVB, PCUR = GRN, "#2A2A2A", RED, ORG
PSIG, PI2C, PSER = YEL, "#1AA6A6", BLU


def pinout(ax, x, y, name, sub, pins, accent, pw=66):
    """커넥터 핀맵. pins = [(신호명, 색), ...] 1번 핀부터."""
    n = len(pins)
    w = n * pw
    ax.add_patch(patches.FancyBboxPatch((x, y + 96), w, 30,
                 boxstyle="round,pad=0,rounding_size=5",
                 fc=accent, ec="none", zorder=12))
    ax.text(x + 12, y + 111, name, fontsize=11.2, fontweight="bold",
            color="#FFFFFF", va="center", zorder=13)
    ax.text(x + w - 12, y + 111, sub, fontsize=9.0, color="#FFFFFF",
            ha="right", va="center", zorder=13, alpha=0.88)
    ax.add_patch(patches.Rectangle((x, y + 46), w, 44, fc="#E8E4D8",
                 ec=INK, lw=1.5, zorder=12))
    for i, (lab, col) in enumerate(pins):
        px = x + i * pw
        if i:
            ax.plot([px, px], [y + 46, y + 90], color="#B8B2A2", lw=1.0, zorder=13)
        ax.add_patch(patches.Rectangle((px + pw*0.26, y + 54), pw*0.48, 28,
                     fc=col, ec=INK, lw=1.0, zorder=14))
        ax.text(px + pw/2, y + 68, str(i + 1), fontsize=9.4, fontweight="bold",
                color="#FFFFFF" if col != P5V else "#FFFFFF",
                ha="center", va="center", zorder=15)
        ax.text(px + pw/2, y + 30, lab, fontsize=9.0, fontweight="bold",
                color=INK, ha="center", va="center", zorder=13)
    ax.annotate("", xy=(x + pw/2, y + 14), xytext=(x + pw*1.7, y + 14),
                arrowprops=dict(arrowstyle="-|>", color=GREY, lw=1.4), zorder=13)
    ax.text(x + pw*1.85, y + 14, "1번 핀", fontsize=8.6, color=GREY,
            va="center", zorder=13)
    return w


def chip(ax, x, y, w, h, title, sub, col=INK, fc="#1C2026"):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=6",
                 fc=fc, ec=INK, lw=1.5, zorder=12))
    ax.text(x + w/2, y + h*0.60, title, fontsize=10.4, fontweight="bold",
            color="#F0F4F8", ha="center", va="center", zorder=13)
    ax.text(x + w/2, y + h*0.28, sub, fontsize=8.4, color="#9FB0C0",
            ha="center", va="center", zorder=13)


def parambox(ax, x, y, w, h, title, rows):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=8",
                 fc="#FFFFFF", ec=RULE, lw=1.5, zorder=4))
    ax.add_patch(patches.Rectangle((x, y + h - 36), w, 36, fc=INK,
                 ec="none", zorder=5))
    ax.text(x + 14, y + h - 18, title, fontsize=11.0, fontweight="bold",
            color="#FFFFFF", va="center", zorder=6)
    for i, (k, v, c) in enumerate(rows):
        ry = y + h - 62 - i*27
        ax.text(x + 14, ry, k, fontsize=9.4, color=INK, va="center", zorder=6)
        ax.text(x + w*0.60, ry, v, fontsize=9.4, fontweight="bold",
                color=RED if c else INK, va="center", zorder=6)
        if c:
            ax.text(x + w*0.60 + 68, ry, c, fontsize=8.4, color=GREY,
                    va="center", zorder=6)


def sheet3():
    w, h = 1760, 1740
    fig, ax = new_sheet(w, h, "3. 신호 배선",
                        "FC 커넥터에서 각 장치까지. 핀 1번 위치를 반드시 맞춘다",
                        "Shepherdron  ·  3/4")
    GX, GW = 44, w - 88

    # ═══ 패널 1 : FC 중심 신호 결선도 ═════════════════════
    ay = 870
    panel(ax, GX, ay, GW, 720, 1, "FC 중심 신호 결선도", accent=BLU)

    fx, fy = GX + 700, ay + 300
    ports = dr_fc(ax, fx, fy, s=1.0, detail=False, front_labels=False)
    ax.text(fx + 150, fy + 210 + 72, "KoA FC H743", fontsize=12.4,
            fontweight="bold", color=INK, ha="center", zorder=18)

    def ptag(txt, sub, px, py, col, ha="center"):
        ax.text(px, py, txt, fontsize=9.8, fontweight="bold", color=col,
                ha=ha, va="center", zorder=18)
        ax.text(px, py - 16, sub, fontsize=8.2, color=GREY, ha=ha,
                va="center", zorder=18)

    ax.text(ports["POWER"][0], ay + 252, "POWER", fontsize=8.8, color=GREY,
            ha="center", va="center", zorder=18)
    ax.text(ports["POWER"][0], ay + 236, "→ 2장", fontsize=8.0, color=GREY,
            ha="center", va="center", zorder=18)
    ptag("PWM", "10핀", ports["PWM"][0] + 18, ay + 272, "#9A7A00", ha="left")
    ptag("RC", "4핀", ports["RC"][0] + 16, ay + 248, BLU, ha="left")
    ptag("GPS", "6핀", ports["GPS"][0] + 16, ay + 272, GRN, ha="left")

    # ── ESC 신호 (PWM 1~4) ──
    ex = GX + 120
    chip(ax, ex, ay + 60, 240, 78, "ESC 신호 4개", "PWM 1~4 → M1~M4")
    ax.text(ex + 120, ay + 42, "10핀 → 서보 3핀 변환 하네스", fontsize=9.2,
            color=GREY, ha="center", zorder=15)
    cable(ax, [ports["PWM"], (ports["PWM"][0], ay + 230),
               (ex + 120, ay + 230), (ex + 120, ay + 138)], YEL, lw=4.4)
    callout(ax, ex + 120, ay + 230, 1, col="#9A7A00")

    # ── 수신기 (RC) ──
    rx_ = GX + 520
    rtip = dr_rx(ax, rx_, ay + 70, s=1.3)
    cable(ax, [ports["RC"], (ports["RC"][0], ay + 195),
               (rtip[0], ay + 195), rtip], BLU, lw=4.4)
    callout(ax, rtip[0], ay + 195, 2, col=BLU)

    # ── GPS + 나침반 ──
    gx_ = GX + 1150
    gtip = dr_gps(ax, gx_, ay + 125, s=1.25)
    cable(ax, [ports["GPS"], (ports["GPS"][0], ay + 36),
               (gtip[0], ay + 36), gtip], GRN, lw=4.4)
    callout(ax, ports["GPS"][0], ay + 36, 3, col=GRN)

    # ── 광류 + 거리계 (I2C) ──
    ftip = dr_flow(ax, GX + 150, ay + 330, s=1.5)
    cable(ax, [ftip, (ftip[0], ay + 480), (GX + 640, ay + 480),
               (GX + 640, ports["I2C"][1]), ports["I2C"]], PI2C, lw=4.0)
    callout(ax, GX + 640, ay + 480, 5, col=PI2C)

    # ── Raspberry Pi (TELEM2 경유) ──
    pix, piy = GX + 1280, ay + 330
    pi = dr_pi(ax, pix, piy, s=0.72, labels=False)
    ax.text(pix + 108, piy + 164, "Raspberry Pi 4", fontsize=11.4,
            fontweight="bold", color=INK, ha="center", zorder=18)
    chip(ax, GX + 1030, ay + 250, 150, 54, "USB-TTL", "3.3V FTDI", fc="#2A2030")
    cable(ax, [ports["TELEM2"], (GX + 1105, ports["TELEM2"][1]),
               (GX + 1105, ay + 304)], ORG, lw=4.4)
    cable(ax, [(GX + 1180, ay + 277), (GX + 1560, ay + 277),
               (GX + 1560, pi["usb"][1]), pi["usb"]], ORG, lw=4.4)
    callout(ax, GX + 1105, ay + 420, 4, col=ORG)
    ax.text(GX + 1120, ay + 372, "MAVLink2", fontsize=9.4, color=GREY,
            ha="left", va="center", zorder=18)
    ax.text(GX + 1120, ay + 354, "921600 bps", fontsize=9.4, color=GREY,
            ha="left", va="center", zorder=18)

    # ── 카메라 → Pi CSI ──
    ctip = dr_camera(ax, GX + 1330, ay + 570, s=1.3)
    cable(ax, [ctip, (GX + 1218, ctip[1]),
               (GX + 1218, pi["csi"][1]), pi["csi"]], "#8A8578", lw=4.0)
    callout(ax, GX + 1218, ay + 480, 6, col="#8A8578")

    note(ax, GX + 300, ay + 528, 390, 130,
         "USB-TTL 5V 선 연결 금지",
         ["FC 와 Pi 가 서로 역급전되어", "양쪽이 모두 손상된다.",
          "TX · RX · GND 3선만 연결하고", "5V 선은 뽑아 둔다."])

    # ═══ 패널 2 : 커넥터 핀맵 ═════════════════════════════
    by = 440
    panel(ax, GX, by, GW, 400, 2,
          "KoA FC 커넥터 핀맵 (공식 매뉴얼 기준)", accent=INK)

    r1 = by + 216
    x_ = GX + 40
    x_ += pinout(ax, x_, r1, "POWER", "6핀", [
        ("5V", P5V), ("5V", P5V), ("Curr", PCUR), ("Vbat", PVB),
        ("GND", PGND), ("GND", PGND)], RED) + 56
    x_ += pinout(ax, x_, r1, "RC", "4핀", [
        ("GND", PGND), ("SBUS", PSER), ("TX5", PSER), ("5V", P5V)], BLU) + 56
    pinout(ax, x_, r1, "GPS", "6핀", [
        ("GND", PGND), ("SDA", PI2C), ("SCL", PI2C), ("RX1", PSER),
        ("TX1", PSER), ("5V", P5V)], GRN)

    r2 = by + 36
    x_ = GX + 40
    x_ += pinout(ax, x_, r2, "PWM", "10핀", [
        ("GND", PGND), ("PWM8", PSIG), ("PWM7", PSIG), ("PWM6", PSIG),
        ("PWM5", PSIG), ("PWM4", PSIG), ("PWM3", PSIG), ("PWM2", PSIG),
        ("PWM1", PSIG), ("5V", P5V)], "#9A7A00") + 56
    pinout(ax, x_, r2, "TELEM2", "6핀 · 표준 MAVLink", [
        ("5V", P5V), ("TX", PSER), ("RX", PSER), ("CTS", PSER),
        ("RTS", PSER), ("GND", PGND)], ORG)

    ax.text(GX + 40, by + 20,
            "PWM 커넥터는 1번이 GND, 9번이 PWM1 이다. M1~M4 는 PWM1~PWM4 에 순서대로 들어간다.",
            fontsize=9.6, color=GREY, zorder=15)

    # ═══ 경고 ════════════════════════════════════════════
    note(ax, GX, 330, GW, 80, "TX 와 RX 는 반드시 엇갈려 연결한다",
         ["FC TELEM2 의 TX 는 Pi 쪽 RX 로, FC 의 RX 는 Pi 쪽 TX 로 간다. "
          "같은 이름끼리 연결하면 통신이 전혀 되지 않는다."])

    # ═══ 표 + 파라미터 ═══════════════════════════════════
    tw = GW * 0.63
    head = ["#", "구간", "케이블", "확인 사항"]
    trows = [
        ["S1", "FC PWM → ESC 신호 4개", "10핀 → 서보 3핀 하네스",
         "PWM1=M1 ... PWM4=M4. 순서가 틀리면 즉시 전복된다"],
        ["S2", "FC RC → 수신기 SBUS", "4핀 JST-GH",
         "수신기는 FC 내장 5V BEC 에서 급전된다"],
        ["S3", "FC GPS → GPS + 나침반", "6핀 JST-GH",
         "FC 에 나침반이 없으므로 실내에서도 외장 나침반이 필요하다"],
        ["S4", "FC TELEM2 → Pi USB-A", "USB-TTL 3.3V",
         "TX↔RX 교차. 5V 선 연결 금지"],
        ["S5", "FC I2C → 광류 + 거리계", "4핀 JST-GH",
         "실내 위치 유지용. GPS 없이 비행할 때 필수"],
        ["S6", "카메라 → Pi CSI", "15핀 FPC 200mm",
         "ESC 전력선과 이격한다. 전방 45도 하향 고정"],
    ]
    table(ax, GX, 60, tw, head, trows, [0.05, 0.25, 0.20, 0.50])

    parambox(ax, GX + tw + 28, 60, GW - tw - 28, 6*30 + 30,
             "ArduPilot 파라미터", [
        ("FRAME_CLASS", "1", "멀티콥터"),
        ("FRAME_TYPE", "1", "Quad X"),
        ("SERIAL2_PROTOCOL", "2", "MAVLink2"),
        ("SERIAL2_BAUD", "921", "불안정시 115"),
        ("SERIAL6_PROTOCOL", "23", "RC Input"),
        ("BATT_MONITOR", "4", "전압+전류"),
    ])

    fig.savefig("manual_3_signal.png", facecolor=PAPER,
                bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    print("manual_3_signal.png")


# ═══════════════════════ 4장 : 조립 순서 ═══════════════════════
def step(ax, x, y, w, h, n, title, lines, draw=None, accent=BLU):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=9",
                 fc="#FFFFFF", ec=RULE, lw=1.5, zorder=4))
    ax.add_patch(patches.Rectangle((x + 1, y + h - 74), w - 2, 2,
                 fc="#EDF1F5", ec="none", zorder=5))
    ax.add_patch(patches.Circle((x + 34, y + h - 36), 20, fc=accent,
                                ec="none", zorder=7))
    ax.text(x + 34, y + h - 36, str(n), fontsize=15, fontweight="bold",
            color="#FFFFFF", ha="center", va="center", zorder=8)
    ax.text(x + 66, y + h - 30, title, fontsize=12.2, fontweight="bold",
            color=INK, va="center", zorder=7)
    for i, ln in enumerate(lines):
        ax.text(x + 66, y + h - 52 - i*18, ln, fontsize=9.0, color=GREY,
                va="center", zorder=7)
    if draw is not None:
        with no_caption():
            draw(ax)


def checklist(ax, x, y, w, h, title, items, accent=INK, cols=1):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=9",
                 fc="#FFFFFF", ec=RULE, lw=1.5, zorder=4))
    ax.add_patch(patches.Rectangle((x, y + h - 42), w, 42, fc=accent,
                 ec="none", zorder=5))
    ax.text(x + 18, y + h - 21, title, fontsize=12.6, fontweight="bold",
            color="#FFFFFF", va="center", zorder=6)
    per = (len(items) + cols - 1) // cols
    cw = w / cols
    for i, it in enumerate(items):
        c, r = divmod(i, per)
        ix = x + 18 + c*cw
        iy = y + h - 74 - r*29
        ax.add_patch(patches.Rectangle((ix, iy - 9), 18, 18, fc="#FFFFFF",
                     ec=GREY, lw=1.6, zorder=6))
        ax.text(ix + 28, iy, it, fontsize=9.8, color=INK, va="center", zorder=6)


def ordered(ax, x, y, w, h, title, items, accent=GRN):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=9",
                 fc="#FFFFFF", ec=RULE, lw=1.5, zorder=4))
    ax.add_patch(patches.Rectangle((x, y + h - 42), w, 42, fc=accent,
                 ec="none", zorder=5))
    ax.text(x + 18, y + h - 21, title, fontsize=12.6, fontweight="bold",
            color="#FFFFFF", va="center", zorder=6)
    for i, it in enumerate(items):
        iy = y + h - 70 - i*26
        ax.add_patch(patches.Circle((x + 28, iy), 12, fc="#EEF3F8",
                     ec=accent, lw=1.5, zorder=6))
        ax.text(x + 28, iy, str(i + 1), fontsize=9.4, fontweight="bold",
                color=accent, ha="center", va="center", zorder=7)
        ax.text(x + 50, iy, it, fontsize=9.8, color=INK, va="center", zorder=6)


def icon_laptop(ax, cx, cy, s=1.0):
    ax.add_patch(patches.FancyBboxPatch((cx - 52*s, cy - 6*s), 104*s, 62*s,
                 boxstyle="round,pad=0,rounding_size=4",
                 fc="#23272E", ec=INK, lw=1.5, zorder=12))
    ax.add_patch(patches.Rectangle((cx - 44*s, cy + 2*s), 88*s, 46*s,
                 fc="#4A6A8A", ec="none", zorder=13))
    ax.add_patch(patches.Polygon([(cx - 66*s, cy - 14*s), (cx + 66*s, cy - 14*s),
                                  (cx + 56*s, cy - 6*s), (cx - 56*s, cy - 6*s)],
                 closed=True, fc="#3A424D", ec=INK, lw=1.2, zorder=12))


def icon_calib(ax, cx, cy, s=1.0):
    for k, r in enumerate((44*s, 30*s)):
        th = np.radians(np.linspace(40 + k*180, 300 + k*180, 60))
        ax.plot(cx + r*np.cos(th), cy + r*np.sin(th), color=BLU, lw=3.0,
                zorder=12, solid_capstyle="round")
        ax.annotate("", xy=(cx + r*math.cos(th[-1]), cy + r*math.sin(th[-1])),
                    xytext=(cx + r*math.cos(th[-4]), cy + r*math.sin(th[-4])),
                    arrowprops=dict(arrowstyle="-|>", color=BLU, lw=3.0), zorder=12)
    ax.add_patch(patches.Circle((cx, cy), 13*s, fc=PCB, ec=INK, lw=1.4, zorder=13))


def sheet4():
    w, h = 1760, 1360
    fig, ax = new_sheet(w, h, "4. 조립 순서와 점검",
                        "위에서 아래로, 왼쪽에서 오른쪽으로 순서대로 진행한다",
                        "Shepherdron  ·  4/4")
    GX, GW = 44, w - 88

    ay = 470
    panel(ax, GX, ay, GW, 740, 1, "조립 순서 12단계", accent=BLU)
    cols, rows = 4, 3
    cw = (GW - 80 - (cols-1)*16) / cols
    ch = (740 - 76 - (rows-1)*16) / rows

    def cpos(i):
        r, c = divmod(i, cols)
        return GX + 40 + c*(cw+16), ay + 740 - 72 - (r+1)*ch - r*16

    def mid(X, Y):
        return X + cw/2, Y + (ch - 74)/2 - 8

    steps = [
        (1, "프레임 조립", ["하단판에 암 4개를 볼트로 체결", "전방 암 2개는 빨강으로 맞춘다"],
         lambda a, X, Y: dr_f450(a, mid(X, Y)[0], mid(X, Y)[1]-8, s=0.35)),
        (2, "모터 장착", ["암 끝단에 M1~M4 를 볼트 4개로", "선은 기체 안쪽으로 빼낸다"],
         lambda a, X, Y: dr_motor(a, *mid(X, Y), s=1.25, wires_dir=200, label=False)),
        (3, "ESC 장착", ["암 하단에 케이블타이로 고정", "수축튜브가 벗겨지지 않았는지 확인"],
         lambda a, X, Y: dr_esc(a, mid(X, Y)[0]-70, mid(X, Y)[1]-20, s=1.6, label=None)),
        (4, "전원 분배 납땜", ["하단판 PDB 패드에 배터리 리드", "납땜 후 +/- 단락 측정"],
         lambda a, X, Y: dr_pdb(a, mid(X, Y)[0]-56, mid(X, Y)[1]-40, s=0.75)),
        (5, "ESC 전원 결선", ["PDB → ESC 4개, 극성 확인", "빨강 +, 검정 - 를 두 번 확인"],
         lambda a, X, Y: dr_battery(a, mid(X, Y)[0]-100, mid(X, Y)[1]-32, s=0.70)),
        (6, "ESC → 모터 3상", ["3선 순서는 무관", "역회전이면 2선만 바꿔 끼운다"],
         lambda a, X, Y: (dr_esc(a, mid(X, Y)[0]-104, mid(X, Y)[1]-18, s=1.0, label=None),
                          dr_motor(a, mid(X, Y)[0]+66, mid(X, Y)[1], s=1.0,
                                   wires_dir=180, label=False))),
        (7, "FC 장착", ["상단판 중앙, 30.5mm 마운트", "FC 전방 표시를 기체 전방과 일치"],
         lambda a, X, Y: dr_fc(a, mid(X, Y)[0]-57, mid(X, Y)[1]-40, s=0.38,
                               detail=False, front_labels=False)),
        (8, "FC 결선", ["POWER · PWM · RC · GPS 연결", "커넥터 1번 핀 방향을 확인"],
         lambda a, X, Y: [jst(a, mid(X, Y)[0]-96+k*66, mid(X, Y)[1]-10, 6, "",
                              s=1.5) for k in range(3)]),
        (9, "수신기 · GPS", ["수신기는 상단판 후방", "GPS 마스트 화살표를 전방으로"],
         lambda a, X, Y: (dr_rx(a, mid(X, Y)[0]-112, mid(X, Y)[1]-22, s=0.90),
                          dr_gps(a, mid(X, Y)[0]+80, mid(X, Y)[1]+2, s=0.76))),
        (10, "Pi · 카메라", ["Pi 는 스탠드오프로 상단판 위", "카메라는 전방 45도 하향 고정"],
         lambda a, X, Y: (dr_pi(a, mid(X, Y)[0]-126, mid(X, Y)[1]-38, s=0.40,
                                labels=False),
                          dr_camera(a, mid(X, Y)[0]+76, mid(X, Y)[1]-24, s=0.86))),
        (11, "펌웨어 · 파라미터", ["ArduCopter 설치 후 3장 표대로", "SERIAL2 / SERIAL6 설정"],
         lambda a, X, Y: icon_laptop(a, *mid(X, Y), s=1.05)),
        (12, "캘리브레이션", ["가속도 · 나침반 · ESC · 조종기", "프로펠러를 뺀 상태로 진행"],
         lambda a, X, Y: icon_calib(a, *mid(X, Y), s=1.05)),
    ]
    for i, (n, title, lines, dfn) in enumerate(steps):
        X, Y = cpos(i)
        step(ax, X, Y, cw, ch, n, title, lines,
             draw=lambda a, X=X, Y=Y, dfn=dfn: dfn(a, X, Y),
             accent=BLU if n <= 6 else GRN)

    # ── 점검표 / 첫 시동 ──
    lw_ = GW * 0.60
    checklist(ax, GX, 86, lw_, 330, "비행 전 점검표", [
        "프로펠러 CW / CCW 위치가 M1~M4 와 맞는가",
        "프로펠러 고정 너트가 조여져 있는가",
        "모든 납땜부가 수축튜브로 절연되었는가",
        "배터리 전압이 16.0V 이상인가",
        "배터리가 벨크로로 단단히 고정되었는가",
        "FC 전방 표시가 기체 전방과 일치하는가",
        "GPS 모듈 전방 화살표가 기체 전방과 같은가",
        "microSD 가 FC 에 삽입되어 있는가",
        "USB-TTL 의 5V 선이 분리되어 있는가",
        "조종기 스로틀이 최하단에 있는가",
        "페일세이프 동작을 확인했는가",
        "실내 시연이면 프로펠러 가드를 달았는가",
        "반경 3m 이내에 사람이 없는가",
        "리포백 또는 모래가 준비되어 있는가",
        "조종기와 수신기 바인딩이 되어 있는가",
        "실내 비행 허가와 공간 사용 승인을 받았는가",
    ], accent=INK, cols=2)

    rx_ = GX + lw_ + 24
    rw = GW - lw_ - 24
    ordered(ax, rx_, 216, rw, 200, "첫 시동 순서", [
        "프로펠러를 뺀 채 배터리 연결",
        "Mission Planner 로 센서 상태 확인",
        "ESC 캘리브레이션",
        "MOT_TEST 로 회전 방향 확인",
        "프로펠러 장착 후 1m 호버",
    ], accent=GRN)
    note(ax, rx_, 86, rw, 116, "이상이 생기면 즉시",
         ["1. 스로틀을 최하로 내린다",
          "2. 시동을 해제한다 (Disarm)",
          "3. 조종기로 수동 전환 — 조종기가 항상 우선"])

    fig.savefig("manual_4_assembly.png", facecolor=PAPER,
                bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    print("manual_4_assembly.png")


if __name__ == "__main__":
    sheet1()
    sheet2()
    sheet3()
    sheet4()
