"""Shepherdron 관제 화면.

이 화면이 다른 군중계수기와 달라야 하는 지점은 하나다. 상용 제품은 보는 데서
멈추지만 Shepherdron 은 본 다음 날아가서 사람을 유도한다. 그래서 화면도
'인식'과 '행동' 두 층으로 나눈다.

    인식 (좌)   카메라 영상 · 밀집도 · 수치 · 추이        상태색 4단계
    행동 (우)   전술 지도 · 임무 상태 · 유도 방향 · 기체   브랜드색(라임) 하나

라임색은 드론이 하는 일에만 쓴다. 타겟 조준선, 비행 경로, 유도 화살표,
임무 단계. 화면을 처음 보는 사람도 '초록빛 노랑 = 드론' 을 바로 배운다.

시각 문법 (기본값처럼 보이지 않기 위한 규칙)
    - 모서리를 굴리지 않는다. 면은 1px 선으로 나눈다.
    - 숫자 · 시각 · 좌표는 전부 고정폭(SF Mono)이다. 한글은 Pretendard.
    - 영상 위에는 실제 카메라처럼 타임코드 · 프레임번호 · 뷰파인더 모서리.
    - 지도에는 거리 링과 시야각 쐐기. 장식이 아니라 축척이다.
    - 수치가 없는 칸은 비워 둔다. 가짜 값으로 채우지 않는다.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from vision.density_field import (
    DEFAULT_TIERS,
    DensityFieldResult,
    RoiReport,
    analyze_roi,
    level_color,
    level_tag,
)
from vision.pipeline import PipelineResult
from vision.tactical import TacticalPicture
from vision.text_painter import TextPainter, hex_to_bgr

# ── 토큰 ─────────────────────────────────────────────────
BG = "#0A0B0D"
S1 = "#101215"
S2 = "#15181C"
HAIR = "#1E2226"
LINE = "#2A2F35"
TXT = "#E7E9EC"
TXT2 = "#959CA5"
TXT3 = "#5C636B"
LIME = "#C8F542"            # Shepherdron — 드론이 하는 일에만
LIME_DIM = "#5F7323"
ROI_C = "#D9C27A"

MISSION_KO = {"IDLE": "대기", "NAVIGATING": "출동", "HOVERING": "안내",
              "RETRACTING": "회수", "RETURNING": "복귀", "STANDBY": "수동",
              "FAILSAFE": "이상"}
TRACK = ["IDLE", "NAVIGATING", "HOVERING", "RETRACTING", "RETURNING"]
PAYLOAD_KO = {"STOWED": "접힘", "DEPLOYING": "전개 중", "DEPLOYED": "전개",
              "RETRACTING": "수축 중", "FAULT": "고장"}


@dataclass
class Layout:
    w: int = 1920
    h: int = 1080
    m: int = 16                 # 바깥 여백
    g: int = 12                 # 칸 사이
    top_h: int = 56
    right_w: int = 652
    readout_h: int = 86
    tac_h: int = 520
    msn_h: int = 252

    @property
    def _lx(self):
        return self.m, self.w - self.m - self.right_w - self.g

    @property
    def video(self):
        x1, x2 = self._lx
        y1 = self.top_h + self.g
        h = int((x2 - x1) * 9 / 16)
        return x1, y1, x2, y1 + h

    @property
    def readout(self):
        x1, x2 = self._lx
        y1 = self.video[3] + self.g
        return x1, y1, x2, y1 + self.readout_h

    @property
    def trend(self):
        x1, x2 = self._lx
        return x1, self.readout[3] + self.g, x2, self.h - self.m

    @property
    def tac(self):
        x1 = self.w - self.m - self.right_w
        y1 = self.top_h + self.g
        return x1, y1, self.w - self.m, y1 + self.tac_h

    @property
    def msn(self):
        x1, _, x2, y = self.tac
        return x1, y + self.g, x2, y + self.g + self.msn_h

    @property
    def log(self):
        x1, _, x2, y = self.msn
        return x1, y + self.g, x2, self.h - self.m


# ── 밀집도 컬러맵 ─────────────────────────────────────────
_LUT_STOPS = [(0.00, "#10307A"), (0.18, "#1E7FA8"), (0.38, "#2E9E4F"),
              (0.58, "#C9D62B"), (0.76, "#E8A32A"), (1.00, "#D83A2B"),
              (1.50, "#8E1B13")]
_LUT_MAX = 1.5


def density_lut() -> np.ndarray:
    lut = np.zeros((256, 3), np.uint8)
    stops = [(t, np.array(hex_to_bgr(c), np.float32)) for t, c in _LUT_STOPS]
    for i, t in enumerate(np.linspace(0.0, _LUT_MAX, 256)):
        for k in range(len(stops) - 1):
            t0, c0 = stops[k]
            t1, c1 = stops[k + 1]
            if t0 <= t <= t1:
                f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                lut[i] = (c0 + (c1 - c0) * f).astype(np.uint8)
                break
        else:
            lut[i] = stops[-1][1].astype(np.uint8)
    return lut


_LUT = density_lut()


def draw_density_heat(vis, fr: DensityFieldResult, ref: float,
                      max_alpha: float = 0.74):
    if fr.heat is None or ref <= 0:
        return vis
    h, w = vis.shape[:2]
    heat = cv2.resize(fr.heat, (w, h), interpolation=cv2.INTER_LINEAR)
    norm = np.clip(heat / ref, 0.0, _LUT_MAX)
    colored = _LUT[(norm / _LUT_MAX * 255).astype(np.uint8)]
    a = np.clip((heat - 0.02 * ref) / (0.45 * ref), 0.0, 1.0)
    alpha = (a[..., None] ** 0.85) * max_alpha
    return (vis.astype(np.float32) * (1 - alpha)
            + colored.astype(np.float32) * alpha).astype(np.uint8)


# ── 그리기 유틸 ───────────────────────────────────────────
def _fill(img, box, c):
    x1, y1, x2, y2 = [int(v) for v in box]
    if x2 > x1 and y2 > y1:
        cv2.rectangle(img, (x1, y1), (x2, y2), hex_to_bgr(c), -1)


def _stroke(img, box, c, t=1):
    x1, y1, x2, y2 = [int(v) for v in box]
    if x2 > x1 and y2 > y1:
        cv2.rectangle(img, (x1, y1), (x2, y2), hex_to_bgr(c), t)


def _line(img, p, q, c, t=1):
    cv2.line(img, (int(p[0]), int(p[1])), (int(q[0]), int(q[1])),
             hex_to_bgr(c), t, cv2.LINE_AA)


def _dashed(img, p, q, c, t=1, dash=8, gap=6):
    d = math.hypot(q[0] - p[0], q[1] - p[1])
    if d < 1:
        return
    ux, uy = (q[0] - p[0]) / d, (q[1] - p[1]) / d
    s = 0.0
    while s < d:
        e = min(d, s + dash)
        _line(img, (p[0] + ux * s, p[1] + uy * s), (p[0] + ux * e, p[1] + uy * e), c, t)
        s = e + gap


def _arrow(img, p, q, c, t=2, head=12):
    _line(img, p, q, c, t)
    ang = math.atan2(q[1] - p[1], q[0] - p[0])
    for s in (+1, -1):
        a = ang + math.pi + s * math.radians(26)
        _line(img, q, (q[0] + head * math.cos(a), q[1] + head * math.sin(a)), c, t)


def fit_into(frame, box_w, box_h):
    fh, fw = frame.shape[:2]
    if fw <= 0 or fh <= 0:
        return frame, 0, 0, 1.0
    s = min(box_w / fw, box_h / fh)
    nw, nh = max(1, int(fw * s)), max(1, int(fh * s))
    return cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA), \
        (box_w - nw) // 2, (box_h - nh) // 2, s


def derive_status(result: PipelineResult) -> str:
    if result.alert_active:
        return "DANGER"
    fr = result.field
    if fr is not None and fr.level in ("WARNING", "DANGER"):
        return "WARNING"
    return "SAFE"


# ── 이벤트 ────────────────────────────────────────────────
@dataclass
class Event:
    t: str
    text: str
    kind: str = "info"          # info | level | mission | warn
    level: int = 0
    tag: str = ""


class LevelFilter:
    """등급이 경계값 근처에서 매 프레임 바뀌지 않게 한다.

    새 등급이 hold 프레임 연속 유지돼야 받아들인다. 관제 화면에서
    등급이 깜빡이면 운용자는 어느 것도 믿지 않게 된다.
    """

    def __init__(self, hold: int = 8):
        self.hold = hold
        self.value = 0
        self._cand = 0
        self._n = 0

    def update(self, level: int) -> int:
        if level == self.value:
            self._n = 0
            return self.value
        if level == self._cand:
            self._n += 1
        else:
            self._cand, self._n = level, 1
        if self._n >= self.hold:
            self.value, self._n = level, 0
        return self.value


class EventLog:
    def __init__(self, maxlen: int = 40):
        self.items: Deque[Event] = deque(maxlen=maxlen)
        self._level = 0
        self._mission = "IDLE"
        self._fallback = False

    def add(self, text, kind="info", level=0, tag=""):
        self.items.append(Event(time.strftime("%H:%M:%S"), text, kind, level, tag))

    def observe(self, level: Optional[int], peak: float,
                mission_state: Optional[str], mission_reason: str,
                on_fallback: bool) -> None:
        if level is not None and level != self._level:
            up = level > self._level
            self.add(f"등급 {'상승' if up else '하강'} · 국부 최대 {peak:.1f} 명/㎡",
                     "level", level, level_tag(level))
            self._level = level
        if mission_state and mission_state != self._mission:
            self.add(mission_reason or MISSION_KO.get(mission_state, mission_state),
                     "mission", 0, MISSION_KO.get(mission_state, mission_state))
            self._mission = mission_state
        if on_fallback != self._fallback:
            self.add("라이브 끊김 · 녹화본 전환" if on_fallback else "라이브 복구",
                     "warn", 2, "소스")
            self._fallback = on_fallback


class PresentationRenderer:
    def __init__(self, layout: Optional[Layout] = None,
                 painter: Optional[TextPainter] = None,
                 history: int = 300, lang: Optional[str] = None,
                 channel: str = "CAM 01", roi: Optional[Sequence] = None,
                 roi_area_m2: Optional[float] = None,
                 tiers: Sequence[float] = DEFAULT_TIERS,
                 hfov_deg: float = 70.0):
        self.L = layout or Layout()
        self.T = painter or TextPainter()
        self.lang = "ko"
        self.channel = channel
        self.roi = list(roi) if roi else None
        self.roi_area_m2 = roi_area_m2
        self.tiers = tuple(tiers)
        self.hfov = hfov_deg
        self.counts: Deque[int] = deque(maxlen=history)
        self.peaks: Deque[float] = deque(maxlen=history)
        self.levels: Deque[int] = deque(maxlen=history)
        self.active: Deque[bool] = deque(maxlen=history)
        self.log = EventLog()
        self.log.add("세션 시작", "info", 0, "SYS")
        self.level = LevelFilter(hold=8)
        self._t0 = time.monotonic()

    # ════════════════ 브랜드 ════════════════
    def _mark(self, img, x, y, c=LIME):
        """양치기 지팡이 + 로터. Shepherdron 마크."""
        col = hex_to_bgr(c)
        cv2.ellipse(img, (x + 18, y + 13), (9, 9), 0, 180, 360, col, 3, cv2.LINE_AA)
        cv2.line(img, (x + 9, y + 13), (x + 9, y + 38), col, 3, cv2.LINE_AA)
        cv2.line(img, (x + 27, y + 13), (x + 27, y + 18), col, 3, cv2.LINE_AA)
        for dx, dy in ((18, 26), (32, 26), (18, 38), (32, 38)):
            cv2.circle(img, (x + dx, y + dy), 4, col, 1, cv2.LINE_AA)
        cv2.line(img, (x + 18, y + 26), (x + 32, y + 38), col, 1, cv2.LINE_AA)
        cv2.line(img, (x + 32, y + 26), (x + 18, y + 38), col, 1, cv2.LINE_AA)

    def _tracked(self, x, y, text, size, weight, color, track=2, anchor="lm"):
        """자간을 벌려 쓴 워드마크."""
        cx = x
        for ch in text:
            self.T.add(cx, y, ch, size, weight, color, anchor)
            cx += self.T.measure(ch, size, weight)[0] + track
        return cx

    def _hdr(self, img, box, code, name, brand=False, right=""):
        x1, y1, x2, _ = box
        _fill(img, (x1, y1, x2, y1 + 30), S1)
        _line(img, (x1, y1 + 30), (x2, y1 + 30), HAIR)
        if brand:
            _fill(img, (x1, y1, x1 + 3, y1 + 30), LIME)
        self.T.add(x1 + 14, y1 + 15, code, 13, "mono", LIME if brand else TXT3, "lm")
        cw = self.T.measure(code, 13, "mono")[0]
        self.T.add(x1 + 24 + cw, y1 + 15, name, 15, "bold", TXT2, "lm")
        if right:
            self.T.add(x2 - 12, y1 + 15, right, 13, "mono", TXT3, "rm")

    # ════════════════ 영상 위 ════════════════
    def draw_overlay(self, frame, result: PipelineResult, roi: Optional[RoiReport],
                     show_heatmap=True, show_boxes=True, show_roi=True, **_):
        vis = frame.copy()
        fr = result.field
        if show_heatmap and fr is not None and fr.heat is not None:
            vis = draw_density_heat(vis, fr, self.tiers[-1] if self.tiers else 4.0)
        if show_roi and roi is not None and len(roi.polygon) >= 3:
            cv2.polylines(vis, [np.array(roi.polygon, np.int32)], True,
                          hex_to_bgr(ROI_C), 2, cv2.LINE_AA)
        if show_boxes:
            for (x1, y1, x2, y2) in result.detection.boxes:
                cv2.rectangle(vis, (x1, y1), (x2, y2), (205, 210, 214), 1)
            for fx, fy in result.detection.foot_points:
                cv2.circle(vis, (fx, fy), 2, (255, 255, 255), -1, cv2.LINE_AA)
        if result.target is not None:
            tx, ty = result.target.pixel
            c = hex_to_bgr(LIME)
            cv2.circle(vis, (tx, ty), 30, c, 2, cv2.LINE_AA)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cv2.line(vis, (tx + dx * 12, ty + dy * 12),
                         (tx + dx * 44, ty + dy * 44), c, 2, cv2.LINE_AA)
        return vis

    def _viewfinder(self, img, x1, y1, x2, y2):
        c = hex_to_bgr("#8A9097")
        L = 22
        for (cx, cy, sx, sy) in ((x1 + 10, y1 + 10, 1, 1), (x2 - 10, y1 + 10, -1, 1),
                                 (x1 + 10, y2 - 10, 1, -1), (x2 - 10, y2 - 10, -1, -1)):
            cv2.line(img, (cx, cy), (cx + sx * L, cy), c, 2, cv2.LINE_AA)
            cv2.line(img, (cx, cy), (cx, cy + sy * L), c, 2, cv2.LINE_AA)
        mx, my = (x1 + x2) // 2, (y1 + y2) // 2
        cv2.line(img, (mx - 8, my), (mx + 8, my), c, 1, cv2.LINE_AA)
        cv2.line(img, (mx, my - 8), (mx, my + 8), c, 1, cv2.LINE_AA)

    # ════════════════ 합성 ════════════════
    def render(self, frame, result: PipelineResult, *,
               tactical: Optional[TacticalPicture] = None, mission=None,
               source_label: str = "", on_fallback: bool = False,
               paused: bool = False, show_heatmap: bool = True,
               show_boxes: bool = True, show_roi: bool = True,
               model_label: str = "", **_) -> np.ndarray:
        L, T = self.L, self.T
        src_h, src_w = frame.shape[:2]
        img = np.full((L.h, L.w, 3), hex_to_bgr(BG), np.uint8)

        fr = result.field
        roi = (analyze_roi(fr, frame.shape, self.roi, "ROI", self.roi_area_m2,
                           self.tiers) if fr is not None else None)
        mstate = mission.state.value if mission is not None else None

        if roi is not None:
            roi.level = self.level.update(roi.level)
        self.counts.append(result.detection.count)
        self.peaks.append(fr.peak_density if fr else 0.0)
        self.levels.append(roi.level if roi else 0)
        self.active.append(mstate not in (None, "IDLE"))
        self.log.observe(roi.level if roi else None,
                         roi.peak_density if roi else 0.0,
                         mstate, mission.reason if mission else "", on_fallback)

        self._top(img, result, mission, on_fallback)

        # ── 영상 ──
        vx1, vy1, vx2, vy2 = L.video
        _fill(img, (vx1, vy1, vx2, vy2), "#000000")
        vis = self.draw_overlay(frame, result, roi, show_heatmap, show_boxes, show_roi)
        fit, ox, oy, _ = fit_into(vis, vx2 - vx1, vy2 - vy1)
        fh, fw = fit.shape[:2]
        ax, ay = vx1 + ox, vy1 + oy
        img[ay:ay + fh, ax:ax + fw] = fit
        self._viewfinder(img, ax, ay, ax + fw, ay + fh)
        T.add(ax + 22, ay + 22, "TOTAL", 15, "mono", "#C9CED3", "la")
        T.add(ax + 22, ay + 40, f"{result.detection.count}", 46, "mono", "#FFFFFF", "la")
        if roi is not None:
            tag = level_tag(roi.level)
            tw = T.measure(tag, 18, "black")[0]
            nw = T.measure(f"{result.detection.count}", 46, "mono")[0]
            bx = ax + 34 + nw
            _fill(img, (bx, ay + 50, bx + tw + 20, ay + 80), roi.color)
            T.add(bx + 10, ay + 65, tag, 18, "black", "#0B0D10", "lm")
        T.add(ax + fw - 22, ay + 26, f"{self.channel}  {src_w}x{src_h}  "
              f"{result.fps:4.1f}FPS", 14, "mono", "#C9CED3", "ra")
        now = time.time()
        tc = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)) + \
            f".{int((now % 1) * 100):02d}"
        T.add(ax + 22, ay + fh - 22, f"{tc}  F{result.frame_index:06d}", 14,
              "mono", "#C9CED3", "ls")
        if source_label:
            T.add(ax + fw - 22, ay + fh - 22, source_label[:28], 15, "regular",
                  "#C9CED3", "rs")
        if on_fallback:
            _fill(img, (vx1, vy1, vx2, vy1 + 28), "#6B4E10")
            T.add((vx1 + vx2) // 2, vy1 + 14, "라이브 소스 끊김 — 녹화본 재생 중",
                  15, "bold", "#FFF1CC", "mm")
        if paused:
            T.add(ax + fw - 22, ay + 52, "PAUSED", 16, "mono", "#F0C040", "ra")
        _stroke(img, (vx1, vy1, vx2, vy2), LINE)

        self._readout(img, result, roi)
        self._trend(img)
        self._tac(img, tactical, mission)
        self._msn(img, mission, tactical)
        self._log(img)
        return T.flush(img)

    # ════════════════ 상단 ════════════════
    def _top(self, img, result, mission, on_fallback):
        L, T = self.L, self.T
        _fill(img, (0, 0, L.w, L.top_h), S1)
        _line(img, (0, L.top_h - 1), (L.w, L.top_h - 1), LINE)
        self._mark(img, L.m + 2, 8)
        ex = self._tracked(L.m + 54, 22, "SHEPHERDRON", 21, "black", TXT, track=3)
        T.add(L.m + 54, 42, "CROWD GUIDANCE DRONE", 11, "mono", TXT3, "lm")
        _line(img, (ex + 18, 14), (ex + 18, L.top_h - 14), LINE)
        T.add(ex + 34, 28, "군중 밀집 감지 · 유도 관제", 15, "regular", TXT2, "lm")

        rx = L.w - L.m
        now = time.time()
        clock = time.strftime("%H:%M:%S", time.localtime(now)) + f".{int((now % 1) * 10)}"
        T.add(rx, 28, clock, 20, "mono", TXT, "rm")
        rx -= T.measure(clock, 20, "mono")[0] + 26
        _line(img, (rx + 13, 14), (rx + 13, L.top_h - 14), LINE)

        def pill(label, val, col, fill=None):
            nonlocal rx
            vw = T.measure(val, 15, "bold")[0]
            lw = T.measure(label, 12, "mono")[0]
            w = lw + vw + 30
            if fill:
                _fill(img, (rx - w, 15, rx, L.top_h - 15), fill)
            T.add(rx - 10, 28, val, 15, "bold", col, "rm")
            T.add(rx - 20 - vw, 28, label, 12, "mono", TXT3 if not fill else "#0B0D10", "rm")
            rx -= w + 12

        if mission is not None:
            ms = mission.state.value
            active = ms != "IDLE"
            pill("MSN", MISSION_KO.get(ms, ms), "#0B0D10" if active else TXT2,
                 LIME if active else None)
            pill("UAV", "가상 기체", TXT2)
        live = not on_fallback
        pill("SRC", "LIVE" if live else "REPLAY", "#FF5A4F" if live else TXT2)
        if live and (result.frame_index // 8) % 2 == 0:
            cv2.circle(img, (int(rx + 4), 28), 4, hex_to_bgr("#FF5A4F"), -1,
                       cv2.LINE_AA)

    # ════════════════ 수치 ════════════════
    def _readout(self, img, result, roi):
        L, T = self.L, self.T
        x1, y1, x2, y2 = L.readout
        _fill(img, (x1, y1, x2, y2), S1)
        _stroke(img, (x1, y1, x2, y2), HAIR)
        fr = result.field
        cells = [
            ("인원", f"{roi.count if roi else result.detection.count}", "명"),
            ("면적", f"{roi.area_m2:.0f}" if roi and roi.area_m2 else "—", "㎡"),
            ("군중밀도", f"{roi.density:.2f}" if roi else "—", "명/㎡"),
            ("국부 최대", f"{fr.peak_density:.2f}" if fr else "—", "명/㎡"),
        ]
        n = len(cells) + 1
        cw = (x2 - x1) / n
        for i, (k, v, u) in enumerate(cells):
            cx = int(x1 + i * cw)
            if i:
                _line(img, (cx, y1 + 14), (cx, y2 - 14), HAIR)
            T.add(cx + 20, y1 + 22, k, 14, "regular", TXT3, "lm")
            T.add(cx + 20, y1 + 58, v, 34, "mono", TXT, "lm")
            vw = T.measure(v, 34, "mono")[0]
            T.add(cx + 26 + vw, y1 + 64, u, 14, "regular", TXT3, "lm")
        cx = int(x1 + (n - 1) * cw)
        _line(img, (cx, y1 + 14), (cx, y2 - 14), HAIR)
        T.add(cx + 20, y1 + 22, "등급", 14, "regular", TXT3, "lm")
        if roi is not None:
            for k in range(5):
                bx = cx + 20 + k * 36
                on = k <= roi.level
                _fill(img, (bx, y1 + 44, bx + 30, y1 + 52),
                      level_color(k) if on else "#20252A")
            T.add(cx + 20, y1 + 70, level_tag(roi.level), 18, "black",
                  roi.color, "lm")
            T.add(x2 - 14, y1 + 22, "국부 최대 기준", 12, "regular", TXT3, "rm")

    # ════════════════ 추이 ════════════════
    def _trend(self, img):
        L, T = self.L, self.T
        box = L.trend
        x1, y1, x2, y2 = box
        _fill(img, box, S1)
        _stroke(img, box, HAIR)
        last = (f"PEAK {self.peaks[-1]:.2f}  N {self.counts[-1]}  ·  "
                if self.peaks else "")
        self._hdr(img, box, "DNS", "밀집 추이 · 국부 최대",
                  right=f"{last}{len(self.peaks)}F")
        px1, py1, px2, py2 = x1 + 52, y1 + 44, x2 - 18, y2 - 30
        n = len(self.peaks)
        top = self.tiers[-1] * 1.5 if self.tiers else 6.0

        def yv(v):
            return py2 - min(v, top) / top * (py2 - py1)

        for i, tv in enumerate(self.tiers):
            gy = yv(tv)
            _dashed(img, (px1, gy), (px2, gy), level_color(i + 1), 1, 4, 6)
            T.add(px1 - 8, gy, f"{tv:g}", 12, "mono", level_color(i + 1), "rm")
        _line(img, (px1, py2), (px2, py2), LINE)
        T.add(px1 - 8, py2, "0", 12, "mono", TXT3, "rm")
        T.add(px1, py2 + 16, "MSN", 11, "mono", LIME_DIM, "lm")
        if n < 2:
            return
        xs = np.linspace(px1, px2, n)
        for i in range(n - 1):
            if self.active[i]:
                _fill(img, (xs[i], py2 + 6, max(xs[i] + 2, xs[i + 1]), py2 + 10), LIME)
        cmax = max(4, max(self.counts))
        cpts = np.array([[int(xs[i]), int(py2 - c / cmax * (py2 - py1))]
                         for i, c in enumerate(self.counts)], np.int32)
        cv2.polylines(img, [cpts], False, hex_to_bgr("#3A4148"), 1, cv2.LINE_AA)
        for i in range(n - 1):
            _line(img, (xs[i], yv(self.peaks[i])), (xs[i + 1], yv(self.peaks[i + 1])),
                  level_color(self.levels[i + 1]), 2)


    # ════════════════ 전술 지도 ════════════════
    def _tac(self, img, pic: Optional[TacticalPicture], mission):
        L, T = self.L, self.T
        box = L.tac
        x1, y1, x2, y2 = box
        _fill(img, box, S1)
        _stroke(img, box, HAIR)

        drone = mission.drone if mission is not None else None
        need = 8.0
        if pic is not None and pic.people:
            # 멀리 선 한두 명 때문에 축척이 넓어지면 정작 군집이 점으로 줄어든다.
            # 85 번째 백분위로 축척을 잡고, 핫스팟과 기체는 반드시 들어오게 한다.
            rs = sorted(math.hypot(p.right_m, p.forward_m) for p in pic.people)
            need = max(need, rs[int(0.85 * (len(rs) - 1))] * 1.25)
            if pic.hotspot is not None:
                need = max(need, math.hypot(*pic.hotspot) * 1.35)
        if drone is not None:
            need = max(need, math.hypot(*drone.position) * 1.2)
        step = next(s for s in (1, 2, 5, 10, 20) if need / s <= 5)
        rmax = step * math.ceil(need / step)
        self._hdr(img, box, "TAC", "전술 지도", brand=True,
                  right=f"RING {step}m  ·  HFOV {self.hfov:.0f}°")

        mx1, my1, mx2, my2 = x1 + 1, y1 + 31, x2 - 1, y2 - 1
        ox, oy = (mx1 + mx2) / 2, my2 - 34
        ppm = min((oy - my1 - 20) / rmax, (mx2 - mx1) / 2 / (rmax * 0.9))

        def P(r, f):
            return ox + r * ppm, oy - f * ppm

        # 격자 1 m
        for k in range(-int(rmax) - 1, int(rmax) + 2):
            gx = ox + k * ppm
            if mx1 < gx < mx2:
                _line(img, (gx, my1), (gx, my2), "#14171A")
        for k in range(0, int(rmax) + 2):
            gy = oy - k * ppm
            if my1 < gy < my2:
                _line(img, (mx1, gy), (mx2, gy), "#14171A")
        # 시야 쐐기
        half = math.radians(self.hfov / 2)
        far = rmax * 1.2
        wedge = np.array([P(0, 0), P(far * math.sin(-half), far * math.cos(half)),
                          P(far * math.sin(half), far * math.cos(half))], np.int32)
        ov = img.copy()
        cv2.fillPoly(ov, [wedge], hex_to_bgr("#171B20"))
        cv2.addWeighted(ov, 0.9, img, 0.1, 0, img)
        _line(img, P(0, 0), wedge[1], LINE)
        _line(img, P(0, 0), wedge[2], LINE)
        # 거리 링
        for r in np.arange(step, rmax + 1e-6, step):
            cv2.ellipse(img, (int(ox), int(oy)), (int(r * ppm), int(r * ppm)), 0,
                        180, 360, hex_to_bgr(LINE), 1, cv2.LINE_AA)
            lx, ly = P(-(r) * math.sin(half) - 0.1, r * math.cos(half))
            T.add(int(lx) - 6, int(ly), f"{r:g}m", 12, "mono", TXT3, "rm")

        # 사람
        if pic is not None:
            for p in pic.people:
                lv = sum(1 for t in self.tiers if p.density >= t)
                cx_, cy_ = P(p.right_m, p.forward_m)
                if my1 < cy_ < my2 and mx1 < cx_ < mx2:
                    cv2.circle(img, (int(cx_), int(cy_)), 4,
                               hex_to_bgr(level_color(lv)), -1, cv2.LINE_AA)
            if pic.hotspot is not None:
                hx, hy = P(*pic.hotspot)
                lv = sum(1 for t in self.tiers if pic.hotspot_density >= t)
                for rr, th in ((0.75, 2), (1.5, 1)):
                    cv2.circle(img, (int(hx), int(hy)), int(rr * ppm),
                               hex_to_bgr(level_color(lv)), th, cv2.LINE_AA)
                T.add(int(hx - 1.5 * ppm) - 6, int(hy - 1.5 * ppm * 0.7),
                      f"{pic.hotspot_density:.1f}", 14, "mono", level_color(lv), "rm")
                ev = pic.evacuation
                if ev is not None and lv >= 2:
                    ex, ey = P(*ev.point)
                    d = max(1.0, math.hypot(ex - hx, ey - hy))
                    ux, uy = (ex - hx) / d, (ey - hy) / d
                    a0 = 1.5 * ppm + 6                    # 핫스팟 바깥 링에서 시작
                    a1 = a0 + max(46.0, 2.2 * ppm)        # 사람이 2 m 이상 빠지는 방향
                    _arrow(img, (hx + ux * a0, hy + uy * a0),
                           (hx + ux * a1, hy + uy * a1), LIME, 4, 16)
                    lx = hx + ux * (a1 + 14)
                    ly = hy + uy * (a1 + 14)
                    T.add(int(lx), int(ly), f"유도 {ev.name}", 15, "bold", LIME,
                          "lm" if ux >= -0.2 else "rm")

        # 이륙 지점
        hx0, hy0 = P(0, 0)
        cv2.circle(img, (int(hx0), int(hy0)), 9, hex_to_bgr(TXT3), 1, cv2.LINE_AA)
        T.add(int(hx0), int(hy0), "H", 11, "mono", TXT2, "mm")
        T.add(int(hx0), int(hy0) + 20, "CAM · 이륙점", 12, "regular", TXT3, "mm")

        # 기체
        if drone is not None:
            tr = list(drone.trail)
            for i in range(1, len(tr), 2):
                _line(img, P(*tr[i - 1]), P(*tr[i]), LIME_DIM, 1)
            dx, dy = P(*drone.position)
            if mission.state.value == "NAVIGATING" and drone.goal is not None:
                gx, gy = P(*drone.goal)
                _dashed(img, (dx, dy), (gx, gy), LIME, 2, 10, 6)
                cv2.circle(img, (int(gx), int(gy)), 6, hex_to_bgr(LIME), 1, cv2.LINE_AA)
            if mission.state.value == "HOVERING":
                pulse = 0.6 + 0.4 * abs(math.sin(time.monotonic() * 3))
                cv2.circle(img, (int(dx), int(dy)), int(ppm * 1.0 * pulse + 6),
                           hex_to_bgr(LIME), 2, cv2.LINE_AA)
            self._drone_icon(img, dx, dy, drone.state.heading_deg or 0.0,
                             airborne=drone.flying)
            if drone.flying:
                T.add(int(dx) + 18, int(dy) - 16,
                      f"{drone.state.relative_alt_m or 0:.1f}m", 13, "mono", LIME, "lm")

        T.add(mx1 + 12, my2 - 12, "카메라 기준 · 겉보기 크기 투영", 12, "regular",
              TXT3, "ls")

    def _drone_icon(self, img, x, y, heading_deg, airborne=True):
        c = hex_to_bgr(LIME if airborne else "#7D8A55")
        a = math.radians(heading_deg)
        arm = 11
        for k in range(4):
            ang = a + math.radians(45 + 90 * k)
            ex, ey = x + arm * math.sin(ang), y - arm * math.cos(ang)
            cv2.line(img, (int(x), int(y)), (int(ex), int(ey)), c, 2, cv2.LINE_AA)
            cv2.circle(img, (int(ex), int(ey)), 5, c, 1, cv2.LINE_AA)
        nx, ny = x + 16 * math.sin(a), y - 16 * math.cos(a)
        cv2.line(img, (int(x), int(y)), (int(nx), int(ny)), c, 2, cv2.LINE_AA)
        cv2.circle(img, (int(x), int(y)), 3, c, -1, cv2.LINE_AA)

    # ════════════════ 임무 ════════════════
    def _msn(self, img, mission, pic):
        L, T = self.L, self.T
        box = L.msn
        x1, y1, x2, y2 = box
        _fill(img, box, S1)
        _stroke(img, box, HAIR)
        right = ""
        if mission is not None:
            right = f"DONE {mission.mission.missions_completed}"
        self._hdr(img, box, "MSN", "임무", brand=True, right=right)

        y = y1 + 44
        cur = mission.state.value if mission is not None else "IDLE"
        idx = TRACK.index(cur) if cur in TRACK else -1
        seg_w = (x2 - x1 - 24 - 4 * 6) / 5
        for k, st in enumerate(TRACK):
            bx = x1 + 12 + k * (seg_w + 6)
            if k == idx:
                _fill(img, (bx, y, bx + seg_w, y + 34), LIME)
                col = "#0B0D10"
            elif 0 < k < idx:
                _stroke(img, (bx, y, bx + seg_w, y + 34), LIME_DIM)
                col = LIME_DIM
            else:
                _stroke(img, (bx, y, bx + seg_w, y + 34), LINE)
                col = TXT3
            T.add(bx + seg_w / 2, y + 17, MISSION_KO[st], 15, "bold", col, "mm")
            if k < 4:
                T.add(bx + seg_w + 3, y + 17, "›", 14, "regular", TXT3, "mm")
        if cur in ("STANDBY", "FAILSAFE"):
            _fill(img, (x1 + 12, y, x2 - 12, y + 34),
                  "#7A2A22" if cur == "FAILSAFE" else "#2A3A5A")
            T.add((x1 + x2) / 2, y + 17, f"{MISSION_KO[cur]} · 임무 명령 중지", 15,
                  "bold", "#FFFFFF", "mm")
        y += 50

        rows: List[Tuple[str, str, str]] = []
        if mission is not None:
            d = mission.drone
            rows.append(("사유", mission.reason or "경보 대기", "ko"))
            if cur != "IDLE" and mission.goal_ground is not None:
                gr, gf = mission.goal_ground
                px, py = d.position
                rows.append(("지령", f"FWD {gf - py:+5.1f}m   RGT {gr - px:+5.1f}m", "mono"))
            else:
                rows.append(("지령", "—", "mono"))
        ev = pic.evacuation if pic is not None else None
        if ev is not None and pic.hotspot_density >= (self.tiers[1] if len(self.tiers) > 1 else 2):
            rows.append(("유도", f"{ev.name}  →  {ev.density_there:.1f} 명/㎡ 구역", "ko"))
        else:
            rows.append(("유도", "—", "mono"))
        if mission is not None:
            d = mission.drone
            rows.append(("기체", f"ALT {d.state.relative_alt_m or 0:4.1f}m  "
                                 f"GS {d.state.groundspeed_ms or 0:3.1f}m/s  "
                                 f"BAT {d.state.battery_remaining_pct or 0:3d}%", "mono"))
            ps = mission.payload.state.value
            rows.append(("구조물", PAYLOAD_KO.get(ps, ps), "ko"))
        for i, (k, v, kind) in enumerate(rows):
            ry = y + i * 30
            if ry + 20 > y2:
                break
            _line(img, (x1 + 12, ry + 26), (x2 - 12, ry + 26), HAIR)
            T.add(x1 + 16, ry + 12, k, 14, "regular", TXT3, "lm")
            hi = (k in ("지령", "유도") and v != "—") or (k == "구조물" and v in ("전개", "전개 중"))
            T.add(x1 + 92, ry + 12, v, 15 if kind == "mono" else 15,
                  "mono" if kind == "mono" else "bold", LIME if hi else TXT, "lm")

    # ════════════════ 이벤트 ════════════════
    def _log(self, img):
        L, T = self.L, self.T
        box = L.log
        x1, y1, x2, y2 = box
        _fill(img, box, S1)
        _stroke(img, box, HAIR)
        self._hdr(img, box, "LOG", "이벤트", right=f"{len(self.log.items)}")
        rh = 30
        avail = max(0, (y2 - y1 - 36) // rh)
        items = list(self.log.items)[-avail:][::-1]
        for i, ev in enumerate(items):
            ry = y1 + 36 + i * rh
            T.add(x1 + 14, ry + 13, ev.t, 13, "mono", TXT3, "lm")
            if ev.kind == "mission":
                fill, tc = LIME, "#0B0D10"
            elif ev.kind == "level":
                fill, tc = level_color(ev.level), "#0B0D10"
            elif ev.kind == "warn":
                fill, tc = "#6B4E10", "#FFF1CC"
            else:
                fill, tc = "#22272C", TXT2
            tag = ev.tag or "SYS"
            tw = T.measure(tag, 13, "bold")[0]
            _fill(img, (x1 + 92, ry + 3, x1 + 104 + tw, ry + 23), fill)
            T.add(x1 + 98, ry + 13, tag, 13, "bold", tc, "lm")
            T.add(x1 + 116 + tw, ry + 13, ev.text[:30], 14, "regular",
                  TXT if ev.kind in ("mission", "level") else TXT2, "lm")
