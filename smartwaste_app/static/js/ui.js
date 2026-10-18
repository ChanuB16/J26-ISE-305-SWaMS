// Shared helpers for every page: talking to the app, formatting, colours/levels, small widgets.
export const CFG = window.SW || {};

// ---------------- DOM ----------------
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export function esc(x) {
  return String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
export function icon(name, cls = "i") {
  return `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
}

// ---------------- talking to the app ----------------
const csrf = () => (document.querySelector('meta[name="csrf"]') || {}).content || "";
function setConn(ok, text) {
  const el = document.getElementById("conn");
  if (!el) return;
  el.classList.toggle("bad", !ok);
  el.querySelector(".txt").textContent = text;
  el.title = text;
}
async function call(method, url, body) {
  let r;
  try {
    r = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    setConn(false, "app not reachable");
    throw new Error("Cannot reach the app. Is python app.py still running?");
  }
  if (r.status === 401) {
    location.href = "/login?next=" + encodeURIComponent(location.pathname);
    throw new Error("Please log in again.");
  }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = j.error || "Error " + r.status;
    if (r.status === 503) setConn(false, "database problem");
    throw new Error(msg);
  }
  if (method === "GET") setConn(true, (CFG.demo ? "demo · " : "live · ") + "updated " + hhmm(Date.now(), true));
  return j;
}
export const api = {
  get: (u) => call("GET", u),
  post: (u, b) => call("POST", u, b ?? {}),
  patch: (u, b) => call("PATCH", u, b ?? {}),
  del: (u) => call("DELETE", u),
};

// Calls fn now and every few seconds (settings.py REFRESH_SECONDS). Pauses while the tab is hidden.
export function poll(fn, seconds = CFG.refresh || 15) {
  let timer = null, stopped = false;
  async function run() {
    clearTimeout(timer);
    if (stopped) return;
    if (!document.hidden) {
      try {
        await fn();
      } catch (e) {
        console.warn(e);
      }
    }
    if (!stopped && seconds) timer = setTimeout(run, seconds * 1000);
  }
  run();
  document.addEventListener("visibilitychange", () => { if (!document.hidden) run(); });
  return { now: run, stop: () => { stopped = true; clearTimeout(timer); } };
}

// ---------------- formatting ----------------
export const pad = (n) => String(n).padStart(2, "0");
export function num(v, d = 0, fb = "–") {
  if (v == null || v === "" || isNaN(Number(v))) return fb;
  return Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}
export const pct = (v, d = 0) => (v == null || isNaN(Number(v)) ? "–" : num(v, d) + "%");
export const rs = (v) => (v == null || isNaN(Number(v)) ? "–" : "Rs " + Math.round(Number(v)).toLocaleString("en-US"));
export function hhmm(ms, sec = false) {
  if (!ms) return "–";
  const d = new Date(Number(ms));
  return pad(d.getHours()) + ":" + pad(d.getMinutes()) + (sec ? ":" + pad(d.getSeconds()) : "");
}
export function dt(ms) {
  if (!ms) return "–";
  const d = new Date(Number(ms));
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }) + " " + hhmm(ms);
}
export function ago(ms) {
  if (!ms) return "no data";
  const m = (Date.now() - Number(ms)) / 60000;
  if (m < -1) return "in " + Math.round(-m) + " min";
  if (m < 1) return "just now";
  if (m < 60) return Math.round(m) + " min ago";
  if (m < 48 * 60) return Math.round(m / 60) + " h ago";
  return Math.round(m / 1440) + " days ago";
}
export function hours(h) {
  if (h == null || isNaN(Number(h))) return "–";
  const v = Number(h);
  if (v < 1) return Math.max(0, Math.round(v * 60)) + " min";
  if (v < 48) return (v < 10 ? v.toFixed(1) : Math.round(v)) + " h";
  return Math.round(v / 24) + " days";
}
export function localDate(off = 0) {
  const d = new Date(Date.now() + off * 86400000);
  return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
}
export const dayName = (d, long = false) => new Date(d + "T12:00:00").toLocaleDateString("en-GB",
  long ? { weekday: "long", day: "numeric", month: "long" } : { weekday: "short", day: "numeric", month: "short" }).replace(/,/g, "");
// "+5%", "-3%", "0%" (never "-0%")
export function signPct(v) {
  if (v == null || isNaN(Number(v))) return "–";
  const r = Math.round(Number(v));
  return (r > 0 ? "+" : "") + (r === 0 ? 0 : r) + "%";
}
// time until a bin is full: "now", "in 3.5 h"
export function fullIn(h) {
  if (h == null || isNaN(Number(h))) return "–";
  return Number(h) <= 0 ? "now" : hours(h);
}
export function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}
export function km(lat1, lng1, lat2, lng2) {
  const r = Math.PI / 180;
  const a = Math.sin(((lat2 - lat1) * r) / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(((lng2 - lng1) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(a));
}
export const dist = (k) => (k == null ? "–" : k < 1 ? Math.round(k * 1000) + " m" : k.toFixed(1) + " km");

// ---------------- levels (colour + icon + word, never colour alone) ----------------
export const STATUS = { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b", none: "#898781" };
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
export const TRUCK = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#e87ba4"];
export const LEVELS = {
  normal: { key: "normal", label: "Normal", sym: "✓", color: STATUS.good, range: `below ${CFG.filling}%` },
  filling: { key: "filling", label: "Filling", sym: "●", color: STATUS.warning, range: `${CFG.filling}–${CFG.alert - 1}%` },
  warning: { key: "warning", label: "Warning", sym: "▲", color: STATUS.serious, range: `${CFG.alert}–${CFG.overflow - 1}%` },
  critical: { key: "critical", label: "Critical", sym: "✖", color: STATUS.critical, range: `${CFG.overflow}% or more` },
  none: { key: "none", label: "No data", sym: "–", color: STATUS.none, range: "" },
};
export function level(f) {
  if (f == null || isNaN(Number(f))) return LEVELS.none;
  const v = Number(f);
  if (v >= CFG.overflow) return LEVELS.critical;
  if (v >= CFG.alert) return LEVELS.warning;
  if (v >= CFG.filling) return LEVELS.filling;
  return LEVELS.normal;
}
export function levelPill(f, withValue = false) {
  const l = level(f);
  return `<span class="pill lv-${l.key}" title="${esc(l.range)}"><span class="sym">${l.sym}</span>${l.label}${withValue && f != null ? " · " + pct(f) : ""}</span>`;
}
const RISK = { high: ["rk-high", "▲", "High"], medium: ["rk-medium", "●", "Medium"], low: ["rk-low", "✓", "Low"] };
export function riskPill(r) {
  const x = RISK[r];
  return x ? `<span class="pill ${x[0]}"><span class="sym">${x[1]}</span>${x[2]}</span>` : '<span class="muted">–</span>';
}
export function urgencyKey(u) {
  if (u == null || isNaN(Number(u))) return null;
  return u >= CFG.urgencyHigh ? "high" : u >= CFG.urgencyMedium ? "medium" : "low";
}
export function urgencyPill(u) {
  const k = urgencyKey(u);
  if (!k) return '<span class="muted">–</span>';
  const x = RISK[k];
  return `<span class="pill ${x[0]}" title="Urgency score 0-100"><span class="sym">${x[1]}</span>${Math.round(u)}</span>`;
}
export function gasPill(index, ready) {
  if (ready === false) return '<span class="pill lv-none">warming up</span>';
  if (index == null) return '<span class="muted">–</span>';
  if (index >= CFG.smell) return `<span class="pill rk-high"><span class="sym">▲</span>Strong smell</span>`;
  if (index >= CFG.smell / 2) return `<span class="pill rk-medium"><span class="sym">●</span>Some smell</span>`;
  return `<span class="pill rk-low"><span class="sym">✓</span>Fresh</span>`;
}
export function fillBar(f, pred = null) {
  const l = level(f);
  const w = Math.max(0, Math.min(100, Number(f) || 0));
  const p = pred != null ? `<i style="left:calc(${Math.max(0, Math.min(100, pred))}% - 1px)" title="In 6 hours: ${pct(pred)}"></i>` : "";
  return `<span class="fillbar"><span class="track"><span style="width:${w}%;background:${l.color}"></span>${p}</span><b>${pct(f)}</b></span>`;
}
export function ring(f, size = 150, label = "full") {
  const l = level(f);
  const r = 42, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, Number(f) || 0));
  return `<div class="ring" style="width:${size}px;height:${size}px">
    <svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="${r}" fill="none" stroke="#ecefe7" stroke-width="10"/>
    <circle cx="50" cy="50" r="${r}" fill="none" stroke="${l.color}" stroke-width="10" stroke-linecap="round"
      stroke-dasharray="${(c * v) / 100} ${c}"/></svg>
    <div class="c"><div><b>${f == null ? "–" : Math.round(f) + "%"}</b><span>${esc(label)}</span><div style="margin-top:6px">${levelPill(f)}</div></div></div></div>`;
}
export function levelLegend() {
  return `<div class="legend">${["normal", "filling", "warning", "critical"].map((k) => {
    const l = LEVELS[k];
    return `<span><span class="swatch" style="background:${l.color}"></span>${l.sym} ${l.label} <span class="muted">(${l.range})</span></span>`;
  }).join("")}</div>`;
}

export const ERROR_TEXT = {
  ultrasonic_no_echo: "Level sensor gives no echo (cable, or rubbish closer than 20 cm to the sensor)",
  weight_not_calibrated: "Scale not calibrated (type: tare, then cal 1.0)",
  load_cell_no_answer: "Scale (HX711) does not answer (check DT/SCK wires)",
  dht22_no_data: "Temperature/humidity sensor gives no data",
  gas_no_signal: "Gas sensor gives no signal",
};
export const errText = (c) => ERROR_TEXT[c] || String(c).replace(/_/g, " ");

export function alertList(alerts, { limit = 50, link = true } = {}) {
  if (!alerts || !alerts.length) return `<div class="empty"><b>No warnings right now</b>All bins are fine.</div>`;
  const sym = { critical: "✖", warning: "▲", serious: "!", info: "i" };
  return `<div class="alerts">${alerts.slice(0, limit).map((a) => {
    const text = a.code ? errText(a.code) : a.text;
    const t = link && a.bin ? `<a href="/officer/bins/${encodeURIComponent(a.bin)}">${esc(a.title)}</a>` : esc(a.title);
    return `<div class="alert ${a.level}"><span class="sym" aria-hidden="true">${sym[a.level] || "i"}</span>
      <div><div class="t">${t}</div><div class="s">${esc(text)}</div></div></div>`;
  }).join("")}${alerts.length > limit ? `<div class="muted small">+ ${alerts.length - limit} more</div>` : ""}</div>`;
}

export function empty(title, text = "") {
  return `<div class="empty"><b>${esc(title)}</b>${text}</div>`;
}

// ---------------- tooltip ----------------
const tipEl = () => document.getElementById("tip");
export function showTip(e, html) {
  const t = tipEl();
  if (!t) return;
  t.innerHTML = html;
  t.style.display = "block";
  const w = t.offsetWidth, h = t.offsetHeight;
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + w > window.innerWidth - 8) x = e.clientX - w - 14;
  if (y + h > window.innerHeight - 8) y = e.clientY - h - 14;
  t.style.left = Math.max(4, x) + "px";
  t.style.top = Math.max(4, y) + "px";
}
export function hideTip() {
  const t = tipEl();
  if (t) t.style.display = "none";
}

// ---------------- messages ----------------
export function toast(text, bad = false) {
  const el = document.createElement("div");
  el.className = "toast" + (bad ? " bad" : "");
  el.setAttribute("role", "status");
  el.textContent = text;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), bad ? 6000 : 3500);
}
export function showError(el, e) {
  if (!el) return;
  el.innerHTML = e ? `<div class="error-bar">${esc(e.message || e)}</div>` : "";
}
export function dialog(html) {
  const bg = document.createElement("div");
  bg.className = "dialog-bg";
  bg.innerHTML = `<div class="dialog" role="dialog" aria-modal="true">${html}<div class="row mt" style="justify-content:flex-end"><button class="btn ghost" data-close>Close</button></div></div>`;
  bg.addEventListener("click", (e) => { if (e.target === bg || e.target.closest("[data-close]")) bg.remove(); });
  document.addEventListener("keydown", function k(e) { if (e.key === "Escape") { bg.remove(); document.removeEventListener("keydown", k); } });
  document.body.appendChild(bg);
  return bg;
}
export function syntheticBadge(on) {
  const b = document.getElementById("synBadge");
  if (b) b.classList.toggle("hidden", !on);
}

// ---------------- small CSV download (tables made in the browser) ----------------
export function downloadCSV(filename, rows, cols) {
  const cell = (v) => {
    const s = v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const text = [cols.map((c) => cell(c.label || c)).join(","), ...rows.map((r) => cols.map((c) => cell(c.get ? c.get(r) : r[c])).join(","))].join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" }));
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

// Segmented control: <div class="seg" id="x"><button data-v="a">..</button></div>
export function seg(el, onChange) {
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (!b) return;
    $$("button", el).forEach((x) => x.classList.toggle("on", x === b));
    onChange(b.dataset.v);
  });
}
