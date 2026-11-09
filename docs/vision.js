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

/* ───────────────── 지면 평면 (원근 보정) ─────────────────
 * 비스듬히 내려다본 화면에서는 같은 1 m 가 가까운 쪽에서 더 많은 픽셀을
 * 차지한다. 화면 전체에 축척 하나를 쓰면 가까운 사람들이 실제보다 멀리
 * 떨어진 것으로 계산돼 밀집도가 낮게 나온다. 45도 · 고도 10 m 로 모사해
 * 재 보면 8 m 앞이 0.53, 24 m 앞이 1.77 이었다 — 진짜는 둘 다 1.00 이다.
 * 가까울수록 한산해 보이는 현상의 원인이 이것이다.
 *
 * 바닥 직사각형의 네 모서리를 찍고 실제 치수를 넣으면 호모그래피가 풀린다.
 * 그 뒤로는 모든 계산을 미터 좌표에서 하므로 원근이 아예 사라진다.
 * vision/geometry.py 의 GroundPlane 과 같은 방식이다. */
export class GroundPlane {
  constructor(h = null, widthM = 0, heightM = 0) {
    this.h = h; this.widthM = widthM; this.heightM = heightM; this._cache = null;
  }
  get ok() { return this.h != null; }

  /* imgQuad : 좌상 → 우상 → 우하 → 좌하 순서의 화면 좌표 네 개.
   * 내려다보는 화면은 위쪽이 먼 쪽이므로 그 변을 Y = heightM 에 둔다. */
  static fromQuad(imgQuad, widthM, heightM) {
    if (!imgQuad || imgQuad.length !== 4 || !(widthM > 0) || !(heightM > 0)) return new GroundPlane();
    const h = solveHomography(imgQuad, [[0, heightM], [widthM, heightM], [widthM, 0], [0, 0]]);
    return h ? new GroundPlane(h, widthM, heightM) : new GroundPlane();
  }

  toGround(x, y) {
    const h = this.h;
    if (!h) return null;
    const w = h[6] * x + h[7] * y + 1;
    if (Math.abs(w) < 1e-9) return null;                 // 지평선
    return [(h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w];
  }

  /* 호모그래피는 직선을 직선으로 보내므로 꼭짓점만 옮겨 신발끈으로 재면 된다. */
  areaM2(poly) {
    if (!this.h || !poly || poly.length < 3) return null;
    const g = [];
    for (const [x, y] of poly) { const q = this.toGround(x, y); if (!q) return null; g.push(q); }
    let a = 0;
    for (let i = 0, j = g.length - 1; i < g.length; j = i++)
      a += g[j][0] * g[i][1] - g[i][0] * g[j][1];
    return Math.abs(a) / 2;
  }
}

/* 네 점 대응이면 호모그래피는 8 x 8 일차연립이다. 가우스 소거로 바로 푼다. */
function solveHomography(src, dst) {
  const A = [], b = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i], [X, Y] = dst[i];
    A.push([x, y, 1, 0, 0, 0, -x * X, -y * X]); b.push(X);
    A.push([0, 0, 0, x, y, 1, -x * Y, -y * Y]); b.push(Y);
  }
  for (let c = 0; c < 8; c++) {
    let piv = c;
    for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[piv][c])) piv = r;
    if (Math.abs(A[piv][c]) < 1e-12) return null;        // 네 점이 한 줄에 있다
    [A[c], A[piv]] = [A[piv], A[c]]; [b[c], b[piv]] = [b[piv], b[c]];
    for (let r = 0; r < 8; r++) {
      if (r === c) continue;
      const f = A[r][c] / A[c][c];
      for (let k = c; k < 8; k++) A[r][k] -= f * A[c][k];
      b[r] -= f * b[c];
    }
  }
  return b.map((v, i) => v / A[i][i]);
}

/* ───────────────── 적응형 KDE 밀집도 ─────────────────
 * 사람마다 가우시안을 깔고 더한다. 격자가 없으므로 셀 경계에 걸린 군집도
 * 하나로 잡힌다. 균일한 군중에서는 실제 밀집도로 수렴한다.
 *
 * 거리 환산은 세 가지 중 하나다. ground 가 있으면 미터 좌표에서 바로 재고
 * (가장 정확하다), mPerPx 가 있으면 화면 전체에 그 값을 쓰고, 둘 다 없으면
 * 머리 세로 0.23 m 로 박스 높이에서 그 지점의 축척을 되짚는다.
 */
export function densityField(people, sigmaM = 0.75, mPerPx = null, ground = null) {
  const n = people.length;
  const out = { perPerson: [], peak: 0, peakIndex: -1, mean: 0, sigmaM };
  if (!n) return out;

  const gp = ground && ground.ok ? ground : null;
  const gxy = gp ? people.map((p) => gp.toGround(p.x, p.y)) : null;
  const scales = people.map((p) => mPerPx ?? HEAD_H_M / Math.max(1, p.boxH));
  const inv = 1 / (2 * Math.PI * sigmaM * sigmaM);
  const two = 2 * sigmaM * sigmaM;

  for (let i = 0; i < n; i++) {
    let total = 0;
    for (let j = 0; j < n; j++) {
      let dM;
      if (i === j) dM = 0;
      else if (gxy) {
        if (!gxy[i] || !gxy[j]) continue;
        dM = Math.hypot(gxy[i][0] - gxy[j][0], gxy[i][1] - gxy[j][1]);
      } else {
        const dx = people[i].x - people[j].x;
        const dy = people[i].y - people[j].y;
        dM = Math.hypot(dx, dy) * (scales[i] + scales[j]) * 0.5;
      }
      total += inv * Math.exp(-(dM * dM) / two);
    }
    out.perPerson.push({ x: people[i].x, y: people[i].y, density: total,
                         scale: scales[i], ground: gxy ? gxy[i] : null });
    out.mean += total;
    if (total > out.peak) { out.peak = total; out.peakIndex = i; }
  }
  out.mean /= n;
  return out;
}

/* 표시용 저해상도 장. 사람마다 가우시안 패치를 더한다. */
export function densityRaster(people, sigmaM, srcW, srcH, fieldW = 160, mPerPx = null, ground = null) {
  const fw = Math.max(16, Math.min(fieldW, srcW));
  const fh = Math.max(9, Math.round((srcH * fw) / srcW));
  const heat = new Float32Array(fw * fh);
  if (!people.length) return { heat, fw, fh };
  if (ground && ground.ok) return groundRaster(people, sigmaM, srcW, srcH, fw, fh, ground);

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

/* 지면 평면이 있을 때의 히트맵. 가우시안은 미터 격자에 등방으로 뿌리고,
 * 화면 격자는 그걸 되읽기만 한다. 화면에서 직접 뿌리면 원근 때문에 패치가
 * 타원으로 일그러져야 하는데, 지면에서 뿌리면 그 문제가 없다.
 * 화면 칸 → 지면 좌표 표는 보정이 바뀔 때만 다시 만든다. */
function groundRaster(people, sigmaM, srcW, srcH, fw, fh, gp) {
  const heat = new Float32Array(fw * fh);
  const g = [];
  for (const p of people) { const q = gp.toGround(p.x, p.y); if (q) g.push(q); }
  if (!g.length) return { heat, fw, fh };

  const pad = 3 * sigmaM;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const [X, Y] of g) {
    x0 = Math.min(x0, X); x1 = Math.max(x1, X);
    y0 = Math.min(y0, Y); y1 = Math.max(y1, Y);
  }
  x0 -= pad; x1 += pad; y0 -= pad; y1 += pad;
  const gw = Math.max(2, Math.min(256, Math.ceil(((x1 - x0) * 3) / sigmaM)));
  const gh = Math.max(2, Math.min(256, Math.ceil(((y1 - y0) * 3) / sigmaM)));
  const cw = (x1 - x0) / gw, ch = (y1 - y0) / gh;
  const grid = new Float32Array(gw * gh);

  const inv = 1 / (2 * Math.PI * sigmaM * sigmaM), two = 2 * sigmaM * sigmaM;
  const rx = Math.ceil((3 * sigmaM) / cw), ry = Math.ceil((3 * sigmaM) / ch);
  for (const [X, Y] of g) {
    const ci = (X - x0) / cw, cj = (Y - y0) / ch;
    const i0 = Math.max(0, Math.floor(ci) - rx), i1 = Math.min(gw, Math.floor(ci) + rx + 1);
    const j0 = Math.max(0, Math.floor(cj) - ry), j1 = Math.min(gh, Math.floor(cj) + ry + 1);
    for (let j = j0; j < j1; j++) {
      const dy = (j + 0.5 - cj) * ch;
      for (let i = i0; i < i1; i++) {
        const dx = (i + 0.5 - ci) * cw;
        grid[j * gw + i] += inv * Math.exp(-(dx * dx + dy * dy) / two);
      }
    }
  }

  const key = `${fw}x${fh}x${srcW}x${srcH}`;
  if (!gp._cache || gp._cache.key !== key) {
    const map = new Float64Array(fw * fh * 2);
    for (let y = 0; y < fh; y++)
      for (let x = 0; x < fw; x++) {
        const q = gp.toGround(((x + 0.5) * srcW) / fw, ((y + 0.5) * srcH) / fh);
        const k = (y * fw + x) * 2;
        map[k] = q ? q[0] : NaN; map[k + 1] = q ? q[1] : NaN;
      }
    gp._cache = { key, map };
  }
  const map = gp._cache.map;
  for (let n = 0; n < fw * fh; n++) {
    const X = map[n * 2], Y = map[n * 2 + 1];
    if (!(X >= x0 && X < x1 && Y >= y0 && Y < y1)) continue;
    const i = Math.min(gw - 1, Math.floor((X - x0) / cw));
    const j = Math.min(gh - 1, Math.floor((Y - y0) / ch));
    heat[n] = grid[j * gw + i];
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

  // 면적의 출처는 셋이다. 직접 입력 > 지면 보정 > 머리 크기 추정 순으로 믿는다.
  const fromGround = opts.areaM2 == null && opts.ground && opts.ground.ok
    ? opts.ground.areaM2(polygon) : null;
  const areaGiven = opts.areaM2 != null || fromGround != null;
  const area = opts.areaM2 != null ? opts.areaM2
    : (fromGround != null ? fromGround : estimateAreaM2(polygon, field.perPerson, srcW, srcH));
  // 영상 위 표시도 한 사람의 최댓값이 아니라 무리의 무게중심을 쓴다.
  // 비슷한 점이 수십 개라 최댓값만 고르면 표시가 옆 사람으로 옮겨 다닌다.
  let peak = 0;
  for (const p of inside) if (p.density > peak) peak = p.density;
  let peakPoint = null;
  if (peak > 0) {
    const cut = peak * 0.8;
    let wx = 0, wy = 0, w = 0;
    for (const p of inside) {
      if (p.density < cut) continue;
      const k = p.density - cut + 1e-9;
      wx += p.x * k; wy += p.y * k; w += k;
    }
    if (w > 0) peakPoint = [wx / w, wy / w];
  }
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

export function project(people, srcW, hfovDeg, mPerPx = null, ground = null) {
  const cx = srcW / 2;
  // 지면 보정이 있으면 원근이 이미 풀려 있다. 보정 사각형의 가까운 변이
  // 화각을 꽉 채우는 거리에 카메라가 있다고 보고 전방 거리를 잰다 —
  // 그래야 inView 의 부채꼴이 보정 구역과 어긋나지 않는다.
  if (ground && ground.ok) {
    const off = (ground.widthM / 2) / Math.tan((hfovDeg * Math.PI) / 180 / 2);
    return people.map((p) => {
      const q = ground.toGround(p.x, p.y);
      return q ? { right: q[0] - ground.widthM / 2, forward: Math.max(0.3, q[1] + off) }
               : { right: 0, forward: 0.3 };
    });
  }
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

/* ───────────────── 방향 기억 ─────────────────
 * 유도는 관측이 아니라 개입이다. 어떤 방향을 가리키면 사람이 그쪽으로
 * 가고, 그 결과가 화면에 보이기까지는 몇 초가 걸린다. 매 프레임 "지금
 * 제일 빈 쪽" 만 보고 고르면, 방금 사람을 보낸 곳이 아직 비어 보이므로
 * 계속 그쪽을 가리키다가 거기가 꽉 찬 뒤에야 바꾼다. 그 다음엔 반대쪽이
 * 비어 보여 다시 넘어가고, 화살표가 좌우로 왕복한다.
 *
 * 두 가지를 기억한다.
 *   부하(load)  : 그 방향으로 얼마나 오래 유도했는가. 보낸 만큼 미리
 *                 비용을 매긴다. 시정수 loadTauS 로 잊는다.
 *   추세(trend) : 그 방향의 밀집도가 오르는 중인가. 지금은 비어도
 *                 차오르고 있으면 피한다.
 * 둘 다 명/m² 단위의 벌점으로 바꿔 측정 밀집도에 더한다.
 *
 * 언제 쓸모가 있는가. 모사해 보면 조건이 분명하다. 보낸 사람이 계속 화면
 * 안에 있으면 측정 밀집도가 이미 그 이력을 담고 있어서 기억은 아무것도
 * 바꾸지 않는다 — 같은 결과가 나온다. 쓸모는 유도한 사람이 화각 밖으로
 * 나갈 때 생긴다. 줄의 20% 만 보이면 최대 대기가 13.8 → 10.0 명으로,
 * 전혀 안 보이면 442 → 24 명으로 줄었다. 기체가 핫스팟 위에 떠서
 * 멀리 보낸 사람을 못 보는 실제 상황이 바로 그 경우다. */
export class BearingMemory {
  constructor({ bins = 24, loadTauS = 18, trendTauS = 10,
                loadWeight = 0.8, trendWeight = 1.0, spreadDeg = 30,
                minDwellS = 4, breakMargin = 0.25 } = {}) {
    Object.assign(this, { bins, loadTauS, trendTauS, loadWeight, trendWeight,
                          spreadDeg, minDwellS, breakMargin });
    this.load = new Float64Array(bins);
    this.dens = new Float64Array(bins).fill(NaN);
    this.trend = new Float64Array(bins);
    this.held = null; this._heldAt = 0; this._t = null;
  }
  reset() {
    this.load.fill(0); this.dens.fill(NaN); this.trend.fill(0);
    this.held = null; this._t = null;
  }

  _bin(deg) { const n = this.bins; return ((Math.round(deg / (360 / n)) % n) + n) % n; }
  _arc(a, b) { return Math.abs((((a - b) % 360) + 540) % 360 - 180); }

  penalty(deg) {
    const b = this._bin(deg);
    return this.loadWeight * this.load[b] + this.trendWeight * Math.max(0, this.trend[b]);
  }

  /* cands : [{ bearing, density, ... }] 중 하나를 고른다.
   * 세 가지가 동시에 걸려 있다.
   *   1. 최소 유지  : 한 번 가리키면 minDwellS 동안은 바꾸지 않는다. 바닥의
   *                   사람이 화살표를 보고 움직이는 데 그만큼 걸린다.
   *   2. 전환 문턱  : 그 뒤에도 더 나은 쪽이 breakMargin 만큼 확실히 나아야
   *                   옮긴다. 비슷하면 그대로 둔다.
   *   3. 기억       : 점수에 부하와 추세를 더해, 오래 보낸 쪽과 차오르는 쪽을
   *                   미리 피한다. */
  decide(cands, t) {
    const dt = this._t == null ? 0 : Math.max(0, Math.min(t - this._t, 2));
    this._t = t;
    if (!cands || !cands.length) { this.held = null; return null; }

    if (dt > 0) {
      const k = Math.exp(-dt / this.loadTauS);
      for (let i = 0; i < this.bins; i++) this.load[i] *= k;
    }
    const a = dt > 0 ? 1 - Math.exp(-dt / this.trendTauS) : 1;
    for (const c of cands) {
      const b = this._bin(c.bearing);
      if (Number.isNaN(this.dens[b])) { this.dens[b] = c.density; continue; }
      const prev = this.dens[b];
      this.dens[b] += a * (c.density - prev);
      if (dt > 0) this.trend[b] += a * ((this.dens[b] - prev) / dt - this.trend[b]);
    }

    for (const c of cands) c.score = c.density + this.penalty(c.bearing);
    let best = cands[0];
    for (const c of cands) if (c.score < best.score) best = c;

    let pick = best;
    const kept = this.held == null ? null : cands.find((c) => c.bearing === this.held);
    if (kept) {
      if (t - this._heldAt < this.minDwellS) pick = kept;
      else if (kept.score <= best.score + this.breakMargin) pick = kept;
    }
    if (this.held !== pick.bearing) { this.held = pick.bearing; this._heldAt = t; }

    // 가리킨 방향에 부하를 쌓는다. 바로 옆도 사람이 섞여 가므로 같이 받는다.
    if (dt > 0) {
      for (let i = 0; i < this.bins; i++) {
        const d = this._arc(i * (360 / this.bins), pick.bearing);
        if (d > this.spreadDeg) continue;
        this.load[i] += (dt / this.loadTauS) * Math.cos(((d / this.spreadDeg) * Math.PI) / 2);
      }
    }
    return pick;
  }
}

/* 핫스팟에서 가장 덜 붐비면서 카메라가 보고 있는 방향.
 * 보이지 않는 곳은 후보에서 뺀다 — 비어 보이는 것과 비어 있는 것은 다르다.
 *
 * prevBearing 을 주면 그쪽을 먼저 본다. 15도 간격으로 끊어 고르는 탓에, 두
 * 방향의 밀집도가 비슷하면 매 프레임 번갈아 뽑혀 화살표가 떤다. 이전 방향이
 * stick 배 안쪽이면 그대로 둔다. */
export function evacuationBearing(pts, hotspot, sigmaM, hfovDeg, maxRangeM,
                                  radiusM = 2.5, stepDeg = 15,
                                  prevBearing = null, stick = 1.3,
                                  memory = null, tNow = 0) {
  let best = null, prev = null;
  const samples = [];
  for (let k = 0; k < Math.round(360 / stepDeg); k++) {
    const th = k * stepDeg, rad = (th * Math.PI) / 180;
    const q = [hotspot[0] + radiusM * Math.sin(rad), hotspot[1] + radiusM * Math.cos(rad)];
    if (!inView(q, hfovDeg, maxRangeM)) continue;
    const d = groundDensity(q, pts, sigmaM);
    const c = { bearing: th, density: d, score: d, point: q, name: bearingName(th) };
    samples.push(c);
    if (!best || d < best.density - 1e-9) best = c;
    if (prevBearing != null && th === prevBearing) prev = c;
  }
  // 기억이 있으면 고르는 일을 그쪽에 맡긴다. 유지 시간까지 함께 보기 때문이다.
  if (memory) {
    const pick = memory.decide(samples, tNow);
    if (pick) pick.samples = samples;
    return pick;
  }
  if (prev && best && prev.density <= best.density * stick) return prev;
  if (best) best.samples = samples;
  return best;
}

/* 가장 붐비는 '한 사람' 이 아니라 '무리' 의 무게중심을 목표로 삼는다.
 * 사람이 수백 명이면 최댓값 근처에 비슷한 점이 수십 개라, 한 명만 고르면
 * 매 프레임 옆 사람으로 옮겨 다닌다. 최댓값의 ratio 이상인 점들을 밀집도로
 * 가중평균하면 그 떨림이 사라지고, 무리가 실제로 움직일 때만 따라간다. */
export function densePeak(people, ratio = 0.8) {
  if (!people.length) return null;
  const peak = Math.max(...people.map((p) => p.density));
  const cut = peak * ratio;
  let wx = 0, wy = 0, w = 0;
  for (const p of people) {
    if (p.density < cut) continue;
    const k = p.density - cut + 1e-9;            // 경계에 걸친 점의 영향을 줄인다
    wx += p.right * k; wy += p.forward * k; w += k;
  }
  if (w <= 0) return { point: null, density: peak };
  return { point: [wx / w, wy / w], density: peak };
}

/* 프레임마다 다시 계산한 목표를 시간축으로 눌러 준다.
 *   deadbandM 안쪽 : 무시한다. 검출이 한둘 바뀔 때마다 나는 잔떨림이다.
 *   jumpM 바깥쪽   : 바로 따라가지 않고, 그 자리에 jumpHoldS 만큼 머무르는지
 *                    확인한 뒤 옮긴다. 한 프레임짜리 오검출에 끌려가지 않는다.
 *   그 사이        : 시정수 tau 의 지수평활로 천천히 끌어간다. */
export class HotspotFilter {
  constructor({ tau = 1.2, deadbandM = 0.6, jumpM = 3, jumpHoldS = 1.2 } = {}) {
    Object.assign(this, { tau, deadbandM, jumpM, jumpHoldS });
    this.value = null; this._t = null; this._cand = null; this._candAt = 0;
  }
  reset() { this.value = null; this._t = null; this._cand = null; }
  update(p, t) {
    const dt = this._t == null ? 0 : Math.max(0, Math.min(t - this._t, 1));
    this._t = t;
    if (!p) return this.value;
    if (!this.value) { this.value = p.slice(); return this.value; }
    const d = Math.hypot(p[0] - this.value[0], p[1] - this.value[1]);
    if (d >= this.jumpM) {
      if (this._cand && Math.hypot(p[0] - this._cand[0], p[1] - this._cand[1]) < this.jumpM) {
        if (t - this._candAt >= this.jumpHoldS) { this.value = p.slice(); this._cand = null; }
      } else { this._cand = p.slice(); this._candAt = t; }
      return this.value;
    }
    this._cand = null;
    if (d < this.deadbandM) return this.value;
    const a = this.tau > 0 ? 1 - Math.exp(-dt / this.tau) : 1;
    this.value = [this.value[0] + a * (p[0] - this.value[0]),
                  this.value[1] + a * (p[1] - this.value[1])];
    return this.value;
  }
}

export function buildPicture(people, srcW, sigmaM, hfovDeg, opts = {}) {
  const { mPerPx = null, prevBearing = null, ground = null, memory = null, t = null } = opts;
  const pts = project(people, srcW, hfovDeg, mPerPx, ground);
  const pic = { people: [], hotspot: null, hotspotDensity: 0, evacuation: null, maxRange: 0 };
  if (!pts.length) return pic;
  pic.people = pts.map((p) => ({ ...p, density: groundDensity([p.right, p.forward], pts, sigmaM) }));
  // 최댓값 대신 95 분위를 쓴다. 멀리 하나 잘못 잡히면 사거리가 통째로 흔들린다.
  const rs = pic.people.map((p) => Math.hypot(p.right, p.forward)).sort((a, b) => a - b);
  pic.maxRange = rs[Math.min(rs.length - 1, Math.floor(rs.length * 0.95))] * 1.15;
  const dp = densePeak(pic.people);
  pic.hotspot = dp.point;
  pic.hotspotDensity = dp.density;
  if (pic.hotspot)
    pic.evacuation = evacuationBearing(pts, pic.hotspot, sigmaM, hfovDeg, pic.maxRange,
                                       2.5, 15, prevBearing, 1.3, memory, t ?? 0);
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
  cooldownS: 15, navTimeoutS: 60, retargetM: 2.5,
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
        // 군중이 실제로 옮겨 가면 따라가되, 다 와 가면 더 건드리지 않는다.
        // 도착 직전에 목표를 흔들면 기체가 그 자리를 맴돈다.
        const near = Math.hypot(this.goal[0] - this.pos[0], this.goal[1] - this.pos[1]);
        if (d >= C.retargetM && near > C.arrivalRadiusM * 2) this.goal = hotspot.slice();
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
