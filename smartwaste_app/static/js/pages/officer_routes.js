import { $, $$, api, poll, esc, icon, num, pct, ago, hhmm, rs, level, levelPill, showError, toast, TRUCK, CFG, dayName, localDate } from "../ui.js";
import { createMap, binMarker } from "../map.js";

const S = { date: localDate(0), mode: null, data: null, lastPlan: 0, waiting: false };
let map = null;

function kpi(lab, val, sub = "") {
  return `<div class="card kpi"><div><div class="lab">${lab}</div><div class="val">${val}</div><div class="sub2">${sub}</div></div></div>`;
}
const today = () => S.date === localDate(0);

function setMode(m) {
  S.mode = S.mode === m ? null : m;
  $("#btnClosure").classList.toggle("on", S.mode === "closure");
  $("#btnJam").classList.toggle("on", S.mode === "jam");
  $("#msg").className = "msg";
  $("#msg").textContent = S.mode ? `Now click the road on the map where the ${S.mode === "jam" ? "traffic jam" : "closure"} is.` : "";
}

async function mapClick(lat, lng) {
  if (!S.mode || !today()) return;
  const kind = S.mode;
  setMode(kind);
  try {
    await api.post("/api/traffic", { kind, lat, lng });
    waitForPlan(kind === "jam" ? "Traffic jam saved." : "Road closure saved.");
  } catch (e) { toast(e.message, true); }
}

function waitForPlan(text) {
  S.waiting = Date.now();
  $("#msg").className = "msg ok";
  $("#msg").textContent = text + " Waiting for the route planner to make new routes…";
  setTimeout(() => P.now(), 1500);
}

function render() {
  const d = S.data;
  if (!d) return;
  const s = d.summary;
  const trucks = d.trucks;
  const running = (S.jobs || []).includes("routes");
  $("#plannerWarn").innerHTML = today() && !running ? `<div class="warn-bar">The live route planner is not running here, so road closures and re-plans will not change the routes. Start “Live route planner” on the <a href="/officer/system">System page</a> (or run <code>python r3_live_routes.py</code>).</div>` : "";
  $("#tools").style.display = today() ? "" : "none";
  $("#csv").href = "/api/export/routes.csv?date=" + S.date;
  $("#planInfo").innerHTML = s ? `Plan made at <b>${hhmm(s.made_at)}</b> (${esc(s.trigger || "")}) · roads: ${esc(s.roads || "?")} · solver: ${esc(s.solver || "?")}` : "No plan for this day.";
  if (S.waiting && s && s.made_at > S.waiting - 2000) {
    $("#msg").className = "msg ok";
    $("#msg").textContent = `New routes ready: made ${num(s.replan_seconds, 2)} s after the change was noticed.`;
    S.waiting = false;
  }
  $("#kpis").innerHTML = s ? kpi("Bins planned", s.planned, `${(s.skipped || []).length} not collected`) +
    kpi("Distance", `${num(s.total_km, 1)}<small> km</small>`, `${trucks.filter((t) => t.stops.length).length} trucks`) +
    kpi("Diesel", `${num(s.fuel_l, 1)}<small> L</small>`, rs(s.cost_lkr)) +
    kpi("Re-plan time", `${num(s.replan_seconds, 2)}<small> s</small>`, s.replan_seconds != null && s.replan_seconds <= 5 ? "✓ under 5 s (NFR01)" : "target: under 5 s")
    : "";

  // map
  const items = [], pts = [];
  const onRoute = new Set();
  trucks.forEach((t) => {
    const color = TRUCK[t.index % TRUCK.length];
    if (t.path && t.path.length > 1) { items.push({ kind: "line", points: t.path, color, width: 5 }); pts.push(...t.path); }
    t.stops.forEach((st, k) => {
      onRoute.add(st.bin_id);
      items.push({ kind: "num", n: k + 1, lat: st.lat, lng: st.lng, color: st.done ? "#898781" : color, z: 500,
        popup: `<b>${esc(st.bin_id)}</b> ${esc(st.name || "")}<br>${esc(t.name)}, stop ${k + 1}<br>Arrive ${esc(st.eta || "")} · ${pct(st.fill_pct)} full${st.done ? "<br>✓ emptied" : ""}`,
        hover: `${esc(t.name)} stop ${k + 1}: ${esc(st.bin_id)} (${st.eta || ""})` });
      pts.push([st.lat, st.lng]);
    });
  });
  map.set("routes", items);
  map.set("bins", (d.bins || []).filter((b) => !onRoute.has(b.id)).map((b) => binMarker(b, level(b.fill), { size: 14, sym: "", popup: `<b>${esc(b.id)}</b> ${esc(b.name)}<br>${pct(b.fill)} full now, ${pct(b.pred)} in 6 h<br>not on a route` })));
  map.set("traffic", d.traffic.map((z) => ({ kind: "zone", lat: z.lat, lng: z.lng, radius: z.radius_m || 300, color: z.kind === "jam" ? "#eb6834" : "#d03b3b", fillOpacity: z.kind === "jam" ? 0.12 : 0.22,
    popup: `${z.kind === "jam" ? "Traffic jam" : "Road closed"}<br>${esc(z.note || "")}<br>until ${hhmm(z.until)}` })));
  map.set("trucks", [{ kind: "depot", lat: CFG.depot[0], lng: CFG.depot[1], text: "Depot", popup: esc(CFG.depot_name) },
    ...trucks.filter((t) => t.lat != null).map((t) => ({ kind: "truck", lat: t.lat, lng: t.lng, text: t.name, color: TRUCK[t.index % TRUCK.length], z: 900, popup: `${esc(t.name)}: ${esc(t.status)}<br>GPS ${ago(t.gps_ts)}` }))]);
  map.fit(pts.length ? pts.concat([CFG.depot]) : (d.bins || []).map((b) => [b.lat, b.lng]).concat([CFG.depot]));
  $("#legend").innerHTML = trucks.map((t) => `<span><span class="swatch" style="background:${TRUCK[t.index % TRUCK.length]};width:16px;height:4px"></span>${esc(t.name)}</span>`).join("") +
    '<span><span class="swatch" style="background:#898781;border-radius:50%"></span>emptied stop</span><span><span class="swatch" style="background:rgba(208,59,59,.35);border:2px solid #d03b3b;border-radius:50%"></span>road closed</span><span><span class="swatch" style="background:rgba(235,104,52,.2);border:2px solid #eb6834;border-radius:50%"></span>traffic jam</span><span class="muted">small dots = bins not on a route</span>';

  // traffic list
  $("#traffic").innerHTML = d.traffic.length ? `<div class="alerts">${d.traffic.map((z) => `<div class="alert ${z.kind === "jam" ? "serious" : "critical"}"><span class="sym">${z.kind === "jam" ? "!" : "✖"}</span><div style="flex:1">
      <div class="t">${z.kind === "jam" ? "Traffic jam" : "Road closed"}</div><div class="s">${esc(z.note || "")} · until ${hhmm(z.until)}</div></div>
      ${today() ? `<button class="btn ghost small" data-del="${esc(z.id)}">Remove</button>` : ""}</div>`).join("")}</div>`
    : '<p class="muted">All roads open.</p>';
  $$("#traffic [data-del]").forEach((b) => (b.onclick = async () => {
    try { await api.del("/api/traffic/" + encodeURIComponent(b.dataset.del)); waitForPlan("Road opened."); } catch (e) { toast(e.message, true); }
  }));
  const sk = (s && s.skipped) || [];
  $("#skipped").innerHTML = sk.length ? `<ul class="factor-list small">${sk.map((x) => `<li><a href="/officer/bins/${encodeURIComponent(x.bin_id)}">${esc(x.bin_id)}</a>: ${esc(x.reason)}</li>`).join("")}</ul>` : '<p class="muted">Every bin that needed collecting is on a route.</p>';

  const em = d.emptied_today || [];
  $("#emptied").innerHTML = !today() ? '<p class="muted">Only shown for today.</p>' : em.length ? `<ul class="factor-list small">${em.map((x) => `<li>${hhmm(x.at)} – <a href="/officer/bins/${encodeURIComponent(x.id)}">${esc(x.id)}</a> ${esc(x.name)}</li>`).join("")}</ul>` : '<p class="muted">No bin emptied yet today.</p>';
  // trucks
  $("#trucks").innerHTML = trucks.length ? trucks.map((t) => {
    const color = TRUCK[t.index % TRUCK.length];
    const st = t.status === "broken" ? '<span class="pill lv-critical">✖ broken</span>' : t.status === "on_route" ? '<span class="pill lv-normal">● on the road</span>' : t.status === "at_depot" ? '<span class="pill lv-none">at depot</span>' : '<span class="pill lv-info">available</span>';
    const next = t.stops.findIndex((x) => !x.done);
    return `<div class="card truck-card" style="border-left-color:${color}">
      <div class="card-head"><h2>${icon("truck")} ${esc(t.name)} ${st}</h2>
      ${today() ? `<button class="btn ${t.status === "broken" ? "" : "danger"} small" data-truck="${esc(t.id)}" data-status="${t.status === "broken" ? "available" : "broken"}">${t.status === "broken" ? "Truck fixed" : "Truck broken"}</button>` : ""}</div>
      <p class="small muted">${t.stops.length ? `${t.done}/${t.stops.length} bins emptied · ${num(t.km, 1)} km · ${num(t.minutes, 0)} min · start ${esc(t.start)} · diesel ${num(t.fuel_l, 1)} L (${rs(t.cost_lkr)})` : esc(t.note || "No stops in this plan.")}</p>
      ${t.stops.length ? `<ol class="timeline">${t.stops.map((x, k) => `<li class="${x.done ? "done" : k === next ? "next" : ""}"><span class="dot">${x.done ? "✓" : k + 1}</span>
        <span class="when">${esc(x.eta || "")}</span><a href="/officer/bins/${encodeURIComponent(x.bin_id)}">${esc(x.bin_id)}</a> ${esc(x.name || "")} ${levelPill(x.fill_pct, true)}${x.done ? ' <span class="small muted">emptied</span>' : ""}</li>`).join("")}</ol>` : ""}
    </div>`;
  }).join("") : '<div class="card"><div class="empty"><b>No trucks</b>The route planner adds them.</div></div>';
  $$("#trucks [data-truck]").forEach((b) => (b.onclick = async () => {
    try {
      await api.post(`/api/trucks/${encodeURIComponent(b.dataset.truck)}/status`, { status: b.dataset.status });
      waitForPlan(b.dataset.status === "broken" ? "Truck marked broken. Its bins go to the other trucks." : "Truck marked fixed.");
    } catch (e) { toast(e.message, true); }
  }));
}

async function loadDays() {
  try {
    const d = await api.get("/api/route-days");
    const days = [...new Set([localDate(0), ...d.days])].sort().reverse();
    $("#date").innerHTML = days.map((x) => `<option value="${x}" ${x === S.date ? "selected" : ""}>${x === localDate(0) ? "Today, " : ""}${esc(dayName(x))}</option>`).join("");
  } catch { /* keep today only */ }
}

async function load() {
  try {
    const [d, st] = await Promise.all([api.get("/api/routes?date=" + S.date), api.get("/api/status")]);
    S.data = d;
    S.jobs = st.jobs_running;
    showError($("#err"), null);
  } catch (e) {
    showError($("#err"), e);
  }
  if (!map) map = await createMap($("#map"), { center: CFG.depot, onClick: mapClick });
  render();
}

$("#date").innerHTML = `<option value="${S.date}">Today</option>`;
$("#date").onchange = (e) => { S.date = e.target.value; setMode(null); P.now(); };
$("#btnClosure").onclick = () => setMode("closure");
$("#btnJam").onclick = () => setMode("jam");
$("#btnClear").onclick = async () => { try { await api.del("/api/traffic"); waitForPlan("All roads are open again."); } catch (e) { toast(e.message, true); } };
$("#btnReplan").onclick = async () => { try { await api.post("/api/replan"); waitForPlan("Re-plan asked."); } catch (e) { toast(e.message, true); } };
loadDays();
const P = poll(load, 5);
