import { $, api, esc, icon, toast } from "../ui.js";

let photo = null;      // data:image/jpeg;base64,....
let busy = false;

// Make the photo small (max 1024 px, JPEG) so classification is fast on CPU
// and the upload fits inside the 600 KB limit on /api/classify.
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
      let q = 0.85, out = c.toDataURL("image/jpeg", q);
      while (out.length > 450000 && q > 0.3) { q -= 0.15; out = c.toDataURL("image/jpeg", q); }
      resolve(out);
    };
    img.onerror = () => reject(new Error("This file is not a photo."));
    img.src = URL.createObjectURL(file);
  });
}

function pct(x) { return Math.round(Number(x) * 100) + "%"; }

// Colour the "sym" circle green for a confident answer, orange for "not sure".
function bar(frac, colour) {
  const w = Math.min(100, Math.max(0, Math.round(frac * 100)));
  return `<div class="fillbar"><div class="track"><span style="width:${w}%;background:${colour}"></span></div><b>${w}%</b></div>`;
}

function renderResult(r) {
  if (!r) {
    $("#result").innerHTML = '<div class="empty"><b>No photo yet</b>Pick a photo on the left to see the result here.</div>';
    return;
  }
  const sure = r.reliable;
  const title = sure ? esc(r.label || r.category) : "Not sure";
  const colour = sure ? "#1e6b3c" : "#c98a00";
  const sym = sure ? icon("check", "i") : icon("alert", "i");
  const top3 = (r.top3 || []).map((t) =>
    `<tr><td>${esc(t.category)}</td><td class="num right">${pct(t.confidence)}${t.category === r.category ? " <b>&larr;</b>" : ""}</td></tr>`
  ).join("");
  const pointsNote = sure && r.confidence >= 0.70
    ? '<p class="small"><b>+10 points</b> will be added at the next rewards check.</p>'
    : (sure
      ? '<p class="small muted">No points (confidence below 70%).</p>'
      : '<p class="small muted">Try a clearer photo with one item in good light.</p>');

  $("#result").innerHTML = `
    <div class="alerts"><div class="alert ${sure ? "" : "warning"}">
      <span class="sym" style="background:${colour}">${sym}</span>
      <div style="flex:1">
        <div class="t">${title}</div>
        <div class="s">${bar(r.confidence, colour)}</div>
        <div class="small muted">${(r.inference_seconds || 0).toFixed(2)} s</div>
        ${r.guidance ? `<p class="small">${esc(r.guidance)}</p>` : ""}
        ${pointsNote}
      </div>
    </div></div>
    <div class="card-head mt"><h3>All chances</h3></div>
    <table class="tbl"><tbody>${top3}</tbody></table>
  `;
}

$("#photo").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    photo = await shrink(f);
    $("#photoText").innerHTML = `<img src="${photo}" alt="your photo">Tap to change the photo`;
    $("#send").disabled = false;
    $("#msg").className = "msg";
    $("#msg").textContent = "";
    renderResult(null);
  } catch (err) {
    toast(err.message, true);
    photo = null;
    $("#send").disabled = true;
  }
};

$("#form").onsubmit = async (e) => {
  e.preventDefault();
  if (!photo || busy) return;
  busy = true;
  const m = $("#msg");
  $("#send").disabled = true;
  m.className = "msg";
  m.textContent = "Checking the photo… (the first time can take 5–10 seconds)";
  try {
    const r = await api.post("/api/classify", { photo, lang: $("#lang").value });
    renderResult(r);
    m.className = "msg ok";
    m.textContent = r.reliable
      ? "Done. Your scan was sent to the council."
      : "Done. The AI was not sure – try another photo.";
  } catch (err) {
    m.className = "msg bad";
    m.textContent = err.message;
  } finally {
    busy = false;
    $("#send").disabled = !photo;
  }
};
