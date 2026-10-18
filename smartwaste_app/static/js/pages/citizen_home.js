import { $, api, poll, esc, icon, num, pct, level, levelPill, levelLegend, showError, CFG, km, dist, toast } from "../ui.js";
import { createMap, binMarker } from "../map.js";

let map = null, me = null, D = null, nearest = null;

function walkUrl(lat, lng) {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}&travelmode=walking`;
}

function drawMap() {
  if (!map || !D) return;
  map.set("bins", D.bins.map((b) => binMarker(b, level(b.fill), {
    highlight: nearest && nearest.best && nearest.best.id === b.id,
    popup: `<b>${esc(b.name)}</b><br>${level(b.fill).label} · ${pct(b.fill)} full<br><a href="${walkUrl(b.lat, b.lng)}" target="_blank" rel="noopener">Directions</a>`,
  })));
  const extra = [];
  if (me) extra.push({ kind: "me", lat: me[0], lng: me[1], hover: "You are here", z: 1000 });
  if (me && nearest && nearest.best) extra.push({ kind: "line", points: [me, [nearest.best.lat, nearest.best.lng]], color: "#2a78d6", width: 3, dash: true });
  map.set("me", extra);
  map.fit(me ? [me, ...(nearest && nearest.best ? [[nearest.best.lat, nearest.best.lng]] : [])] : D.bins.map((b) => [b.lat, b.lng]), !!me);
}

function renderList() {
  const rows = D.bins.map((b) => ({ ...b, d: me ? km(me[0], me[1], b.lat, b.lng) : null }))
    .sort((a, b) => (a.d ?? 0) - (b.d ?? 0) || (a.fill ?? 0) - (b.fill ?? 0)).slice(0, 6);
  $("#nearSub").textContent = me ? "Closest first." : "Bins with the most space. Share your location to see the closest.";
  $("#list").innerHTML = rows.length ? `<table class="tbl"><tbody>${rows.map((b) => `<tr><td><b>${esc(b.name)}</b><div class="muted small">${esc(b.zone)}${b.d != null ? " · " + dist(b.d) : ""}</div></td><td class="right">${levelPill(b.fill)}</td></tr>`).join("")}</tbody></table>`
    : '<p class="muted">No bins yet.</p>';
}

async function findFrom(lat, lng) {
  me = [lat, lng];
  try {
    nearest = await api.get(`/api/nearest?lat=${lat}&lng=${lng}`);
  } catch (e) {
    toast(e.message, true);
    return;
  }
  const b = nearest.best;
  $("#result").innerHTML = b ? `<div class="card" style="border:2px solid #0ca30c"><div class="card-head"><h2>${icon("check")} Go to: ${esc(b.name)}</h2>${levelPill(b.fill)}</div>
      <p>${dist(b.km)} away (straight line) · ${pct(b.fill)} full now · ${esc(b.zone)}</p>
      <div class="row"><a class="btn" href="${walkUrl(b.lat, b.lng)}" target="_blank" rel="noopener">${icon("nav")} Directions</a>
      <a class="btn ghost" href="/citizen/report?bin=${encodeURIComponent(b.id)}">Report a problem here</a></div>
      ${nearest.others.length ? `<p class="small muted mt">Also with space: ${nearest.others.map((o) => `${esc(o.name)} (${dist(o.km)}, ${pct(o.fill)})`).join(" · ")}</p>` : ""}</div>`
    : `<div class="warn-bar">No bin with space within ${CFG.maxKm} km.${nearest.nearest_any ? ` The closest bin is ${esc(nearest.nearest_any.name)} (${dist(nearest.nearest_any.km)}, ${pct(nearest.nearest_any.fill)} full). Please report it if it is overflowing.` : ""}</div>`;
  drawMap();
  renderList();
}

async function load() {
  try {
    D = await api.get("/api/citizen");
    showError($("#err"), null);
  } catch (e) {
    showError($("#err"), e);
    return;
  }
  if (!map) {
    map = await createMap($("#map"), { center: CFG.depot, onClick: (lat, lng) => findFrom(lat, lng) });
    $("#legend").innerHTML = "";
    $("#map").insertAdjacentHTML("afterend", `<div class="mt">${levelLegend()}</div>`);
  }
  drawMap();
  renderList();
  const lv = D.level;
  $("#points").innerHTML = `<div class="row" style="align-items:flex-end"><div class="bigscore">${num(D.points)}</div><div class="muted small">points<br>${esc(lv.name)}${D.rank ? ` · #${D.rank} of ${D.players}` : ""}</div></div>`;
  const tips = Object.entries(D.tips || {}).flatMap(([z, t]) => (Array.isArray(t) ? t : Object.values(t || {})).map((x) => `<li><b>${esc(z)}</b>: ${esc(x)}</li>`));
  $("#tips").innerHTML = tips.length ? `<ul class="factor-list small">${tips.join("")}</ul>` : '<ul class="factor-list small"><li>Separate food waste, plastic and paper.</li><li>If a bin is full, use the app to find another one – do not leave bags next to it.</li><li>Take a photo of your sorted waste with the scanner app to earn points.</li></ul>';
  $("#busy").innerHTML = D.busy_today ? `<div class="warn-bar">▲ Today is a busy waste day${D.busy_today.holiday ? " (" + esc(D.busy_today.holiday) + ")" : ""}. Bins may fill faster. Points for confirmed reports and photos are doubled on busy days in that area.</div>` : "";
}

$("#locBtn").onclick = () => {
  if (!navigator.geolocation || !window.isSecureContext) {
    toast("Your browser cannot share the location here (it needs https or localhost). Tap the map instead.", true);
    return;
  }
  $("#locBtn").disabled = true;
  navigator.geolocation.getCurrentPosition((p) => { $("#locBtn").disabled = false; findFrom(p.coords.latitude, p.coords.longitude); },
    () => { $("#locBtn").disabled = false; toast("Location was not shared. Tap the map where you are.", true); }, { enableHighAccuracy: true, timeout: 10000 });
};
poll(load, 30);
