import { $, $$, api, poll, esc, pct, ago, level, levelLegend, levelPill, fillBar, riskPill, urgencyPill, gasPill,
  showError, syntheticBadge, seg, CFG, num } from "../ui.js";
import { createMap, binMarker } from "../map.js";

const params = new URLSearchParams(location.search);
const state = { level: params.get("level") || "all", zone: params.get("zone") || "", q: "", sort: "urgency", demo: true, rows: [] };
let map = null;

function filtered() {
  const q = state.q.trim().toLowerCase();
  let rows = state.rows.filter((b) =>
    (state.level === "all" || level(b.fill).key === state.level) &&
    (!state.zone || b.zone === state.zone) &&
    (state.demo || !b.synthetic) &&
    (!q || (b.id + " " + b.name + " " + b.zone).toLowerCase().includes(q)));
  const key = { urgency: (b) => b.urgency ?? -1, fill: (b) => b.fill ?? -1, pred: (b) => b.pred ?? -1 }[state.sort];
  rows = rows.slice().sort(key ? (a, b) => key(b) - key(a) : (a, b) => a.id.localeCompare(b.id));
  return rows;
}

function render() {
  const rows = filtered();
  const all = state.rows.filter((b) => (state.demo || !b.synthetic) && (!state.zone || b.zone === state.zone));
  $$("[data-n]").forEach((s) => {
    const k = s.dataset.n;
    s.textContent = k === "all" ? all.length : all.filter((b) => level(b.fill).key === k).length;
  });
  $("#count").textContent = `${rows.length} bin${rows.length === 1 ? "" : "s"}`;
  $("#table").innerHTML = rows.length ? `<table class="tbl"><thead><tr><th>Bin</th><th>Level</th><th>Fill now (▮ in 6 h)</th><th>In 6 h</th><th>Risk</th><th>Urgency</th><th>Smell</th><th>Battery</th><th>Last data</th></tr></thead><tbody>
    ${rows.map((b) => `<tr class="click" data-id="${esc(b.id)}">
      <td><span class="id">${esc(b.id)}</span>${b.synthetic ? ' <span class="pill lv-none" title="Demo bin (no sensor)">demo</span>' : ' <span class="pill lv-brand" title="Real smart bin">real</span>'}<div class="muted small">${esc(b.name)}${b.zone ? " · " + esc(b.zone) : ""}</div></td>
      <td>${levelPill(b.fill)}</td>
      <td>${fillBar(b.fill, b.pred)}</td>
      <td class="num">${pct(b.pred)}</td>
      <td>${riskPill(b.risk)}</td>
      <td>${urgencyPill(b.urgency)}</td>
      <td>${gasPill(b.gas_index, b.gas_ready)}</td>
      <td class="num">${b.battery_pct == null ? '<span class="muted">–</span>' : (b.battery_pct < CFG.lowBattery ? '<span class="pill rk-high">▲ ' + num(b.battery_pct) + "%</span>" : num(b.battery_pct) + "%")}</td>
      <td class="nowrap small ${b.stale && !b.synthetic ? "" : "muted"}">${b.stale && !b.synthetic ? "▲ " : ""}${ago(b.ts)}</td></tr>`).join("")}</tbody></table>`
    : '<div class="empty"><b>No bins match</b>Change the filters above.</div>';
  $$("#table tr[data-id]").forEach((tr) => (tr.onclick = () => (location.href = "/officer/bins/" + encodeURIComponent(tr.dataset.id))));
  if (map) {
    const pts = rows.filter((b) => b.lat != null);
    map.set("bins", pts.map((b) => binMarker(b, level(b.fill), {
      popup: `<b>${esc(b.id)}</b> ${esc(b.name)}<br>Now ${pct(b.fill)} · in 6 h ${pct(b.pred)}<br><a href="/officer/bins/${encodeURIComponent(b.id)}">Open →</a>`,
    })));
    map.fit(pts.map((b) => [b.lat, b.lng]));
  }
}

async function load() {
  try {
    const d = await api.get("/api/bins");
    state.rows = d.bins;
    syntheticBadge(d.bins.some((b) => b.synthetic));
    const zones = [...new Set(d.bins.map((b) => b.zone).filter(Boolean))].sort();
    const sel = $("#zone");
    if (sel.options.length - 1 !== zones.length) {
      sel.innerHTML = '<option value="">All areas</option>' + zones.map((z) => `<option ${z === state.zone ? "selected" : ""}>${esc(z)}</option>`).join("");
    }
    showError($("#err"), null);
  } catch (e) {
    showError($("#err"), e);
  }
  if (!map) {
    map = await createMap($("#map"), { center: CFG.depot });
    $("#legend").innerHTML = levelLegend();
  }
  render();
}

$$("#lv button").forEach((b) => b.classList.toggle("on", b.dataset.v === state.level));
seg($("#lv"), (v) => { state.level = v; render(); });
$("#zone").onchange = (e) => { state.zone = e.target.value; render(); };
$("#sort").onchange = (e) => { state.sort = e.target.value; render(); };
$("#q").oninput = (e) => { state.q = e.target.value; render(); };
$("#demo").onchange = (e) => { state.demo = e.target.checked; render(); };
poll(load);
