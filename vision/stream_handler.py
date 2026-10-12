import cv2
import threading
import time
from typing import Optional, Union, Tuple
import numpy as np


class StreamHandler:
    """
    IP Webcam (HTTP/RTSP), 로컬 웹캠(0, 1), 비디오 파일을
    버퍼 지연 없이 최신 프레임으로 수신하는 멀티스레드 스트림 처리기
    """

    def __init__(self, source: Union[str, int], reconnect_interval: float = 3.0):
        # 소스가 숫자로 된 문자열인 경우 int로 변환 (웹캠 번호)
        if isinstance(source, str) and source.isdigit():
            self.source = int(source)
        else:
            self.source = source

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
            else:
                # 프레임 수신 실패 (연결 끊김)
                print("[StreamHandler] Frame drop or connection lost. Reconnecting...")
                self.connected = False
                time.sleep(1.0)
                if self.is_running:
                    self._connect()

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """가장 최신 프레임을 논블로킹으로 반환"""
        with self.lock:
            if self.latest_frame is not None:
                return True, self.latest_frame.copy()
            return False, None

    def stop(self):
        """스트림 종료 및 리소스 해제"""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.cap is not None:
            self.cap.release()
        self.connected = False
        print("[StreamHandler] Stream released and closed.")
