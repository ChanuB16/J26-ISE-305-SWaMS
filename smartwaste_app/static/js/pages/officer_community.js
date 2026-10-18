import { $, $$, api, poll, esc, icon, num, ago, dt, dayName, showError, seg, toast, dialog, SERIES } from "../ui.js";
import { barChart } from "../charts.js";

let D = null, filter = "open";
const ST = { new: ["lv-info", "New"], in_progress: ["rk-medium", "In progress"], resolved: ["lv-normal", "✓ Resolved"] };
const kpi = (ic, lab, val, sub) => `<div class="card kpi"><div class="ic">${icon(ic)}</div><div><div class="lab">${lab}</div><div class="val">${val}</div><div class="sub2">${sub}</div></div></div>`;

function render() {
  const d = D;
  const open = d.reports.filter((r) => r.status !== "resolved");
  const pts = d.users.reduce((s, u) => s + u.points, 0);
  $("#kpis").innerHTML = kpi("chat", "Open reports", open.length, `${d.reports.filter((r) => r.status === "new").length} new`) +
    kpi("people", "Citizens with points", d.users.length, `${num(pts)} points in total`) +
    kpi("camera", "Waste photos", d.photos.length, `${d.photos.filter((p) => Number(p.confidence) >= 0.7).length} earned points`) +
    kpi("alert", "Full-bin reports", d.reports.filter((r) => r.type === "overflowing_bin").length, "checked against the sensor");

  const rows = d.reports.filter((r) => filter === "all" || (filter === "open" ? r.status !== "resolved" : r.status === filter));
  $("#reports").innerHTML = rows.length ? `<table class="tbl"><thead><tr><th>When</th><th>Problem</th><th>Bin / place</th><th>By</th><th>Photo</th><th>Status</th></tr></thead><tbody>${rows.map((r) => `
    <tr><td class="nowrap">${dt(r.ts)}<div class="muted small">${ago(r.ts)}</div></td>
    <td><b>${esc(r.type_label)}</b>${r.note ? `<div class="small">${esc(r.note)}</div>` : ""}</td>
    <td>${r.bin_id ? `<a href="/officer/bins/${encodeURIComponent(r.bin_id)}">${esc(r.bin_id)}</a>` : ""}${r.zone ? `<div class="muted small">${esc(r.zone)}</div>` : ""}${r.lat != null ? `<div class="small"><a href="https://www.google.com/maps?q=${r.lat},${r.lng}" target="_blank" rel="noopener">${icon("pin")} map</a></div>` : ""}</td>
    <td>${esc(r.name || r.user || "")}${r.example ? ' <span class="pill lv-none">example</span>' : ""}</td>
    <td>${r.has_photo ? `<img class="thumb" loading="lazy" src="/api/reports/${encodeURIComponent(r.id)}/photo" alt="photo" data-photo="${esc(r.id)}">` : '<span class="muted">–</span>'}</td>
    <td><span class="pill ${ST[r.status] ? ST[r.status][0] : "lv-none"}">${ST[r.status] ? ST[r.status][1] : esc(r.status)}</span>
      <select data-id="${esc(r.id)}" aria-label="Change status" style="margin-top:4px;min-height:30px;padding:3px 6px;font-size:12px">${Object.entries(ST).map(([k, v]) => `<option value="${k}" ${k === r.status ? "selected" : ""}>${v[1].replace("✓ ", "")}</option>`).join("")}</select></td></tr>`).join("")}</tbody></table>`
    : '<div class="empty"><b>No reports here</b>Citizens report problems from their page (Report).</div>';
  $$("#reports select[data-id]").forEach((s) => (s.onchange = async () => {
    try { await api.post(`/api/reports/${encodeURIComponent(s.dataset.id)}/status`, { status: s.value }); toast("Status saved."); P.now(); } catch (e) { toast(e.message, true); }
  }));
  $$("#reports img[data-photo]").forEach((img) => (img.onclick = () => dialog(`<img src="${img.src}" alt="report photo">`)));

  $("#board").innerHTML = d.users.length ? `<table class="tbl"><thead><tr><th>#</th><th>Citizen</th><th>Level</th><th class="right">Points</th></tr></thead><tbody>${d.users.slice(0, 10).map((u, i) =>
    `<tr><td>${i + 1}</td><td>${esc(u.user)}</td><td class="small">${esc(u.level)}</td><td class="num right"><b>${num(u.points)}</b></td></tr>`).join("")}</tbody></table>`
    : '<p class="muted">No points yet. Run “Give reward points” on the System page.</p>';

  const types = {};
  d.photos.forEach((p) => (types[p.waste_type || "?"] = (types[p.waste_type || "?"] || 0) + 1));
  const tk = Object.keys(types).sort((a, b) => types[b] - types[a]);
  if (tk.length) barChart($("#photos"), { categories: tk, horizontal: true, digits: 0, integer: true, labelWidth: 100, series: [{ name: "Photos", color: SERIES[0], values: tk.map((k) => types[k]) }] });
  else $("#photos").innerHTML = '<p class="muted">No photos yet (Component 1 writes them to classifications/).</p>';

  const hist = d.users.flatMap((u) => u.history.map((h) => ({ ...h, user: u.user }))).sort((a, b) => (b.ts || 0) - (a.ts || 0)).slice(0, 15);
  $("#history").innerHTML = hist.length ? `<table class="tbl"><thead><tr><th>When</th><th>Citizen</th><th>For</th><th class="right">Points</th></tr></thead><tbody>${hist.map((h) =>
    `<tr><td class="nowrap small">${ago(h.ts)}</td><td>${esc(h.user)}</td><td class="small">${esc(h.note || h.action)}</td><td class="num right">${h.points ? "+" + h.points : "0"}</td></tr>`).join("")}</tbody></table>`
    : '<p class="muted">Nothing yet.</p>';
  const days = Object.keys(d.guidance || {}).sort();
  $("#tips").innerHTML = days.length ? days.map((day) => {
    const items = Object.entries(d.guidance[day] || {}).flatMap(([z, t]) => (Array.isArray(t) ? t : Object.values(t || {})).map((x) => `<li><b>${esc(z)}</b>: ${esc(x)}</li>`));
    return `<h3 style="margin-top:6px">${esc(dayName(day, true))}</h3><ul class="factor-list small">${items.join("")}</ul>`;
  }).join("") : '<p class="muted">No special tips for the next days.</p>';
}

async function load() {
  try {
    D = await api.get("/api/community");
    showError($("#err"), null);
    if (document.activeElement && document.activeElement.closest("#reports select")) return;
    render();
  } catch (e) {
    showError($("#err"), e);
  }
}
seg($("#st"), (v) => { filter = v; if (D) render(); });
const P = poll(load);
