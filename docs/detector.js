/* 브라우저 YOLOv8n 사람 검출 — onnxruntime-web.
 *
 * 노트북 파이썬판과 같은 가중치(yolov8n)를 ONNX 로 내보내 쓴다. coco-ssd 는
 * 군중에서 겹친 사람을 많이 놓쳐서 바꿨다.
 *
 * 전처리·후처리는 파이썬 onnxruntime 으로 ultralytics 결과와 대조해 맞췄다
 * (bus.jpg 4명, IoU 0.90~0.98, 좌표 오차 1.6~12 px).
 *   1. 640x640 레터박스, 여백은 114, 가운데 정렬
 *   2. RGB · CHW · /255
 *   3. 출력 [1,84,8400] 에서 4번 행이 person 점수
 *   4. cx,cy,w,h → xyxy 로 바꾸고 레터박스를 되돌림
 *   5. IoU 0.45 NMS
 */
/* ort.min.js 에는 WebGPU 가 들어 있지 않다. 그것만 싣고 executionProviders 에
 * 'webgpu' 를 넣으면 조용히 WASM 으로 떨어져 단일 스레드로 돈다(초당 1~3장).
 * index.html 에서 ort.all.min.js 를 싣는 이유다. */
const ORT_BASE = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";
export const INPUT = 640;
const ANCHORS = 8400;
const PERSON_ROW = 4;

export class Detector {
  constructor(modelUrl = "./yolov8n.onnx") {
    this.modelUrl = modelUrl;
    this.session = null;
    this.backend = "—";
    this.cv = document.createElement("canvas");
    this.cv.width = INPUT; this.cv.height = INPUT;
    this.ctx = this.cv.getContext("2d", { willReadFrequently: true });
    this.input = new Float32Array(3 * INPUT * INPUT);
  }

  async load(onProgress) {
    const ort = self.ort;
    ort.env.wasm.wasmPaths = ORT_BASE;
    // GitHub Pages 는 COOP/COEP 헤더를 주지 않으므로 스레드를 못 쓴다. SIMD 는 된다.
    ort.env.wasm.numThreads = 1;
    ort.env.wasm.simd = true;

    onProgress?.("모델 내려받는 중");
    const buf = await fetchWithProgress(this.modelUrl, onProgress);

    const avail = typeof navigator !== "undefined" && navigator.gpu
      ? ["webgpu", "wasm"] : ["wasm"];
    let last = null;
    for (const ep of avail) {
      try {
        onProgress?.(ep === "webgpu" ? "GPU 준비 중" : "CPU 준비 중");
        this.session = await ort.InferenceSession.create(buf, {
          executionProviders: [ep], graphOptimizationLevel: "all",
        });
        this.backend = ep === "webgpu" ? "GPU" : "CPU";
        return this;
      } catch (e) { last = e; }
    }
    throw new Error(last?.message || "추론 엔진을 초기화하지 못했습니다");
  }

  /* 영상 한 장 → 사람 박스. src 는 <video> 도 <canvas> 도 된다.
   * 방향을 바로잡은 캔버스를 넘기면 검출도 그 방향으로 돈다. */
  async detect(src, conf = 0.3, iouThr = 0.45, maxBoxes = 100) {
    if (!this.session) return [];
    const W = src.videoWidth || src.width, H = src.videoHeight || src.height;
    if (!W || !H) return [];

    const r = Math.min(INPUT / W, INPUT / H);
    const nw = Math.round(W * r), nh = Math.round(H * r);
    const dx = ((INPUT - nw) / 2) | 0, dy = ((INPUT - nh) / 2) | 0;

    this.ctx.fillStyle = "#727272";                 // 114,114,114
    this.ctx.fillRect(0, 0, INPUT, INPUT);
    this.ctx.drawImage(src, dx, dy, nw, nh);
    const px = this.ctx.getImageData(0, 0, INPUT, INPUT).data;

    const n = INPUT * INPUT, f = this.input;
    for (let i = 0; i < n; i++) {
      f[i] = px[i * 4] / 255;                       // R
      f[n + i] = px[i * 4 + 1] / 255;               // G
      f[2 * n + i] = px[i * 4 + 2] / 255;           // B
    }

    const ort = self.ort;
    const name = this.session.inputNames[0];
    const out = await this.session.run(
      { [name]: new ort.Tensor("float32", f, [1, 3, INPUT, INPUT]) });
    const d = out[this.session.outputNames[0]].data;

    const cand = [];
    for (let i = 0; i < ANCHORS; i++) {
      const s = d[PERSON_ROW * ANCHORS + i];
      if (s < conf) continue;
      const cx = d[i], cy = d[ANCHORS + i];
      const bw = d[2 * ANCHORS + i], bh = d[3 * ANCHORS + i];
      cand.push({
        score: s,
        x1: (cx - bw / 2 - dx) / r, y1: (cy - bh / 2 - dy) / r,
        x2: (cx + bw / 2 - dx) / r, y2: (cy + bh / 2 - dy) / r,
      });
    }
    return nms(cand, iouThr, maxBoxes).map((b) => ({
      bbox: [Math.max(0, b.x1), Math.max(0, b.y1),
             Math.min(W, b.x2) - Math.max(0, b.x1),
             Math.min(H, b.y2) - Math.max(0, b.y1)],
      score: b.score,
    }));
  }
}

function iou(a, b) {
  const ix1 = Math.max(a.x1, b.x1), iy1 = Math.max(a.y1, b.y1);
  const ix2 = Math.min(a.x2, b.x2), iy2 = Math.min(a.y2, b.y2);
  const inter = Math.max(0, ix2 - ix1) * Math.max(0, iy2 - iy1);
  const u = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter;
  return u > 0 ? inter / u : 0;
}

function nms(cand, thr, max) {
  cand.sort((p, q) => q.score - p.score);
  const keep = [];
  for (const c of cand) {
    let ok = true;
    for (const k of keep) if (iou(c, k) >= thr) { ok = false; break; }
    if (ok) { keep.push(c); if (keep.length >= max) break; }
  }
  return keep;
}

/* 12 MB 를 내려받는 동안 진행률을 보여 준다. 아무 표시가 없으면 멈춘 줄 안다. */
async function fetchWithProgress(url, onProgress) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`모델을 받지 못했습니다 (${res.status})`);
  const total = Number(res.headers.get("content-length")) || 0;
  if (!res.body || !total) return await res.arrayBuffer();
  const reader = res.body.getReader();
  const parts = [];
  let got = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value); got += value.length;
    onProgress?.(`모델 내려받는 중 ${Math.round((got / total) * 100)}%`);
  }
  const buf = new Uint8Array(got);
  let off = 0;
  for (const p of parts) { buf.set(p, off); off += p.length; }
  return buf.buffer;
}
