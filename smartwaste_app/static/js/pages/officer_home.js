import { $, api, poll, esc, icon, num, pct, ago, hours, greeting, level, LEVELS, levelLegend, fillBar, riskPill,
  urgencyPill, alertList, showError, syntheticBadge, TRUCK, CFG, dayName, rs, fullIn, signPct } from "../ui.js";
import { createMap, binMarker } from "../map.js";
import { barChart } from "../charts.js";

let map = null;

function kpi(ic, cls, lab, val, sub) {
  return `<div class="card kpi"><div class="ic ${cls}">${icon(ic)}</div><div><div class="lab">${lab}</div><div class="val">${val}</div><div class="sub2">${sub}</div></div></div>`;
}

async function load() {
  let d;
  try {
    d = await api.get("/api/overview");
    showError($("#err"), null);
  } catch (e) {
    showError($("#err"), e);
    return;
  }
  syntheticBadge(d.synthetic);
  const k = d.kpis;
  $("#hello").textContent = `${greeting()}, ${CFG.user.name}`;
  $("#sub").textContent = `${k.total} bins (${k.real} real, ${k.total - k.real} demo) · data ${ago(d.at)}`;
  $("#kpis").innerHTML =
    kpi("bin", "", "Total bins", k.total, `average fill ${pct(k.avg_fill)}`) +
    kpi("alert", "critical", "Critical (90%+)", k.critical, `${k.high_risk} with high overflow risk`) +
    kpi("trend", "warning", "Warning (75–89%)", k.warning, `${k.filling} filling (50–74%)`) +
    kpi("truck", "info", "Trucks on the road", `${k.trucks_on_route}<small> / ${k.trucks_total}</small>`, k.trucks_broken ? `${k.trucks_broken} broken` : "none broken");

  // map
  if (!map) {
    map = await createMap($("#map"), { center: CFG.depot });
    $("#legend").innerHTML = levelLegend();
  }
  const withLoc = d.bins.filter((b) => b.lat != null);
  map.set("bins", withLoc.map((b) => binMarker(b, level(b.fill), {
    popup: `<b>${esc(b.id)}</b> ${esc(b.name)}<br>${esc(b.zone)}<br>Now: <b>${pct(b.fill)}</b> (${level(b.fill).label})<br>In 6 hours: ${pct(b.pred)}<br>Urgency: ${b.urgency ?? "–"}<br><a href="/officer/bins/${encodeURIComponent(b.id)}">Open bin →</a>`,
  })));
  const trucks = (d.routes.trucks || []).filter((t) => t.lat != null);
  map.set("trucks", [{ kind: "depot", lat: CFG.depot[0], lng: CFG.depot[1], text: "Depot" },
    ...trucks.map((t) => ({ kind: "truck", lat: t.lat, lng: t.lng, text: t.name, color: TRUCK[t.index % TRUCK.length], hover: `${esc(t.name)}: ${esc(t.status)}` }))]);
  map.fit(withLoc.map((b) => [b.lat, b.lng]).concat([CFG.depot]));

  // alerts
  $("#alerts").innerHTML = alertList(d.alerts, { limit: 40 });
  const crit = d.alerts.filter((a) => a.level === "critical" || a.level === "warning").length;
  $("#alertCount").innerHTML = d.alerts.length ? `<span class="pill ${crit ? "lv-critical" : "lv-info"}">${d.alerts.length} warning${d.alerts.length > 1 ? "s" : ""}</span>` : "";

  // urgent table
  const top = d.bins.filter((b) => b.urgency != null || b.fill != null).slice(0, 8);
  $("#urgent").innerHTML = top.length ? `<table class="tbl"><thead><tr><th>Bin</th><th>Fill now (▮ = in 6 h)</th><th>Overflow risk</th><th>Urgency</th><th>Full in</th></tr></thead><tbody>${top.map((b) => `
    <tr class="click" data-id="${esc(b.id)}"><td><span class="id">${esc(b.id)}</span><div class="muted small">${esc(b.name)} · ${esc(b.zone)}</div></td>
    <td>${fillBar(b.fill, b.pred)}</td><td>${riskPill(b.risk)}</td><td>${urgencyPill(b.urgency)}</td><td class="nowrap">${fullIn(b.hours_to_full)}</td></tr>`).join("")}</tbody></table>`
    : '<div class="empty"><b>No bins yet</b>Start the bin, or add demo bins on the System page.</div>';
  $("#urgent").querySelectorAll("tr[data-id]").forEach((tr) => (tr.onclick = () => (location.href = "/officer/bins/" + encodeURIComponent(tr.dataset.id))));

  // level counts
  const counts = { normal: k.normal, filling: k.filling, warning: k.warning, critical: k.critical };
  const total = Math.max(1, k.normal + k.filling + k.warning + k.critical);
  $("#levels").innerHTML = `<div class="parts">${Object.entries(counts).map(([key, n]) => {
    const l = LEVELS[key];
    return `<a class="part" href="/officer/bins?level=${key}" style="color:inherit;text-decoration:none"><div class="top-line"><span>${l.sym} ${l.label} <span class="muted small">${l.range}</span></span><b class="num">${n}</b></div>
      <div class="track"><span style="width:${(n / total) * 100}%;background:${l.color}"></span></div></a>`;
  }).join("")}</div>`;
  const c = d.community;
  $("#community").innerHTML = `<div class="tiles">
    <div class="tile"><div class="lab">${icon("chat")} New citizen reports</div><div class="val">${c.reports_new}<small> / ${c.reports}</small></div></div>
    <div class="tile"><div class="lab">${icon("gift")} Green points given</div><div class="val">${num(c.points)}</div><div class="s">${c.citizens} citizens</div></div></div>
    <p class="small mt"><a href="/officer/community">Open community →</a></p>`;

  // forecast
  const fc = d.forecast || [];
  $("#fcInfo").textContent = fc.length ? `Tonnes for all 6 areas. Model: ${d.forecast_info.model || "?"}${d.forecast_source === "file" ? " (from the saved file)" : ""}. Line = a normal day.` : "";
  barChart($("#fcChart"), {
    categories: fc.map((t) => dayName(t.date).replace(/ (\d+) (\w+)$/, "\n$1 $2")),
    twoLineLabels: true,
    series: [{ name: "Forecast", color: "#2a78d6", colors: fc.map((t) => (t.busy.length ? "#eda100" : "#2a78d6")), values: fc.map((t) => t.forecast) }],
    markers: [{ name: "Normal day", color: "#0b0b0b", values: fc.map((t) => t.normal) }],
    unit: " t", digits: 1, height: 220,
    tip: (i) => `<br>Normal day: ${num(fc[i].normal, 1)} t (${signPct(fc[i].change)})${fc[i].busy.length ? "<br>▲ Busy day: " + esc(fc[i].busy.join(", ")) : ""}${fc[i].holiday ? "<br>" + esc(fc[i].holiday) : ""}`,
    emptyTitle: "No forecast yet", emptyText: "Run the 7-day forecast job on the System page.",
  });

  // routes
  const r = d.routes;
  const s = r.summary;
  $("#routes").innerHTML = (s ? `<p class="small muted">Plan made ${ago(s.made_at)} (${esc(s.trigger || "")}). ${s.planned} bins, ${num(s.total_km, 1)} km, diesel ${num(s.fuel_l, 1)} L (${rs(s.cost_lkr)}).</p>` :
    '<p class="small muted">No plan for today yet. Start the route planner on the System page.</p>') +
    (r.trucks.length ? r.trucks.map((t) => {
      const n = t.stops.length, done = t.done;
      const st = t.status === "broken" ? '<span class="pill lv-critical">✖ broken</span>' : t.status === "on_route" ? '<span class="pill lv-normal">● on the road</span>' : '<span class="pill lv-none">at depot</span>';
      return `<div class="mt"><div class="row between"><b><span class="swatch" style="background:${TRUCK[t.index % TRUCK.length]}"></span> ${esc(t.name)}</b>${st}</div>
        <div class="fillbar" style="width:100%;margin-top:6px"><span class="track"><span style="width:${n ? (done / n) * 100 : 0}%;background:${TRUCK[t.index % TRUCK.length]}"></span></span><b style="min-width:70px">${done}/${n} bins</b></div>
        <div class="muted small">${n ? `${num(t.km, 1)} km · ${num(t.minutes, 0)} min · start ${esc(t.start)}` : esc(t.note || "no stops")}</div></div>`;
    }).join("") : '<div class="empty"><b>No trucks yet</b></div>');
}

poll(load);
