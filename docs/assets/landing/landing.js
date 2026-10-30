/* gnomon landing: the page furniture and the hero sundial.
   Ported from the approved mockup docs/superpowers/specs/2026-10-21-docs-landing-mockup-v2.html. */

/* ============================================================
   Page furniture that never needs WebGL.
   ============================================================ */
// The calibrated scale's ticks: every unit, longer every 5, cut marks at the level floors.
function buildTicks() {
  const box = document.querySelector('.ticks');
  if (!box) return;
  const cuts = [25, 45, 60, 75, 88];
  let html = '';
  for (let v = 0; v <= 100; v++) {
    const cls = cuts.includes(v) ? 'cut' : (v % 5 === 0 ? 'five' : '');
    const left = v === 100 ? 'calc(100% - 1px)' : v + '%';
    html += `<i class="${cls}" style="left:${left}"></i>`;
  }
  for (const v of cuts) html += `<b style="left:${v}%">${v}</b>`;
  box.innerHTML = html;
}

// The contact band repeats the dial's chapter ring as a faint engraved arc.
function contactArc() {
  const svg = document.querySelector('.contact-arc');
  if (!svg) return;
  const out = [];
  const at = (v, r) => { const a = Math.PI * (1 - v / 100) + Math.PI / 2; return [r * Math.cos(a), -r * Math.sin(a)]; };
  const f = n => n.toFixed(2);
  for (let v = 0; v <= 100; v++) {
    const major = [0, 25, 45, 60, 75, 88, 100].includes(v), five = v % 5 === 0;
    const r0 = major ? 80 : five ? 86 : 89, [x0, y0] = at(v, r0), [x1, y1] = at(v, 93);
    out.push(`<line x1="${f(x0)}" y1="${f(y0)}" x2="${f(x1)}" y2="${f(y1)}" stroke="${major ? '#4F7FC0' : '#22385A'}" stroke-width="${major ? 0.6 : 0.3}"/>`);
  }
  out.push('<circle r="95" fill="none" stroke="#1A2F4D" stroke-width="0.35"/>');
  out.push('<circle r="70" fill="none" stroke="#14263F" stroke-width="0.35"/>');
  svg.innerHTML = out.join('');
}

// Copy the install command.
function copyCommand() {
  const btn = document.querySelector('.copy'), code = document.getElementById('install-cmd');
  if (!btn || !code) return;
  btn.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(code.dataset.copy); btn.textContent = 'Copied'; }
    catch (e) { const r = document.createRange(); r.selectNodeContents(code); const s = getSelection(); s.removeAllRanges(); s.addRange(r); btn.textContent = 'Selected'; }
    setTimeout(() => { btn.textContent = 'Copy'; }, 1800);
  });
}

buildTicks();
contactArc();
copyCommand();

/* ============================================================
   The hero sundial: a porcelain dial in a steel case, with an obelisk gnomon.
   The AQ scale is the hour fan; a moving sun casts the reading.
   World: y up, dial centre at the origin, the scale on the near half (toward the camera).
   Two renderers share this file's geometry: WebGL (three.js, live) and SVG (static fallback).
   ============================================================ */
const D2R = Math.PI / 180;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const mix = (a, b, t) => a + (b - a) * t;
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const easeOut = x => 1 - Math.pow(1 - clamp(x), 3);
const easeInOut = x => { x = clamp(x); return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };

const LEVELS = [['Novice', 0, 25], ['Apprentice', 25, 45], ['Adequate', 45, 60], ['Proficient', 60, 75], ['Advanced', 75, 88], ['Elite', 88, 100]];
const FLOORS = [0, 25, 45, 60, 75, 88, 100];
const ENAMEL = ['#D5D9DD', '#CFE0F7', '#9EC2EF', '#6BA1E4', '#4189DC', '#2A78D6'];   // grey track, then --blue-100 … --blue-500
const levelOf = v => LEVELS.find(([, a, b]) => v >= a && (v < b || b === 100)) || LEVELS[0];

// Dimensions, in world units. The dial plate is 20 across.
const G = {
  R: 10, faceR: 9.3, plateH: 1.1, faceY: 1.0,
  railOut: 9.0, railIn: 8.42, idxIn: 7.55, idxOut: 8.95, num: 6.98, bandIn: 5.55, bandOut: 6.35, name: 4.86,
  hourIn: 1.95, hourOut: 5.38, hubRing: 1.72,
  plinthW: 1.05, plinthH: 0.38, shaftW0: 0.5, shaftW1: 0.34, shaftH: 5.9, pyrH: 0.72
};
G.top = G.faceY + G.plinthH + G.shaftH + G.pyrH;   // obelisk apex height

// A scale value → its direction on the plate (x, z). FAN -1 lays the scale on the near half, so the shadow
// falls toward the viewer and is never hidden behind the obelisk. Values past 100 carry on round the far half.
const FAN = -1;
function dirOf(v) { const a = Math.PI * (1 - v / 100); return [Math.cos(a), -FAN * Math.sin(a)]; }

/* ---------- the sun ----------
   One cycle has two parts. The day (phase 0 → 1, 34 s) carries the shadow across the scale, from 0 at dawn to 100
   at dusk, on the approved arc: 11° above the horizon at both ends and 33° at noon. The night (phase 1 → 2, 9 s)
   keeps the sun circling, low, in front of the dial, so the shadow sweeps round behind the gnomon and is back at 0
   for the next dawn. The light never goes out, so the dial never turns flat grey. */
const SUN = { e0: 11, e1: 33, dip: 4 };   // degrees: dawn and dusk, noon, and how far the sun sinks at midnight
const DAY = 34, NIGHT = 9;
// The night speeds the sun up smoothly, so the far half takes NIGHT seconds and the speed never jumps.
const NIGHT_GAIN = 2 * (1 - NIGHT / DAY) / NIGHT;
// The day's arc is the approved sin^0.85 curve. Its last tenth toward the horizon is a matching quadratic, so the
// elevation turns into the night without a kink; the night's dip starts and ends on the same slope.
const ARC_S = 0.1, ARC_A = 1.15 * Math.pow(ARC_S, -0.15), ARC_B = -0.15 * Math.pow(ARC_S, -1.15);
const NIGHT_N = (SUN.e1 - SUN.e0) * ARC_A / SUN.dip;
const dayArc = s => (s >= ARC_S ? Math.pow(s, 0.85) : s * (ARC_A + ARC_B * s));
function elevation(phi) {
  if (phi <= 1) return SUN.e0 + (SUN.e1 - SUN.e0) * dayArc(Math.sin(Math.PI * clamp(phi)));
  return SUN.e0 - SUN.dip * (1 - Math.pow(clamp(1 - Math.sin(Math.PI * (phi - 1))), NIGHT_N));
}
// Seconds into the sweep → the phase, in [0, 2).
function phaseAt(t) {
  const cyc = DAY + NIGHT, c = ((t % cyc) + cyc) % cyc;
  if (c < DAY) return c / DAY;
  const u = (c - DAY) / NIGHT;
  return 1 + (NIGHT / DAY) * u + NIGHT_GAIN * NIGHT * (u / 2 - Math.sin(2 * Math.PI * u) / (4 * Math.PI));
}
// The sun for a phase: its scale value, elevation, the shadow's direction on the plate, and L, pointing at the sun.
function sunAt(phi) {
  const v = 100 * phi, e = elevation(phi) * D2R;
  const [dx, dz] = dirOf(v);
  return { v, e, dir: [dx, dz], L: [-dx * Math.cos(e), Math.sin(e), -dz * Math.cos(e)] };
}

/* ---------- composition: where the dial sits, per layout ---------- */
const hero = document.querySelector('.hero');
const glBox = hero.querySelector('.hero-gl');
const stage = hero.querySelector('.hero-stage');
const readingEl = hero.querySelector('.reading');
const readV = hero.querySelector('.reading-v'), readN = hero.querySelector('.reading-n');
const motionBtn = hero.querySelector('.motion-btn');
const reduceMQ = matchMedia('(prefers-reduced-motion: reduce)');
const narrowMQ = matchMedia('(max-width: 900px)');
const STILL_PHASE = 0.8;   // the frame shown with reduced motion and by the static fallback

function compose(w, h) {
  const hr = hero.getBoundingClientRect(), sr = stage.getBoundingClientRect();
  const sx = sr.left - hr.left, sy = sr.top - hr.top, sw = sr.width, sh = sr.height;
  let c;
  if (narrowMQ.matches) {
    c = { el: 36, az: 20, fov: 24 };
    c.rPx = Math.min(sw * 0.46, sh * 0.62, 300);
    c.ox = sx + sw * 0.5; c.oy = sy + sh * 0.55;
  } else {
    c = { el: 34, az: 24, fov: 21 };
    c.rPx = Math.min(sw * 0.5, sh * 0.6, 600);
    c.ox = Math.min(sx + sw * 0.53, w - c.rPx * 1.02); c.oy = sy + sh * 0.6;
  }
  c.w = w; c.h = h; c.ty = 2.2;
  c.k = h / (2 * Math.tan(c.fov * D2R / 2));     // pixels per unit at depth 1
  c.D = G.R * c.k / c.rPx;
  return c;
}

// Pinhole camera with a shift lens: looks at (0, ty, 0) from (el, az); the dial centre lands on (ox, oy).
const V = {
  sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
  dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
  cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
  norm: a => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; }
};
function cameraFor(c, dAz = 0, dEl = 0, dDist = 1) {
  const el = (c.el + dEl) * D2R, az = (c.az + dAz) * D2R, D = c.D * dDist;
  const tgt = [0, c.ty, 0];
  const eye = [D * Math.cos(el) * Math.sin(az), c.ty + D * Math.sin(el), D * Math.cos(el) * Math.cos(az)];
  const f = V.norm(V.sub(tgt, eye)), r = V.norm(V.cross(f, [0, 1, 0])), u = V.cross(r, f);
  const raw = p => { const q = V.sub(p, eye); const z = V.dot(q, f); return [c.w / 2 + c.k * V.dot(q, r) / z, c.h / 2 - c.k * V.dot(q, u) / z, z]; };
  const [dx0, dy0] = raw([0, G.faceY, 0]);
  const shiftX = c.ox - dx0, shiftY = c.oy - dy0;
  return { eye, tgt, f, r, u, shiftX, shiftY, fov: c.fov, project: p => { const s = raw(p); return [s[0] + shiftX, s[1] + shiftY, s[2]]; } };
}

/* ---------- live reading (decorative; the scale itself is in the page text) ---------- */
let shownV = -1, readingOn = false;
function setReading(v, on) {
  if (!on) {   // the shadow is off the scale: fade the reading out but keep its place
    if (readingOn) { readingEl.classList.add('is-off'); readingOn = false; }
    return;
  }
  const n = Math.round(v);
  if (readingEl.hidden) readingEl.hidden = false;
  if (!readingOn) { readingEl.classList.remove('is-off'); readingOn = true; }
  if (n !== shownV) { readV.textContent = String(n).padStart(2, ' '); readN.textContent = levelOf(n)[0]; shownV = n; }
}

/* ---------- static renderer (SVG): no WebGL, or the CDN is blocked ---------- */
const NS = 'http://www.w3.org/2000/svg';
function drawSVG(svg, p) {
  const w = glBox.clientWidth, h = glBox.clientHeight;
  if (!w || !h) return;
  const c = compose(w, h), cam = cameraFor(c), sun = sunAt(p);
  const P = (x, y, z) => cam.project([x, y, z]);
  const f = n => n.toFixed(1);
  const pts = a => a.map(q => f(q[0]) + ',' + f(q[1])).join(' ');
  const ring = (r, y, a0 = 0, a1 = 2 * Math.PI, n = 160) => { const o = []; for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n; o.push(P(r * Math.cos(a), y, -r * Math.sin(a))); } return o; };
  const at = (v, r, y = G.faceY) => { const [x, z] = dirOf(v); return P(x * r, y, z * r); };
  const fan = (r, v0, v1, y = G.faceY, n = 48) => { const o = []; for (let i = 0; i <= n; i++) o.push(at(v0 + (v1 - v0) * i / n, r, y)); return o; };
  const C = P(0, G.faceY, 0);
  const out = [];
  out.push(`<defs>
    <radialGradient id="gPool" cx="${f(C[0])}" cy="${f(C[1])}" r="${f(c.rPx * 2.1)}" gradientUnits="userSpaceOnUse" gradientTransform="translate(${f(C[0])} ${f(C[1])}) scale(1 .62) translate(${f(-C[0])} ${f(-C[1])})"><stop offset="0" stop-color="#1B3459"/><stop offset=".45" stop-color="#11233F"/><stop offset="1" stop-color="#08121F" stop-opacity="0"/></radialGradient>
    <linearGradient id="gWall" x1="${f(C[0] - c.rPx)}" x2="${f(C[0] + c.rPx)}" y1="0" y2="0" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#2B3442"/><stop offset=".3" stop-color="#8C96A4"/><stop offset=".52" stop-color="#E9EDF2"/><stop offset=".62" stop-color="#8E98A6"/><stop offset="1" stop-color="#1E2631"/></linearGradient>
    <linearGradient id="gBezel" x1="0" y1="${f(C[1] - c.rPx * .6)}" x2="0" y2="${f(C[1] + c.rPx * .6)}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#5B6574"/><stop offset=".5" stop-color="#D9DEE5"/><stop offset="1" stop-color="#F7F9FB"/></linearGradient>
    <radialGradient id="gFace" cx="${f(C[0] + c.rPx * .25)}" cy="${f(C[1] + c.rPx * .1)}" r="${f(c.rPx * 1.25)}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#F6F8FA"/><stop offset=".7" stop-color="#E4E9EF"/><stop offset="1" stop-color="#C9D1DA"/></radialGradient>
    <linearGradient id="gSteelL" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5D93DE"/><stop offset="1" stop-color="#1D4C9E"/></linearGradient>
    <linearGradient id="gSteelD" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1C3F7E"/><stop offset="1" stop-color="#0D2350"/></linearGradient>
    <linearGradient id="gSilverL" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F2F5F8"/><stop offset="1" stop-color="#A9B2BE"/></linearGradient>
    <linearGradient id="gSilverD" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7D8794"/><stop offset="1" stop-color="#3B4350"/></linearGradient>
    <filter id="fSoft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="${f(c.rPx * 0.006)}"/></filter>
    <filter id="fBlur" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="${f(c.rPx * 0.03)}"/></filter>
  </defs>`);
  // the floor: a pool of light, the plate's contact shadow
  out.push(`<rect width="${w}" height="${h}" fill="url(#gPool)"/>`);
  out.push(`<polygon points="${pts(ring(G.R * 1.04, 0))}" fill="#02060C" opacity=".75" filter="url(#fBlur)"/>`);
  // the case wall (front half) and the bezel
  const a0 = Math.PI + (c.az * D2R), front = ring(G.R, G.plateH, a0, a0 + Math.PI).concat(ring(G.R, 0, a0, a0 + Math.PI).reverse());
  out.push(`<polygon points="${pts(front)}" fill="url(#gWall)"/>`);
  out.push(`<path fill-rule="evenodd" fill="url(#gBezel)" d="M${pts(ring(G.R, G.plateH))}Z M${pts(ring(G.faceR, G.plateH))}Z"/>`);
  out.push(`<polygon points="${pts(ring(G.faceR, G.faceY))}" fill="url(#gFace)"/>`);
  // enamel band, railway track, ticks, hour lines
  LEVELS.forEach(([, a, b], i) => {
    const g = 0.5, s0 = a === 0 ? a : a + g, s1 = b === 100 ? b : b - g;
    out.push(`<polygon points="${pts(fan(G.bandOut, s0, s1).concat(fan(G.bandIn, s1, s0)))}" fill="${ENAMEL[i]}"/>`);
  });
  const ink = '#1A2333';
  out.push(`<polyline points="${pts(fan(G.railOut, 0, 100, G.faceY, 120))}" fill="none" stroke="${ink}" stroke-width=".7"/>`);
  out.push(`<polyline points="${pts(fan(G.railIn, 0, 100, G.faceY, 120))}" fill="none" stroke="${ink}" stroke-width=".5"/>`);
  out.push(`<polygon points="${pts(ring(G.hubRing, G.faceY, 0, 2 * Math.PI, 64))}" fill="none" stroke="${ink}" stroke-width=".5"/>`);
  for (let v = 0; v <= 100; v++) {
    const big = v % 5 === 0, [x0, y0] = at(v, big ? 8.25 : G.railIn), [x1, y1] = at(v, G.railOut);
    out.push(`<line x1="${f(x0)}" y1="${f(y0)}" x2="${f(x1)}" y2="${f(y1)}" stroke="${ink}" stroke-width="${big ? 1.1 : .5}"/>`);
  }
  for (const v of FLOORS) { const [x0, y0] = at(v, G.hourIn), [x1, y1] = at(v, G.hourOut); out.push(`<line x1="${f(x0)}" y1="${f(y0)}" x2="${f(x1)}" y2="${f(y1)}" stroke="${ink}" stroke-width=".5" opacity=".7"/>`); }
  // the obelisk's shadow: the hull of its foot and its apex, cast along the sunlight (soft, like the live one)
  const len = (G.top - G.faceY) / Math.tan(sun.e), tip = [sun.dir[0] * Math.min(len, G.faceR), sun.dir[1] * Math.min(len, G.faceR)];
  const nx = -sun.dir[1], nz = sun.dir[0], wB = G.shaftW0 * 1.05;
  const shadow = [[nx * wB, nz * wB], [tip[0] + nx * 0.06, tip[1] + nz * 0.06], [tip[0] - nx * 0.06, tip[1] - nz * 0.06], [-nx * wB, -nz * wB]].map(([x, z]) => P(x, G.faceY, z));
  out.push(`<polygon points="${pts(shadow)}" fill="#0E1C33" opacity=".42" filter="url(#fSoft)"/>`);
  // applied indices at the level floors
  for (const v of FLOORS) {
    const [dx, dz] = dirOf(v), tx = -dz * 0.08, tz = dx * 0.08, y = G.faceY + 0.06;
    const q = [[dx * G.idxIn + tx, dz * G.idxIn + tz], [dx * G.idxOut + tx, dz * G.idxOut + tz], [dx * G.idxOut - tx, dz * G.idxOut - tz], [dx * G.idxIn - tx, dz * G.idxIn - tz]].map(([x, z]) => P(x, y, z));
    out.push(`<polygon points="${pts(q)}" fill="#F4F7FA" stroke="#5E6876" stroke-width=".6"/>`);
  }
  // numerals and level names, set on the dial in the page's figure face
  const fs = Math.max(9, c.rPx * 0.033);
  for (const v of FLOORS) { const [x, y] = at(v, G.num); out.push(`<text x="${f(x)}" y="${f(y)}" font-family="IBM Plex Mono, ui-monospace, monospace" font-size="${f(fs)}" font-weight="500" fill="${ink}" text-anchor="middle" dominant-baseline="central">${v}</text>`); }
  LEVELS.forEach(([name, a, b]) => { const [x, y] = at((a + b) / 2, G.name); out.push(`<text x="${f(x)}" y="${f(y)}" font-family="IBM Plex Mono, ui-monospace, monospace" font-size="${f(fs * 0.62)}" letter-spacing="${f(fs * 0.1)}" font-weight="500" fill="${ink}" text-anchor="middle" dominant-baseline="central">${name.toUpperCase()}</text>`); });
  // the obelisk: plinth, shaft and pyramidion; the face turned toward the sun is the lit one
  const yaw = (c.az + 45) * D2R, rot = (x, z) => [x * Math.cos(yaw) + z * Math.sin(yaw), -x * Math.sin(yaw) + z * Math.cos(yaw)];
  const sq = (hw, y) => [[hw, hw], [-hw, hw], [-hw, -hw], [hw, -hw]].map(([x, z]) => { const [a, b] = rot(x, z); return [a, y, b]; });
  const y0 = G.faceY, y1 = y0 + G.plinthH, y2 = y1 + G.shaftH, ap = [0, G.top, 0];
  const solid = (bot, top) => {
    const faces = [];
    for (let i = 0; i < 4; i++) { const j = (i + 1) % 4; faces.push(top ? [bot[i], bot[j], top[j], top[i]] : null); }
    return faces;
  };
  const toCam = V.norm(V.sub(cam.eye, [0, 2, 0]));
  const drawFaces = (bot, top, lit, dark) => {
    solid(bot, top).forEach(q => {
      const n = V.norm(V.cross(V.sub(q[1], q[0]), V.sub(q[3], q[0])));
      const nn = V.dot(n, [q[0][0], 0, q[0][2]]) < 0 ? n.map(x => -x) : n;
      if (V.dot(nn, toCam) <= 0) return;
      const left = V.dot(nn, cam.r) < 0;   // the face turned toward the key light reads lit, like the live render
      out.push(`<polygon points="${pts(q.map(v => P(...v)))}" fill="url(#${left ? lit : dark})" stroke="${left ? '#9EC2EF' : '#2A4A85'}" stroke-width=".5" stroke-linejoin="round"/>`);
    });
  };
  drawFaces(sq(G.plinthW, y0), sq(G.plinthW, y1), 'gSilverL', 'gSilverD');
  out.push(`<polygon points="${pts(sq(G.plinthW, y1).map(v => P(...v)))}" fill="#E3E8EE"/>`);
  drawFaces(sq(G.shaftW0, y1), sq(G.shaftW1, y2), 'gSteelL', 'gSteelD');
  const capTop = sq(G.shaftW1, y2);
  for (let i = 0; i < 4; i++) {
    const a = capTop[i], b = capTop[(i + 1) % 4], n = V.norm(V.cross(V.sub(b, a), V.sub(ap, a)));
    const nn = V.dot(n, [a[0] + b[0], 0, a[2] + b[2]]) < 0 ? n.map(x => -x) : n;
    if (V.dot(nn, toCam) <= 0) continue;
    out.push(`<polygon points="${pts([a, b, ap].map(v => P(...v)))}" fill="${V.dot(nn, cam.r) < 0 ? '#F2F5F8' : '#9AA6B6'}"/>`);
  }
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.innerHTML = out.join('');
}

function startSVG() {
  glBox.querySelector('canvas')?.remove();
  let svg = glBox.querySelector('svg');
  if (!svg) { svg = document.createElementNS(NS, 'svg'); svg.setAttribute('preserveAspectRatio', 'none'); glBox.appendChild(svg); }
  glBox.dataset.renderer = 'svg';
  motionBtn.hidden = true;
  const redraw = () => drawSVG(svg, STILL_PHASE);
  redraw();
  setReading(100 * STILL_PHASE, true);
  new ResizeObserver(redraw).observe(glBox);
  if (document.fonts) document.fonts.ready.then(redraw);
}

/* ---------- live renderer (WebGL via three.js) ---------- */
const lin = h => { const c = parseInt(h.slice(1), 16); return [(c >> 16) & 255, (c >> 8) & 255, c & 255].map(x => { x /= 255; return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }); };
const glsl3 = a => `vec3(${a.map(x => x.toFixed(5)).join(',')})`;
const f4 = x => x.toFixed(4);

// Shadows are computed in the shaders from the shapes that cast them; there is no shadow map. That keeps the
// penumbra smooth (no sampling noise to dither its edge) and lets each surface take only the shadows it should:
// the dial gets the obelisk, the indices and the bezel lip; the floor gets the case alone, so no sliver of the
// obelisk's shadow escapes onto the backdrop.
const SOFT = 0.0175;   // penumbra growth per unit of distance from the caster: a sun about 2° across
// The obelisk as a distance field, in its own frame (y up from the dial face), a hair inside the mesh so its
// own surfaces never shade themselves.
const OB = {
  pw: G.plinthW - 0.02, ph: G.plinthH - 0.01, pr: 0.07,
  y1: G.plinthH, y2: G.plinthH + G.shaftH, y3: G.top - G.faceY,
  w0: G.shaftW0 - 0.015, w1: G.shaftW1 - 0.012
};
OB.bound = OB.pw * Math.SQRT2 + 0.4;   // rays that miss this cylinder pass well clear of the obelisk

const SHADOW_GLSL = /* glsl */`
uniform vec3 gnSunDir;
uniform float gnYaw, gnShadowOn;
varying vec3 vGnWorld;
varying vec3 vGnNormal;
float gnSdBox(vec3 p, vec3 b, float r) { vec3 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0) - r; }
// A square section whose half-width runs from w0 at y0 to w1 at y1; k keeps the estimate safe on a steep taper.
float gnSdTaper(vec3 p, float y0, float y1, float w0, float w1, float k) {
  float w = mix(w0, w1, clamp((p.y - y0) / (y1 - y0), 0.0, 1.0));
  vec2 s = abs(p.xz) - w;
  vec2 d = vec2(length(max(s, 0.0)) + min(max(s.x, s.y), 0.0), max(y0 - p.y, p.y - y1));
  return k * (length(max(d, 0.0)) + min(max(d.x, d.y), 0.0));
}
float gnSdObelisk(vec3 p) {
  float d = gnSdBox(p - vec3(0.0, ${f4(OB.ph / 2)}, 0.0), vec3(${f4(OB.pw)}, ${f4(OB.ph / 2)}, ${f4(OB.pw)}), ${f4(OB.pr)});
  d = min(d, gnSdTaper(p, ${f4(OB.y1)}, ${f4(OB.y2)}, ${f4(OB.w0)}, ${f4(OB.w1)}, 1.0));
  return min(d, gnSdTaper(p, ${f4(OB.y2)}, ${f4(OB.y3)}, ${f4(OB.w1)}, 0.0, 0.88));
}
// Soft shadow traced through the distance field: sharp where the obelisk meets the dial, wider toward the tip,
// with the penumbra centred on the hard edge. px, one pixel's size on the surface, keeps a hard edge from aliasing.
float gnObeliskShadow(vec3 wp, vec3 wn, float px) {
  float cy = cos(gnYaw), sy = sin(gnYaw);
  vec3 ro = wp + wn * 0.03; ro.y -= ${f4(G.faceY)};
  ro.xz = vec2(ro.x * cy - ro.z * sy, ro.x * sy + ro.z * cy);
  vec3 rd = vec3(gnSunDir.x * cy - gnSunDir.z * sy, gnSunDir.y, gnSunDir.x * sy + gnSunDir.z * cy);
  float a = dot(rd.xz, rd.xz), b = dot(ro.xz, rd.xz), c = dot(ro.xz, ro.xz) - ${f4(OB.bound * OB.bound)};
  float disc = b * b - a * c;
  if (disc <= 0.0) return 1.0;
  disc = sqrt(disc);
  float t = max((-b - disc) / a, 0.02);
  float t1 = min((-b + disc) / a, (${f4(OB.y3 + 0.4)} - ro.y) / max(rd.y, 0.02));
  if (t1 <= t) return 1.0;
  float res = 1.0;
  for (int i = 0; i < 64; i++) {
    float h = gnSdObelisk(ro + rd * t);
    res = min(res, h / (${f4(SOFT)} * t + px));
    if (res < -1.0 || t > t1) break;
    t += clamp(h, 0.01, 0.3);
  }
  res = max(res, -1.0);
  return 0.25 * (1.0 + res) * (1.0 + res) * (2.0 - res);
}
`;

// The dial face: porcelain enamel, printed ink, an inlaid enamel band (all drawn from distance fields,
// so they stay sharp at any size), the printed lettering from a texture, contact shading, and the shadows
// of the applied indices and of the bezel's lip.
const IDX = { r: (G.idxIn + G.idxOut) / 2, w: 0.17, h: 0.1, l: G.idxOut - G.idxIn, round: 0.04 };
const LIP = { r: 9.45, h: G.plateH - 0.02 - G.faceY };   // the bezel's inner edge, and its height above the dial
const FACE_GLSL_DECL = /* glsl */`
#define FAN_SIGN (${FAN.toFixed(1)})
uniform sampler2D gnInk;
float gnLine(float d, float hw) { float fw = max(fwidth(d), 1e-5); float w = max(hw, 0.6 * fw); return clamp(0.5 + (w - d) / fw, 0.0, 1.0) * (hw / w); }
float gnRad(float r, float r0, float r1) { float fw = max(fwidth(r), 1e-5); return clamp((r - r0) / fw + 0.5, 0.0, 1.0) * clamp((r1 - r) / fw + 0.5, 0.0, 1.0); }
// The applied index nearest this point (they sit at the level floors) and its short shadow.
float gnIndexShadow(vec3 wp, float px) {
  vec2 gp = vec2(wp.x, -FAN_SIGN * wp.z);
  float th = atan(gp.y, gp.x); if (th < -0.5 * PI) th += 2.0 * PI;
  float v = 100.0 * (1.0 - th / PI);
  float fl = v < 12.5 ? 0.0 : v < 35.0 ? 25.0 : v < 52.5 ? 45.0 : v < 67.5 ? 60.0 : v < 81.5 ? 75.0 : v < 94.0 ? 88.0 : 100.0;
  float an = PI * (1.0 - fl / 100.0);
  vec2 dir = vec2(cos(an), -FAN_SIGN * sin(an));
  vec3 q = wp - vec3(dir.x * ${f4(IDX.r)}, ${f4(G.faceY + IDX.h / 2)}, dir.y * ${f4(IDX.r)});
  vec3 ro = vec3(q.x * dir.y - q.z * dir.x, q.y + 0.03, q.x * dir.x + q.z * dir.y);
  if (abs(ro.x) > 0.75 || abs(ro.z) > 1.3) return 1.0;
  vec3 rd = vec3(gnSunDir.x * dir.y - gnSunDir.z * dir.x, gnSunDir.y, gnSunDir.x * dir.x + gnSunDir.z * dir.y);
  float res = 1.0, t = 0.004;
  for (int i = 0; i < 24; i++) {
    vec3 p = ro + rd * t;
    float h = gnSdBox(p, vec3(${f4(IDX.w / 2)}, ${f4(IDX.h / 2)}, ${f4(IDX.l / 2)}), ${f4(IDX.round)});
    res = min(res, h / (${f4(SOFT)} * t + px));
    if (res < -1.0 || p.y > ${f4(IDX.h / 2 + 0.03)}) break;
    t += clamp(h, 0.004, 0.08);
  }
  res = max(res, -1.0);
  return 0.25 * (1.0 + res) * (1.0 + res) * (2.0 - res);
}
// With a low sun the bezel's lip shades a thin crescent of the dial on the sun's side.
float gnLipShadow(vec3 wp, float px) {
  float hl = max(length(gnSunDir.xz), 1e-4);
  float reach = ${f4(LIP.h)} * hl / max(gnSunDir.y, 0.02);
  float d = ${f4(LIP.r)} - length(wp.xz + gnSunDir.xz / hl * reach);
  float w = ${f4(SOFT)} * reach + px;
  return smoothstep(-w, w, d);
}
`;
const FACE_GLSL_MAP = /* glsl */`
vec2 gp = vec2(vGnWorld.x, -FAN_SIGN * vGnWorld.z);
float gr = length(gp);
float gth = atan(gp.y, gp.x); if (gth < -0.5 * PI) gth += 2.0 * PI;
float gv = 100.0 * (1.0 - gth / PI);
float perV = PI / 100.0 * gr;
float fwv = max(fwidth(gv), 1e-4);
float inArc = clamp((gv + 0.35) / fwv, 0.0, 1.0) * clamp((100.35 - gv) / fwv, 0.0, 1.0);
float inScale = clamp(gv / fwv + 0.5, 0.0, 1.0) * clamp((100.0 - gv) / fwv + 0.5, 0.0, 1.0);
float dUnit = abs(gv - clamp(floor(gv + 0.5), 0.0, 100.0)) * perV;
float d5 = abs(gv - clamp(5.0 * floor(gv / 5.0 + 0.5), 0.0, 100.0)) * perV;
float dCut = min(min(min(abs(gv - 25.0), abs(gv - 45.0)), min(abs(gv - 60.0), abs(gv - 75.0))), abs(gv - 88.0));
float dFloor = min(dCut, min(abs(gv), abs(gv - 100.0))) * perV;
dCut *= perV;
float ink = 0.0;
ink = max(ink, gnLine(dUnit, 0.0105) * gnRad(gr, ${G.railIn.toFixed(3)}, ${G.railOut.toFixed(3)}));
ink = max(ink, gnLine(d5, 0.021) * gnRad(gr, 8.2, ${G.railOut.toFixed(3)}));
ink = max(ink, gnLine(abs(gr - ${G.railOut.toFixed(3)}), 0.013) * inArc);
ink = max(ink, gnLine(abs(gr - ${G.railIn.toFixed(3)}), 0.008) * inArc);
ink = max(ink, 0.8 * gnLine(dFloor, 0.0095) * gnRad(gr, ${G.hourIn.toFixed(3)}, ${G.hourOut.toFixed(3)}));
ink = max(ink, gnLine(abs(gr - ${G.hubRing.toFixed(3)}), 0.009));
vec2 tuv = vec2(vGnWorld.x, -vGnWorld.z) / ${(2 * G.faceR).toFixed(3)} + 0.5;
ink = max(ink, texture2D(gnInk, tuv).r);
float band = gnRad(gr, ${G.bandIn.toFixed(3)}, ${G.bandOut.toFixed(3)}) * inScale * (1.0 - gnLine(dCut, 0.05));
vec3 bc = gv < 25.0 ? ${glsl3(lin(ENAMEL[0]))} : gv < 45.0 ? ${glsl3(lin(ENAMEL[1]))} : gv < 60.0 ? ${glsl3(lin(ENAMEL[2]))} : gv < 75.0 ? ${glsl3(lin(ENAMEL[3]))} : gv < 88.0 ? ${glsl3(lin(ENAMEL[4]))} : ${glsl3(lin(ENAMEL[5]))};
diffuseColor.rgb = mix(diffuseColor.rgb, bc, band);
diffuseColor.rgb = mix(diffuseColor.rgb, ${glsl3(lin('#161E2C'))}, ink);
roughnessFactor = mix(roughnessFactor, 0.62, band);
roughnessFactor = mix(roughnessFactor, 0.9, ink);
// contact shading: under the plinth and along the bezel wall
float cy = cos(gnYaw), sy = sin(gnYaw);
vec2 lq = vec2(vGnWorld.x * cy - vGnWorld.z * sy, vGnWorld.x * sy + vGnWorld.z * cy);
vec2 bq = abs(lq) - vec2(${G.plinthW.toFixed(3)});
float dPl = length(max(bq, 0.0)) + min(max(bq.x, bq.y), 0.0);
float gnAO = 1.0 - 0.62 * exp(-max(dPl, 0.0) * 3.2);
gnAO *= 1.0 - 0.38 * exp(-max(${G.faceR.toFixed(3)} - gr, 0.0) * 6.0);
// a lamp, not an overcast sky: the light pools on the dial and falls off toward the rim
float gnFall = 0.8 + 0.2 * exp(-pow(gr / 8.0, 2.0));
`;

// The floor is the backdrop. It takes the case's own shadow (the footprint swept away from the sun, softer
// toward its far end) and nothing from the obelisk.
const FLOOR_FRAG = /* glsl */`
uniform vec3 gnSunDir, gnBg, gnPool;
uniform float gnShadowOn, gnSunI;
varying vec3 vGnWorld;
float gnCaseShadow(vec2 p, float px) {
  float hl = max(length(gnSunDir.xz), 1e-4), sl = max(gnSunDir.y, 0.02);
  vec2 away = -gnSunDir.xz / hl;
  float len = ${f4(G.plateH)} * hl / sl;
  float a = clamp(dot(p, away), 0.0, len);
  vec2 q = p - away * a;
  float lq = max(length(q), 1e-4);
  // the same sun as on the dial: the penumbra grows with the distance to the case's rim, and the far end,
  // which the light meets at a grazing angle, is stretched along the floor by 1 / sin(elevation)
  float w = px + ${f4(SOFT)} * a / hl * (1.0 + abs(dot(q / lq, away)) * (1.0 / sl - 1.0));
  return smoothstep(-w, w, lq - ${f4(G.R)});
}
void main(){
  vec2 p = vGnWorld.xz; float rp = length(p);
  float px = length(fwidth(vGnWorld));
  float pool = exp(-pow(rp / 22.0, 2.0));
  float sh = mix(1.0, gnCaseShadow(p, px), gnShadowOn);
  float ao = 1.0 - 0.82 * exp(-max(rp - ${G.R.toFixed(2)}, 0.0) * 1.05);
  vec3 col = mix(gnBg, gnPool * (0.45 + 0.55 * mix(1.0, sh, gnSunI) * (0.4 + 0.6 * gnSunI)), pool) * ao;
  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}`;

function injectMaterial(THREE, mat, key, SHU, extra = {}) {
  const lightsPatched = THREE.ShaderChunk.lights_fragment_begin.replace(
    'getDirectionalLightInfo( directionalLight, directLight );',
    'getDirectionalLightInfo( directionalLight, directLight );\n\t\tdirectLight.color *= gnSh;');
  if (lightsPatched === THREE.ShaderChunk.lights_fragment_begin) throw new Error('three.js light chunk changed; cannot attach the dial shadow');
  const shade = extra.face
    ? 'float gnSh = gnFall * mix(1.0, gnObeliskShadow(vGnWorld, normalize(vGnNormal), gnPx) * gnIndexShadow(vGnWorld, gnPx) * gnLipShadow(vGnWorld, gnPx), gnShadowOn);\n'
    : 'float gnSh = mix(1.0, gnObeliskShadow(vGnWorld, normalize(vGnNormal), gnPx), gnShadowOn);\n';
  mat.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, SHU, extra.uniforms || {});
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vGnWorld;\nvarying vec3 vGnNormal;')
      .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\nvGnWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;\nvGnNormal = normalize(mat3(modelMatrix) * objectNormal);');
    let fs = sh.fragmentShader.replace('#include <common>', '#include <common>\n' + SHADOW_GLSL + (extra.decl || ''));
    if (extra.map) fs = fs.replace('#include <roughnessmap_fragment>', '#include <roughnessmap_fragment>\n' + extra.map);
    fs = fs.replace('#include <lights_fragment_begin>', 'float gnPx = length(fwidth(vGnWorld));\n' + shade + lightsPatched);
    if (extra.ao) fs = fs.replace('#include <aomap_fragment>', '#include <aomap_fragment>\n' + extra.ao);
    sh.fragmentShader = fs;
  };
  mat.customProgramCacheKey = () => 'gn-' + key;
  return mat;
}

// A product studio for reflections: a deep blue cyclorama, two strip lights and an overhead softbox.
function studioEnvironment(THREE, renderer) {
  const env = new THREE.Scene();
  env.add(new THREE.Mesh(new THREE.SphereGeometry(60, 48, 24), new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false,
    vertexShader: 'varying vec3 vD; void main(){ vD = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader: `varying vec3 vD; void main(){ float y = vD.y;
      vec3 low = vec3(0.004, 0.007, 0.014), hor = vec3(0.034, 0.056, 0.105), sky = vec3(0.010, 0.017, 0.034);
      vec3 c = y < 0.0 ? mix(hor, low, smoothstep(0.0, -0.45, y)) : mix(hor, sky, smoothstep(0.0, 0.75, y));
      // the lit dial seen in reflection: bright toward the key side, a black flag on the right,
      // fading with depth so vertical steel faces carry a studio-sweep gradient
      vec2 hz = normalize(vD.xz + 1e-5);
      float below = smoothstep(-0.03, -0.2, y), sweep = smoothstep(-0.63, -0.44, y);
      float pool = pow(max(dot(hz, normalize(vec2(-0.75, 0.66))), 0.0), 2.2) * below * sweep;
      c += vec3(0.62, 0.60, 0.57) * pool;
      float pool2 = pow(max(dot(hz, normalize(vec2(0.86, -0.5))), 0.0), 2.0) * below * sweep;
      c += vec3(0.05, 0.085, 0.16) * pool2;
      float ridge = pow(max(dot(hz, normalize(vec2(0.41, 0.91))), 0.0), 60.0) * below * sweep;
      c += vec3(1.5, 1.5, 1.45) * ridge;
      gl_FragColor = vec4(c, 1.0); }`
  })));
  const panel = (w, h, p, k, hex) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(hex).multiplyScalar(k), side: THREE.DoubleSide }));
    m.position.set(...p); m.lookAt(0, 1, 0); env.add(m);
  };
  panel(24, 13, [-7, 27, 9], 2.4, '#FFFFFF');    // overhead softbox, front-left
  panel(3.5, 24, [-28, 7, 7], 3.2, '#FFF3E8');   // tall strip, left
  panel(3.5, 24, [27, 9, -7.2], 2.1, '#D9E6FF');  // rim strip, right and behind: the cap's right facet
  panel(14, 3, [-22, 2.2, 14], 2.2, '#FFF3E6');    // low strip, front left: the cap's left facet
  panel(44, 4.5, [8, 1.2, 30], 0.45, '#7896C4'); // low bounce card in front
  panel(50, 16, [-6, 22, -32], 0.85, '#DFE6EF'); // a wide diffuser behind the dial, at the bezel's reflection angle
  const pm = new THREE.PMREMGenerator(renderer);
  const tex = pm.fromScene(env, 0.03).texture;
  pm.dispose();
  return tex;
}

// The obelisk: a chamfered plinth, a tapered square shaft with bevelled corners, a pyramidion. Flat-shaded facets.
function obeliskGeometry(THREE) {
  const pos = [];
  const oct = (hw, ch, y) => { const a = hw - ch; return [[hw, -a], [hw, a], [a, hw], [-a, hw], [-hw, a], [-hw, -a], [-a, -hw], [a, -hw]].map(([x, z]) => [x, y, z]); };
  const tri = (a, b, c, up = false) => {
    const n = V.cross(V.sub(b, a), V.sub(c, a));
    const ref = up ? [0, 1, 0] : [(a[0] + b[0] + c[0]) / 3, 0, (a[2] + b[2] + c[2]) / 3];
    if (V.dot(n, ref) < 0) pos.push(...a, ...c, ...b); else pos.push(...a, ...b, ...c);
  };
  const band = (r0, r1) => { for (let i = 0; i < 8; i++) { const j = (i + 1) % 8; tri(r0[i], r0[j], r1[j]); tri(r0[i], r1[j], r1[i]); } };
  const y1 = G.plinthH, y2 = y1 + G.shaftH, y3 = y2 + G.pyrH;
  const done = () => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos.splice(0), 3)); g.computeVertexNormals(); return g; };
  const pb = oct(G.plinthW, 0.08, 0), pm = oct(G.plinthW, 0.08, y1 - 0.075), pt = oct(G.plinthW - 0.075, 0.06, y1);
  band(pb, pm); band(pm, pt);
  for (let i = 0; i < 8; i++) tri([0, y1, 0], pt[i], pt[(i + 1) % 8], true);
  const plinth = done();
  const s0 = oct(G.shaftW0, 0.05, y1), s1 = oct(G.shaftW1, 0.034, y2);
  band(s0, s1);
  const shaft = done();
  for (let i = 0; i < 8; i++) tri(s1[i], s1[(i + 1) % 8], [0, y3, 0]);
  return { plinth, shaft, cap: done() };
}

// Printed lettering for the dial, drawn once into a mask: numerals, level names and the maker's mark.
async function inkTexture(THREE, renderer, size) {
  try {
    await Promise.race([Promise.all([document.fonts.load('500 60px "IBM Plex Mono"'), document.fonts.load('600 60px "Archivo"')]), new Promise(r => setTimeout(r, 1800))]);
  } catch (e) { /* system fonts stand in */ }
  const cv = document.createElement('canvas'); cv.width = cv.height = size;
  const g = cv.getContext('2d');
  const s = size / (2 * G.faceR);
  const mono = '"IBM Plex Mono", ui-monospace, Menlo, monospace', sans = 'Archivo, "Helvetica Neue", Arial, sans-serif';
  const track = px => { if ('letterSpacing' in g) g.letterSpacing = px + 'px'; };
  g.fillStyle = '#000'; g.fillRect(0, 0, size, size);
  g.translate(size / 2, size / 2); g.fillStyle = '#fff'; g.textAlign = 'center'; g.textBaseline = 'middle';
  const put = (text, v, r, px, weight, tr) => {
    const [dx, dz] = dirOf(v);
    g.save(); g.translate(dx * r * s, dz * r * s); g.rotate(Math.atan2(dz, dx) + FAN * Math.PI / 2);
    g.font = `${weight} ${px}px ${mono}`; track(tr); g.fillText(text, 0, 0); g.restore();
  };
  for (const v of FLOORS) put(String(v), v, G.num, 0.5 * s, 500, 0);
  LEVELS.forEach(([n, a, b]) => put(n.toUpperCase(), (a + b) / 2, G.name, 0.27 * s, 500, 0.27 * s * 0.16));
  g.save(); g.translate(FAN < 0 ? 2.7 * s : 0, FAN * 4.75 * s + (FAN < 0 ? 0.6 * s : 0)); g.textBaseline = 'alphabetic';
  if ('fontStretch' in g) g.fontStretch = 'semi-expanded';
  g.font = `600 ${0.62 * s}px ${sans}`; track(-0.03 * 0.62 * s); g.fillText('gnomon', 0, 0);
  if ('fontStretch' in g) g.fontStretch = 'normal';
  g.font = `500 ${0.15 * s}px ${mono}`; track(0.15 * s * 0.24); g.fillText('AGENTIC QUOTIENT · BY XMARTLABS', 0, 0.42 * s);
  g.restore();
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.NoColorSpace;
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return tex;
}

async function startGL() {
  const THREE = await import('three');
  const [{ RoundedBoxGeometry }, { mergeGeometries }] = await Promise.all([
    import('three/addons/geometries/RoundedBoxGeometry.js'), import('three/addons/utils/BufferGeometryUtils.js')]);

  const canvas = document.createElement('canvas');
  glBox.appendChild(canvas);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
  let shaderFailed = false;
  renderer.debug.onShaderError = () => { shaderFailed = true; };
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NeutralToneMapping;      // a product-shot curve: keeps the brand blue true
  renderer.toneMappingExposure = 1.0;
  renderer.setClearColor('#08121F', 1);
  glBox.dataset.renderer = 'webgl';
  // A lost context (GPU reset, eviction) hands over to the SVG dial for good: `lost` keeps the
  // resize, intersection and visibility triggers from restarting a render loop on a dead context.
  let lost = false;
  canvas.addEventListener('webglcontextlost', e => {
    e.preventDefault(); lost = true; stop(); motionBtn.hidden = true; canvas.remove(); startSVG();
  });

  const scene = new THREE.Scene();
  scene.environment = studioEnvironment(THREE, renderer);

  /* uniforms every surface shares: where the sun is, how the obelisk is turned, how strong the shadows are */
  const SHU = { gnSunDir: { value: new THREE.Vector3(0, 1, 0) }, gnYaw: { value: 0 }, gnShadowOn: { value: 1 } };

  /* materials */
  const inkTex = await inkTexture(THREE, renderer, innerWidth < 700 ? 1536 : 2048);
  const faceU = { gnInk: { value: inkTex } };
  const M = {
    polished: injectMaterial(THREE, new THREE.MeshPhysicalMaterial({ color: '#DDE2E8', metalness: 1, roughness: 0.15 }), 'polished', SHU),
    brushed: injectMaterial(THREE, new THREE.MeshPhysicalMaterial({ color: '#C2C9D1', metalness: 1, roughness: 0.42 }), 'brushed', SHU),
    blued: injectMaterial(THREE, new THREE.MeshPhysicalMaterial({ color: '#3B6FCB', metalness: 1, roughness: 0.15, envMapIntensity: 1.5 }), 'blued', SHU),
    enamel: injectMaterial(THREE, new THREE.MeshPhysicalMaterial({ color: '#EEF1F4', roughness: 0.74, envMapIntensity: 0.6 }), 'enamel', SHU,
      { uniforms: faceU, decl: FACE_GLSL_DECL, map: FACE_GLSL_MAP, face: true, ao: 'reflectedLight.indirectDiffuse *= gnAO; reflectedLight.indirectSpecular *= mix(1.0, gnAO, 0.6);' })
  };
  const floorMat = new THREE.ShaderMaterial({
    uniforms: { ...SHU, gnBg: { value: new THREE.Vector3(...lin('#08121F')) }, gnPool: { value: new THREE.Vector3(...lin('#1C3558')) }, gnSunI: { value: 1 } },
    vertexShader: 'varying vec3 vGnWorld; void main(){ vec4 wp = modelMatrix * vec4(position, 1.0); vGnWorld = wp.xyz; gl_Position = projectionMatrix * viewMatrix * wp; }',
    fragmentShader: FLOOR_FRAG,
    toneMapped: false
  });

  /* geometry */
  const lathe = (r0, y0, r1, y1) => new THREE.LatheGeometry([new THREE.Vector2(r0, y0), new THREE.Vector2(r1, y1)], 320);
  const wall = new THREE.Mesh(mergeGeometries([lathe(9.9, 0, G.R, 0.1), lathe(G.R, 0.1, G.R, 0.96)]), M.brushed);
  const bezel = new THREE.Mesh(mergeGeometries([
    lathe(G.R, 0.96, 9.88, G.plateH), lathe(9.88, G.plateH, 9.45, G.plateH - 0.02), lathe(9.45, G.plateH - 0.02, G.faceR, G.faceY)]), M.polished);
  const face = new THREE.Mesh(new THREE.CircleGeometry(G.faceR, 320), M.enamel);
  face.rotation.x = -Math.PI / 2; face.position.y = G.faceY;
  const floor = new THREE.Mesh(new THREE.CircleGeometry(420, 96), floorMat);
  floor.rotation.x = -Math.PI / 2;
  const og = obeliskGeometry(THREE);
  const gnomon = new THREE.Group();
  gnomon.add(new THREE.Mesh(og.plinth, M.polished), new THREE.Mesh(og.shaft, M.blued), new THREE.Mesh(og.cap, M.polished));
  gnomon.position.y = G.faceY;
  scene.add(wall, bezel, face, floor, gnomon);
  const idxGeo = new RoundedBoxGeometry(IDX.w, IDX.h, IDX.l, 2, IDX.round);
  for (const v of FLOORS) {
    const [dx, dz] = dirOf(v);
    const m = new THREE.Mesh(idxGeo, M.polished);
    m.position.set(dx * IDX.r, G.faceY + IDX.h / 2, dz * IDX.r); m.rotation.y = Math.atan2(dx, dz);
    scene.add(m);
  }

  /* the sun */
  const sun = new THREE.DirectionalLight(0xffffff, 3);
  scene.add(sun, sun.target);
  const warm = new THREE.Color('#FFD2A4'), noon = new THREE.Color('#FFF5EC');
  function placeSun(phi, k, eScale = 1) {
    const s = sunAt(phi);
    if (eScale !== 1) { s.e *= eScale; s.L = [-s.dir[0] * Math.cos(s.e), Math.sin(s.e), -s.dir[1] * Math.cos(s.e)]; }
    const [lx, ly, lz] = s.L, t = smooth(6 * D2R, 34 * D2R, s.e);
    sun.position.set(lx * 40, ly * 40, lz * 40);
    sun.color.copy(warm).lerp(noon, t);
    sun.intensity = k * mix(13.5, 8.6, t);
    SHU.gnSunDir.value.set(lx, ly, lz);
    SHU.gnShadowOn.value = clamp(k * 1.25);
    floorMat.uniforms.gnSunI.value = k;
    return s;
  }

  /* camera and layout */
  const cam = new THREE.PerspectiveCamera(20, 1, 1, 900);
  let comp = null, W = 0, H = 0, dpr = Math.min(window.devicePixelRatio || 1, 2);
  function resize() {
    W = glBox.clientWidth; H = glBox.clientHeight;
    if (!W || !H) return;
    renderer.setPixelRatio(dpr); renderer.setSize(W, H, false);
    comp = compose(W, H);
    const yaw = (comp.az + 45) * D2R;
    gnomon.rotation.y = yaw; SHU.gnYaw.value = yaw;
  }
  function placeCamera(dAz, dEl, dDist) {
    const k = cameraFor(comp, dAz, dEl, dDist);
    cam.fov = comp.fov; cam.aspect = W / H;
    cam.position.set(...k.eye); cam.lookAt(...k.tgt);
    cam.setViewOffset(W, H, -k.shiftX, -k.shiftY, W, H);
    cam.updateProjectionMatrix();
  }
  function render() { renderer.render(scene, cam); }

  /* time: a sunrise intro, then the endless day-and-night cycle described at sunAt() */
  const INTRO = 3.2, P0 = 0.36;
  function frame(t, still) {
    if (!comp) return;
    if (still) {
      placeSun(STILL_PHASE, 1); placeCamera(0, 0, 1); render();
      setReading(100 * STILL_PHASE, true);
      return;
    }
    let phi, k = 1, rise = 1;
    if (t < INTRO) { rise = easeOut(t / INTRO); phi = P0; k = smooth(0, 0.85, rise); }
    else phi = phaseAt(t - INTRO + P0 * DAY);
    placeSun(phi, k, mix(0.25, 1, rise));
    const intro = 1 - easeInOut(t / 3.8);
    ptr.x += (ptr.tx - ptr.x) * 0.045; ptr.y += (ptr.ty - ptr.y) * 0.045;
    const dAz = 1.1 * Math.sin(t * 2 * Math.PI / 27) - 2.4 * ptr.x;
    const dEl = 0.5 * Math.sin(t * 2 * Math.PI / 35 + 1) + 1.2 * ptr.y + 3.2 * intro;
    placeCamera(dAz, dEl, 1 + 0.075 * intro);
    render();
    setReading(100 * phi, k > 0.6 && phi <= 1);
  }

  const ptr = { x: 0, y: 0, tx: 0, ty: 0 };
  hero.addEventListener('pointermove', e => {
    if (e.pointerType !== 'mouse') return;
    const r = hero.getBoundingClientRect();
    ptr.tx = clamp((e.clientX - r.left) / r.width * 2 - 1, -1, 1); ptr.ty = clamp((e.clientY - r.top) / r.height * 2 - 1, -1, 1);
  });
  hero.addEventListener('pointerleave', () => { ptr.tx = 0; ptr.ty = 0; });

  let clock = 0, last = 0, raf = 0, running = false, paused = false, onScreen = true, ema = 16.7, slow = 0, first = true;
  const still = () => reduceMQ.matches;
  const loop = now => {
    raf = requestAnimationFrame(loop);
    const dt = last ? Math.min(100, now - last) : 16.7;
    last = now; clock += dt / 1000;
    ema = ema * 0.94 + dt * 0.06;
    // a GPU that can't keep up gets fewer pixels rather than a stutter
    if (clock > 4 && dpr > 1 && ema > 21) { if (++slow > 45) { dpr = Math.max(1, dpr - 0.25); slow = 0; resize(); } } else slow = 0;
    frame(clock, false);
    if (first) { first = false; goLive(); }
  };
  const start = () => { if (lost || still() || running || paused || !onScreen || document.hidden) return; running = true; last = 0; raf = requestAnimationFrame(loop); };
  function stop() { running = false; cancelAnimationFrame(raf); }

  // Hand over from the static stand-in, if one was shown: fade it out as the render fades in.
  function goLive() {
    glBox.classList.add('is-live');
    const ph = glBox.querySelector('svg.is-placeholder');
    if (ph) { ph.classList.add('is-leaving'); setTimeout(() => ph.remove(), 1500); }
  }
  if (glBox.querySelector('svg.is-placeholder')) clock = INTRO;   // the stand-in already showed daylight: skip the sunrise

  resize();
  // Compile now: a GPU that rejects the dial's shaders gets the static frame, not a blank hero.
  if (comp) { placeSun(STILL_PHASE, 1); placeCamera(0, 0, 1); render(); }
  if (shaderFailed) { renderer.dispose(); canvas.remove(); throw new Error('the dial shaders did not compile'); }
  new ResizeObserver(() => { if (lost) return; resize(); if (!running) frame(clock, still()); }).observe(glBox);
  if (still()) { frame(0, true); goLive(); }
  else {
    motionBtn.hidden = false;
    motionBtn.addEventListener('click', () => {
      paused = !paused;
      motionBtn.textContent = paused ? 'Resume motion' : 'Pause motion';
      paused ? stop() : start();
    });
    new IntersectionObserver(([en]) => { onScreen = en.isIntersecting; onScreen ? start() : stop(); }).observe(hero);
    document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));
    start();
  }
  reduceMQ.addEventListener('change', e => { if (e.matches && !lost) { stop(); motionBtn.hidden = true; frame(0, true); } });
}

/* ---------- boot ---------- */
function hasWebGL() {
  try {
    const cv = document.createElement('canvas'), gl = cv.getContext('webgl2');
    gl?.getExtension('WEBGL_lose_context')?.loseContext();
    return !!gl;
  } catch (e) { return false; }
}
// On a slow network the static dial stands in until the live one is ready, then hands over.
function showPlaceholder() {
  if (glBox.classList.contains('is-live') || glBox.querySelector('svg')) return;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('preserveAspectRatio', 'none'); svg.classList.add('is-placeholder');
  glBox.appendChild(svg);
  drawSVG(svg, STILL_PHASE);
}
if (!hasWebGL()) startSVG();
else {
  const slowNet = setTimeout(showPlaceholder, 1500);
  startGL().then(() => clearTimeout(slowNet)).catch(err => {
    clearTimeout(slowNet);
    console.warn('gnomon dial: falling back to the static frame', err);
    glBox.querySelector('svg.is-placeholder')?.remove();
    startSVG();
  });
}
