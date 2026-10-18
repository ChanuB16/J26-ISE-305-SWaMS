import { $, $$, api, poll, esc, icon, num, pct, ago, dt, hours, level, levelPill, riskPill, urgencyPill, urgencyKey, gasPill,
  ring, alertList, showError, syntheticBadge, seg, CFG, errText, dist, STATUS, fillBar } from "../ui.js";
import { lineChart } from "../charts.js";

const ID = window.BIN_ID;
const H = { range: "24h", day: "", rows: [], page: 0, loadedAt: 0 };
const PAGE = 50;

function tile(ic, lab, val, sub = "") {
  return `<div class="tile"><div class="lab">${icon(ic)} ${lab}</div><div class="val">${val}</div>${sub ? `<div class="s">${sub}</div>` : ""}</div>`;
}
function wifiWord(r) {
  if (r == null) return "";
  return r > -60 ? "strong" : r > -72 ? "good" : r > -82 ? "weak" : "very weak";
}

function renderDetail(d) {
  const b = d.bin;
  syntheticBadge(b.synthetic);
  $("#name").textContent = `${b.id} · ${b.name}`;
  document.title = `${b.id} · SmartWaste LK`;
  $("#meta").innerHTML = [b.zone && `${icon("pin")} ${esc(b.zone)}`, b.type && esc(b.type), b.capacity_l && `${num(b.capacity_l)} L`,
    b.lat != null && `${b.lat.toFixed(5)}, ${b.lng.toFixed(5)}`].filter(Boolean).map((x) => `<span>${x}</span>`).join("<span>·</span>");
  $("#topPills").innerHTML = (b.synthetic ? '<span class="pill lv-none" title="Demo bin made by b6_demo_bins.py - it has no real sensor">demo bin (no sensor)</span>' : '<span class="pill lv-brand">real smart bin</span>') +
    (b.stale && !b.synthetic ? ' <span class="pill rk-high">▲ no recent data</span>' : "") +
    ` <span class="pill lv-none">${icon("clock")} ${ago(b.ts)}</span>`;

  // now
  $("#now").innerHTML = ring(b.fill, 150, "full now") + `<div class="stack" style="gap:8px;flex:1;min-width:140px">
    ${tile("weight", "Weight", b.weight_kg == null ? "–" : num(b.weight_kg, 2) + "<small> kg</small>")}
    ${tile("road", "Sensor → rubbish", b.distance_cm == null ? "–" : num(b.distance_cm, 1) + "<small> cm</small>")}</div>`;

  // prediction
  if (b.pred != null) {
    const st = { ok: "", warming_up: "gas sensor warming up", no_recent_data: "no recent data - prediction may be old", demo: "demo bin" }[b.pred_status] ?? b.pred_status;
    $("#pred").innerHTML = `<div class="row" style="align-items:flex-end;gap:14px"><div class="bigscore" style="color:${level(b.pred).color === STATUS.warning ? "#8a6100" : level(b.pred).color}">${pct(b.pred)}</div>
      <div>${levelPill(b.pred)}<div class="muted small" style="margin-top:4px">now ${pct(b.fill)} → in 6 hours ${pct(b.pred)}</div></div></div>
      <div class="tiles mt">${tile("alert", "Overflow risk", riskPill(b.risk))}${tile("clock", `Reaches ${CFG.overflow}%`, b.hours_to_full == null ? "–" : (b.hours_to_full <= 0 ? "now" : "in " + hours(b.hours_to_full)))}</div>
      <p class="small muted mt">Model: ${esc(b.model || "?")} · updated ${ago(b.pred_at || b.ts)}${st ? " · " + esc(st) : ""}</p>`;
  } else {
    $("#pred").innerHTML = `<div class="empty"><b>No prediction yet</b>Start “Live bin predictions” on the <a href="/officer/system">System page</a>. It needs about an hour of readings.</div>`;
  }

  // urgency
  const parts = d.urgency_parts;
  const total = parts.reduce((s, p) => s + p.points, 0);
  const score = b.urgency ?? Math.round(total);
  $("#urgPill").innerHTML = urgencyPill(score);
  $("#urg").innerHTML = `<div class="row" style="align-items:flex-end;gap:10px"><div class="bigscore">${Math.round(score)}</div><div class="muted small">of 100${b.urgency == null ? "<br>(estimate: no ML prediction yet)" : "<br>ML urgency score"}</div></div>
    <div class="parts mt">${parts.map((p) => `<div class="part"><div class="top-line"><span>${esc(p.label)} <span class="muted small">${num(p.value, 0)} × ${p.weight}</span></span><b class="num">${num(p.points, 1)}</b></div>
      <div class="track"><span style="width:${(p.points / (p.weight * 100)) * 100}%;background:#2a78d6"></span></div></div>`).join("")}</div>
    <p class="small muted mt">Bar = how much of that part's maximum (${parts.map((p) => p.weight * 100).join(" / ")} points) is used. ${urgencyKey(score) === "high" ? "<b>Collect first.</b>" : ""}</p>`;

  // sensors
  $("#sensTime").textContent = b.ts ? `reading of ${dt(b.ts)}` : "";
  $("#sensors").innerHTML =
    tile("thermo", "Temperature", b.temp_c == null ? "–" : num(b.temp_c, 1) + "<small> °C</small>") +
    tile("drop", "Humidity", pct(b.humidity)) +
    tile("gas", "Gas / smell", b.gas_ready === false ? "warming up" : num(b.gas_index), `${gasPill(b.gas_index, b.gas_ready)}${b.gas_mv != null ? " " + num(b.gas_mv) + " mV" : ""}`) +
    tile("battery", "Battery", pct(b.battery_pct), b.battery_v != null ? num(b.battery_v, 2) + " V" + (b.battery_pct != null && b.battery_pct < CFG.lowBattery ? " ▲ low" : "") : "") +
    tile("wifi", "WiFi signal", b.rssi == null ? "–" : num(b.rssi) + "<small> dBm</small>", wifiWord(b.rssi)) +
    tile("check", "Last emptied", b.last_collected ? ago(b.last_collected) : "–", b.last_collected ? dt(b.last_collected) : "") +
    tile("star", "On-bin urgency", b.urgency_now == null ? "–" : num(b.urgency_now), "status lights score (fill now)");

  // alerts and nearest
  $("#alerts").innerHTML = alertList(d.alerts.concat(b.errors.length && !d.alerts.some((a) => a.code) ? b.errors.map((e) => ({ level: "info", title: "Sensor problem", code: e })) : []), { link: false });
  const n = d.nearest;
  $("#nearRule").textContent = n ? `Rule (Component 2, method R1): ${n.rule}.` : "";
  if (!n) $("#near").innerHTML = '<div class="muted">This bin has no location.</div>';
  else if (n.best) {
    const o = n.others || [];
    $("#near").innerHTML = `<div class="alert" style="border-left-color:${STATUS.good}"><span class="sym" style="background:${STATUS.good}">✓</span><div><div class="t"><a href="/officer/bins/${encodeURIComponent(n.best.id)}">${esc(n.best.id)} · ${esc(n.best.name)}</a></div>
      <div class="s">${dist(n.best.km)} away (straight line) · ${pct(n.best.fill)} full now · ${pct(n.best.pred)} in 6 h</div></div></div>` +
      (o.length ? `<p class="small muted mt">Other bins with space: ${o.map((x) => `<a href="/officer/bins/${encodeURIComponent(x.id)}">${esc(x.id)}</a> (${dist(x.km)}, ${pct(x.fill)})`).join(", ")}</p>` : "");
  } else {
    $("#near").innerHTML = `<div class="warn-bar">No bin with space within ${CFG.maxKm} km.${n.nearest_any ? ` Closest bin: ${esc(n.nearest_any.id)} (${dist(n.nearest_any.km)}, ${pct(n.nearest_any.fill)} full).` : ""}</div>`;
  }

  // collections
  const cols = d.collections || [];
  const month = cols.filter((c) => c.ts > Date.now() - 30 * 86400000).length;
  $("#colCount").textContent = cols.length ? `${month} in the last 30 days` : "";
  $("#collections").innerHTML = cols.length ? `<table class="tbl"><thead><tr><th>When</th><th>Fill before</th><th>Fill after</th><th>Weight before</th></tr></thead><tbody>${cols.slice(0, 30).map((c) => `
    <tr><td class="nowrap">${dt(c.ts)} <span class="muted small">${ago(c.ts)}</span></td><td>${c.fill_before_pct != null ? levelPill(c.fill_before_pct, true) : "–"}</td><td class="num">${pct(c.fill_after_pct)}</td><td class="num">${c.weight_before_kg != null ? num(c.weight_before_kg, 2) + " kg" : "–"}</td></tr>`).join("")}</tbody></table>`
    : b.last_collected ? `<p>Last emptied ${dt(b.last_collected)} (${ago(b.last_collected)}).</p>` : '<div class="empty"><b>No emptying recorded yet</b>The bin records it when its level drops, or type <code>collected</code> in the Serial Monitor.</div>';

  // device
  const v = d.device;
  $("#device").innerHTML = v ? `<table class="tbl"><tbody>
    <tr><td>Firmware</td><td>${esc(v.fw || "–")}</td></tr>
    <tr><td>Empty / full distance</td><td>${num(v.empty_distance_cm, 1)} cm / ${num(v.full_distance_cm, 1)} cm</td></tr>
    <tr><td>Scale calibrated</td><td>${v.weight_calibrated ? '<span class="pill lv-normal">✓ yes</span>' : '<span class="pill rk-high">▲ no</span>'}</td></tr>
    <tr><td>Gas baseline</td><td>${num(v.gas_baseline_mv)} mV</td></tr>
    <tr><td>Sends every</td><td>${num(v.send_interval_s)} s</td></tr>
    <tr><td>Clock module (RTC)</td><td>${v.rtc_found ? "found" : "not found"}</td></tr>
    <tr><td>Restarts (boot count)</td><td>${num(v.boot)}</td></tr>
    <tr><td>MAC / IP</td><td><code>${esc(v.mac || "–")}</code> <code>${esc(v.ip || "–")}</code></td></tr>
    <tr><td>Device info sent</td><td>${ago(v.updated)}</td></tr></tbody></table>`
    : `<div class="muted">${b.synthetic ? "Demo bins have no device." : "The bin has not sent its device info yet."}</div>`;
}

function readingsUrl(csv = false) {
  const q = H.day ? `day=${H.day}` : `range=${H.range}`;
  return `/api/bins/${encodeURIComponent(ID)}/readings${csv ? ".csv" : ""}?${q}`;
}

function cellClass(f) {
  const k = level(f).key;
  return k === "none" ? "" : "c-" + k;
}

function renderTable() {
  const rows = H.rows.slice().reverse();
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  H.page = Math.min(H.page, pages - 1);
  const part = rows.slice(H.page * PAGE, (H.page + 1) * PAGE);
  $("#pager").innerHTML = rows.length > PAGE ? `<button class="btn ghost small" data-p="-1" ${H.page === 0 ? "disabled" : ""}>← Newer</button><span>page ${H.page + 1} of ${pages}</span><button class="btn ghost small" data-p="1" ${H.page >= pages - 1 ? "disabled" : ""}>Older →</button>` : "";
  $$("#pager button").forEach((b) => (b.onclick = () => { H.page += Number(b.dataset.p); renderTable(); }));
  $("#histTable").innerHTML = part.length ? `<table class="tbl"><thead><tr><th>Time</th><th>Fill</th><th>Distance</th><th>Weight</th><th>Gas index</th><th>Temp</th><th>Humidity</th><th>Battery</th><th>Urgency</th><th>Problems</th></tr></thead><tbody>${part.map((r) => `
    <tr><td class="nowrap">${dt(r.ts)}${r.n ? ` <span class="muted small">(${r.n} avg)</span>` : ""}</td>
    <td class="num nowrap ${cellClass(r.fill_pct)}">${r.fill_pct == null ? "–" : level(r.fill_pct).sym + " " + num(r.fill_pct, 1) + "%"}</td>
    <td class="num">${r.distance_cm == null ? "–" : num(r.distance_cm, 1) + " cm"}</td>
    <td class="num">${r.weight_kg == null ? "–" : num(r.weight_kg, 2) + " kg"}</td>
    <td class="num ${r.gas_index != null && r.gas_index >= CFG.smell ? "c-critical" : ""}">${r.gas_ready === false ? '<span class="muted">warm-up</span>' : num(r.gas_index)}</td>
    <td class="num">${r.temp_c == null ? "–" : num(r.temp_c, 1) + " °C"}</td>
    <td class="num">${pct(r.humidity_pct)}</td>
    <td class="num ${r.battery_pct != null && r.battery_pct < CFG.lowBattery ? "c-critical" : ""}">${pct(r.battery_pct)}</td>
    <td class="num">${num(r.urgency_now)}</td>
    <td class="small">${(r.errors || []).map((e) => `<span title="${esc(errText(e))}">${esc(e)}</span>`).join(", ")}</td></tr>`).join("")}</tbody></table>`
    : '<div class="empty"><b>No readings in this time</b></div>';
}

async function loadHistory(force = false) {
  if (!force && H.loadedAt && (H.day || H.range === "3d" || H.range === "7d") && Date.now() - H.loadedAt < 120000) return;
  $("#csv").href = readingsUrl(true);
  let d;
  try {
    d = await api.get(readingsUrl());
  } catch (e) {
    $("#histInfo").innerHTML = `<span class="msg bad">${esc(e.message)}</span>`;
    return;
  }
  H.rows = d.rows;
  H.loadedAt = Date.now();
  const s = d.stats;
  $("#histInfo").textContent = d.raw_count
    ? `${num(d.raw_count)} readings (${d.label})` + (d.bucket_seconds ? ` – shown as ${d.bucket_seconds / 60}-minute steps (fill = highest in each step, others = average). The CSV has every reading.` : ".")
    : H.synthetic ? "Demo bins have no sensor history (only the real bin sends readings)." : "";
  $("#stats").innerHTML = d.raw_count ? [["Fill", s.fill_pct, "%", 0], ["Weight", s.weight_kg, " kg", 2], ["Gas index", s.gas_index, "", 0], ["Temperature", s.temp_c, " °C", 1], ["Humidity", s.humidity_pct, "%", 0]]
    .map(([l, x, u, dg]) => `<div class="tile"><div class="lab">${l}</div><div class="val" style="font-size:15px">${x ? num(x.min, dg) + "–" + num(x.max, dg) + u : "–"}</div><div class="s">${x ? "average " + num(x.avg, dg) + u : ""}</div></div>`).join("") : "";
  const xMin = d.start, xMax = d.end;
  const pts = (f) => H.rows.map((r) => [r.ts, r[f] == null ? null : Number(r[f])]);
  const empty = { emptyTitle: d.raw_count ? "No values" : "No readings in this time", emptyText: d.raw_count ? "" : "Check that the bin is switched on and sending (Serial Monitor: wifi, send)." };
  lineChart($("#chFill"), {
    series: [{ name: "Fill level", color: "#2a78d6", points: pts("fill_pct") }], yMin: 0, yMax: 100, unit: "%", xMin, xMax, height: 240, ...empty,
    bands: [{ from: 0, to: CFG.filling, color: STATUS.good }, { from: CFG.filling, to: CFG.alert, color: STATUS.warning }, { from: CFG.alert, to: CFG.overflow, color: STATUS.serious }, { from: CFG.overflow, to: 100, color: STATUS.critical }],
    lines: [{ y: CFG.alert, label: `warning ${CFG.alert}%` }, { y: CFG.overflow, label: `critical ${CFG.overflow}%`, color: STATUS.critical }],
    tipExtra: (p) => "<br>" + level(p[1]).sym + " " + level(p[1]).label,
  });
  lineChart($("#chWeight"), { series: [{ name: "Weight", color: "#1baf7a", points: pts("weight_kg") }], unit: " kg", yMin: 0, xMin, xMax, height: 170, ...empty });
  lineChart($("#chGas"), { series: [{ name: "Gas index", color: "#eb6834", points: pts("gas_index") }], yMin: 0, yMax: 100, xMin, xMax, height: 170, lines: [{ y: CFG.smell, label: `strong smell ${CFG.smell}` }], ...empty });
  lineChart($("#chTemp"), { series: [{ name: "Temperature", color: "#e34948", points: pts("temp_c") }], unit: " °C", xMin, xMax, height: 170, ...empty });
  lineChart($("#chHum"), { series: [{ name: "Humidity", color: "#6250d6", points: pts("humidity_pct") }], unit: "%", yMin: 0, yMax: 100, xMin, xMax, height: 170, ...empty });
  lineChart($("#chBat"), { series: [{ name: "Battery", color: "#008300", points: pts("battery_pct") }], unit: "%", yMin: 0, yMax: 100, xMin, xMax, height: 170, lines: [{ y: CFG.lowBattery, label: "low" }], ...empty });
  lineChart($("#chUrg"), { series: [{ name: "On-bin urgency", color: "#eda100", points: pts("urgency_now") }], yMin: 0, yMax: 100, xMin, xMax, height: 170, lines: [{ y: CFG.urgencyHigh, label: "high" }], ...empty });
  renderTable();
}

async function load() {
  try {
    const d = await api.get(`/api/bins/${encodeURIComponent(ID)}`);
    H.synthetic = d.bin.synthetic;
    renderDetail(d);
    showError($("#err"), null);
  } catch (e) {
    showError($("#err"), e);
  }
  loadHistory();
}

seg($("#range"), (v) => { H.range = v; H.day = ""; $("#day").value = ""; H.page = 0; loadHistory(true); });
$("#day").max = CFG.today;
$("#day").onchange = (e) => {
  H.day = e.target.value;
  $$("#range button").forEach((b) => b.classList.toggle("on", !H.day && b.dataset.v === H.range));
  H.page = 0;
  loadHistory(true);
};
poll(load);
