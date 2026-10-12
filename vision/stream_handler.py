import os
import threading
import time
from typing import Optional, Tuple, Union

import cv2
import numpy as np


class StreamHandler:
    """
    IP Webcam (HTTP/RTSP), 로컬 웹캠(0, 1), 비디오 파일을
    버퍼 지연 없이 최신 프레임으로 수신하는 멀티스레드 스트림 처리기
    """

    def __init__(
        self,
        source: Union[str, int],
        reconnect_interval: float = 3.0,
        loop_files: bool = False,
    ):
        # 소스가 숫자로 된 문자열인 경우 int로 변환 (웹캠 번호)
        if isinstance(source, str) and source.isdigit():
            self.source = int(source)
        else:
            self.source = source

        # 동영상 파일은 끝이 있다. 네트워크 스트림처럼 무한 재연결하면
        # 녹화 클립으로 테스트할 때 프로그램이 영영 끝나지 않는다.
        self.is_file = (
            isinstance(self.source, str)
            and "://" not in self.source
            and os.path.exists(self.source)
        )
        self.loop_files = loop_files
        self.exhausted = False          # 파일 끝에 도달했는가

        self.reconnect_interval = reconnect_interval
        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.is_running = False
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.connected = False

    def start(self) -> "StreamHandler":
        self.is_running = True
        self._connect()
        # 라이브 스트림은 지연이 생명이므로 백그라운드에서 최신 프레임만 남긴다.
        # 반대로 동영상 파일은 모든 프레임을 빠짐없이 봐야 하므로(임계치 튜닝,
        # 벤치마크) 소비자 속도에 맞춰 동기로 읽는다.
        if not self.is_file:
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()
        return self

    def _connect(self):
        print(f"[StreamHandler] Connecting to video source: {self.source}...")
        if self.cap is not None:
            self.cap.release()

        self.cap = cv2.VideoCapture(self.source)

        # IP 스트림 버퍼 최소화 설정 (지연 방지)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if self.cap.isOpened():
            self.connected = True
            print(f"[StreamHandler] Successfully connected to {self.source}!")
        else:
            self.connected = False
            print(f"[StreamHandler] Failed to open stream: {self.source}. Will retry in background.")

    def _capture_loop(self):
        """백그라운드에서 최신 프레임을 끊임없이 갱신하여 지연(Lag)을 없앱니다."""
        while self.is_running:
            if not self.connected or self.cap is None or not self.cap.isOpened():
                time.sleep(self.reconnect_interval)
                if self.is_running:
                    self._connect()
                continue

            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.latest_frame = frame
                self.connected = True
                continue

            if self.is_file:
                if self.loop_files:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                print("[StreamHandler] End of file reached.")
                self.exhausted = True
                self.connected = False
                self.is_running = False
                return

            # 네트워크 스트림: 끊김으로 보고 재연결한다
            print("[StreamHandler] Frame drop or connection lost. Reconnecting...")
            self.connected = False
            time.sleep(1.0)
            if self.is_running:
                self._connect()

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """라이브 소스는 최신 프레임을, 파일은 다음 프레임을 순서대로 반환."""
        if self.is_file:
            if self.cap is None or self.exhausted:
                return False, None
            ok, frame = self.cap.read()
            if ok and frame is not None:
                return True, frame
            if self.loop_files:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
                if ok and frame is not None:
                    return True, frame
            print("[StreamHandler] End of file reached.")
            self.exhausted = True
            self.connected = False
            return False, None

        with self.lock:
            if self.latest_frame is not None:
                frame = self.latest_frame
                # 파일 재생이 끝났으면 같은 프레임을 무한히 돌려주지 않는다
                if self.exhausted:
                    self.latest_frame = None
                return True, frame.copy()
            return False, None

    @property
    def finished(self) -> bool:
        """더 이상 읽을 프레임이 없는가 (파일 소스 전용)."""
        return self.exhausted

    def stop(self):
        """스트림 종료 및 리소스 해제"""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.cap is not None:
            self.cap.release()
        self.connected = False
        print("[StreamHandler] Stream released and closed.")
