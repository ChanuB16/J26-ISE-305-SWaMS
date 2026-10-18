import { $, api, esc, num, pct, rs, dt, dayName, levelPill, riskPill, urgencyPill, alertList, showError, syntheticBadge, localDate, fullIn, signPct } from "../ui.js";

$("#printed").textContent = dt(Date.now());
$("#rday").value = localDate(0);
$("#rday").max = localDate(0);
$("#rday").onchange = () => ($("#rlink").href = "/api/export/routes.csv?date=" + $("#rday").value);
const setBin = () => ($("#blink").href = `/api/bins/${encodeURIComponent($("#bin").value)}/readings.csv?range=${$("#range").value}`);
$("#bin").onchange = $("#range").onchange = setBin;

function kpi(lab, val, sub) {
  return `<div class="card kpi"><div><div class="lab">${lab}</div><div class="val">${val}</div><div class="sub2">${sub}</div></div></div>`;
}

async function load() {
  let d;
  try {
    d = await api.get("/api/overview");
  } catch (e) {
    showError($("#err"), e);
    return;
  }
  syntheticBadge(d.synthetic);
  const real = d.bins.filter((b) => !b.synthetic);
  $("#bin").innerHTML = d.bins.map((b) => `<option value="${esc(b.id)}" ${b.id === (real[0] || {}).id ? "selected" : ""}>${esc(b.id)} – ${esc(b.name)}</option>`).join("");
  setBin();
  const k = d.kpis;
  $("#kpis").innerHTML = kpi("Bins", k.total, `average fill ${pct(k.avg_fill)}`) + kpi("Critical / warning", `${k.critical} / ${k.warning}`, `${k.high_risk} high overflow risk`) +
    kpi("Trucks on the road", `${k.trucks_on_route} / ${k.trucks_total}`, k.trucks_broken ? `${k.trucks_broken} broken` : "none broken") +
    kpi("Citizen reports", `${d.community.reports_new} new`, `${d.community.reports} in total`);
  const top = d.bins.filter((b) => (b.fill ?? 0) >= 75 || b.risk === "high" || (b.urgency ?? 0) >= 75).slice(0, 15);
  $("#urgent").innerHTML = top.length ? `<table class="tbl"><thead><tr><th>Bin</th><th>Now</th><th>In 6 h</th><th>Risk</th><th>Urgency</th><th>Full in</th></tr></thead><tbody>${top.map((b) =>
    `<tr><td><b>${esc(b.id)}</b> <span class="muted small">${esc(b.name)}</span></td><td>${levelPill(b.fill, true)}</td><td class="num">${pct(b.pred)}</td><td>${riskPill(b.risk)}</td><td>${urgencyPill(b.urgency)}</td><td>${fullIn(b.hours_to_full)}</td></tr>`).join("")}</tbody></table>`
    : '<p class="muted">No bin is above 75% or at high risk.</p>';
  $("#alerts").innerHTML = alertList(d.alerts, { limit: 12, link: false });
  const fc = d.forecast;
  $("#fc").innerHTML = fc.length ? `<table class="tbl"><thead><tr><th>Day</th><th>Forecast</th><th>Normal</th><th>Change</th><th>Busy areas</th></tr></thead><tbody>${fc.map((t) =>
    `<tr><td>${esc(dayName(t.date))}</td><td class="num"><b>${num(t.forecast, 1)} t</b></td><td class="num">${num(t.normal, 1)} t</td><td class="num">${signPct(t.change)}</td><td>${t.busy.length ? "▲ " + esc(t.busy.join(", ")) : ""}${t.holiday ? ' <span class="muted small">' + esc(t.holiday) + "</span>" : ""}</td></tr>`).join("")}</tbody></table>`
    : '<p class="muted">No forecast.</p>';
  const r = d.routes, s = r.summary;
  $("#routes").innerHTML = s ? `<p>${s.planned} bins planned · ${num(s.total_km, 1)} km · diesel ${num(s.fuel_l, 1)} L (${rs(s.cost_lkr)}) · re-plan ${num(s.replan_seconds, 2)} s</p>
    <table class="tbl"><thead><tr><th>Truck</th><th>Status</th><th>Bins</th><th>km</th><th>Start</th></tr></thead><tbody>${r.trucks.map((t) =>
      `<tr><td>${esc(t.name)}</td><td>${esc(t.status)}</td><td>${t.done}/${t.stops.length}</td><td class="num">${num(t.km, 1)}</td><td>${esc(t.start)}</td></tr>`).join("")}</tbody></table>`
    : '<p class="muted">No plan for today.</p>';
}
load();
