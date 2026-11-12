#!/usr/bin/env python3
"""줄자 붐 벤치 제어 — 라즈베리파이에서 띄우고 노트북 브라우저로 조작한다.

    기체(Pi)에서   python scripts/payload_bench.py
    노트북에서     브라우저로 http://<Pi주소>:8080

하드웨어 없이 노트북에서 화면만 보려면
    python scripts/payload_bench.py --fake

**이것은 벤치 도구다. 비행 경로가 아니다.**
    비행 중 판단과 구동은 shepherdron_pi.py 가 한다. 지상-기체 링크는 관측만
    나르고 명령은 나르지 않는다(link/protocol.py). 그 설계를 깨지 않으려고
    벤치 제어를 이 별도 프로세스로 분리했다. 비행 전에 이 서비스를 끈다.

왜 웹인가
    노트북에 추가 설치가 필요 없고, 같은 화면을 휴대폰으로도 열 수 있다.
    벤치에서 기구 옆에 서서 조작할 때 이 편이 안전하다.
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from hardware.payload_tape import TapeBoomConfig, TapeBoomPayload  # noqa: E402

log = logging.getLogger("shepherdron.bench")

PAGE = """<!doctype html><html lang=ko><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>줄자 붐 벤치</title><style>
:root{--bg:#f7f7f5;--fg:#14181c;--mut:#6e7d8c;--line:#d8dde3;--card:#fff;
--ok:#0e8a45;--mid:#e07b00;--bad:#c62828;--stop:#111}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#14181c;--fg:#eef2f6;
--mut:#9aa7b4;--line:#2a3138;--card:#1b2127;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"Pretendard","Apple SD Gothic Neo",sans-serif}
.wrap{max-width:560px;margin:0 auto;padding:24px max(16px,env(safe-area-inset-left)) 40px}
h1{font-size:20px;margin:0 0 2px}.sub{color:var(--mut);font-size:13px;margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:14px}
.state{display:flex;align-items:center;gap:12px}
.dot{width:14px;height:14px;border-radius:50%;background:var(--mut);flex:none}
.name{font-size:28px;font-weight:700;letter-spacing:-.01em}
.why{color:var(--mut);font-size:13px;margin-top:6px;min-height:19px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
button{font:inherit;font-weight:600;border:1px solid var(--line);border-radius:11px;
padding:16px 12px;background:var(--card);color:var(--fg);cursor:pointer}
button:active{transform:translateY(1px)}button[disabled]{opacity:.4;cursor:not-allowed}
.stop{grid-column:1/-1;background:var(--stop);color:#fff;border-color:var(--stop);padding:18px}
.sw{display:flex;gap:10px;margin-top:14px;font-size:13px;color:var(--mut)}
.sw span{flex:1;border:1px solid var(--line);border-radius:9px;padding:9px 11px;text-align:center}
.sw .on{background:var(--ok);border-color:var(--ok);color:#fff;font-weight:600}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:14px}
.bar i{display:block;height:100%;width:0;background:var(--mid);transition:width .12s}
.note{font-size:12px;color:var(--mut);border-left:3px solid var(--line);padding-left:10px}
</style><div class=wrap>
<h1>줄자 붐 벤치 제어</h1><p class=sub id=host></p>
<div class=card>
  <div class=state><i class=dot id=dot></i><b class=name id=st>연결 중</b></div>
  <div class=why id=why></div>
  <div class=bar><i id=duty></i></div>
  <div class=sw><span id=s1>수납 센서</span><span id=s2>전개 센서</span></div>
</div>
<div class=card>
  <div class=row>
    <button id=dep>전개</button><button id=ret>수축</button>
    <button class=stop id=stp>정지</button>
  </div>
</div>
<p class=note>벤치 전용입니다. 비행 전에 이 서비스를 끄세요.
프로펠러를 뺀 상태에서 쓰고, 움직이는 날에 손을 대지 마세요.</p>
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
}
draw();setInterval(draw,200);
</script></html>"""


class Service:
    """상태기계를 50 Hz 로 돌리는 배경 스레드. HTTP 핸들러는 여기만 건드린다."""

    def __init__(self, payload: TapeBoomPayload):
        self.p = payload
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(0.02):
            with self._lock:
                try:
                    self.p.update()
                except Exception:                       # 루프가 죽으면 모터가 안 선다
                    log.exception("update 실패 — 정지")
                    try:
                        self.p.stop("내부 오류")
                    except Exception:
                        pass

    def act(self, what: str) -> dict:
        with self._lock:
            if what == "deploy":
                self.p.deploy()
            elif what == "retract":
                self.p.retract()
            elif what == "stop":
                self.p.stop()
            self.p.update()
            return self.p.snapshot()

    def snapshot(self) -> dict:
        with self._lock:
            return self.p.snapshot()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        with self._lock:
            self.p.close()


def make_handler(svc: Service):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: dict, code: int = 200) -> None:
            self._send(json.dumps(obj).encode(), "application/json; charset=utf-8", code)

        def do_GET(self):                               # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send(PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._json(svc.snapshot())
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):                              # noqa: N802
            what = self.path.rsplit("/", 1)[-1]
            if what in ("deploy", "retract", "stop"):
                log.info("명령: %s (%s)", what, self.client_address[0])
                self._json(svc.act(what))
            else:
                self._json({"error": "unknown command"}, 404)

        def log_message(self, *a):                      # 접근 로그는 끈다
            pass

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description="줄자 붐 벤치 제어 서버")
    ap.add_argument("--fake", action="store_true", help="하드웨어 없이 (노트북 화면 확인용)")
    ap.add_argument("--host", default="0.0.0.0", help="바인드 주소")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--duty", type=float, default=TapeBoomConfig.duty)
    ap.add_argument("--invert", action="store_true", help="모터가 반대로 돌면")
    ap.add_argument("--deploy-timeout", type=float, default=TapeBoomConfig.deploy_timeout_s)
    ap.add_argument("--retract-timeout", type=float, default=TapeBoomConfig.retract_timeout_s)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = TapeBoomConfig(duty=a.duty, invert=a.invert,
                         deploy_timeout_s=a.deploy_timeout,
                         retract_timeout_s=a.retract_timeout)
    if a.fake:
        from hardware.payload_tape import FakeBackend
        backend = FakeBackend(travel_s=3.0)
        log.warning("FAKE 모드 — 실제 모터는 돌지 않는다")
    else:
        try:
            from hardware.payload_tape import GpiozeroBackend
            backend = GpiozeroBackend(cfg)
        except Exception as e:
            log.error("GPIO 를 열지 못했다: %s", e)
            log.error("라즈베리파이가 맞는지, python3-gpiozero · python3-lgpio 가 깔렸는지 확인."
                      " 노트북에서 화면만 보려면 --fake")
            return 1

    svc = Service(TapeBoomPayload(backend, cfg))
    httpd = ThreadingHTTPServer((a.host, a.port), make_handler(svc))
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
