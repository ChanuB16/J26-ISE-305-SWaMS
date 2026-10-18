import { $, $$, api, esc, icon, ago, dt, pct, level, km, dist, toast, dialog } from "../ui.js";

let D = null, me = null, photo = null;
const want = new URLSearchParams(location.search).get("bin");
const ST = { new: ["lv-info", "Received"], in_progress: ["rk-medium", "In progress"], resolved: ["lv-normal", "✓ Resolved"] };

function fillBins() {
  const sel = $("#bin");
  const cur = sel.value || want || "";
  const rows = D.bins.map((b) => ({ ...b, d: me ? km(me[0], me[1], b.lat, b.lng) : null })).sort((a, b) => (a.d ?? 0) - (b.d ?? 0) || a.name.localeCompare(b.name));
  sel.innerHTML = '<option value="">– not at a bin –</option>' + rows.map((b) => `<option value="${esc(b.id)}" ${b.id === cur ? "selected" : ""}>${esc(b.name)} (${esc(b.zone)})${b.d != null ? " – " + dist(b.d) : ""} – ${level(b.fill).label}</option>`).join("");
}

function renderMine() {
  const r = D.reports;
  $("#mine").innerHTML = r.length ? `<div class="alerts">${r.map((x) => `<div class="alert"><span class="sym" style="background:#1e6b3c">${icon("check", "i")}</span><div style="flex:1">
      <div class="row between"><div class="t">${esc(x.type_label)}</div><span class="pill ${ST[x.status] ? ST[x.status][0] : "lv-none"}">${ST[x.status] ? ST[x.status][1] : esc(x.status)}</span></div>
      <div class="s">${x.bin_id ? esc(x.bin_id) + " · " : ""}${dt(x.ts)} (${ago(x.ts)})</div>
      ${x.note ? `<div class="small">${esc(x.note)}</div>` : ""}
      <div class="small">${x.points != null ? (x.points > 0 ? `<b>+${x.points} points</b> – ${esc(x.points_note || "")}` : `No points – ${esc(x.points_note || "")}`) : '<span class="muted">Points are checked soon.</span>'}</div>
      ${x.has_photo ? `<img class="thumb mt" src="/api/reports/${encodeURIComponent(x.id)}/photo" alt="your photo" data-big>` : ""}</div></div>`).join("")}</div>`
    : '<div class="empty"><b>No reports yet</b>Your reports and their status appear here.</div>';
  $$("#mine img[data-big]").forEach((i) => (i.onclick = () => dialog(`<img src="${i.src}" alt="photo">`)));
}

async function load() {
  try {
    D = await api.get("/api/citizen");
    fillBins();
    renderMine();
  } catch (e) {
    $("#mine").innerHTML = `<div class="error-bar">${esc(e.message)}</div>`;
  }
}

// make the photo small (max 1024 px, JPEG) so it uploads fast on mobile data
function shrink(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const s = Math.min(1, 1024 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * s);
      c.height = Math.round(img.height * s);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      let q = 0.8, out = c.toDataURL("image/jpeg", q);
      while (out.length > 450000 && q > 0.3) { q -= 0.15; out = c.toDataURL("image/jpeg", q); }
      resolve(out);
    };
    img.onerror = () => reject(new Error("This file is not a photo."));
    img.src = URL.createObjectURL(file);
  });
}

$("#photo").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    photo = await shrink(f);
    $("#photoText").innerHTML = `<img src="${photo}" alt="your photo">Tap to change the photo`;
  } catch (err) { toast(err.message, true); photo = null; }
};
$$("#types input").forEach((i) => (i.onchange = () => ($("#binHint").textContent = i.value === "overflowing_bin" ? "(needed for an overflowing bin)" : "(if it is at a bin)")));
$("#locBtn").onclick = () => {
  if (!navigator.geolocation || !window.isSecureContext) { toast("Location needs https or localhost. Choose the bin from the list.", true); return; }
  navigator.geolocation.getCurrentPosition((p) => {
    me = [p.coords.latitude, p.coords.longitude];
    $("#locText").textContent = `Location added (${me[0].toFixed(5)}, ${me[1].toFixed(5)}). Closest bins are first in the list.`;
    fillBins();
  }, () => toast("Location was not shared.", true), { enableHighAccuracy: true, timeout: 10000 });
};
$("#form").onsubmit = async (e) => {
  e.preventDefault();
  const type = ($("#types input:checked") || {}).value;
  const m = $("#msg");
  $("#send").disabled = true;
  m.className = "msg";
  m.textContent = "Sending…";
  try {
    await api.post("/api/reports", { type, bin_id: $("#bin").value, note: $("#note").value, photo, lat: me ? me[0] : null, lng: me ? me[1] : null });
    m.className = "msg ok";
    m.textContent = "Thank you! Your report was sent to the council.";
    $("#note").value = "";
    photo = null;
    $("#photo").value = "";
    $("#photoText").innerHTML = `${icon("camera")}<br>Tap to take or choose a photo`;
    load();
  } catch (err) {
    m.className = "msg bad";
    m.textContent = err.message;
  } finally {
    $("#send").disabled = false;
  }
};
load();
setInterval(() => { if (!document.hidden) load(); }, 30000);
