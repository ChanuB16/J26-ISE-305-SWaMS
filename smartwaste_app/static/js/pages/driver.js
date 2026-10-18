import { $, $$, api, poll, esc, icon, num, pct, ago, hhmm, level, levelPill, showError, toast, TRUCK, CFG, km, dist, localDate } from "../ui.js";
import { createMap } from "../map.js";

const S = { truck: null, data: null, madeAt: null };
let map = null, myPos = null;
const KEY = "sw_driver_truck";

function navUrl(lat, lng) {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}&travelmode=driving`;
}

function render() {
  const d = S.data;
  const trucks = d.trucks;
  if (!trucks.length) {
    $("#next").innerHTML = `<h2>No route today</h2><p class="muted">The route planner has not made a plan yet.</p>`;
    return;
  }
  const sel = $("#truck");
  if (sel.options.length !== trucks.length) sel.innerHTML = trucks.map((t) => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("");
  if (!S.truck || !trucks.some((t) => t.id === S.truck)) {
    let saved = null;
    try { saved = localStorage.getItem(KEY); } catch { /* ignore */ }
    S.truck = (d.my_truck && trucks.some((t) => t.id === d.my_truck) && d.my_truck) || (saved && trucks.some((t) => t.id === saved) && saved) || trucks[0].id;
  }
  sel.value = S.truck;
  const t = trucks.find((x) => x.id === S.truck);
  const color = TRUCK[t.index % TRUCK.length];
  const s = d.summary;
  $("#planInfo").textContent = s ? `Plan made ${hhmm(s.made_at)} (${s.trigger || ""})` : "";
  if (S.madeAt && t.made_at && t.made_at !== S.madeAt) {
    $("#changed").innerHTML = `<div class="warn-bar">${icon("refresh")} Your route changed at ${hhmm(t.made_at)}${s && s.trigger ? " (" + esc(s.trigger) + ")" : ""}. Check the next stop.</div>`;
  }
  S.madeAt = t.made_at || S.madeAt;
  const stops = t.stops;
  const idx = stops.findIndex((x) => !x.done);
  const done = stops.filter((x) => x.done).length;
  const from = myPos || (t.lat != null ? [t.lat, t.lng] : null);
  if (t.status === "broken") {
    $("#next").innerHTML = `<div class="muted">TRUCK REPORTED BROKEN</div><h2>${esc(t.name)} is out of service</h2><p class="muted">Your bins were given to the other trucks (if the planner is running). Press “Truck fixed” when it works again.</p>`;
  } else if (!stops.length) {
    $("#next").innerHTML = `<div class="muted">${esc(t.name)}</div><h2>No stops for you today</h2><p class="muted">${esc(t.note || "Stay at the depot until the planner sends a route.")}</p>`;
  } else if (idx < 0) {
    $("#next").innerHTML = `<div class="muted">${esc(t.name)} · all ${stops.length} bins emptied</div><h2>${icon("check")} Route finished</h2><p class="muted">Drive back to the depot (${esc(CFG.depot_name)}).</p>
      <div class="row mt"><a class="btn white big" href="${navUrl(CFG.depot[0], CFG.depot[1])}" target="_blank" rel="noopener">${icon("nav")} Navigate to depot</a></div>`;
  } else {
    const n = stops[idx];
    const away = from ? km(from[0], from[1], n.lat, n.lng) : null;
    $("#next").innerHTML = `<div class="row between"><span class="muted">NEXT STOP · ${idx + 1} of ${stops.length}</span>${levelPill(n.fill_pct, true)}</div>
      <h2>${esc(n.bin_id)} · ${esc(n.name || "")}</h2>
      <div class="row muted small">${icon("clock")} arrive about <b style="color:#fff">${esc(n.eta || "–")}</b>${away != null ? ` · ${icon("pin")} ${dist(away)} away (straight line)` : ""}</div>
      <div class="progress mt"><span style="width:${(done / stops.length) * 100}%"></span></div>
      <div class="small muted" style="margin-top:4px">${done} of ${stops.length} bins emptied · ${num(t.km, 1)} km route</div>
      <div class="row mt"><a class="btn ghost big" href="${navUrl(n.lat, n.lng)}" target="_blank" rel="noopener">${icon("nav")} Navigate</a>
      <button class="btn white big" id="doneBtn">${icon("check")} Mark as emptied</button></div>`;
    $("#doneBtn").onclick = async () => {
      $("#doneBtn").disabled = true;
      try {
        await api.post(`/api/routes/${d.date}/${encodeURIComponent(t.id)}/stops/${idx}/done`);
        toast(`${n.bin_id} marked as emptied.`);
      } catch (e) { toast(e.message, true); }
      P.now();
    };
  }
  $("#routeSum").textContent = stops.length ? `${stops.length} stops · ${num(t.km, 1)} km · ${num(t.minutes, 0)} min` : "";
  $("#stops").innerHTML = stops.length ? `<ol class="timeline">${stops.map((x, k) => `<li class="${x.done ? "done" : k === idx ? "next" : ""}"><span class="dot">${x.done ? "✓" : k + 1}</span>
    <span class="when">${esc(x.eta || "")}</span><b>${esc(x.bin_id)}</b> ${esc(x.name || "")}<div>${x.done ? '<span class="small muted">emptied</span>' : levelPill(x.fill_pct, true)}</div></li>`).join("")}</ol>` : '<p class="muted">No stops.</p>';
  const em = d.emptied_today || [];
  $("#emptied").innerHTML = em.length ? `<table class="tbl"><tbody>${em.map((x) => `<tr><td>${icon("check")} <b>${esc(x.id)}</b> ${esc(x.name)}</td><td class="right small muted">${hhmm(x.at)}</td></tr>`).join("")}</tbody></table>` : '<p class="muted">None yet.</p>';
  $("#broken").innerHTML = t.status === "broken" ? `<button class="btn big block" data-s="available">${icon("check")} Truck fixed</button>` : `<button class="btn danger big block" data-s="broken">${icon("alert")} Report truck broken</button>`;
  $$("#broken button").forEach((b) => (b.onclick = async () => {
    if (b.dataset.s === "broken" && !confirm("Report this truck as broken? Your bins will be moved to other trucks.")) return;
    try { await api.post(`/api/trucks/${encodeURIComponent(t.id)}/status`, { status: b.dataset.s }); toast(b.dataset.s === "broken" ? "Reported. The planner will move your bins." : "Marked as fixed."); } catch (e) { toast(e.message, true); }
    P.now();
  }));
  // map
  const items = [];
  if (t.path && t.path.length > 1) items.push({ kind: "line", points: t.path, color, width: 5 });
  stops.forEach((x, k) => items.push({ kind: "num", n: k + 1, lat: x.lat, lng: x.lng, color: x.done ? "#898781" : k === idx ? "#1e6b3c" : color, z: k === idx ? 800 : 400,
    popup: `<b>${esc(x.bin_id)}</b> ${esc(x.name || "")}<br>${esc(x.eta || "")} · ${pct(x.fill_pct)}<br><a href="${navUrl(x.lat, x.lng)}" target="_blank" rel="noopener">Navigate</a>` }));
  items.push({ kind: "depot", lat: CFG.depot[0], lng: CFG.depot[1], text: "Depot" });
  if (t.lat != null) items.push({ kind: "truck", lat: t.lat, lng: t.lng, text: t.name, color, z: 900 });
  if (myPos) items.push({ kind: "me", lat: myPos[0], lng: myPos[1], hover: "You" });
  map.set("route", items);
  map.fit(stops.map((x) => [x.lat, x.lng]).concat([CFG.depot]));
}

async function load() {
  try {
    S.data = await api.get("/api/routes?date=" + localDate(0));
    showError($("#err"), null);
  } catch (e) {
    showError($("#err"), e);
    return;
  }
  if (!map) map = await createMap($("#map"), { center: CFG.depot });
  render();
}

$("#truck").onchange = (e) => {
  S.truck = e.target.value;
  S.madeAt = null;
  $("#changed").innerHTML = "";
  try { localStorage.setItem(KEY, S.truck); } catch { /* ignore */ }
  render();
};
if (navigator.geolocation && window.isSecureContext) {
  navigator.geolocation.watchPosition((p) => { myPos = [p.coords.latitude, p.coords.longitude]; }, () => {}, { enableHighAccuracy: true, maximumAge: 30000 });
}
const P = poll(load, 10);
