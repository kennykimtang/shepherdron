#!/usr/bin/env python3
"""기체 카메라 MJPEG 스트리밍 — 지상국이 이 영상을 받아 YOLO 를 돌린다.

라즈베리파이에서 실행한다. CSI 카메라(또는 USB/웹캠)를 열어 HTTP MJPEG 로 내보낸다.

사용법
    python scripts/stream_camera.py                      # CSI, 1280x720
    python scripts/stream_camera.py --source 0 --width 640 --height 480
지상국에서
    python shepherdron_ground.py --source http://<pi-ip>:8000/stream.mjpg --pi <pi-ip>
"""
from __future__ import annotations

import argparse
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vision.camera import open_source  # noqa: E402

_frame_lock = threading.Lock()
_latest_jpeg: bytes | None = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):            # 요청마다 로그를 찍지 않는다
        pass

    def do_GET(self):
        if self.path not in ("/stream.mjpg", "/"):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
        self.end_headers()
        try:
            while True:
                with _frame_lock:
                    buf = _latest_jpeg
                if buf is None:
                    continue
                self.wfile.write(b"--FRAME\r\n")
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(buf)))
                self.end_headers()
                self.wfile.write(buf)
                self.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass


class Server(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser(description="Stream the aircraft camera as MJPEG")
    ap.add_argument("--source", default="csi", help='"csi" | 웹캠 번호 | 파일')
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--quality", type=int, default=70, help="JPEG 품질 (낮출수록 대역폭 절약)")
    args = ap.parse_args()

    cam = open_source(args.source, args.width, args.height, args.fps).start()
    print(f"[stream] http://0.0.0.0:{args.port}/stream.mjpg  "
          f"({args.width}x{args.height} q{args.quality})")

    def capture():
        global _latest_jpeg
        params = [int(cv2.IMWRITE_JPEG_QUALITY), args.quality]
        while True:
            ok, frame = cam.read()
            if not ok or frame is None:
                continue
            ok, buf = cv2.imencode(".jpg", frame, params)
            if ok:
                with _frame_lock:
                    _latest_jpeg = buf.tobytes()

    threading.Thread(target=capture, daemon=True).start()
    try:
        Server(("", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n[stream] 종료")
    finally:
        cam.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
