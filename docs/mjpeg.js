/* MJPEG 바이트열에서 완성된 JPEG 를 떼어 낸다 — DOM 없이 돈다(테스트 대상).
 *
 * 서버(scripts/panel.py)는 multipart 로 보내지만 경계 문자열 대신 JPEG 표지
 * (SOI FFD8 … EOI FFD9)로 자른다. JPEG 본문의 0xFF 는 0xFF00 으로 채워지므로
 * FFD9 가 본문 중간에 나오지 않는다. multipart 머리말은 ASCII 라 0xFF 가 없다.
 *
 * push() 는 이번 조각까지로 완성된 프레임 중 **마지막 한 장**만 돌려준다.
 * 밀려서 여러 장이 한꺼번에 왔다면 앞의 것은 버린다 — 실시간 화면에는
 * 최신 장면만 의미가 있다. 버린 수는 skipped 로 알려 준다.
 */
export class MjpegSplitter {
  constructor() {
    this.buf = new Uint8Array(0);
    this.scan = 0;        // EOI 를 이어서 찾을 위치. 같은 바이트를 다시 훑지 않는다
  }

  push(chunk) {
    this.buf = cat(this.buf, chunk);
    let last = null, count = 0;
    for (;;) {
      const a = mark(this.buf, 0xd8, 0);
      if (a < 0) {        // 표지가 두 조각에 걸쳤을 수 있어 마지막 바이트는 남긴다
        this.buf = this.buf.subarray(Math.max(0, this.buf.length - 1));
        this.scan = 0;
        break;
      }
      const z = mark(this.buf, 0xd9, Math.max(a + 2, this.scan));
      if (z < 0) {
        if (a) this.buf = this.buf.subarray(a);
        this.scan = Math.max(0, this.buf.length - 1);
        break;
      }
      last = this.buf.slice(a, z + 2);
      count++;
      this.buf = this.buf.subarray(z + 2);
      this.scan = 0;
    }
    return { frame: last, skipped: Math.max(0, count - 1) };
  }
}

function mark(b, x, from) {
  for (let i = Math.max(0, from); i < b.length - 1; i++) {
    if (b[i] === 0xff && b[i + 1] === x) return i;
  }
  return -1;
}

function cat(a, b) {
  if (!a.length) return b;
  const c = new Uint8Array(a.length + b.length);
  c.set(a); c.set(b, a.length);
  return c;
}
