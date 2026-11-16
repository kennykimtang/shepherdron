"""웹 앱 자산 점검 — 브라우저 없이 돈다.

지켜야 할 것
    1. detector.js 의 MODEL_REV 는 docs/head.onnx 와 맞아야 한다.
       안 맞으면 모델을 바꿔도 브라우저가 저장해 둔 옛 모델을 계속 쓴다.
    2. MJPEG 분할기는 조각이 어떻게 잘려 와도 프레임을 정확히 떼어 내야 한다.
       기체 카메라가 이 프로젝트의 유일한 영상 소스다.
"""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def test_model_rev_matches_the_model_file():
    js = (DOCS / "detector.js").read_text(encoding="utf-8")
    m = re.search(r'MODEL_REV\s*=\s*"([0-9a-f]{8,})"', js)
    assert m, "detector.js 에 MODEL_REV 가 없다"
    digest = hashlib.sha256((DOCS / "head.onnx").read_bytes()).hexdigest()
    assert digest.startswith(m.group(1)), (
        f"head.onnx 가 바뀌었다. detector.js 의 MODEL_REV 를 {digest[:12]} 로 고쳐야 "
        "브라우저가 새 모델을 받는다")


NODE_CASES = r"""
import { MjpegSplitter } from %s;
const J = (...b) => Uint8Array.from(b);
const A = J(0xff, 0xd8, 1, 2, 3, 0xff, 0xd9);           // 7 바이트짜리 가짜 JPEG
const B = J(0xff, 0xd8, 9, 0xff, 0x00, 8, 0xff, 0xd9);   // 본문에 FF00 이 낀 것
const hdr = new TextEncoder().encode("--FRAME\r\nContent-Type: image/jpeg\r\n\r\n");
const cat = (...xs) => { const n = xs.reduce((s, x) => s + x.length, 0);
  const o = new Uint8Array(n); let k = 0; for (const x of xs) { o.set(x, k); k += x.length; } return o; };
const out = {};

// 1) 한 바이트씩 들어와도 한 장이 정확히 나온다
{ const s = new MjpegSplitter(); const got = [];
  for (const b of cat(hdr, A, J(13, 10))) { const r = s.push(J(b)); if (r.frame) got.push([...r.frame]); }
  out.byteByByte = got; }

// 2) 한 조각에 두 장이면 마지막 것만, 하나는 버렸다고 알린다
{ const s = new MjpegSplitter(); const r = s.push(cat(hdr, A, hdr, B));
  out.twoAtOnce = { frame: [...r.frame], skipped: r.skipped }; }

// 3) 시작 표지 FF|D8 이 두 조각에 걸쳐도 놓치지 않는다
{ const s = new MjpegSplitter(); const all = cat(hdr, A);
  const i = hdr.length + 1;                     // FF 와 D8 사이에서 자른다
  const r1 = s.push(all.subarray(0, i)); const r2 = s.push(all.subarray(i));
  out.splitMarker = { first: r1.frame, second: r2.frame ? [...r2.frame] : null }; }

// 4) 끝 표지 FF|D9 가 걸쳐도 된다
{ const s = new MjpegSplitter(); const all = cat(hdr, A);
  const i = all.length - 1;
  const r1 = s.push(all.subarray(0, i)); const r2 = s.push(all.subarray(i));
  out.splitEnd = { first: r1.frame, second: r2.frame ? [...r2.frame] : null }; }

// 5) 백 장을 흘려도 버퍼가 자라지 않는다
{ const s = new MjpegSplitter(); let n = 0;
  for (let k = 0; k < 100; k++) { if (s.push(cat(hdr, B, J(13, 10))).frame) n++; }
  out.steady = { frames: n, leftover: s.buf.length }; }

console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없다")
def test_mjpeg_splitter_in_node(tmp_path):
    url = json.dumps((DOCS / "mjpeg.js").as_uri())
    script = tmp_path / "case.mjs"
    script.write_text(NODE_CASES % url, encoding="utf-8")
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    A = [0xFF, 0xD8, 1, 2, 3, 0xFF, 0xD9]
    B = [0xFF, 0xD8, 9, 0xFF, 0x00, 8, 0xFF, 0xD9]
    assert out["byteByByte"] == [A]
    assert out["twoAtOnce"] == {"frame": B, "skipped": 1}
    assert out["splitMarker"] == {"first": None, "second": A}
    assert out["splitEnd"] == {"first": None, "second": A}
    assert out["steady"]["frames"] == 100
    assert out["steady"]["leftover"] < 64
