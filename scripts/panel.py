#!/usr/bin/env python3
"""Shepherdron 기체 제어판 — 기체(Pi)에서 띄우고 브라우저로 조작한다.

    기체에서   python3 scripts/panel.py
    노트북에서 http://actuator.local:8080

한 페이지에서 보는 것
    카메라 영상 · 전개 구동부 · FC 링크 상태

왜 rpicam-vid 를 쓰는가
    scripts/stream_camera.py 는 OpenCV 를 쓴다. Pi OS Lite 에 OpenCV 를 올리면
    수백 MB 에 빌드도 오래 걸린다. rpicam-apps 는 이미 깔려 있고 MJPEG 를 바로
    뱉으므로, 그 표준출력을 받아 프레임만 잘라 중계한다. 의존성이 늘지 않는다.

**이것은 벤치·점검 도구다. 비행 경로가 아니다.**
    지상-기체 링크는 관측만 나르고 명령은 나르지 않는다(link/protocol.py).
    그 설계를 깨지 않으려고 제어판을 별도 프로세스로 두었다. 비행 전에 끈다.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import pathlib
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from hardware.payload import PayloadState  # noqa: E402
from hardware.payload_tape import TapeBoomConfig, TapeBoomPayload  # noqa: E402

log = logging.getLogger("shepherdron.panel")
SOI, EOI = b"\xff\xd8", b"\xff\xd9"


# ───────────────────────── 카메라 ─────────────────────────
class Camera:
    """rpicam-vid 의 MJPEG 출력을 프레임 단위로 잘라 최신 한 장만 들고 있다.

    보는 사람이 여럿이어도 최신 프레임을 공유한다. 느린 클라이언트가 있어도
    프레임이 쌓이지 않고 버려진다 — 실시간성이 지연보다 중요하다.
    """

    def __init__(self, width=1280, height=720, fps=15, fake=False):
        self.size = (width, height)
        self.fps = fps
        self.fake = fake
        self._jpeg: bytes | None = None
        self._lock = threading.Condition()
        self._stop = threading.Event()
        self._err = "" if fake else "시작하는 중"
        self._n = 0
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def ok(self) -> bool:
        return self._jpeg is not None

    @property
    def error(self) -> str:
        return self._err

    @property
    def frames(self) -> int:
        return self._n

    def _publish(self, jpeg: bytes) -> None:
        with self._lock:
            self._jpeg = jpeg
            self._n += 1
            self._lock.notify_all()

    def wait(self, last: int, timeout=5.0):
        """last 보다 새 프레임이 나올 때까지 기다린다. (프레임번호, 바이트)"""
        with self._lock:
            if self._n <= last:
                self._lock.wait(timeout)
            return self._n, self._jpeg

    def _loop(self) -> None:
        if self.fake:
            self._fake_loop()
            return
        exe = shutil.which("rpicam-vid") or shutil.which("libcamera-vid")
        if not exe:
            self._err = "rpicam-vid 없음 — sudo apt install rpicam-apps"
            log.error(self._err)
            return
        cmd = [exe, "-t", "0", "--codec", "mjpeg", "--nopreview", "-o", "-",
               "--width", str(self.size[0]), "--height", str(self.size[1]),
               "--framerate", str(self.fps), "--flush"]
        while not self._stop.is_set():
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, bufsize=0)
            except Exception as e:
                self._err = f"카메라 실행 실패: {e}"
                log.error(self._err)
                return
            buf = b""
            while not self._stop.is_set():
                chunk = p.stdout.read(8192)
                if not chunk:
                    break
                buf += chunk
                while True:                       # 한 번에 여러 장이 올 수 있다
                    s = buf.find(SOI)
                    if s < 0:
                        buf = b""
                        break
                    e = buf.find(EOI, s + 2)
                    if e < 0:
                        buf = buf[s:]
                        break
                    self._publish(buf[s:e + 2])
                    self._err = ""
                    buf = buf[e + 2:]
            err = (p.stderr.read() or b"").decode(errors="replace").strip()
            p.kill()
            if self._stop.is_set():
                return
            self._err = err.splitlines()[-1] if err else "카메라가 멈췄다 — 재시작"
            log.warning("카메라 재시작: %s", self._err)
            time.sleep(2)

    def _fake_loop(self) -> None:
        """노트북에서 화면만 확인할 때. PIL 로 프레임을 만들어 낸다."""
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self._err = "fake 모드에는 pillow 가 필요하다"
            return
        while not self._stop.is_set():
            im = Image.new("RGB", self.size, (24, 28, 34))
            d = ImageDraw.Draw(im)
            d.text((28, 28), "FAKE CAMERA", fill=(220, 225, 232))
            d.text((28, 52), time.strftime("%H:%M:%S"), fill=(140, 200, 255))
            d.line((0, self.size[1] // 2, self.size[0], self.size[1] // 2),
                   fill=(60, 70, 80))
            b = io.BytesIO()
            im.save(b, "JPEG", quality=70)
            self._publish(b.getvalue())
            time.sleep(1.0 / max(1, self.fps))

    def close(self) -> None:
        self._stop.set()


# ───────────────────────── FC 링크 ─────────────────────────
def check_fc(device="/dev/ttyAMA0", baud=921600, seconds=4.0) -> dict:
    """요청이 올 때만 포트를 연다. 계속 쥐고 있으면 임무 코드가 못 쓴다."""
    out = {"device": device, "baud": baud, "heartbeat": False,
           "param": None, "note": ""}
    try:
        from pymavlink import mavutil
    except ImportError:
        out["note"] = "pymavlink 없음"
        return out
    conn = None
    try:
        conn = mavutil.mavlink_connection(device, baud=baud)
        hb = conn.wait_heartbeat(timeout=seconds)
        if not hb:
            out["note"] = "HEARTBEAT 없음 — FC TX → Pi 10번 또는 FC 전원 확인"
            return out
        out["heartbeat"] = True
        out["autopilot"] = mavutil.mavlink.enums["MAV_AUTOPILOT"][hb.autopilot].name
        out["system"] = conn.target_system
        conn.mav.param_request_read_send(conn.target_system,
                                         conn.target_component, b"SERIAL2_BAUD", -1)
        end = time.monotonic() + 3.0
        while time.monotonic() < end:
            m = conn.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
            if m and m.param_id.strip("\x00") == "SERIAL2_BAUD":
                out["param"] = int(m.param_value)
                break
        out["note"] = ("양방향 정상" if out["param"] is not None
                       else "수신만 됨 — Pi 8번 → FC RX 확인")
    except Exception as e:
        out["note"] = f"{type(e).__name__}: {e}"
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return out


# ───────────────────────── 페이지 ─────────────────────────
PAGE = """<!doctype html><html lang=ko><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Shepherdron 제어판</title><style>
:root{--bg:#f6f7f8;--fg:#14181c;--mut:#6e7d8c;--line:#d9dee4;--card:#fff;
--ok:#0e8a45;--mid:#e07b00;--bad:#c62828;--dark:#111}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#101418;--fg:#eef2f6;
--mut:#93a1ae;--line:#272e35;--card:#171d23;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Pretendard","Apple SD Gothic Neo",sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:22px max(16px,env(safe-area-inset-left)) 44px}
h1{font-size:19px;margin:0 0 2px}.sub{color:var(--mut);font-size:13px;margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:16px;margin-bottom:14px}
.card h2{font-size:14px;margin:0 0 12px;color:var(--mut);font-weight:600;
letter-spacing:.02em;text-transform:uppercase}
.cam{position:relative;background:#000;border-radius:10px;overflow:hidden;
aspect-ratio:16/9;display:flex;align-items:center;justify-content:center}
.cam img{width:100%;height:100%;object-fit:contain;display:block}
.cam .msg{color:#9aa7b4;font-size:13px;padding:16px;text-align:center}
.state{display:flex;align-items:center;gap:11px}
.dot{width:13px;height:13px;border-radius:50%;background:var(--mut);flex:none}
.name{font-size:25px;font-weight:700}
.why{color:var(--mut);font-size:13px;margin-top:5px;min-height:18px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:13px}
button{font:inherit;font-weight:600;border:1px solid var(--line);border-radius:10px;
padding:14px 10px;background:var(--card);color:var(--fg);cursor:pointer}
button:active{transform:translateY(1px)}button[disabled]{opacity:.4;cursor:not-allowed}
.stop{grid-column:1/-1;background:var(--dark);color:#fff;border-color:var(--dark)}
.wide{grid-column:1/-1}
.sw{display:flex;gap:9px;margin-top:12px;font-size:12px;color:var(--mut)}
.sw span{flex:1;border:1px solid var(--line);border-radius:8px;padding:8px;text-align:center}
.sw .on{background:var(--ok);border-color:var(--ok);color:#fff;font-weight:600}
.bar{height:5px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:12px}
.bar i{display:block;height:100%;width:0;background:var(--mid);transition:width .12s}
table{width:100%;border-collapse:collapse;font-size:13px}
td{padding:5px 0;border-bottom:1px solid var(--line)}td:last-child{text-align:right;font-weight:600}
tr:last-child td{border-bottom:0}
.note{font-size:12px;color:var(--mut);border-left:3px solid var(--line);padding-left:10px}
</style><div class=wrap>
<h1>Shepherdron 기체 제어판</h1><p class=sub id=host></p>

<div class=card><h2>카메라</h2>
  <div class=cam id=cam><div class=msg id=camMsg>불러오는 중…</div></div>
  <table style="margin-top:12px"><tr><td>상태</td><td id=camState>—</td></tr></table>
</div>

<div class=card><h2>전개 구동부</h2>
  <div class=state><i class=dot id=dot></i><b class=name id=st>연결 중</b></div>
  <div class=why id=why></div>
  <div class=bar><i id=duty></i></div>
  <div class=sw><span id=s1>수납 센서</span><span id=s2>전개 센서</span></div>
  <div class=row>
    <button id=dep>전개</button><button id=ret>수축</button>
    <button class=stop id=stp>정지</button>
  </div>
</div>

<div class=card><h2>비행제어기 링크</h2>
  <table>
    <tr><td>포트</td><td id=fcDev>—</td></tr>
    <tr><td>HEARTBEAT</td><td id=fcHb>—</td></tr>
    <tr><td>양방향 (파라미터 응답)</td><td id=fcParam>—</td></tr>
    <tr><td>판정</td><td id=fcNote>눌러서 확인</td></tr>
  </table>
  <div class=row><button class=wide id=fcBtn>링크 점검</button></div>
</div>

<p class=note>벤치 전용입니다. 비행 전에 이 서비스를 끄세요.
움직이는 날에 손을 대지 마세요.</p>
</div><script>
const $=i=>document.getElementById(i);
const COLOR={STOWED:'var(--ok)',DEPLOYED:'var(--ok)',DEPLOYING:'var(--mid)',
RETRACTING:'var(--mid)',FAULT:'var(--bad)'};
const LABEL={STOWED:'수납됨',DEPLOYED:'전개됨',DEPLOYING:'전개 중',
RETRACTING:'수축 중',FAULT:'이상'};
$('host').textContent=location.host;
let busy=false;
async function cmd(p){if(busy)return;busy=true;
  try{await fetch('/api/'+p,{method:'POST'})}catch(e){}busy=false;draw()}
$('dep').onclick=()=>cmd('deploy');$('ret').onclick=()=>cmd('retract');
$('stp').onclick=()=>cmd('stop');
$('fcBtn').onclick=async()=>{const b=$('fcBtn');b.disabled=true;b.textContent='점검 중…';
  try{const r=await(await fetch('/api/fc',{method:'POST'})).json();
    $('fcDev').textContent=r.device+' @ '+r.baud;
    $('fcHb').textContent=r.heartbeat?('예 · '+(r.autopilot||'')):'아니오';
    $('fcParam').textContent=r.param!==null&&r.param!==undefined?('예 · SERIAL2_BAUD='+r.param):'아니오';
    $('fcNote').textContent=r.note||'—';
  }catch(e){$('fcNote').textContent='요청 실패'}
  b.disabled=false;b.textContent='링크 점검'};
function camUp(s){
  const box=$('cam');
  if(s.camera_ok){ if(!box.querySelector('img')){
      box.innerHTML='<img src="/camera.mjpg" alt="camera">'; } }
  else if(!box.querySelector('.msg')){ box.innerHTML='<div class=msg id=camMsg></div>'; }
  const m=box.querySelector('.msg'); if(m) m.textContent=s.camera_error||'영상 없음';
  $('camState').textContent=s.camera_ok?('정상 · '+s.camera_frames+' 프레임'):(s.camera_error||'없음');
}
async function draw(){let s;
  try{s=await(await fetch('/api/state')).json()}
  catch(e){$('st').textContent='연결 끊김';$('dot').style.background='var(--bad)';return}
  $('st').textContent=LABEL[s.state]||s.state;
  $('dot').style.background=COLOR[s.state]||'var(--mut)';
  $('why').textContent=s.fault||'';
  $('duty').style.width=Math.abs(s.duty)*100+'%';
  $('s1').className=s.stowed_switch?'on':'';
  $('s2').className=s.deployed_switch?'on':'';
  const mv=s.state==='DEPLOYING'||s.state==='RETRACTING';
  $('dep').disabled=mv||s.state==='DEPLOYED';
  $('ret').disabled=mv||s.state==='STOWED';
  camUp(s);
}
draw();setInterval(draw,400);
</script></html>"""


# ───────────────────────── 서버 ─────────────────────────
class Service:
    def __init__(self, payload, camera):
        self.p, self.cam = payload, camera
        self._lock = threading.Lock()
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._stop.wait(0.02):
            with self._lock:
                try:
                    self.p.update()
                except Exception:
                    log.exception("update 실패 — 정지")
                    try:
                        self.p.stop("내부 오류")
                    except Exception:
                        pass

    def act(self, what):
        with self._lock:
            getattr(self.p, {"deploy": "deploy", "retract": "retract",
                             "stop": "stop"}[what])()
            self.p.update()
            return self.snapshot()

    def snapshot(self):
        s = self.p.snapshot()
        s.update(camera_ok=self.cam.ok, camera_error=self.cam.error,
                 camera_frames=self.cam.frames)
        return s

    def close(self):
        self._stop.set()
        with self._lock:
            self.p.close()
        self.cam.close()


def make_handler(svc, fc_device, fc_baud):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, body, ctype, code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(json.dumps(obj).encode(), "application/json; charset=utf-8", code)

        def do_GET(self):                                   # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send(PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._json(svc.snapshot())
            elif self.path == "/camera.mjpg":
                self._mjpeg()
            else:
                self._json({"error": "not found"}, 404)

        def _mjpeg(self):
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            last = 0
            try:
                while True:
                    last, jpeg = svc.cam.wait(last)
                    if jpeg is None:
                        continue
                    self.wfile.write(b"--FRAME\r\nContent-Type: image/jpeg\r\n"
                                     b"Content-Length: " + str(len(jpeg)).encode()
                                     + b"\r\n\r\n" + jpeg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def do_POST(self):                                  # noqa: N802
            what = self.path.rsplit("/", 1)[-1]
            if what in ("deploy", "retract", "stop"):
                log.info("명령: %s (%s)", what, self.client_address[0])
                self._json(svc.act(what))
            elif what == "fc":
                self._json(check_fc(fc_device, fc_baud))
            else:
                self._json({"error": "unknown"}, 404)

        def log_message(self, *a):
            pass

    return H


def main() -> int:
    ap = argparse.ArgumentParser(description="Shepherdron 기체 제어판")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--fc-device", default="/dev/ttyAMA0")
    ap.add_argument("--fc-baud", type=int, default=921600)
    ap.add_argument("--fake", action="store_true",
                    help="하드웨어 없이 (노트북에서 화면 확인용)")
    ap.add_argument("--no-camera", action="store_true")
    ap.add_argument("--invert", action="store_true", help="모터가 반대로 돌면")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = TapeBoomConfig(invert=a.invert)
    if a.fake:
        from hardware.payload_tape import FakeBackend
        backend = FakeBackend(travel_s=3.0)
        log.warning("FAKE 모드 — 실제 모터는 돌지 않는다")
    else:
        try:
            from hardware.payload_tape import GpiozeroBackend
            backend = GpiozeroBackend(cfg)
        except Exception as e:
            from hardware.payload_tape import FakeBackend
            backend = FakeBackend(travel_s=3.0)
            log.warning("GPIO 를 못 열어 FAKE 로 대체한다 (%s)", e)
            log.warning("구동부를 쓰려면 sudo apt install python3-gpiozero python3-lgpio")

    cam = Camera(a.width, a.height, a.fps, fake=a.fake)
    if a.no_camera:
        cam.close()
    svc = Service(TapeBoomPayload(backend, cfg), cam)
    httpd = ThreadingHTTPServer((a.host, a.port), make_handler(svc, a.fc_device, a.fc_baud))
    log.info("http://%s:%d  (Ctrl+C 로 종료)", a.host, a.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("종료 중")
    finally:
        httpd.server_close()
        svc.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
