/* 브라우저 머리 검출 — onnxruntime-web.
 *
 * 쓰는 가중치는 CrowdHuman 으로 학습한 person+head 2클래스 YOLOv11s 다
 * (huggingface.co/Sharath33/Person, openrail++). 그중 head 클래스만 쓴다.
 *
 * COCO 로 학습한 yolov8n 의 person 은 전신 박스를 기대하고 배운 탓에, 몸통이
 * 앞사람에 가린 군중에서는 거의 못 잡는다. 마라톤 출발선 사진(2589x1458,
 * 300명 이상)으로 재 보니 앞줄 4명이 전부였다. 군중에서 끝까지 보이는 건
 * 머리뿐이라 머리로 바꿨다. 같은 사진 같은 조건에서 136명이 나온다.
 * 드론은 내려다보므로 머리 위치가 곧 그 사람의 지상 위치이기도 하다.
 *
 *   1. 640x640 레터박스, 여백은 114, 가운데 정렬
 *   2. RGB · CHW · /255
 *   3. 출력은 boxes[1,8400,4](cx,cy,w,h) · scores[1,8400,1] · classes[1,8400,1]
 *      — yolov8n 의 [1,84,8400] 과 달리 클래스 argmax 까지 그래프 안에서 끝난다.
 *      classes 1 이 head 다.
 *   4. 레터박스를 되돌려 원본 좌표로
 *   5. IoU NMS
 *
 * 타일 추론(tiles>1)
 *   1080p 한 장을 통째로 640 으로 줄이면 뒤쪽 사람이 15~20 px 밖에 안 남아
 *   거의 다 놓친다. 그래서 화면을 NxN 으로 쪼개 조각마다 640 추론을 돌린다.
 *   조각 하나가 담당하는 넓이가 1/N 이므로 같은 사람이 N 배 크게 들어간다.
 *   조각은 서로 조금 겹쳐 두고, 검출은 '겹치지 않는 중심 구역' 안에 중심이
 *   들어온 것만 남긴다. 구역이 화면을 빈틈없이 나누므로 같은 사람이 두 조각에서
 *   두 번 세어지지 않는다. 가까이 있어 커다랗게 잡히는 사람은 조각 경계에 잘려
 *   놓치기 쉬워서, 전체 화면 추론 한 번을 항상 같이 돌리고 마지막에 합친다.
 */
/* ort.min.js 에는 WebGPU 가 들어 있지 않다. 그것만 싣고 executionProviders 에
 * 'webgpu' 를 넣으면 조용히 WASM 으로 떨어져 단일 스레드로 돈다(초당 1~3장).
 * index.html 에서 ort.all.min.js 를 싣는 이유다. */
const ORT_BASE = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";
export const INPUT = 640;
export const HEAD_CLASS = 1;
const OVERLAP = 0.2;            // 조각이 중심 구역 밖으로 더 보는 비율

export class Detector {
  constructor(modelUrl = "./head.onnx") {
    this.modelUrl = modelUrl;
    this.session = null;
    this.backend = "—";
    this.out = null;
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
        // 출력 이름으로 찾는다. 순서에 기대면 다른 내보내기에서 조용히 어긋난다.
        const names = this.session.outputNames;
        this.out = {
          boxes: names.find((s) => /box/i.test(s)),
          scores: names.find((s) => /score|conf/i.test(s)),
          classes: names.find((s) => /class|label/i.test(s)),
        };
        if (!this.out.boxes || !this.out.scores || !this.out.classes)
          throw new Error(`모델 출력이 예상과 다릅니다 (${names.join(", ")})`);
        return this;
      } catch (e) { last = e; }
    }
    throw new Error(last?.message || "추론 엔진을 초기화하지 못했습니다");
  }

  /* 영상 한 장 → 사람 박스. src 는 <video> 도 <canvas> 도 된다.
   * 방향을 바로잡은 캔버스를 넘기면 검출도 그 방향으로 돈다.
   * tiles 는 화면을 몇 등분해 볼지다. 1 이면 한 번, 2 면 전체 + 2x2 = 다섯 번. */
  async detect(src, opts = {}) {
    const { conf = 0.25, iouThr = 0.55, maxBoxes = 500, tiles = 1 } = opts;
    if (!this.session) return [];
    const W = src.videoWidth || src.width, H = src.videoHeight || src.height;
    if (!W || !H) return [];

    const passes = [];
    passes.push(await this.#infer(src, 0, 0, W, H, conf, 0));
    if (tiles > 1) {
      const stepX = W / tiles, stepY = H / tiles;
      const mx = stepX * OVERLAP, my = stepY * OVERLAP;
      const tile = [];
      for (let iy = 0; iy < tiles; iy++) {
        for (let ix = 0; ix < tiles; ix++) {
          const x0 = Math.max(0, ix * stepX - mx), y0 = Math.max(0, iy * stepY - my);
          const x1 = Math.min(W, (ix + 1) * stepX + mx);
          const y1 = Math.min(H, (iy + 1) * stepY + my);
          const got = await this.#infer(src, x0, y0, x1 - x0, y1 - y0, conf, 1);
          // 중심 구역 밖은 옆 조각이 맡는다. 경계에 잘린 박스를 여기서 떨군다.
          for (const b of got) {
            const cx = (b.x1 + b.x2) / 2, cy = (b.y1 + b.y2) / 2;
            if (cx >= ix * stepX && cx < (ix + 1) * stepX &&
                cy >= iy * stepY && cy < (iy + 1) * stepY) tile.push(b);
          }
        }
      }
      passes.push(tile);
    }

    const keep = merge(passes, iouThr, maxBoxes);
    return keep.map((b) => ({
      bbox: [Math.max(0, b.x1), Math.max(0, b.y1),
             Math.min(W, b.x2) - Math.max(0, b.x1),
             Math.min(H, b.y2) - Math.max(0, b.y1)],
      score: b.score,
    }));
  }

  /* src 의 (sx,sy,sw,sh) 조각 하나를 640 에 레터박스로 넣고 추론한다.
   * 돌려주는 좌표는 조각이 아니라 원본 화면 기준이다. */
  async #infer(src, sx, sy, sw, sh, conf, pass) {
    const r = Math.min(INPUT / sw, INPUT / sh);
    const nw = Math.round(sw * r), nh = Math.round(sh * r);
    const dx = ((INPUT - nw) / 2) | 0, dy = ((INPUT - nh) / 2) | 0;

    this.ctx.fillStyle = "#727272";                 // 114,114,114
    this.ctx.fillRect(0, 0, INPUT, INPUT);
    this.ctx.drawImage(src, sx, sy, sw, sh, dx, dy, nw, nh);
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
    const bx = out[this.out.boxes].data, sc = out[this.out.scores].data,
          cl = out[this.out.classes].data;
    const anchors = sc.length;

    const cand = [];
    for (let i = 0; i < anchors; i++) {
      if (sc[i] < conf || cl[i] !== HEAD_CLASS) continue;
      const o = i * 4;
      const cx = bx[o], cy = bx[o + 1], bw = bx[o + 2], bh = bx[o + 3];
      cand.push({
        score: sc[i], pass,
        x1: sx + (cx - bw / 2 - dx) / r, y1: sy + (cy - bh / 2 - dy) / r,
        x2: sx + (cx + bw / 2 - dx) / r, y2: sy + (cy + bh / 2 - dy) / r,
      });
    }
    return cand;
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

/* 겹침 넓이를 작은 쪽 박스로 나눈 값. 한쪽이 다른 쪽에 거의 들어앉아 있으면 1 에
 * 가깝다. 조각 경계에서 잘린 박스는 온전한 박스 안에 들어앉는데, IoU 만으로는
 * 잘린 정도만큼 값이 낮아져 중복으로 안 걸러진다. */
function contain(a, b) {
  const ix1 = Math.max(a.x1, b.x1), iy1 = Math.max(a.y1, b.y1);
  const ix2 = Math.min(a.x2, b.x2), iy2 = Math.min(a.y2, b.y2);
  const inter = Math.max(0, ix2 - ix1) * Math.max(0, iy2 - iy1);
  const m = Math.min((a.x2 - a.x1) * (a.y2 - a.y1), (b.x2 - b.x1) * (b.y2 - b.y1));
  return m > 0 ? inter / m : 0;
}

/* 여러 번 돌린 결과를 한 벌로 합친다. 같은 추론 안에서는 IoU 만 본다. 군중에서는
 * 사람끼리 원래 많이 겹쳐서, 들어앉았다는 이유로 지우면 뒷사람이 사라진다.
 * 다른 추론끼리만 '들어앉음'을 중복으로 본다. */
function merge(passes, thr, max) {
  const all = [];
  for (const p of passes) for (const c of nms(p, thr, max)) all.push(c);
  all.sort((p, q) => q.score - p.score);
  const keep = [];
  for (const c of all) {
    let ok = true;
    for (const k of keep) {
      if (iou(c, k) >= thr) { ok = false; break; }
      if (c.pass !== k.pass && contain(c, k) >= 0.8) { ok = false; break; }
    }
    if (ok) { keep.push(c); if (keep.length >= max) break; }
  }
  return keep;
}

/* 38 MB 를 내려받는 동안 진행률을 보여 준다. 아무 표시가 없으면 멈춘 줄 안다. */
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
