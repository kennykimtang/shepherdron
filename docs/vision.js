/* Shepherdron 웹 데모 — 판단 로직.
 *
 * vision/density_field.py · vision/tactical.py · flight/mission.py 를 옮긴 것이다.
 * 같은 수식을 써야 노트북에서 돌린 결과와 브라우저 결과가 어긋나지 않는다.
 * 브라우저 API 를 쓰지 않으므로 node 에서 그대로 검증할 수 있다.
 */

export const PERSON_H_M = 1.7;
/* 머리 박스 세로를 축척의 기준자로 쓴다. 성인 머리는 턱 끝에서 정수리까지
 * 대략 0.23 m 다. 전신보다 짧아 한 사람만 보면 오차가 크지만, 군중에서는
 * 수십~수백 개가 동시에 잡혀 회귀로 평균이 난다. 실제 면적을 알고 있으면
 * mPerPx 로 넣어 이 추정을 통째로 대신할 수 있다 — 그쪽이 늘 더 정확하다. */
export const HEAD_H_M = 0.23;
export const DEFAULT_TIERS = [1, 2, 3, 4];

/* 등급 색. 채도를 낮춰 한 계열로 읽히게 맞췄다. 히트맵도 같은 값을 쓰므로
 * 화면의 색과 범례가 어긋나지 않는다. */
export const LEVELS = [
  { n: 0, name: "안전", color: "#8A9199" },
  { n: 1, name: "관심", color: "#5B82A8" },
  { n: 2, name: "주의", color: "#B08A2E" },
  { n: 3, name: "경계", color: "#B96E36" },
  { n: 4, name: "심각", color: "#A84038" },
];

export const levelOf = (d, tiers = DEFAULT_TIERS) =>
  tiers.reduce((a, t) => a + (d >= t ? 1 : 0), 0);
export const levelInfo = (i) => LEVELS[Math.min(i, LEVELS.length - 1)];
export const levelTag = (i) => `${i}-${levelInfo(i).name}`;

/* ───────────────── 적응형 KDE 밀집도 ─────────────────
 * 사람마다 가우시안을 깔고 더한다. 격자가 없으므로 셀 경계에 걸린 군집도
 * 하나로 잡힌다. 균일한 군중에서는 실제 밀집도로 수렴한다.
 *
 * 거리 환산은 겉보기 크기로 한다. 머리 세로를 0.23 m 로 두면 박스 높이가
 * 그 지점의 축척(m/px)을 준다. mPerPx 를 주면 화면 전체에 그 값을 쓴다.
 */
export function densityField(people, sigmaM = 0.75, mPerPx = null) {
  const n = people.length;
  const out = { perPerson: [], peak: 0, peakIndex: -1, mean: 0, sigmaM };
  if (!n) return out;

  const scales = people.map((p) => mPerPx ?? HEAD_H_M / Math.max(1, p.boxH));
  const inv = 1 / (2 * Math.PI * sigmaM * sigmaM);
  const two = 2 * sigmaM * sigmaM;

  for (let i = 0; i < n; i++) {
    let total = 0;
    for (let j = 0; j < n; j++) {
      let dM;
      if (i === j) dM = 0;
      else {
        const dx = people[i].x - people[j].x;
        const dy = people[i].y - people[j].y;
        dM = Math.hypot(dx, dy) * (scales[i] + scales[j]) * 0.5;
      }
      total += inv * Math.exp(-(dM * dM) / two);
    }
    out.perPerson.push({ x: people[i].x, y: people[i].y, density: total, scale: scales[i] });
    out.mean += total;
    if (total > out.peak) { out.peak = total; out.peakIndex = i; }
  }
  out.mean /= n;
  return out;
}

/* 표시용 저해상도 장. 사람마다 가우시안 패치를 더한다. */
export function densityRaster(people, sigmaM, srcW, srcH, fieldW = 160, mPerPx = null) {
  const fw = Math.max(16, Math.min(fieldW, srcW));
  const fh = Math.max(9, Math.round((srcH * fw) / srcW));
  const heat = new Float32Array(fw * fh);
  if (!people.length) return { heat, fw, fh };

  const k = fw / srcW;
  const inv = 1 / (2 * Math.PI * sigmaM * sigmaM);
  const two = 2 * sigmaM * sigmaM;

  for (const p of people) {
    const s = mPerPx ?? HEAD_H_M / Math.max(1, p.boxH);
    let sp = (sigmaM / Math.max(s, 1e-6)) * k;
    sp = Math.max(1, Math.min(sp, Math.max(fw, fh)));
    const cx = p.x * k, cy = p.y * k;
    const rad = Math.ceil(3 * sp);
    const x0 = Math.max(0, Math.floor(cx) - rad), x1 = Math.min(fw, Math.floor(cx) + rad + 1);
    const y0 = Math.max(0, Math.floor(cy) - rad), y1 = Math.min(fh, Math.floor(cy) + rad + 1);
    const mpp = s / k;                       // 필드 픽셀 하나가 덮는 미터
    for (let y = y0; y < y1; y++) {
      const dy = (y - cy) * mpp;
      for (let x = x0; x < x1; x++) {
        const dx = (x - cx) * mpp;
        heat[y * fw + x] += inv * Math.exp(-(dx * dx + dy * dy) / two);
      }
    }
  }
  return { heat, fw, fh };
}

/* ───────────────── ROI · 면적 ─────────────────
 * 캘리브레이션 없이 m² 를 내기 위해, 검출된 사람들의 겉보기 크기로
 * 영상 행(y) → 축척(m/px) 1차 모델을 세우고 영역에 걸쳐 적분한다.
 */
export function scaleModel(perPerson) {
  if (!perPerson.length) return null;
  if (perPerson.length === 1) return { a: 0, b: perPerson[0].scale };
  const ys = perPerson.map((p) => p.y), ss = perPerson.map((p) => p.scale);
  const my = ys.reduce((a, v) => a + v, 0) / ys.length;
  const ms = ss.reduce((a, v) => a + v, 0) / ss.length;
  let num = 0, den = 0;
  for (let i = 0; i < ys.length; i++) { num += (ys[i] - my) * (ss[i] - ms); den += (ys[i] - my) ** 2; }
  if (den < 1e-9) return { a: 0, b: ms };
  const a = num / den;
  return { a, b: ms - a * my };
}

export function pointInPolygon(x, y, poly) {
  if (!poly || poly.length < 3) return true;
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/* 다각형이 덮는 픽셀 넓이. 실제 면적을 알고 있을 때 축척(m/px)을 역산하는 데 쓴다. */
export function polygonAreaPx(poly, srcW, srcH, step = 8) {
  const p = poly && poly.length >= 3
    ? poly : [[0, 0], [srcW - 1, 0], [srcW - 1, srcH - 1], [0, srcH - 1]];
  let n = 0;
  for (let y = 0; y < srcH; y += step)
    for (let x = 0; x < srcW; x += step) if (pointInPolygon(x, y, p)) n++;
  return n * step * step;
}

export function estimateAreaM2(poly, perPerson, srcW, srcH, step = 8) {
  const m = scaleModel(perPerson);
  if (!m) return null;
  let area = 0;
  for (let y = 0; y < srcH; y += step) {
    const s = Math.max(1e-5, m.a * y + m.b);
    const cell = s * s * step * step;
    for (let x = 0; x < srcW; x += step) if (pointInPolygon(x, y, poly)) area += cell;
  }
  return area;
}

export function analyzeRoi(field, poly, srcW, srcH, opts = {}) {
  const tiers = opts.tiers || DEFAULT_TIERS;
  const polygon = poly && poly.length >= 3
    ? poly : [[0, 0], [srcW - 1, 0], [srcW - 1, srcH - 1], [0, srcH - 1]];
  const inside = field.perPerson.filter(
    (p) => p.x >= 0 && p.x < srcW && p.y >= 0 && p.y < srcH && pointInPolygon(p.x, p.y, polygon));

  const areaGiven = opts.areaM2 != null;
  const area = areaGiven ? opts.areaM2 : estimateAreaM2(polygon, field.perPerson, srcW, srcH);
  let peak = 0, peakPoint = null;
  for (const p of inside) if (p.density > peak) { peak = p.density; peakPoint = [p.x, p.y]; }
  const density = area && area > 0 ? inside.length / area : 0;

  return {
    polygon, count: inside.length, areaM2: area, areaEstimated: !areaGiven,
    density, peakDensity: peak, peakPoint,
    // 등급은 국부 최대로 정한다. 압사는 평균이 아니라 한 지점에서 일어난다.
    level: levelOf(inside.length ? peak : density, tiers),
  };
}

/* ───────────────── 전술 투영 ───────────────── */
export const focalPx = (w, hfovDeg) => (w / 2) / Math.tan((hfovDeg * Math.PI) / 180 / 2);

export function project(people, srcW, hfovDeg, mPerPx = null) {
  const cx = srcW / 2;
  // 실제 축척을 아는 경우엔 바닥을 평면으로 본다. 내려다보는 카메라에서는
  // 겉보기 크기로 거리를 되짚는 것보다 이쪽이 맞다.
  if (mPerPx) {
    const base = Math.max(...people.map((p) => p.y), 1);
    return people.map((p) => ({
      right: (p.x - cx) * mPerPx,
      forward: Math.max(0.3, (base - p.y) * mPerPx + 1),
    }));
  }
  const f = focalPx(srcW, hfovDeg);
  return people.map((p) => {
    const rng = (f * HEAD_H_M) / Math.max(1, p.boxH);
    return { right: ((p.x - cx) / f) * rng, forward: rng };
  });
}

export function groundDensity(q, pts, sigmaM) {
  const inv = 1 / (2 * Math.PI * sigmaM * sigmaM), two = 2 * sigmaM * sigmaM;
  let s = 0;
  for (const p of pts) s += inv * Math.exp(-(((q[0] - p.right) ** 2) + ((q[1] - p.forward) ** 2)) / two);
  return s;
}

const BEARING_KO = ["전방", "우전방", "우측", "우후방", "후방", "좌후방", "좌측", "좌전방"];
export const bearingName = (deg) => BEARING_KO[Math.floor((((deg % 360) + 360) % 360 + 22.5) / 45) % 8];

export function inView(q, hfovDeg, maxRangeM, marginDeg = 2) {
  const [r, f] = q;
  if (f <= 0.3) return false;
  if (Math.abs(Math.atan2(r, f)) * 180 / Math.PI > hfovDeg / 2 - marginDeg) return false;
  return Math.hypot(r, f) <= maxRangeM;
}

/* 핫스팟에서 가장 덜 붐비면서 카메라가 보고 있는 방향.
 * 보이지 않는 곳은 후보에서 뺀다 — 비어 보이는 것과 비어 있는 것은 다르다. */
export function evacuationBearing(pts, hotspot, sigmaM, hfovDeg, maxRangeM, radiusM = 2.5, stepDeg = 15) {
  let best = null;
  for (let k = 0; k < Math.round(360 / stepDeg); k++) {
    const th = k * stepDeg, rad = (th * Math.PI) / 180;
    const q = [hotspot[0] + radiusM * Math.sin(rad), hotspot[1] + radiusM * Math.cos(rad)];
    if (!inView(q, hfovDeg, maxRangeM)) continue;
    const d = groundDensity(q, pts, sigmaM);
    if (!best || d < best.density - 1e-9) best = { bearing: th, density: d, point: q, name: bearingName(th) };
  }
  return best;
}

export function buildPicture(people, srcW, sigmaM, hfovDeg, mPerPx = null) {
  const pts = project(people, srcW, hfovDeg, mPerPx);
  const pic = { people: [], hotspot: null, hotspotDensity: 0, evacuation: null, maxRange: 0 };
  if (!pts.length) return pic;
  pic.people = pts.map((p) => ({ ...p, density: groundDensity([p.right, p.forward], pts, sigmaM) }));
  pic.maxRange = Math.max(...pic.people.map((p) => Math.hypot(p.right, p.forward))) * 1.15;
  const top = pic.people.reduce((a, b) => (b.density > a.density ? b : a));
  pic.hotspot = [top.right, top.forward];
  pic.hotspotDensity = top.density;
  pic.evacuation = evacuationBearing(pts, pic.hotspot, sigmaM, hfovDeg, pic.maxRange);
  return pic;
}

/* ───────────────── 안정화 ───────────────── */
export class LevelFilter {
  constructor(hold = 8) { this.hold = hold; this.value = 0; this._c = 0; this._n = 0; }
  update(level) {
    if (level === this.value) { this._n = 0; return this.value; }
    if (level === this._c) this._n++; else { this._c = level; this._n = 1; }
    if (this._n >= this.hold) { this.value = level; this._n = 0; }
    return this.value;
  }
}

/* N-of-M 히스테리시스. 한 프레임 튄 값이 드론을 띄우면 안 된다. */
export class AlertDebouncer {
  constructor(window = 15, onRatio = 0.6, offRatio = 0.25, minOnS = 5) {
    this.window = window; this.onRatio = onRatio; this.offRatio = offRatio;
    this.minOnS = minOnS; this.buf = []; this.active = false; this._since = 0;
  }
  update(raw, t = 0) {
    this.buf.push(raw ? 1 : 0);
    if (this.buf.length > this.window) this.buf.shift();
    const r = this.buf.reduce((a, v) => a + v, 0) / this.buf.length;
    if (!this.active) {
      if (r >= this.onRatio) { this.active = true; this._since = t; }
    } else if (r <= this.offRatio && t - this._since >= this.minOnS) {
      // 드론이 출발한 직후 경보가 꺼져 회항하는 것을 막는다
      this.active = false;
    }
    return this.active;
  }
}

/* ───────────────── 임무 상태기계 ─────────────────
 * flight/mission.py 의 단계와 전이 조건을 그대로 따른다.
 * 좌표계는 카메라 원점 (우측 m, 전방 m).
 */
export const MISSION = {
  IDLE: "대기", NAVIGATING: "출동", HOVERING: "안내",
  RETRACTING: "회수", RETURNING: "복귀",
};
export const TRACK = ["IDLE", "NAVIGATING", "HOVERING", "RETRACTING", "RETURNING"];

export const DEMO_CONFIG = {
  cruiseAltM: 3.0, speedMps: 1.6, climbMps: 1.0,
  arrivalRadiusM: 0.8, hoverS: 10, deployS: 3, retractS: 4,
  cooldownS: 15, navTimeoutS: 60, retargetM: 1.5,
};

export class Mission {
  constructor(cfg = {}) {
    this.cfg = { ...DEMO_CONFIG, ...cfg };
    this.state = "IDLE";
    this.reason = "경보 대기";
    this.pos = [0, 0];
    this.alt = 0;
    this.heading = 0;
    this.goal = null;
    this.trail = [];
    this.payload = "접힘";
    this.completed = 0;
    this._t = null;
    this._entered = 0;
    this._cooldownUntil = -1e9;
    this._manual = false;
    this._payloadAt = 0;
  }
  get flying() { return this.state !== "IDLE" || this.alt > 0.02; }
  dispatch() { this._manual = true; }
  _enter(s, t, reason) { this.state = s; this._entered = t; this.reason = reason; }

  update(alertRising, alertActive, count, hotspot, t) {
    const dt = this._t == null ? 0 : Math.max(0, Math.min(t - this._t, 0.5));
    this._t = t;
    const C = this.cfg;
    const rising = alertRising || this._manual;
    if (this._manual) this._manual = false;

    if (this.state === "IDLE") {
      if (rising && hotspot && t >= this._cooldownUntil) {
        this.goal = hotspot.slice();
        this._enter("NAVIGATING", t, `과밀집 ${count}명`);
      }
    } else if (this.state === "NAVIGATING") {
      if (hotspot) {
        const d = Math.hypot(hotspot[0] - this.goal[0], hotspot[1] - this.goal[1]);
        if (d >= C.retargetM) this.goal = hotspot.slice();   // 군중이 움직이면 재조준
      }
      if (t - this._entered > C.navTimeoutS) {
        this.goal = [0, 0];
        this._enter("RETURNING", t, "이동 시간 초과");
      } else if (this.alt > 0.5 * C.cruiseAltM &&
                 Math.hypot(this.goal[0] - this.pos[0], this.goal[1] - this.pos[1]) <= C.arrivalRadiusM) {
        this._enter("HOVERING", t, "목표 도달");
        this.payload = "전개 중"; this._payloadAt = t;
      }
    } else if (this.state === "HOVERING") {
      if (this.payload === "전개 중" && t - this._payloadAt >= C.deployS) this.payload = "전개";
      if (t - this._entered >= C.hoverS) {
        this._enter("RETRACTING", t, "안내 종료 — 구조물 수축");
        this.payload = "수축 중"; this._payloadAt = t;
      }
    } else if (this.state === "RETRACTING") {
      // 접힘을 확인하기 전에는 복귀하지 않는다
      if (t - this._payloadAt >= C.retractS) {
        this.payload = "접힘";
        this.goal = [0, 0];
        this._enter("RETURNING", t, "수축 완료");
      }
    } else if (this.state === "RETURNING") {
      if (this.alt <= 0.02 && Math.hypot(this.pos[0], this.pos[1]) < 0.15) {
        this.completed++;
        this._cooldownUntil = t + C.cooldownS;
        this.goal = null;
        this._enter("IDLE", t, "임무 완료");
      }
    }
    this._fly(dt);
    return this.state;
  }

  _fly(dt) {
    const C = this.cfg;
    if (this.state === "IDLE" && this.alt <= 0.02) return;
    const home = this.state === "RETURNING";
    const atHome = Math.hypot(this.pos[0], this.pos[1]) < 0.15;
    if (home && atHome) this.alt = Math.max(0, this.alt - C.climbMps * dt);
    else this.alt = Math.min(C.cruiseAltM, this.alt + C.climbMps * dt);

    if (this.goal && this.alt > 0.5 * C.cruiseAltM) {
      const dx = this.goal[0] - this.pos[0], dy = this.goal[1] - this.pos[1];
      const d = Math.hypot(dx, dy);
      if (d > 1e-3) {
        const s = Math.min(d, C.speedMps * dt);
        this.pos[0] += (dx / d) * s; this.pos[1] += (dy / d) * s;
        this.heading = ((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360;
      }
    }
    this.trail.push([this.pos[0], this.pos[1]]);
    if (this.trail.length > 600) this.trail.shift();
  }
}
