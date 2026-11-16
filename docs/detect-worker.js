/* 검출을 화면과 다른 스레드에서 돌린다.
 *
 * 왜 워커인가
 *   추론 한 번에 CPU 로 0.1~0.3 초가 걸린다. 화면 스레드에서 돌리면 그동안
 *   영상 읽기도 그리기도 멈춰서, 화면 fps 가 검출 속도(초당 3~5장)에 묶인다.
 *   기체 페이지는 http 라 WebGPU 도 못 쓰므로 실전에서 그대로 드러난다.
 *   워커로 빼면 화면은 카메라 속도로 그리고, 검출은 되는 대로 따라온다.
 *
 * 주고받는 것
 *   → {type:"load", url}                    ← progress* · ready | error
 *   → {type:"detect", id, frame, opts}      ← result {id, preds | error}
 *   frame 은 ImageBitmap 이고 소유권째 넘어온다(복사 없음). 다 쓰면 닫는다.
 */
import { Detector } from "./detector.js";

const ORT_URL = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/ort.all.min.mjs";
let det = null;

self.onmessage = async (ev) => {
  const m = ev.data;
  if (m.type === "load") {
    try {
      if (!self.ort) {
        const ns = await import(ORT_URL);
        self.ort = ns.InferenceSession ? ns : ns.default;
      }
      det = await new Detector(m.url).load((text) => self.postMessage({ type: "progress", text }));
      self.postMessage({ type: "ready", backend: det.backend, cached: !!det.cached });
    } catch (e) {
      self.postMessage({ type: "error", message: e?.message || String(e) });
    }
  } else if (m.type === "detect") {
    try {
      const preds = await det.detect(m.frame, m.opts || {});
      self.postMessage({ type: "result", id: m.id, preds });
    } catch (e) {
      self.postMessage({ type: "result", id: m.id, error: e?.message || String(e) });
    } finally {
      m.frame?.close?.();
    }
  }
};
