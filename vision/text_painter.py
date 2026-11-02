"""한글 텍스트 렌더러 — OpenCV 는 CJK 를 못 그리므로 PIL 로 한 번에 얹는다.

프레임마다 PIL 왕복을 여러 번 하면 비싸다. 그래서 렌더러가 그리는 동안
텍스트를 모아 두었다가 flush() 에서 한 번만 변환한다.

한글 폰트를 못 찾으면 has_korean 이 False 가 되고, 호출 측이 영문 라벨로
바꿔 쓴다. 팀원 노트북에 폰트가 없어도 네모 상자가 뜨지 않게 하려는 것이다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# 굵기별 후보. 앞에서부터 처음 찾은 것을 쓴다.
_FONT_CANDIDATES: Dict[str, Sequence[str]] = {
    "regular": (
        "assets/fonts/Pretendard-Regular.otf",
        "~/Library/Fonts/Pretendard-Regular.otf",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
    ),
    "bold": (
        "assets/fonts/Pretendard-Bold.otf",
        "~/Library/Fonts/Pretendard-Bold.otf",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
    ),
    # 숫자·시각·좌표 전용. 계기 숫자는 고정폭이어야 자릿수가 흔들리지 않는다.
    # 한글 글리프가 없으므로 ASCII 에만 쓴다.
    "mono": (
        "assets/fonts/JetBrainsMono-Medium.ttf",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ),
    "black": (
        "assets/fonts/Pretendard-Black.otf",
        "~/Library/Fonts/Pretendard-Black.otf",
        "~/Library/Fonts/Pretendard-ExtraBold.otf",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
    ),
}


def _resolve(weight: str) -> Optional[str]:
    env = os.getenv("SHEPHERDRON_FONT")
    if weight != "mono" and env and Path(env).expanduser().exists():
        return str(Path(env).expanduser())
    for cand in _FONT_CANDIDATES.get(weight, ()):
        p = Path(cand).expanduser()
        if p.exists():
            return str(p)
    return None


def hex_to_rgb(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def hex_to_bgr(c: str) -> Tuple[int, int, int]:
    r, g, b = hex_to_rgb(c)
    return (b, g, r)


@dataclass
class TextOp:
    x: int
    y: int
    text: str
    size: int = 20
    weight: str = "regular"
    color: str = "#FFFFFF"
    anchor: str = "la"               # PIL anchor: l/m/r + a(scender)/m/s/d
    spacing: int = 4


class TextPainter:
    """PIL 폰트를 캐시하고, 모아 둔 TextOp 를 한 번에 그린다."""

    def __init__(self) -> None:
        self._paths = {w: _resolve(w) for w in _FONT_CANDIDATES}
        self._cache: Dict[Tuple[str, int], ImageFont.ImageFont] = {}
        self._ops: List[TextOp] = []

    @property
    def has_korean(self) -> bool:
        """한글을 그릴 수 있는 폰트를 찾았는가."""
        return self._paths.get("regular") is not None

    def font(self, size: int, weight: str = "regular") -> ImageFont.ImageFont:
        key = (weight, size)
        if key not in self._cache:
            path = self._paths.get(weight) or self._paths.get("regular")
            if path:
                self._cache[key] = ImageFont.truetype(path, size)
            else:
                self._cache[key] = ImageFont.load_default()
        return self._cache[key]

    # ── 수집 ──────────────────────────────────────────────
    def add(self, x: int, y: int, text: str, size: int = 20,
            weight: str = "regular", color: str = "#FFFFFF",
            anchor: str = "la", spacing: int = 4) -> None:
        self._ops.append(TextOp(int(x), int(y), str(text), size, weight,
                                color, anchor, spacing))

    def clear(self) -> None:
        self._ops.clear()

    @property
    def pending(self) -> int:
        return len(self._ops)

    # ── 측정 ──────────────────────────────────────────────
    def measure(self, text: str, size: int, weight: str = "regular") -> Tuple[int, int]:
        f = self.font(size, weight)
        box = f.getbbox(str(text))
        return (box[2] - box[0], box[3] - box[1])

    # ── 출력 ──────────────────────────────────────────────
    def flush(self, bgr: np.ndarray) -> np.ndarray:
        """모아 둔 텍스트를 BGR 배열에 그려 넣고 비운다. 제자리 수정이 아니다."""
        if not self._ops:
            return bgr
        img = Image.fromarray(bgr[:, :, ::-1])
        draw = ImageDraw.Draw(img)
        for op in self._ops:
            draw.text((op.x, op.y), op.text, font=self.font(op.size, op.weight),
                      fill=hex_to_rgb(op.color), anchor=op.anchor,
                      spacing=op.spacing)
        self._ops.clear()
        return np.asarray(img)[:, :, ::-1].copy()
