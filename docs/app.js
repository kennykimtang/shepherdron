/* Shepherdron 웹 데모 — 카메라 · 검출 · 화면.
 * 판단 로직은 vision.js 에 있고, 그쪽은 노트북 파이썬 코드와 같은 수식을 쓴다.
 */
import * as V from "./vision.js";
import { Detector } from "./detector.js";
import { hostDisplay, joinAsCamera, cameraUrl, drawQr, readCode } from "./link.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const LIME = "#C8F542", LIME_DIM = "#5F7323", ROI_C = "#D9C27A";
const FG3 = "#5C636B", LINE = "#2A2F35";

const S = {
  running: false, stream: null, model: null,
  heat: true, boxes: true, roi: null, areaM2: null,
  hfov: 70, sigma: 0.75, tiers: V.DEFAULT_TIERS,
  level: new V.LevelFilter(8),
  alert: new V.AlertDebouncer(15, 0.6, 0.25, 4),
  mission: new V.Mission(),
  peaks: [], counts: [], levels: [], active: [],
  log: [], lastMsn: "IDLE", lastLv: 0,
  fps: 0, lastT: 0, srcLabel: "대기", live: false, lastActive: false,
  det: null, link: null, every: 1, tick: 0, lastPeople: [], pairTimer: 0,
};

/* ── 밀집도 컬러맵 (파이썬과 같은 정지점) ── */
const STOPS = [[0, "#10307A"], [0.18, "#1E7FA8"], [0.38, "#2E9E4F"],
               [0.58, "#C9D62B"], [0.76, "#E8A32A"], [1.0, "#D83A2B"], [1.5, "#8E1B13"]];
const LUT_MAX = 1.5;
const hex = (c) => [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)];
const LUT = (() => {
  const out = new Uint8Array(256 * 3), st = STOPS.map(([t, c]) => [t, hex(c)]);
  for (let i = 0; i < 256; i++) {
    const t = (i / 255) * LUT_MAX;
    let c = st[st.length - 1][1];
    for (let k = 0; k < st.length - 1; k++) {
      const [t0, c0] = st[k], [t1, c1] = st[k + 1];
      if (t >= t0 && t <= t1) {
        const f = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
        c = [0, 1, 2].map((j) => Math.round(c0[j] + (c1[j] - c0[j]) * f));
        break;
      }
    }
    out[i * 3] = c[0]; out[i * 3 + 1] = c[1]; out[i * 3 + 2] = c[2];
  }
  return out;
})();

/* ── 카메라 ── */
async function listCams() {
  try {
    const devs = (await navigator.mediaDevices.enumerateDevices())
      .filter((d) => d.kind === "videoinput");
    const sel = $("camSel");
    sel.innerHTML = "";
    if (!devs.length) { sel.innerHTML = "<option>카메라 없음</option>"; return; }
    sel.hidden = devs.length < 2;
    devs.forEach((d, i) => {
      const o = document.createElement("option");
      o.value = d.deviceId;
      o.textContent = d.label || `카메라 ${i + 1}`;
      sel.appendChild(o);
    });
  } catch (_) { /* 권한 전에는 목록이 비어 있을 수 있다 */ }
}

async function startCam() {
  if (!navigator.mediaDevices?.getUserMedia) {
    return fail("이 브라우저는 카메라를 지원하지 않습니다. 영상 파일을 열어 주세요.");
  }
  try {
    const id = $("camSel").value;
    const c = { width: { ideal: 1280 }, height: { ideal: 720 } };
    if (id) c.deviceId = { exact: id }; else c.facingMode = { ideal: "environment" };
    stopSrc();
    S.stream = await navigator.mediaDevices.getUserMedia({ video: c, audio: false });
    const v = $("video");
    v.srcObject = S.stream; v.loop = false;
    await v.play();
    await /* ── 폰 : ?cam=CODE 로 열리면 카메라 모드 ── */
async function runCameraMode(code) {
  $("app").hidden = true;
  $("camMode").hidden = false;
  $("camCode").textContent = code;
  const stat = $("camStat"), prev = $("camPrev");
  const set = (t, cls = "") => { stat.textContent = t; stat.className = "camStat " + cls; };
  let facing = "environment", stream = null, link = null;

  async function open() {
    try {
      stream?.getTracks().forEach((t) => t.stop());
      set("카메라 여는 중");
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      prev.srcObject = stream;
      await prev.play().catch(() => {});
      link?.stop?.();
      set("화면을 찾는 중");
      link = joinAsCamera(code, stream, {
        onState(st, detail) {
          if (st === "live") set("보내는 중", "live");
          else if (st === "connecting") set("화면을 찾는 중");
          else if (st === "waiting") set("끊겼습니다. 다시 붙는 중");
          else if (st === "error") set(detail, "err");
        },
        onReport(r) {
          if (!r || typeof r !== "object") return;
          $("camBack").textContent =
            `인원 ${r.n}   최대 ${r.peak} 명/㎡   ${r.lv}   ${r.msn}`;
        },
      });
      try { await navigator.wakeLock?.request("screen"); } catch (_) {}
    } catch (e) {
      set(`카메라를 열지 못했습니다 (${e.name}). 권한을 허용한 뒤 새로고침하세요.`, "err");
    }
  }
  $("camFlip").onclick = () => { facing = facing === "environment" ? "user" : "environment"; open(); };
  $("camStop").onclick = () => {
    link?.stop?.(); stream?.getTracks().forEach((t) => t.stop());
    set("중지했습니다. 새로고침하면 다시 붙습니다.");
  };
  open();
}

const camCode = readCode();
if (camCode) runCameraMode(camCode);
else listCams();
    S.srcLabel = $("camSel").selectedOptions[0]?.textContent || "카메라";
    S.live = true;
    $("camName").textContent = S.srcLabel;
    begin();
  } catch (e) {
    fail(`카메라를 열지 못했습니다 (${e.name}). 다른 앱이 쓰고 있는지, ` +
         `주소가 https 인지 확인하세요. 영상 파일로도 시연할 수 있습니다.`);
  }
}

function openFile(f) {
  stopSrc();
  const v = $("video");
  v.srcObject = null; v.src = URL.createObjectURL(f); v.loop = true;
  v.play();
  S.srcLabel = f.name; S.live = false;
  $("camName").textContent = f.name;
  begin();
}

function stopSrc() {
  if (S.stream) { S.stream.getTracks().forEach((t) => t.stop()); S.stream = null; }
}

/* 무대 위 겹침을 막는다. 한 번에 하나만 뜬다. */
function stage(which, html) {
  for (const id of ["start", "pair", "msg"]) $(id).hidden = id !== which;
  if (which === "msg" && html) $("msg").innerHTML = html;
}

function fail(text) {
  stage("msg", `<b>시작하지 못했습니다</b><span>${text}</span>`);
}

/* 실행 중에만 보이는 조작 */
function showRunControls(on) {
  for (const id of ["btnSource", "btnDispatch", "vr1", "btnHeat", "btnBox", "everySel"]) {
    $(id).hidden = !on;
  }
}

async function begin() {
  if (!S.det) {
    const note = (t) => stage("msg",
      `<b>${t}</b><span>인식 모델을 한 번만 내려받습니다. 약 12 MB.</span>`);
    note("준비 중");
    try { S.det = await new Detector().load(note); }
    catch (e) { return fail(`인식 모델을 준비하지 못했습니다. ${e.message}`); }
    addLog(`YOLOv8n ${S.det.backend}`, "준비");
  }
  stage(null);
  showRunControls(true);
  $("tacEmpty").hidden = true; $("tacCv").hidden = false;
  $("msnEmpty").hidden = true;
  if (!S.running) { S.running = true; loop(); }
}

/* ── 로그 ── */
function addLog(text, tag, bg = "#2A3036", fg = "#C5CBD1") {
  const d = new Date();
  const t = [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, "0")).join(":");
  S.log.unshift({ t, text, tag, bg, fg });
  if (S.log.length > 40) S.log.pop();
  $("logRt").textContent = S.log.length;
  $("logEmpty").hidden = true;
  $("logList").innerHTML = S.log.map((e) =>
    `<div class="e"><time>${e.t}</time>` +
    `<span class="t" style="background:${e.bg};color:${e.fg}">${esc(e.tag)}</span>` +
    `<span class="x">${esc(e.text)}</span></div>`).join("");
}

/* ── 메인 루프 ── */
async function loop() {
  const v = $("video");
  if (v.readyState >= 2 && v.videoWidth) {
    const now = performance.now() / 1000;
    if (S.lastT) S.fps = S.fps * 0.8 + (1 / Math.max(1e-3, now - S.lastT)) * 0.2;
    S.lastT = now;

    // 느린 PC 에서는 검출을 건너뛰고 영상만 부드럽게 흐르게 한다
    if (S.tick++ % S.every === 0) {
      try {
        const preds = await S.det.detect(v, 0.3, 0.45);
        S.lastPeople = preds.map((p) => ({
          x: p.bbox[0] + p.bbox[2] / 2, y: p.bbox[1] + p.bbox[3],
          boxH: p.bbox[3], bbox: p.bbox,
        }));
      } catch (_) {}
    }
    const people = S.lastPeople;

    const W = v.videoWidth, H = v.videoHeight;
    const field = V.densityField(people, S.sigma);
    const roi = V.analyzeRoi(field, S.roi, W, H, { tiers: S.tiers, areaM2: S.areaM2 });
    roi.level = S.level.update(roi.level);
    const pic = V.buildPicture(people, W, S.sigma, S.hfov);

    const raw = roi.level >= 3;
    const active = S.alert.update(raw, now);
    S.mission.update(active && !S.lastActive, active, roi.count, pic.hotspot, now);
    S.lastActive = active;

    push(S.peaks, roi.peakDensity); push(S.counts, roi.count);
    push(S.levels, roi.level); push(S.active, S.mission.state !== "IDLE");

    if (roi.level !== S.lastLv) {
      const L = V.levelInfo(roi.level);
      addLog(`국부 최대 ${roi.peakDensity.toFixed(1)} 명/㎡`,
             V.levelTag(roi.level), L.color, "#101214");
      S.lastLv = roi.level;
    }
    if (S.mission.state !== S.lastMsn) {
      addLog(S.mission.reason, V.MISSION[S.mission.state], LIME, "#101214");
      S.lastMsn = S.mission.state;
    }

    S.link?.report?.({ n: roi.count, peak: +roi.peakDensity.toFixed(2),
                       lv: V.levelTag(roi.level), msn: V.MISSION[S.mission.state] });
    drawView(v, W, H, people, field, roi);
    drawTac(pic);
    drawTrend();
    writePanels(roi, pic);
  }
  requestAnimationFrame(loop);
}
const push = (a, v) => { a.push(v); if (a.length > 240) a.shift(); };

/* ── 영상 + 히트맵 ── */
const heatCv = document.createElement("canvas");
function drawView(v, W, H, people, field, roi) {
  const cv = $("view"), ctx = cv.getContext("2d");
  if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
  ctx.drawImage(v, 0, 0, W, H);

  if (S.heat && people.length) {
    const ref = S.tiers[S.tiers.length - 1];
    const { heat, fw, fh } = V.densityRaster(people, S.sigma, W, H, 160);
    if (heatCv.width !== fw || heatCv.height !== fh) { heatCv.width = fw; heatCv.height = fh; }
    const hx = heatCv.getContext("2d"), img = hx.createImageData(fw, fh);
    for (let i = 0; i < heat.length; i++) {
      const n = Math.min(heat[i] / ref, LUT_MAX);
      const k = Math.round((n / LUT_MAX) * 255) * 3;
      const a = Math.pow(Math.max(0, Math.min(1, (heat[i] - 0.02 * ref) / (0.45 * ref))), 0.85);
      img.data[i * 4] = LUT[k]; img.data[i * 4 + 1] = LUT[k + 1];
      img.data[i * 4 + 2] = LUT[k + 2]; img.data[i * 4 + 3] = Math.round(a * 0.78 * 255);
    }
    hx.putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(heatCv, 0, 0, W, H);
  }

  if (roi.polygon?.length >= 3 && S.roi) {
    ctx.strokeStyle = ROI_C; ctx.lineWidth = Math.max(2, W / 640);
    ctx.beginPath();
    roi.polygon.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath(); ctx.stroke();
  }
  if (S.boxes) {
    ctx.strokeStyle = "rgba(214,222,230,.85)"; ctx.lineWidth = Math.max(1, W / 900);
    for (const p of people) ctx.strokeRect(p.bbox[0], p.bbox[1], p.bbox[2], p.bbox[3]);
    ctx.fillStyle = "#fff";
    for (const p of people) { ctx.beginPath(); ctx.arc(p.x, p.y, Math.max(2, W / 500), 0, 7); ctx.fill(); }
  }
  if (roi.peakPoint && roi.level >= 3) {
    const [tx, ty] = roi.peakPoint, r = W / 24;
    ctx.strokeStyle = LIME; ctx.lineWidth = Math.max(2, W / 550);
    ctx.beginPath(); ctx.arc(tx, ty, r, 0, 7); ctx.stroke();
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      ctx.beginPath(); ctx.moveTo(tx + dx * r * 0.45, ty + dy * r * 0.45);
      ctx.lineTo(tx + dx * r * 1.7, ty + dy * r * 1.7); ctx.stroke();
    }
  }
  // 영상 내 표기
  const fs = Math.max(13, W / 46);
  ctx.font = `600 ${fs}px "IBM Plex Mono",monospace`;
  ctx.fillStyle = "rgba(0,0,0,.45)"; ctx.fillRect(10, 10, fs * 7.2, fs * 2.5);
  ctx.fillStyle = "#fff"; ctx.textBaseline = "top";
  ctx.fillText(`TOTAL ${roi.count}`, 18, 16);
  const L = V.levelInfo(roi.level);
  ctx.font = `700 ${fs * 0.8}px "IBM Plex Sans KR",sans-serif`;
  ctx.fillStyle = L.color; ctx.fillText(V.levelTag(roi.level), 18, 18 + fs * 1.25);
  $("camInfo").textContent =
    `${W}×${H}  ${S.fps.toFixed(1)}fps  ${S.det?.backend || ""}` +
    (S.every > 1 ? `  1/${S.every}` : "");
}

/* ── 전술 지도 ── */
function drawTac(pic) {
  const cv = $("tacCv"), box = cv.parentElement.getBoundingClientRect();
  const w = Math.max(240, Math.floor(box.width)), h = Math.round(w * 0.92);
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; cv.style.height = h + "px"; }
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.fillStyle = "#101215"; g.fillRect(0, 0, w, h);

  const D = S.mission;
  let need = 8;
  if (pic.people.length) {
    const rs = pic.people.map((p) => Math.hypot(p.right, p.forward)).sort((a, b) => a - b);
    need = Math.max(need, rs[Math.floor(0.85 * (rs.length - 1))] * 1.25);
    if (pic.hotspot) need = Math.max(need, Math.hypot(...pic.hotspot) * 1.35);
  }
  need = Math.max(need, Math.hypot(...D.pos) * 1.2);
  const step = [1, 2, 5, 10, 20].find((s) => need / s <= 5) || 20;
  const rmax = step * Math.ceil(need / step);
  $("tacRt").textContent = `RING ${step}m · HFOV ${S.hfov}°`;

  const ox = w / 2, oy = h - 30;
  const ppm = Math.min((oy - 16) / rmax, (w / 2) / (rmax * 0.9));
  const P = (r, f) => [ox + r * ppm, oy - f * ppm];

  const half = (S.hfov / 2) * Math.PI / 180, far = rmax * 1.2;
  g.fillStyle = "#171B20"; g.beginPath(); g.moveTo(...P(0, 0));
  g.lineTo(...P(-far * Math.sin(half), far * Math.cos(half)));
  g.lineTo(...P(far * Math.sin(half), far * Math.cos(half)));
  g.closePath(); g.fill();

  g.strokeStyle = LINE; g.lineWidth = 1;
  for (let r = step; r <= rmax + 1e-6; r += step) {
    g.beginPath(); g.arc(ox, oy, r * ppm, Math.PI, 2 * Math.PI); g.stroke();
    g.fillStyle = FG3; g.font = '11px "IBM Plex Mono",monospace'; g.textAlign = "right";
    const [lx, ly] = P(-r * Math.sin(half) - 0.1, r * Math.cos(half));
    g.fillText(`${r}m`, lx - 4, ly + 4);
  }
  g.textAlign = "left";

  for (const p of pic.people) {
    const lv = V.levelOf(p.density, S.tiers);
    const [x, y] = P(p.right, p.forward);
    g.fillStyle = V.levelInfo(lv).color;
    g.beginPath(); g.arc(x, y, 3.5, 0, 7); g.fill();
  }
  if (pic.hotspot) {
    const [hx2, hy2] = P(...pic.hotspot);
    const lv = V.levelOf(pic.hotspotDensity, S.tiers);
    g.strokeStyle = V.levelInfo(lv).color;
    for (const [rr, lw] of [[0.75, 2], [1.5, 1]]) {
      g.lineWidth = lw; g.beginPath(); g.arc(hx2, hy2, rr * ppm, 0, 7); g.stroke();
    }
    const ev = pic.evacuation;
    if (ev && lv >= 2) {
      const [ex, ey] = P(...ev.point);
      const d = Math.max(1, Math.hypot(ex - hx2, ey - hy2));
      const ux = (ex - hx2) / d, uy = (ey - hy2) / d;
      const a0 = 1.5 * ppm + 6, a1 = a0 + Math.max(40, 2.2 * ppm);
      g.strokeStyle = LIME; g.lineWidth = 3.5; g.beginPath();
      g.moveTo(hx2 + ux * a0, hy2 + uy * a0); g.lineTo(hx2 + ux * a1, hy2 + uy * a1); g.stroke();
      const ang = Math.atan2(uy, ux);
      for (const s of [1, -1]) {
        const b = ang + Math.PI + s * 0.45;
        g.beginPath(); g.moveTo(hx2 + ux * a1, hy2 + uy * a1);
        g.lineTo(hx2 + ux * a1 + 13 * Math.cos(b), hy2 + uy * a1 + 13 * Math.sin(b)); g.stroke();
      }
      g.fillStyle = LIME; g.font = '600 13px "IBM Plex Sans KR",sans-serif';
      g.textAlign = ux >= -0.2 ? "left" : "right";
      g.fillText(`유도 ${ev.name}`, hx2 + ux * (a1 + 12), hy2 + uy * (a1 + 12) + 4);
      g.textAlign = "left";
    }
  }
  // 이륙 지점 · 기체
  const [h0x, h0y] = P(0, 0);
  g.strokeStyle = FG3; g.lineWidth = 1;
  g.beginPath(); g.arc(h0x, h0y, 8, 0, 7); g.stroke();
  g.fillStyle = "#959CA5"; g.font = '10px "IBM Plex Mono",monospace'; g.textAlign = "center";
  g.fillText("H", h0x, h0y + 3.5); g.fillText("CAM · 이륙점", h0x, h0y + 20);
  g.textAlign = "left";

  if (D.trail.length > 1) {
    g.strokeStyle = LIME_DIM; g.lineWidth = 1; g.beginPath();
    D.trail.forEach(([r, f], i) => { const [x, y] = P(r, f); i ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.stroke();
  }
  if (D.flying) {
    const [dx, dy] = P(...D.pos);
    if (D.state === "NAVIGATING" && D.goal) {
      const [gx, gy] = P(...D.goal);
      g.strokeStyle = LIME; g.setLineDash([7, 5]); g.lineWidth = 2;
      g.beginPath(); g.moveTo(dx, dy); g.lineTo(gx, gy); g.stroke(); g.setLineDash([]);
    }
    const a = (D.heading * Math.PI) / 180;
    g.strokeStyle = LIME; g.lineWidth = 2;
    for (let k = 0; k < 4; k++) {
      const an = a + (45 + 90 * k) * Math.PI / 180;
      const ex = dx + 10 * Math.sin(an), ey = dy - 10 * Math.cos(an);
      g.beginPath(); g.moveTo(dx, dy); g.lineTo(ex, ey); g.stroke();
      g.lineWidth = 1; g.beginPath(); g.arc(ex, ey, 4.5, 0, 7); g.stroke(); g.lineWidth = 2;
    }
    g.beginPath(); g.moveTo(dx, dy);
    g.lineTo(dx + 15 * Math.sin(a), dy - 15 * Math.cos(a)); g.stroke();
    g.fillStyle = LIME; g.font = '11px "IBM Plex Mono",monospace';
    g.fillText(`${D.alt.toFixed(1)}m`, dx + 16, dy - 12);
  }
}

/* ── 추이 ── */
function drawTrend() {
  const cv = $("trendCv"), w = Math.floor(cv.parentElement.getBoundingClientRect().width);
  const h = 68, dpr = Math.min(2, window.devicePixelRatio || 1);
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  $("trendRt").textContent = `${S.peaks.length}F`;
  const n = S.peaks.length; if (n < 2) return;
  const x1 = 34, x2 = w - 10, y1 = 8, y2 = h - 14;
  const top = S.tiers[S.tiers.length - 1] * 1.5;
  const X = (i) => x1 + (i / (n - 1)) * (x2 - x1);
  const Y = (v) => y2 - Math.min(v, top) / top * (y2 - y1);

  g.setLineDash([3, 4]); g.lineWidth = 1;
  S.tiers.forEach((t, i) => {
    g.strokeStyle = V.levelInfo(i + 1).color;
    g.beginPath(); g.moveTo(x1, Y(t)); g.lineTo(x2, Y(t)); g.stroke();
    g.fillStyle = V.levelInfo(i + 1).color; g.font = '10px "IBM Plex Mono",monospace';
    g.textAlign = "right"; g.fillText(String(t), x1 - 5, Y(t) + 3.5);
  });
  g.setLineDash([]); g.textAlign = "left";
  g.strokeStyle = LINE; g.beginPath(); g.moveTo(x1, y2); g.lineTo(x2, y2); g.stroke();
  for (let i = 0; i < n - 1; i++) {
    if (S.active[i]) { g.fillStyle = LIME; g.fillRect(X(i), y2 + 3, Math.max(2, X(i + 1) - X(i)), 4); }
  }
  for (let i = 0; i < n - 1; i++) {
    g.strokeStyle = V.levelInfo(S.levels[i + 1]).color; g.lineWidth = 2;
    g.beginPath(); g.moveTo(X(i), Y(S.peaks[i])); g.lineTo(X(i + 1), Y(S.peaks[i + 1])); g.stroke();
  }
}

/* ── 패널 ── */
function writePanels(roi, pic) {
  $("rCount").textContent = roi.count;
  $("rArea").textContent = roi.areaM2 ? Math.round(roi.areaM2) : "—";
  $("rDens").textContent = roi.areaM2 ? roi.density.toFixed(2) : "—";
  $("rPeak").textContent = roi.peakDensity.toFixed(2);
  const L = V.levelInfo(roi.level);
  $("lvTxt").textContent = V.levelTag(roi.level); $("lvTxt").style.color = L.color;
  [...$("lvBar").children].forEach((el, i) => {
    el.style.background = i <= roi.level ? V.levelInfo(i).color : "#20252A";
  });

  const D = S.mission;
  $("msnRt").textContent = `DONE ${D.completed}`;
  $("track").innerHTML = V.TRACK.map((k, i) => {
    const cur = V.TRACK.indexOf(D.state);
    const cls = k === D.state ? "on" : (i < cur && cur > 0 ? "done" : "");
    return `<div class="${cls}">${V.MISSION[k]}</div>`;
  }).join("");

  const rows = [["사유", D.reason, false, false]];
  if (D.state !== "IDLE" && D.goal) {
    rows.push(["지령",
      `FWD ${(D.goal[1] - D.pos[1]).toFixed(1).padStart(5)}m  RGT ${(D.goal[0] - D.pos[0]).toFixed(1).padStart(5)}m`,
      true, true]);
  } else rows.push(["지령", "—", true, false]);
  const ev = pic.evacuation;
  rows.push(ev && pic.hotspotDensity >= S.tiers[1]
    ? ["유도", `${ev.name} → ${ev.density.toFixed(1)} 명/㎡ 구역`, false, true]
    : ["유도", "—", true, false]);
  rows.push(["기체", `ALT ${D.alt.toFixed(1)}m  BAT ${Math.max(0, 100 - Math.floor(D.completed * 4))}%`, true, false]);
  rows.push(["구조물", D.payload, false, D.payload.startsWith("전개")]);
  $("msnRows").innerHTML = rows.map(([k, v, mono, hi]) =>
    `<div class="r"><b>${k}</b><span class="${mono ? "mono " : ""}${hi ? "hi" : ""}">${esc(v)}</span></div>`).join("");

}

/* ── 조작 ── */
setInterval(() => {
  const d = new Date();
  $("clock").textContent = [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, "0")).join(":");
}, 500);

function startPhoneLink() {
  stopSrc(); S.link?.stop?.();
  stage("pair");
  $("pairState").className = "";
  $("pairState").textContent = "코드 만드는 중";
  // 신호 서버가 조용하면 사용자가 영문을 알 수 있어야 한다
  clearTimeout(S.pairTimer);
  S.pairTimer = setTimeout(() => {
    if ($("code").textContent.includes("·")) {
      $("pairState").className = "err";
      $("pairState").textContent =
        "신호 서버에 닿지 못했습니다. 인터넷을 확인하고 다시 눌러 주세요.";
    }
  }, 12000);
  S.link = hostDisplay({
    onCode(code) {
      const url = cameraUrl(code);
      $("code").textContent = code;
      $("camUrl").textContent = url;
      $("qr").innerHTML = "";
      drawQr($("qr"), url);
      $("pairState").textContent = "폰을 기다리는 중";
      clearTimeout(S.pairTimer);
    },
    onState(st, detail) {
      const el = $("pairState");
      el.className = st === "error" ? "err" : "";
      if (st === "waiting") el.textContent = "폰을 기다리는 중";
      else if (st === "live") el.textContent = "연결됨";
      else if (st === "error") el.textContent = detail;
    },
    async onStream(stream) {
      const v = $("video");
      v.srcObject = stream; v.src = ""; v.loop = false;
      await v.play().catch(() => {});
      S.srcLabel = "폰 카메라"; S.live = true;
      $("camName").textContent = "폰 카메라";
      addLog("폰 카메라가 붙었습니다", "연결", "#C8F542", "#101214");
      begin();
    },
  });
}

$("btnPhone").onclick = startPhoneLink;
$("btnStart").onclick = startCam;
$("btnSource").onclick = () => {
  stopSrc(); S.link?.stop?.(); S.link = null;
  $("video").srcObject = null; $("video").src = "";
  S.running = false; S.lastPeople = [];
  showRunControls(false);
  $("tacEmpty").hidden = false; $("tacCv").hidden = true;
  $("msnEmpty").hidden = false;
  $("camName").textContent = "카메라"; $("camInfo").textContent = "";
  stage("start");
};
$("btnCopyUrl").onclick = async () => {
  const t = $("camUrl").textContent;
  try { await navigator.clipboard.writeText(t); $("btnCopyUrl").textContent = "복사됨"; }
  catch (_) { $("btnCopyUrl").textContent = "직접 복사"; }
  setTimeout(() => ($("btnCopyUrl").textContent = "복사"), 1600);
};
$("btnFile").onclick = () => $("file").click();
$("file").onchange = (e) => e.target.files[0] && openFile(e.target.files[0]);
$("btnDispatch").onclick = () => { S.mission.dispatch(); addLog("수동 출동", "임무", LIME, "#101214"); };
const toggle = (id, key) => {
  $(id).onclick = () => { S[key] = !S[key]; $(id).setAttribute("aria-pressed", String(S[key])); };
};
toggle("btnHeat", "heat"); toggle("btnBox", "boxes");
$("everySel").onchange = (e) => { S.every = Math.max(1, +e.target.value || 1); };
$("btnFull").onclick = () => (document.fullscreenElement
  ? document.exitFullscreen() : document.documentElement.requestFullscreen().catch(() => {}));
$("camSel").onchange = () => { if (S.stream) startCam(); };

addEventListener("keydown", (e) => {
  if (e.target.tagName === "SELECT") return;
  const k = e.key.toLowerCase();
  if (k === "m") $("btnDispatch").click();
  else if (k === "h") $("btnHeat").click();
  else if (k === "b") $("btnBox").click();
  else if (k === "f") $("btnFull").click();
});
/* ── 폰 : ?cam=CODE 로 열리면 카메라 모드 ── */
async function runCameraMode(code) {
  $("app").hidden = true;
  $("camMode").hidden = false;
  $("camCode").textContent = code;
  const stat = $("camStat"), prev = $("camPrev");
  const set = (t, cls = "") => { stat.textContent = t; stat.className = "camStat " + cls; };
  let facing = "environment", stream = null, link = null;

  async function open() {
    try {
      stream?.getTracks().forEach((t) => t.stop());
      set("카메라 여는 중");
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      prev.srcObject = stream;
      await prev.play().catch(() => {});
      link?.stop?.();
      set("화면을 찾는 중");
      link = joinAsCamera(code, stream, {
        onState(st, detail) {
          if (st === "live") set("보내는 중", "live");
          else if (st === "connecting") set("화면을 찾는 중");
          else if (st === "waiting") set("끊겼습니다. 다시 붙는 중");
          else if (st === "error") set(detail, "err");
        },
        onReport(r) {
          if (!r || typeof r !== "object") return;
          $("camBack").textContent =
            `인원 ${r.n}   최대 ${r.peak} 명/㎡   ${r.lv}   ${r.msn}`;
        },
      });
      try { await navigator.wakeLock?.request("screen"); } catch (_) {}
    } catch (e) {
      set(`카메라를 열지 못했습니다 (${e.name}). 권한을 허용한 뒤 새로고침하세요.`, "err");
    }
  }
  $("camFlip").onclick = () => { facing = facing === "environment" ? "user" : "environment"; open(); };
  $("camStop").onclick = () => {
    link?.stop?.(); stream?.getTracks().forEach((t) => t.stop());
    set("중지했습니다. 새로고침하면 다시 붙습니다.");
  };
  open();
}

const camCode = readCode();
if (camCode) runCameraMode(camCode);
else listCams();
