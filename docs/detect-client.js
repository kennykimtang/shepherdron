/* 워커에서 도는 검출기의 대리인. Detector 와 모양이 같다(load · detect · backend).
 * app.js 는 어느 쪽인지 몰라도 된다. */
export class WorkerDetector {
  constructor(modelUrl = "./head.onnx") {
    this.modelUrl = modelUrl;
    this.backend = "—";
    this.cached = false;
    this.worker = true;
    this.w = null;
    this.seq = 0;
    this.pending = new Map();
  }

  load(onProgress) {
    return new Promise((ok, no) => {
      let w;
      try {
        w = new Worker(new URL("./detect-worker.js", import.meta.url), { type: "module" });
      } catch (e) { no(e); return; }
      this.w = w;
      const fail = (msg) => { w.terminate(); this.w = null; no(new Error(msg)); };
      w.onerror = (e) => { e.preventDefault?.(); fail(e.message || "검출 워커를 띄우지 못했습니다"); };
      w.onmessage = (ev) => {
        const m = ev.data;
        if (m.type === "progress") onProgress?.(m.text);
        else if (m.type === "error") fail(m.message);
        else if (m.type === "ready") {
          this.backend = m.backend;
          this.cached = m.cached;
          w.onmessage = (e2) => this.#settle(e2.data);
          w.onerror = (e2) => {               // 도중에 죽으면 기다리던 요청을 모두 실패시킨다
            e2.preventDefault?.();
            for (const p of this.pending.values()) p.no(new Error("검출 워커가 멈췄습니다"));
            this.pending.clear();
          };
          ok(this);
        }
      };
      w.postMessage({ type: "load", url: new URL(this.modelUrl, location.href).href });
    });
  }

  #settle(m) {
    const p = this.pending.get(m.id);
    if (!p) return;
    this.pending.delete(m.id);
    if (m.error) p.no(new Error(m.error)); else p.ok(m.preds);
  }

  /* src(캔버스)를 지금 이 순간 그대로 떠서 넘긴다. 넘긴 뒤 src 를 바꿔도 상관없다. */
  async detect(src, opts = {}) {
    if (!this.w) throw new Error("검출 워커가 없습니다");
    const frame = await createImageBitmap(src);
    const id = ++this.seq;
    return new Promise((ok, no) => {
      this.pending.set(id, { ok, no });
      this.w.postMessage({ type: "detect", id, frame, opts }, [frame]);
    });
  }
}
