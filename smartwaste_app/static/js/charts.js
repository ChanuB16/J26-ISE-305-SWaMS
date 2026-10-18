// Small SVG charts with hover tooltips (no chart library needed).
// Rules: thin marks, one y-axis, legend when there are 2+ series, text in ink colours.
import { esc, showTip, hideTip, num, hhmm, pad } from "./ui.js";

const INK = "#0b0b0b", INK2 = "#52514e", MUTED = "#898781", GRID = "#e1e0d9", BASE = "#c3c2b7";
const NS = "http://www.w3.org/2000/svg";

function niceStep(span, count) {
  const raw = span / Math.max(1, count);
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const m = raw / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
}
function ticks(lo, hi, count = 5, step = null) {
  if (hi === lo) hi = lo + 1;
  const s = step || niceStep(hi - lo, count);
  const out = [];
  for (let v = Math.ceil(lo / s) * s; v <= hi + s * 1e-9; v += s) out.push(Number(v.toFixed(10)));
  return out;
}
function timeTicks(t0, t1, width) {
  const span = t1 - t0, H = 3600000, D = 86400000;
  const want = Math.max(2, Math.floor(width / 90));
  const steps = [H, 2 * H, 3 * H, 6 * H, 12 * H, D, 2 * D, 7 * D];
  const step = steps.find((s) => span / s <= want) || 14 * D;
  const out = [];
  const first = new Date(t0);
  if (step >= D) first.setHours(0, 0, 0, 0);
  else first.setMinutes(0, 0, 0);
  for (let t = first.getTime(); t <= t1; t += step) if (t >= t0) out.push(t);
  const fmt = (t) => {
    const d = new Date(t);
    if (step >= 7 * D) return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
    if (step >= D) return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric" });
    if (d.getHours() === 0) return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
    return pad(d.getHours()) + ":00";
  };
  return out.map((t) => ({ t, label: fmt(t) }));
}
function el(tag, attrs = {}, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}
function legendHTML(series) {
  return `<div class="legend" style="margin-bottom:6px">${series.map((s) =>
    `<span><span class="swatch" style="background:${s.color}${s.dash ? ";height:2px;width:14px;border-radius:0" : ""}"></span>${esc(s.name)}</span>`).join("")}</div>`;
}
function onResize(container, draw) {
  let w = container.clientWidth;
  if (container._ro) container._ro.disconnect();
  const ro = new ResizeObserver(() => {
    if (Math.abs(container.clientWidth - w) > 4) { w = container.clientWidth; draw(); }
  });
  ro.observe(container);
  container._ro = ro;
}

// ---------------------------------------------------------------------------
// Line chart: x = time (ms) or numbers. series: [{name, color, points: [[x, y], ...], dash}]
// ---------------------------------------------------------------------------
export function lineChart(container, o) {
  const draw = () => {
    const series = (o.series || []).map((s) => ({ ...s, points: (s.points || []).filter((p) => p[1] != null && !isNaN(p[1])) }))
      .filter((s) => s.points.length);
    container.innerHTML = "";
    if (!series.length) {
      container.innerHTML = `<div class="empty"><b>${esc(o.emptyTitle || "No data for this time")}</b>${esc(o.emptyText || "")}</div>`;
      return;
    }
    const legend = series.length > 1 || o.legend ? legendHTML(series) : "";
    container.insertAdjacentHTML("beforeend", legend);
    const W = Math.max(280, container.clientWidth || 600), H = o.height || 220;
    const m = { l: 44, r: 14, t: 10, b: 26 };
    const xs = series.flatMap((s) => s.points.map((p) => p[0]));
    let x0 = o.xMin ?? Math.min(...xs), x1 = o.xMax ?? Math.max(...xs);
    if (x1 === x0) { x0 -= 1800000; x1 += 1800000; }
    const ys = series.flatMap((s) => s.points.map((p) => p[1]));
    let y0 = o.yMin ?? Math.min(...ys), y1 = o.yMax ?? Math.max(...ys);
    if (o.yMin == null) y0 = Math.min(y0, ...(o.lines || []).map((l) => l.y));
    if (o.yMax == null) y1 = Math.max(y1, ...(o.lines || []).map((l) => l.y));
    if (y1 === y0) { y0 -= 1; y1 += 1; }
    const pad_ = (y1 - y0) * 0.08;
    if (o.yMin == null) y0 -= pad_;
    if (o.yMax == null) y1 += pad_;
    const yt = ticks(y0, y1, Math.max(3, Math.floor(H / 50)));
    if (o.yMin == null) y0 = Math.min(y0, yt[0]);
    if (o.yMax == null) y1 = Math.max(y1, yt[yt.length - 1]);
    const X = (v) => m.l + ((v - x0) / (x1 - x0)) * (W - m.l - m.r);
    const Y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * (H - m.t - m.b);
    const fy = o.yFormat || ((v) => num(v, Math.abs(y1 - y0) < 5 ? 1 : 0) + (o.unit || ""));
    const fx = o.xFormat || ((v) => (o.time === false ? num(v) : new Date(v).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })));

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": o.label || "line chart" });
    // bands (e.g. fill levels)
    for (const b of o.bands || []) {
      const a = Math.max(y0, b.from), z = Math.min(y1, b.to);
      if (z > a) svg.appendChild(el("rect", { x: m.l, width: W - m.l - m.r, y: Y(z), height: Y(a) - Y(z), fill: b.color, opacity: b.opacity ?? 0.08 }));
    }
    for (const v of yt) {
      if (v < y0 || v > y1) continue;
      svg.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: GRID }));
      svg.appendChild(el("text", { x: m.l - 6, y: Y(v) + 3.5, "font-size": 10.5, fill: MUTED, "text-anchor": "end" }, fy(v)));
    }
    svg.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: BASE }));
    const xt = o.time === false ? ticks(x0, x1, Math.floor(W / 80)).map((t) => ({ t, label: (o.xTick || num)(t) })) : timeTicks(x0, x1, W - m.l - m.r);
    for (const t of xt) svg.appendChild(el("text", { x: X(t.t), y: H - 8, "font-size": 10.5, fill: MUTED, "text-anchor": "middle" }, t.label));
    for (const l of o.lines || []) {
      if (l.y < y0 || l.y > y1) continue;
      svg.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: Y(l.y), y2: Y(l.y), stroke: l.color || INK2, "stroke-dasharray": "4 4", "stroke-width": 1 }));
      svg.appendChild(el("text", { x: W - m.r - 2, y: Y(l.y) - 4, "font-size": 10, fill: INK2, "text-anchor": "end" }, l.label));
    }
    // lines (broken where readings are missing)
    for (const s of series) {
      const pts = s.points.slice().sort((a, b) => a[0] - b[0]);
      const gaps = [];
      for (let i = 1; i < pts.length; i++) gaps.push(pts[i][0] - pts[i - 1][0]);
      const med = gaps.length ? gaps.slice().sort((a, b) => a - b)[Math.floor(gaps.length / 2)] : 0;
      const limit = o.gap ?? (med ? Math.max(med * 4, o.time === false ? med * 4 : 20 * 60000) : Infinity);
      let d = "";
      pts.forEach((p, i) => { d += (i === 0 || p[0] - pts[i - 1][0] > limit ? "M" : "L") + X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1); });
      if (o.area && series.length === 1) {
        svg.appendChild(el("path", { d: d + `L${X(pts[pts.length - 1][0])},${Y(Math.max(y0, 0))}L${X(pts[0][0])},${Y(Math.max(y0, 0))}Z`, fill: s.color, opacity: 0.08 }));
      }
      svg.appendChild(el("path", { d, fill: "none", stroke: s.color, "stroke-width": s.width || 2, "stroke-dasharray": s.dash ? "5 4" : null, "stroke-linejoin": "round", "stroke-linecap": "round" }));
      if (pts.length <= 40 && o.dots !== false) {
        for (const p of pts) svg.appendChild(el("circle", { cx: X(p[0]), cy: Y(p[1]), r: 3, fill: s.color, stroke: "#fff", "stroke-width": 1.5 }));
      }
      s._sorted = pts;
    }
    // hover: crosshair + tooltip
    const cross = el("line", { y1: m.t, y2: H - m.b, stroke: INK2, "stroke-width": 1, opacity: 0 });
    svg.appendChild(cross);
    const dots = series.map((s) => svg.appendChild(el("circle", { r: 4.5, fill: s.color, stroke: "#fff", "stroke-width": 2, opacity: 0 })));
    const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
    svg.appendChild(hit);
    const nearest = (pts, x) => {
      let lo = 0, hi = pts.length - 1;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (pts[mid][0] < x) lo = mid; else hi = mid; }
      return Math.abs(pts[lo][0] - x) <= Math.abs(pts[hi][0] - x) ? pts[lo] : pts[hi];
    };
    const move = (e) => {
      const r = svg.getBoundingClientRect();
      const px = ((e.clientX - r.left) / r.width) * W;
      const x = x0 + ((px - m.l) / (W - m.l - m.r)) * (x1 - x0);
      const near = series.map((s) => nearest(s._sorted, x));
      const best = near.reduce((a, b) => (Math.abs(b[0] - x) < Math.abs(a[0] - x) ? b : a));
      cross.setAttribute("x1", X(best[0])); cross.setAttribute("x2", X(best[0])); cross.setAttribute("opacity", 0.5);
      let html = `<b>${esc(fx(best[0]))}</b>`;
      series.forEach((s, i) => {
        const p = near[i];
        const show = Math.abs(p[0] - best[0]) <= (x1 - x0) / 60;
        dots[i].setAttribute("opacity", show ? 1 : 0);
        if (show) {
          dots[i].setAttribute("cx", X(p[0])); dots[i].setAttribute("cy", Y(p[1]));
          html += `<br><span class="k" style="background:${s.color}"></span>${esc(s.name || "")} ${esc(fy(p[1]))}`;
        }
      });
      if (o.tipExtra) html += o.tipExtra(best);
      showTip(e, html);
    };
    hit.addEventListener("mousemove", move);
    hit.addEventListener("touchstart", (e) => move(e.touches[0]), { passive: true });
    hit.addEventListener("mouseleave", () => { hideTip(); cross.setAttribute("opacity", 0); dots.forEach((d) => d.setAttribute("opacity", 0)); });
    container.appendChild(svg);
  };
  draw();
  onResize(container, draw);
}

// ---------------------------------------------------------------------------
// Bar chart. categories: [...]; series: [{name, color, values}]; markers: [{name, color, values}] (short ticks)
// horizontal: true for long names (e.g. model names)
// ---------------------------------------------------------------------------
export function barChart(container, o) {
  const draw = () => {
    container.innerHTML = "";
    const cats = o.categories || [];
    const series = o.series || [];
    if (!cats.length || !series.length) {
      container.innerHTML = `<div class="empty"><b>${esc(o.emptyTitle || "No data yet")}</b>${esc(o.emptyText || "")}</div>`;
      return;
    }
    if (series.length > 1 || (o.markers || []).length) container.insertAdjacentHTML("beforeend", legendHTML([...series, ...(o.markers || []).map((k) => ({ ...k, dash: true }))]));
    const fv = o.format || ((v) => num(v, o.digits ?? 1) + (o.unit || ""));
    const all = series.flatMap((s) => s.values).concat((o.markers || []).flatMap((k) => k.values)).filter((v) => v != null && !isNaN(v));
    let lo = Math.min(0, ...all), hi = o.max ?? Math.max(...all, 0) * 1.05;
    if (hi <= lo) hi = lo + 1;
    let step = niceStep(hi - lo, 5);
    if (o.integer) step = Math.max(1, Math.ceil(step));
    if (o.max == null) hi = Math.ceil(hi / step - 1e-9) * step;
    const tk = ticks(lo, hi, 5, step);
    const tdig = step >= 1 ? 0 : step >= 0.1 ? 1 : step >= 0.01 ? 2 : 3;
    const ft = (v) => num(v, tdig) + (o.unit || "");
    const W = Math.max(280, container.clientWidth || 600);
    const svg = el("svg", { class: "chart", role: "img", "aria-label": o.label || "bar chart" });
    const n = series.length;
    if (o.horizontal) {
      const labelW = Math.min(o.labelWidth || 210, W * 0.45);
      const rowH = n > 1 ? 14 * n + 12 : 26;
      const H = 24 + cats.length * rowH;
      const m = { l: labelW, r: 46, t: 4, b: 20 };
      const X = (v) => m.l + ((v - lo) / (hi - lo)) * (W - m.l - m.r);
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
      for (const v of tk) {
        svg.appendChild(el("line", { x1: X(v), x2: X(v), y1: m.t, y2: H - m.b, stroke: GRID }));
        svg.appendChild(el("text", { x: X(v), y: H - 6, "font-size": 10, fill: MUTED, "text-anchor": "middle" }, ft(v)));
      }
      cats.forEach((c, i) => {
        const y = m.t + i * rowH;
        const hl = (o.highlight || []).includes(i);
        const t = el("text", { x: m.l - 8, y: y + rowH / 2 + 4, "font-size": 11.5, fill: hl ? INK : INK2, "text-anchor": "end", "font-weight": hl ? 700 : 400 });
        t.textContent = String(c).length > 34 ? String(c).slice(0, 33) + "…" : c;
        svg.appendChild(t);
        series.forEach((s, j) => {
          const v = s.values[i];
          if (v == null || isNaN(v)) return;
          const bh = n > 1 ? 12 : 16, by = y + (n > 1 ? 6 + j * 14 : (rowH - bh) / 2);
          const x = Math.min(X(0), X(v)), w = Math.max(1, Math.abs(X(v) - X(0)));
          const color = s.colors ? s.colors[i] : s.color;
          const r = el("rect", { x, y: by, width: w, height: bh, rx: 3, fill: color });
          r.addEventListener("mousemove", (e) => showTip(e, `<b>${esc(c)}</b><br><span class="k" style="background:${color}"></span>${esc(s.name || "")} ${esc(fv(v))}${o.tip ? o.tip(i, j) : ""}`));
          r.addEventListener("mouseleave", hideTip);
          svg.appendChild(r);
          if (o.values !== false) svg.appendChild(el("text", { x: X(v) + 4, y: by + bh / 2 + 4, "font-size": 10.5, fill: INK }, fv(v)));
        });
      });
      svg.appendChild(el("line", { x1: X(0), x2: X(0), y1: m.t, y2: H - m.b, stroke: BASE }));
    } else {
      const H = o.height || 220;
      const m = { l: 42, r: 8, t: 14, b: o.twoLineLabels ? 34 : 24 };
      const Y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
      for (const v of tk) {
        svg.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: GRID }));
        svg.appendChild(el("text", { x: m.l - 6, y: Y(v) + 3.5, "font-size": 10.5, fill: MUTED, "text-anchor": "end" }, ft(v)));
      }
      const band = (W - m.l - m.r) / cats.length;
      const gap = Math.min(10, band * 0.18);
      const bw = Math.max(3, (band - gap * 2 - 2 * (n - 1)) / n);
      cats.forEach((c, i) => {
        const bx = m.l + i * band + gap;
        series.forEach((s, j) => {
          const v = s.values[i];
          if (v == null || isNaN(v)) return;
          const x = bx + j * (bw + 2);
          const color = s.colors ? s.colors[i] : s.color;
          const r = el("rect", { x, y: Math.min(Y(v), Y(0)), width: bw, height: Math.max(1, Math.abs(Y(0) - Y(v))), rx: 3, fill: color });
          r.addEventListener("mousemove", (e) => showTip(e, `<b>${esc(o.tipTitle ? o.tipTitle(i) : c)}</b><br><span class="k" style="background:${color}"></span>${esc(s.name || "")} ${esc(fv(v))}${o.tip ? o.tip(i, j) : ""}`));
          r.addEventListener("mouseleave", hideTip);
          svg.appendChild(r);
          const top = Math.min(Y(v), ...(o.markers || []).map((k) => k.values[i]).filter((z) => z != null).map(Y));
          if (o.values && n === 1) svg.appendChild(el("text", { x: x + bw / 2, y: top - 5, "font-size": 10, fill: INK, "text-anchor": "middle" }, (o.valueFormat || fv)(v)));
        });
        for (const k of o.markers || []) {
          const v = k.values[i];
          if (v == null) continue;
          const mk = el("line", { x1: bx - 2, x2: bx + n * (bw + 2), y1: Y(v), y2: Y(v), stroke: k.color || INK, "stroke-width": 2 });
          svg.appendChild(mk);
        }
        const parts = String(c).split("\n");
        svg.appendChild(el("text", { x: bx + (n * (bw + 2)) / 2, y: H - (o.twoLineLabels ? 20 : 8), "font-size": 10.5, fill: INK2, "text-anchor": "middle" }, parts[0]));
        if (parts[1]) svg.appendChild(el("text", { x: bx + (n * (bw + 2)) / 2, y: H - 7, "font-size": 10, fill: MUTED, "text-anchor": "middle" }, parts[1]));
      });
      svg.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), stroke: BASE }));
    }
    container.appendChild(svg);
  };
  draw();
  onResize(container, draw);
}

// ---------------------------------------------------------------------------
// Scatter / connected dots: series: [{name, color, points: [{x, y, label}]}]
// ---------------------------------------------------------------------------
export function scatterChart(container, o) {
  const draw = () => {
    container.innerHTML = "";
    const series = (o.series || []).filter((s) => s.points && s.points.length);
    if (!series.length) { container.innerHTML = `<div class="empty"><b>No data yet</b></div>`; return; }
    container.insertAdjacentHTML("beforeend", legendHTML(series));
    const W = Math.max(280, container.clientWidth || 600), H = o.height || 260;
    const m = { l: 50, r: 14, t: 24, b: 38 };
    const xs = series.flatMap((s) => s.points.map((p) => p.x)), ys = series.flatMap((s) => s.points.map((p) => p.y));
    const span = (lo, hi) => {
      const st = niceStep((hi - lo) || 1, 5);
      return [Math.floor(lo / st) * st, Math.ceil(hi / st) * st, st];
    };
    const [x0, x1, sx] = span(Math.min(...xs), Math.max(...xs)), [y0, y1, sy] = span(Math.min(0, ...ys), Math.max(...ys) * 1.05);
    const xt = ticks(x0, x1, 5, sx), yt = ticks(y0, y1, 5, sy);
    const X = (v) => m.l + ((v - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
    const Y = (v) => m.t + (1 - (v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": o.label || "scatter chart" });
    for (const v of yt) {
      svg.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: GRID }));
      svg.appendChild(el("text", { x: m.l - 6, y: Y(v) + 3.5, "font-size": 10.5, fill: MUTED, "text-anchor": "end" }, num(v)));
    }
    for (const v of xt) svg.appendChild(el("text", { x: X(v), y: H - 22, "font-size": 10.5, fill: MUTED, "text-anchor": "middle" }, num(v)));
    svg.appendChild(el("text", { x: (m.l + W - m.r) / 2, y: H - 5, "font-size": 11, fill: INK2, "text-anchor": "middle" }, o.xLabel || ""));
    svg.appendChild(el("text", { x: 4, y: 12, "font-size": 11, fill: INK2 }, o.yLabel || ""));
    svg.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: Y(y0), y2: Y(y0), stroke: BASE }));
    for (const s of series) {
      if (s.connect) {
        const pts = s.points.slice().sort((a, b) => a.x - b.x);
        svg.appendChild(el("path", { d: pts.map((p, i) => (i ? "L" : "M") + X(p.x) + "," + Y(p.y)).join(""), fill: "none", stroke: s.color, "stroke-width": 2 }));
      }
      for (const p of s.points) {
        const c = el("circle", { cx: X(p.x), cy: Y(p.y), r: s.big ? 7 : 5, fill: s.color, stroke: "#fff", "stroke-width": 2 });
        c.addEventListener("mousemove", (e) => showTip(e, `<b>${esc(s.name)}</b>${p.label ? " – " + esc(p.label) : ""}<br>${esc(o.xLabel || "x")}: ${num(p.x, 1)}<br>${esc(o.yLabel || "y")}: ${num(p.y, 1)}`));
        c.addEventListener("mouseleave", hideTip);
        svg.appendChild(c);
        if (p.label && s.labels !== false) svg.appendChild(el("text", { x: X(p.x) + 8, y: Y(p.y) - 6, "font-size": 10, fill: INK2 }, p.label));
      }
    }
    container.appendChild(svg);
  };
  draw();
  onResize(container, draw);
}

export const timeLabel = (ms) => new Date(ms).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short" }) + " " + hhmm(ms);
