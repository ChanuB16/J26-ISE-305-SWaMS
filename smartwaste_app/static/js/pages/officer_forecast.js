import { $, api, poll, esc, icon, num, ago, dayName, showError, seg, empty, signPct } from "../ui.js";
import { barChart } from "../charts.js";

let mode = "daily", D = null;
const BLUE = "#2a78d6", BUSY = "#eda100", INK = "#0b0b0b";

function kpi(ic, cls, lab, val, sub) {
  return `<div class="card kpi"><div class="ic ${cls}">${icon(ic)}</div><div><div class="lab">${lab}</div><div class="val">${val}</div><div class="sub2">${sub}</div></div></div>`;
}
const sign = signPct;
const two = (d) => dayName(d).replace(/ (\d+) (\w+)$/, "\n$1 $2");

function render() {
  const d = D;
  if (!d) return;
  const T = d.totals;
  if (!T.length) {
    $("#kpis").innerHTML = "";
    $("#chMain").innerHTML = empty("No forecast yet", "Run “7-day waste forecast” on the System page (or python f3_forecasts_to_firebase.py).");
    $("#table").innerHTML = $("#areas").innerHTML = $("#why").innerHTML = $("#tips").innerHTML = "";
    $("#info").textContent = "";
    return;
  }
  const info = d.info || {};
  $("#info").innerHTML = `Model: <b>${esc(info.model || "?")}</b>${info.made_at ? ` · made ${ago(info.made_at)}` : ""}${info.synthetic ? ' · <span class="pill lv-none">trained on synthetic data</span>' : ""}${d.source === "file" ? ' · <span class="pill rk-medium">from the saved CSV (Firebase has no forecasts)</span>' : ""}`;
  const t0 = T[0], t1 = T[1] || null;
  const sum = T.reduce((s, t) => s + t.forecast, 0), norm = T.reduce((s, t) => s + t.normal, 0);
  const busyDays = T.filter((t) => t.busy.length).length;
  $("#kpis").innerHTML =
    kpi("calendar", "", `Today (${dayName(t0.date)})`, `${num(t0.forecast, 1)}<small> t</small>`, `${sign(t0.change)} vs normal`) +
    kpi("trend", "info", "Tomorrow", t1 ? `${num(t1.forecast, 1)}<small> t</small>` : "–", t1 ? `${sign(t1.change)} vs normal` : "") +
    kpi("chart", "", `Next ${T.length} days`, `${num(sum, 0)}<small> t</small>`, `${sign(norm ? ((sum - norm) / norm) * 100 : 0)} vs normal`) +
    kpi("alert", busyDays ? "warning" : "", "Busy days ahead", busyDays, busyDays ? T.filter((t) => t.busy.length).map((t) => dayName(t.date).split(" ")[0]).join(", ") : "no high-waste days");

  if (mode === "daily") {
    $("#mainTitle").textContent = "All areas: tonnes per day";
    $("#mainSub").textContent = "Bars = forecast · black line = a normal day for that weekday · orange ▲ = busy day in at least one area";
    barChart($("#chMain"), {
      categories: T.map((t) => two(t.date)), twoLineLabels: true, height: 260, unit: " t", digits: 1, values: true,
      valueFormat: (v) => num(v, 1),
      series: [{ name: "Forecast", color: BLUE, colors: T.map((t) => (t.busy.length ? BUSY : BLUE)), values: T.map((t) => t.forecast) }],
      markers: [{ name: "Normal day", color: INK, values: T.map((t) => t.normal) }],
      tipTitle: (i) => dayName(T[i].date, true),
      tip: (i) => `<br>Normal: ${num(T[i].normal, 1)} t (${sign(T[i].change)})${T[i].busy.length ? "<br>▲ Busy: " + esc(T[i].busy.join(", ")) : ""}${T[i].holiday ? "<br>" + esc(T[i].holiday) : ""}${T[i].rain_mm != null ? "<br>Rain: " + num(T[i].rain_mm, 1) + " mm" : ""}`,
    });
  } else {
    $("#mainTitle").textContent = `Each area: tonnes in the next ${T.length} days`;
    $("#mainSub").textContent = "Bars = forecast for the whole week · black line = a normal week";
    const zs = d.zones;
    const wk = zs.map((z) => d.days.reduce((s, day) => s + (Number((d.by_zone[z][day] || {}).forecast_t) || 0), 0));
    const wn = zs.map((z) => d.days.reduce((s, day) => s + (Number((d.by_zone[z][day] || {}).normal_t) || 0), 0));
    barChart($("#chMain"), {
      categories: zs, horizontal: true, unit: " t", digits: 1, labelWidth: 120,
      series: [{ name: "Forecast (week)", color: BLUE, values: wk }],
      markers: [], tip: (i) => `<br>Normal week: ${num(wn[i], 1)} t (${sign(wn[i] ? ((wk[i] - wn[i]) / wn[i]) * 100 : 0)})`,
    });
  }

  // table
  const zs = d.zones;
  $("#table").innerHTML = `<table class="tbl"><thead><tr><th>Area</th>${d.days.map((day) => `<th>${esc(dayName(day))}</th>`).join("")}<th>Week</th></tr></thead><tbody>
    ${zs.map((z) => {
      let w = 0;
      const cells = d.days.map((day) => {
        const f = d.by_zone[z][day];
        if (!f) return "<td>–</td>";
        w += Number(f.forecast_t) || 0;
        return `<td class="${f.high_waste ? "c-filling" : ""}"><b class="num">${num(f.forecast_t, 1)} t</b>${f.high_waste ? ' <span class="pill rk-medium" title="Busy day: top 10% for this area">▲ busy</span>' : ""}<div class="small muted">${sign(f.change_pct)}</div></td>`;
      }).join("");
      return `<tr><td><b>${esc(z)}</b></td>${cells}<td class="num"><b>${num(w, 1)} t</b></td></tr>`;
    }).join("")}
    <tr><td><b>All areas</b></td>${T.map((t) => `<td class="num"><b>${num(t.forecast, 1)} t</b><div class="small muted">${sign(t.change)}</div></td>`).join("")}<td class="num"><b>${num(sum, 1)} t</b></td></tr>
    <tr><td class="muted">Holiday / event</td>${T.map((t) => `<td class="small">${esc(t.holiday || "")}</td>`).join("")}<td></td></tr>
    <tr><td class="muted">Rain (mm)</td>${T.map((t) => `<td class="small num">${t.rain_mm == null ? "" : num(t.rain_mm, 1)}</td>`).join("")}<td></td></tr>
    </tbody></table>`;

  // why busy
  const reasons = T.filter((t) => t.busy.length || t.holiday || Math.abs(t.change) >= 8);
  $("#why").innerHTML = reasons.length ? `<div class="alerts">${reasons.map((t) => `<div class="alert ${t.busy.length ? "warning" : ""}"><span class="sym">${t.busy.length ? "▲" : "i"}</span><div>
      <div class="t">${esc(dayName(t.date, true))}: ${num(t.forecast, 1)} t (${sign(t.change)})</div>
      <div class="s">${[t.holiday && esc(t.holiday), t.busy.length && "busy in " + esc(t.busy.join(", ")), t.rain_mm != null && t.rain_mm >= 10 && `rain ${num(t.rain_mm, 0)} mm`].filter(Boolean).join(" · ") || "different from a normal day"}</div></div></div>`).join("")}</div>`
    : '<p class="muted">All days look normal.</p>';
  const gd = d.guidance || {};
  const tipDays = Object.keys(gd).sort();
  $("#tips").innerHTML = tipDays.length ? tipDays.map((day) => {
    const items = Object.entries(gd[day] || {}).flatMap(([z, tips]) => (Array.isArray(tips) ? tips : Object.values(tips || {})).map((x) => `<li><b>${esc(z)}</b>: ${esc(x)}</li>`));
    return items.length ? `<h3 style="margin-top:6px">${esc(dayName(day, true))}</h3><ul class="factor-list small">${items.join("")}</ul>` : "";
  }).join("") : '<p class="muted small">No tips yet (run “Crew tips” on the System page).</p>';

  // small multiples
  $("#areas").innerHTML = zs.map((z, i) => `<div class="card"><h2>${esc(z)}</h2><div id="area${i}"></div></div>`).join("");
  zs.forEach((z, i) => {
    const fs = d.days.map((day) => d.by_zone[z][day] || null);
    barChart($("#area" + i), {
      categories: d.days.map((day) => dayName(day).split(" ")[0]), height: 170, unit: " t", digits: 1,
      series: [{ name: "Forecast", color: BLUE, colors: fs.map((f) => (f && f.high_waste ? BUSY : BLUE)), values: fs.map((f) => (f ? Number(f.forecast_t) : null)) }],
      markers: [{ name: "Normal day", color: INK, values: fs.map((f) => (f ? Number(f.normal_t) : null)) }],
      tipTitle: (k) => `${z}, ${dayName(d.days[k])}`,
      tip: (k) => (fs[k] ? `<br>Normal: ${num(fs[k].normal_t, 1)} t (${sign(fs[k].change_pct)})${fs[k].high_waste ? "<br>▲ busy day" : ""}` : ""),
    });
  });
}

async function load() {
  try {
    D = await api.get("/api/forecast");
    showError($("#err"), null);
    render();
  } catch (e) {
    showError($("#err"), e);
  }
}
seg($("#mode"), (v) => { mode = v; render(); });
poll(load, 60);
