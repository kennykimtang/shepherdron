"""카메라 소스 추상화 — 개발 PC(IP Webcam/USB)와 라즈베리파이 CSI 를 동일 API 로.

StreamHandler 는 cv2.VideoCapture 기반이라 라즈베리파이 카메라 모듈 3 을
libcamera 스택으로 열 수 없다. Picamera2 백엔드를 따로 두고,
open_source() 가 소스 문자열을 보고 적절한 백엔드를 고른다.
"""
from __future__ import annotations

from typing import Optional, Protocol, Tuple, Union

import numpy as np


class FrameSource(Protocol):
    def start(self) -> "FrameSource": ...
    def read(self) -> Tuple[bool, Optional[np.ndarray]]: ...
    def stop(self) -> None: ...
    @property
    def connected(self) -> bool: ...


class PiCameraSource:
    """Raspberry Pi Camera Module 3 (libcamera / Picamera2) 백엔드.

    개발 PC 에는 picamera2 가 없으므로 import 를 생성 시점까지 미룬다.
    """

    def __init__(self, width: int = 1280, height: int = 720, framerate: int = 30):
        self.width = width
        self.height = height
        self.framerate = framerate
        self._cam = None
        self._connected = False

    def start(self) -> "PiCameraSource":
        try:
            from picamera2 import Picamera2       # type: ignore
        except ImportError as exc:                 # pragma: no cover - Pi 전용 경로
            raise RuntimeError(
                "picamera2 가 없습니다. 라즈베리파이에서 "
                "`sudo apt install -y python3-picamera2` 로 설치하고, "
                "venv 는 --system-site-packages 로 만들어야 합니다."
            ) from exc

        self._cam = Picamera2()
        cfg = self._cam.create_video_configuration(
            main={"size": (self.width, self.height), "format": "RGB888"},
            controls={"FrameRate": self.framerate},
        )
        self._cam.configure(cfg)
        self._cam.start()
        self._connected = True
        print(f"[PiCameraSource] CSI camera started at {self.width}x{self.height}@{self.framerate}")
        return self

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cam is None:
            return False, None
        # Picamera2 는 RGB 로 주고 OpenCV 는 BGR 을 기대한다
        frame = self._cam.capture_array()
        if frame is None:
            return False, None
        return True, frame[:, :, ::-1].copy()

    def stop(self) -> None:
        if self._cam is not None:
            self._cam.stop()
            self._cam.close()
            self._cam = None
        self._connected = False
        print("[PiCameraSource] CSI camera released.")

    @property
    def connected(self) -> bool:
        return self._connected


def open_source(
    source: Union[str, int],
    width: int = 1280,
    height: int = 720,
    framerate: int = 30,
) -> FrameSource:
    """소스 지정자에 맞는 백엔드를 고른다.

      "csi" / "picam"            → PiCameraSource (라즈베리파이 CSI)
      0, 1, "0"                  → USB / 내장 웹캠
      "http://…", "rtsp://…"     → 네트워크 스트림
      "clip.mp4"                 → 파일
    """
    if isinstance(source, str) and source.strip().lower() in {"csi", "picam", "picamera"}:
        return PiCameraSource(width=width, height=height, framerate=framerate)

    from vision.stream_handler import StreamHandler
    return StreamHandler(source=source)
