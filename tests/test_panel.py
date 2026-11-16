"""기체 제어판 서버 테스트 — 카메라 · GPIO 없이 돈다.

지켜야 할 것
    1. 프레임은 조각이 어떻게 잘려 와도 정확히 떼어 낸다.
    2. docs/ 바깥 파일은 절대 내보내지 않는다. 기체에서 도는 서버다.
    3. 비전 앱 · 영상 · 상태 경로가 모두 살아 있다.
"""
import http.client
import importlib.util
import json
import pathlib
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from hardware.payload_tape import FakeBackend, TapeBoomConfig, TapeBoomPayload

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("panel", ROOT / "scripts" / "panel.py")
panel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(panel)

JPEG = b"\xff\xd8" + b"\x01\x02\xff\x00\x03" + b"\xff\xd9"


class TestSplit:
    def test_single_frame(self):
        frames, rest = panel.split_jpegs(b"--FRAME\r\n\r\n" + JPEG + b"\r\n")
        assert frames == [JPEG]
        assert len(rest) <= 2

    def test_many_frames_in_one_read(self):
        frames, _ = panel.split_jpegs(JPEG + b"xx" + JPEG + JPEG)
        assert frames == [JPEG, JPEG, JPEG]

    def test_partial_frame_is_kept_for_the_next_read(self):
        frames, rest = panel.split_jpegs(b"junk" + JPEG[:5])
        assert frames == []
        frames, _ = panel.split_jpegs(rest + JPEG[5:])
        assert frames == [JPEG]

    def test_start_marker_split_across_reads(self):
        data = b"head" + JPEG
        cut = data.index(b"\xff\xd8") + 1          # FF 와 D8 사이
        frames, rest = panel.split_jpegs(data[:cut])
        assert frames == []
        frames, _ = panel.split_jpegs(rest + data[cut:])
        assert frames == [JPEG]

    def test_byte_by_byte(self):
        buf, got = b"", []
        for b in b"--FRAME\r\n" + JPEG + b"\r\n" + JPEG:
            frames, buf = panel.split_jpegs(buf + bytes([b]))
            got += frames
        assert got == [JPEG, JPEG]


class FakeCam:
    ok, error, frames, measured_fps, info = True, "", 1, 20.0, "test"

    def wait(self, last, timeout=5.0):
        if last >= 1:
            time.sleep(0.05)
        return last + 1, JPEG

    def close(self):
        pass


@pytest.fixture
def server():
    svc = panel.Service(TapeBoomPayload(FakeBackend(travel_s=3.0), TapeBoomConfig()), FakeCam())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_handler(svc, "/dev/null", 921600))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    svc.close()


def get(port, path):
    """스트림은 끝이 없으므로 앞부분만, 나머지는 전부 읽는다."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", path)
    r = c.getresponse()
    ct = r.getheader("Content-Type") or ""
    body = r.read(4096) if ct.startswith("multipart/") else r.read()
    return r.status, ct, body, c


class TestRoutes:
    def test_root_is_the_vision_app_with_the_aircraft_camera(self, server):
        st, ct, body, _ = get(server, "/")
        assert st == 200 and "text/html" in ct
        assert b'id="btnPi"' in body

    def test_scripts_are_served_as_javascript(self, server):
        for path in ("/app.js", "/mjpeg.js", "/detector.js"):
            st, ct, _, _ = get(server, path)
            assert st == 200 and "javascript" in ct, path

    def test_state_reports_camera_fps(self, server):
        st, ct, body, _ = get(server, "/api/state")
        s = json.loads(body)
        assert st == 200 and "json" in ct
        assert s["camera_ok"] is True and s["camera_fps"] == 20.0

    def test_camera_stream_sends_jpeg(self, server):
        st, ct, body, c = get(server, "/camera.mjpg")
        c.close()
        assert st == 200 and ct.startswith("multipart/x-mixed-replace")
        assert b"\xff\xd8" in body

    def test_panel_page(self, server):
        st, _, body, _ = get(server, "/panel")
        assert st == 200 and "제어판".encode() in body

    @pytest.mark.parametrize("path", ["/../scripts/panel.py", "/%2e%2e/scripts/panel.py",
                                      "/../../etc/passwd", "/..%2fscripts%2fpanel.py"])
    def test_nothing_outside_docs_is_served(self, server, path):
        st, _, body, _ = get(server, path)
        assert st in (403, 404)
        assert b"def make_handler" not in body and b"root:" not in body
