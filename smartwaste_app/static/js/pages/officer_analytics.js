import { $, $$, api, esc, num, showError, empty, SERIES, dt, CFG } from "../ui.js";
import { barChart, lineChart, scatterChart } from "../charts.js";

const BLUE = SERIES[0], ORANGE = SERIES[1], GREEN = SERIES[2], GOLD = SERIES[3], GREY = "#b9b8b0";
let A = null;
const drawn = {};

function table(rows, cols, hl) {
  if (!rows || !rows.length) return "";
  return `<table class="tbl"><thead><tr>${cols.map((c) => `<th>${esc(c.label || c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r, i) =>
    `<tr${hl && hl(r, i) ? ' style="font-weight:650;background:#f2f8f0"' : ""}>${cols.map((c) => {
      const v = c.get ? c.get(r) : r[c.key || c];
      return `<td class="${typeof v === "number" ? "num" : ""}">${typeof v === "number" ? num(v, c.d ?? 2) : esc(v ?? "")}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table>`;
}
const missing = (name) => empty("No results yet", `${name} is missing. Run the script, then reload.`);
const best = (rows, key, low = true) => rows.reduce((b, r, i) => (b < 0 || (low ? r[key] < rows[b][key] : r[key] > rows[b][key]) ? i : b), -1);

async function drawRQ1() {
  const bin = $("#rq1bin").value, days = $("#rq1days").value;
  let d;
  try { d = await api.get(`/api/rq1?days=${days}${bin ? "&bin=" + encodeURIComponent(bin) : ""}`); } catch (e) { $("#rq1sensors").innerHTML = `<div class="error-bar">${esc(e.message)}</div>`; return; }
  if (!$("#rq1bin").options.length) {
    $("#rq1bin").innerHTML = (d.bins.length ? d.bins : [d.bin]).map((b) => `<option ${b === d.bin ? "selected" : ""}>${esc(b)}</option>`).join("");
  }
  if (!d.count) {
    $("#rq1sensors").innerHTML = empty("No readings in this time", "Switch the bin on and let it send for a while.");
    $("#rq1tiles").innerHTML = "";
    return;
  }
  barChart($("#rq1sensors"), { categories: d.sensors.map((s) => s.name).concat(["All sensors valid"]), horizontal: true, unit: "%", digits: 1, max: 100, labelWidth: 160,
    series: [{ name: "Valid readings", color: GREEN, colors: d.sensors.map(() => GREEN).concat([BLUE]), values: d.sensors.map((s) => s.pct).concat([d.all_valid.pct]) }],
    tip: (i) => `<br>${i < d.sensors.length ? d.sensors[i].valid : d.all_valid.valid} of ${d.count} readings` });
  const t = d.transmission, l = d.latency;
  const tile = (lab, val, sub) => `<div class="tile"><div class="lab">${lab}</div><div class="val">${val}</div><div class="s">${sub}</div></div>`;
  $("#rq1tiles").innerHTML = `<div class="tiles">
    ${tile("Readings", num(d.count), `${dt(d.first)} – ${dt(d.last)}`)}
    ${tile("Transmission success", t.pct == null ? "–" : num(t.pct, 1) + "%", t.expected ? `${num(t.received)} of ${num(t.expected)} received · ${t.starts} power-on(s)` : "no reading numbers (old firmware)")}
    ${tile("Delay bin → Firebase", l ? num(l.median, 2) + " s" : "–", l ? `median · mean ${num(l.mean, 2)} s · 95% under ${num(l.p95, 2)} s · max ${num(l.max, 2)} s` : "needs firmware 1.1.0 (server_ts)")}
    ${tile("Sent later from the buffer", l ? num(l.queued) : "–", "readings kept while WiFi was down")}</div>
    <p class="small muted mt">Board and Firebase clocks can differ by about 1 s – mention this as a limitation.</p>`;
}

function drawC2() {
  drawRQ1();
  $("#rq1bin").onchange = $("#rq1days").onchange = drawRQ1;
  const c = A.c2;
  const m = c.rq2_models;
  if (m.length) {
    const b = best(m, "MAE");
    barChart($("#c2models"), { categories: m.map((r) => r.Model), horizontal: true, unit: "", digits: 2, highlight: [b],
      series: [{ name: "MAE (fill %)", color: BLUE, colors: m.map((r, i) => (r.Type === "baseline" ? GREY : i === b ? GREEN : BLUE)), values: m.map((r) => r.MAE) }],
      tip: (i) => `<br>${esc(m[i].Type)} · RMSE ${num(m[i].RMSE, 2)} · R² ${num(m[i].R2, 3)}` });
    $("#c2modelsT").innerHTML = table(m, [{ label: "Model", key: "Model" }, { label: "Type", key: "Type" }, { label: "MAE", key: "MAE" }, { label: "RMSE", key: "RMSE" }, { label: "R²", key: "R2", d: 3 }, { label: "Validation MAE", key: "Validation MAE" }], (r, i) => i === b) +
      `<p class="small muted mt">Grey = simple baselines, green = best. The live predictions use the best model.</p>`;
  } else $("#c2models").innerHTML = missing("rq2_models.csv");
  const o = c.rq2_overflow;
  if (o.length) {
    barChart($("#c2over"), { categories: o.map((r) => r.Method), horizontal: true, unit: "%", digits: 1, max: 100, labelWidth: 230,
      series: [{ name: "Precision", color: BLUE, values: o.map((r) => r.Precision) }, { name: "Recall", color: ORANGE, values: o.map((r) => r.Recall) }, { name: "F1", color: GREEN, values: o.map((r) => r.F1) }] });
    $("#c2overT").innerHTML = table(o, [{ label: "Method", key: "Method" }, { label: "Precision %", key: "Precision", d: 1 }, { label: "Recall %", key: "Recall", d: 1 }, { label: "F1 %", key: "F1", d: 1 }, { label: "Warnings sent", key: "Alerts", d: 0 }], (r, i) => i === best(o, "F1", false));
  } else $("#c2over").innerHTML = missing("rq2_overflow.csv");
  const f = c.rq2_feature_test;
  if (f.length) barChart($("#c2feat"), { categories: f.map((r) => r["Feature set"]), horizontal: true, digits: 2, labelWidth: 230,
    series: [{ name: "MAE (fill %)", color: BLUE, values: f.map((r) => r.MAE) }], tip: (i) => `<br>${f[i].Inputs} inputs · R² ${num(f[i].R2, 3)}` });
  else $("#c2feat").innerHTML = missing("rq2_feature_test.csv");
  const inp = c.rq2_inputs.slice().sort((a, b) => b["MAE increase"] - a["MAE increase"]).slice(0, 12);
  if (inp.length) barChart($("#c2inputs"), { categories: inp.map((r) => r[""] ?? r.Input ?? Object.values(r)[0]), horizontal: true, digits: 2, labelWidth: 150,
    series: [{ name: "MAE increase", color: BLUE, values: inp.map((r) => r["MAE increase"]) }] });
  else $("#c2inputs").innerHTML = missing("rq2_inputs.csv");
  const u = c.rq3_urgency;
  if (u.length) {
    const k1 = Object.keys(u[0])[1], k2 = Object.keys(u[0])[2];
    barChart($("#c2urg"), { categories: u.map((r) => r.Ranking), horizontal: true, unit: "%", digits: 1, max: 100, labelWidth: 200,
      series: [{ name: k1, color: BLUE, values: u.map((r) => r[k1]) }, { name: k2, color: ORANGE, values: u.map((r) => r[k2]) }] });
  } else $("#c2urg").innerHTML = missing("rq3_urgency.csv");
  const n = c.rq4_nearest;
  if (n.length) {
    barChart($("#c2near"), { categories: n.map((r) => r.Method), horizontal: true, unit: "%", digits: 1, max: 100, labelWidth: 220,
      series: [{ name: "Success (%)", color: GREEN, values: n.map((r) => r["Success (%)"]) }] });
    $("#c2nearT").innerHTML = table(n, [{ label: "Method", key: "Method" }, { label: "Success %", key: "Success (%)", d: 1 }, { label: "Average walk (km)", key: "Average distance (km)" }]);
  } else $("#c2near").innerHTML = missing("rq4_nearest.csv");
}

function drawFC() {
  const c = A.c3;
  const m = c.f2_models;
  if (m.length) {
    const b = best(m, "MAE (t)");
    const base = (r) => /moving|same day/i.test(r.Model);
    barChart($("#fmodels"), { categories: m.map((r) => r.Model), horizontal: true, digits: 3, unit: " t", highlight: [b], labelWidth: 240,
      series: [{ name: "MAE (t)", color: BLUE, colors: m.map((r, i) => (base(r) ? GREY : i === b ? GREEN : BLUE)), values: m.map((r) => r["MAE (t)"]) }],
      tip: (i) => `<br>holidays/festivals ${num(m[i]["MAE holidays and festivals (t)"], 3)} t · normal days ${num(m[i]["MAE normal days (t)"], 3)} t` });
    $("#fmodelsT").innerHTML = table(m, [{ label: "Model", key: "Model" }, { label: "MAE (t)", key: "MAE (t)", d: 3 }, { label: "RMSE (t)", key: "RMSE (t)", d: 3 },
      { label: "MAE % of avg", key: "MAE % of average", d: 1 }, { label: "R² within area", key: "R2 within area", d: 2 }, { label: "MAE holidays (t)", key: "MAE holidays and festivals (t)", d: 3 }, { label: "Train s", key: "Train seconds", d: 1 }], (r, i) => i === b) +
      `<p class="small muted mt">Grey = simple baselines (moving average, same day last week). Green = best.</p>`;
  } else $("#fmodels").innerHTML = missing("f2_models.csv");

  const tp = c.f2_test_predictions;
  if (tp.length) {
    const zones = [...new Set(tp.map((r) => r.zone))].sort();
    const models = Object.keys(tp[0]).filter((k) => !["date", "zone", "actual"].includes(k));
    if (!$("#fzone").options.length) {
      $("#fzone").innerHTML = zones.map((z) => `<option>${esc(z)}</option>`).join("");
      $("#fmodel").innerHTML = models.map((x) => `<option ${/lstm/i.test(x) ? "selected" : ""}>${esc(x)}</option>`).join("");
      $("#fzone").onchange = $("#fmodel").onchange = drawPred;
    }
    drawPred();
  } else $("#fpred").innerHTML = missing("f2_test_predictions.csv");

  const ft = c.f2_feature_test;
  if (ft.length) barChart($("#ffeat"), { categories: ft.map((r) => r.Inputs.replace(/\s+/g, " ")), horizontal: true, digits: 3, unit: " t", labelWidth: 220,
    series: [{ name: "All days", color: BLUE, values: ft.map((r) => r["MAE all days (t)"]) }, { name: "Holidays and festivals", color: ORANGE, values: ft.map((r) => r["MAE holidays and festivals (t)"]) }, { name: "Normal days", color: GREEN, values: ft.map((r) => r["MAE normal days (t)"]) }] });
  else $("#ffeat").innerHTML = missing("f2_feature_test.csv");
  const hw = c.f2_high_waste;
  if (hw.length) barChart($("#fhigh"), { categories: hw.map((r) => r.Method), horizontal: true, unit: "%", digits: 1, max: 100, labelWidth: 230,
    series: [{ name: "F1", color: GREEN, values: hw.map((r) => r.F1) }, { name: "Recall", color: ORANGE, values: hw.map((r) => r.recall) }, { name: "Precision", color: BLUE, values: hw.map((r) => r.precision) }],
    tip: (i) => `<br>${hw[i].warnings} warnings` });
  else $("#fhigh").innerHTML = missing("f2_high_waste.csv");
  const da = c.f2_days_ahead;
  if (da.length) {
    const ks = Object.keys(da[0]).filter((k) => k !== "Days ahead");
    lineChart($("#fdays"), { time: false, series: ks.map((k, i) => ({ name: k, color: SERIES[i], points: da.map((r) => [r["Days ahead"], r[k]]) })), unit: " t", height: 220,
      xFormat: (v) => `${v} day${v === 1 ? "" : "s"} ahead`, xTick: (v) => (Number.isInteger(v) ? String(v) : ""), legend: true, gap: 99 });
  } else $("#fdays").innerHTML = missing("f2_days_ahead.csv");
  const rc = c.f2_rolling_check;
  if (rc.length) {
    const ks = Object.keys(rc[0]).filter((k) => k !== "Test period");
    barChart($("#froll"), { categories: rc.map((r) => r["Test period"].replace(" - ", "\n– ")), twoLineLabels: true, digits: 3, unit: " t", height: 240,
      series: ks.map((k, i) => ({ name: k, color: SERIES[i], values: rc.map((r) => r[k]) })) });
  } else $("#froll").innerHTML = missing("f2_rolling_check.csv");
  const fi = c.f2_inputs.slice().sort((a, b) => b["MAE increase (t)"] - a["MAE increase (t)"]).slice(0, 12);
  if (fi.length) barChart($("#finputs"), { categories: fi.map((r) => r.Input), horizontal: true, digits: 4, unit: " t", labelWidth: 160,
    series: [{ name: "MAE increase (t)", color: BLUE, values: fi.map((r) => r["MAE increase (t)"]) }] });
  else $("#finputs").innerHTML = missing("f2_inputs.csv");
}

function drawPred() {
  const tp = A.c3.f2_test_predictions;
  const z = $("#fzone").value, mdl = $("#fmodel").value;
  const rows = tp.filter((r) => r.zone === z);
  const t = (d) => new Date(d + "T12:00:00").getTime();
  const err = rows.reduce((s, r) => s + Math.abs(r[mdl] - r.actual), 0) / Math.max(1, rows.length);
  lineChart($("#fpred"), {
    series: [{ name: "What really happened", color: "#0b0b0b", points: rows.map((r) => [t(r.date), r.actual]) },
      { name: mdl, color: BLUE, points: rows.map((r) => [t(r.date), r[mdl]]) }],
    unit: " t", height: 260, gap: 3 * 86400000, dots: false,
    xFormat: (v) => new Date(v).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" }),
  });
  $("#fpred").insertAdjacentHTML("beforeend", `<p class="small muted">${esc(z)}: average error ${num(err, 2)} t per day over ${rows.length} test days.</p>`);
}

function drawRT() {
  const c = A.c3;
  const m = c.r2_methods;
  if (m.length) {
    const ours = (r) => /forecast/i.test(r.Method);
    $("#rmethodsT").innerHTML = table(m, [{ label: "Method", key: "Method" }, { label: "km", key: "km", d: 0 }, { label: "Diesel (L)", key: "fuel_l", d: 0 }, { label: "Diesel cost (Rs)", key: "fuel_cost_lkr", d: 0 },
      { label: "Bins emptied", key: "bins_emptied", d: 0 }, { label: "Avg fill when emptied %", key: "avg_fill_collected", d: 1 }, { label: "Overflow bin-days", key: "overflow_bin_days", d: 0 },
      { label: "Service level %", key: "service_level", d: 1 }, { label: "Max solve s", key: "solve_max_s", d: 3 }], (r) => r.Method === "Predictive + forecast");
    const colors = m.map((r) => (ours(r) ? GREEN : /fixed/i.test(r.Method) ? GREY : BLUE));
    barChart($("#rkm"), { categories: m.map((r) => r.Method), horizontal: true, digits: 0, unit: " km", labelWidth: 230, series: [{ name: "km", color: BLUE, colors, values: m.map((r) => r.km) }],
      tip: (i) => `<br>diesel ${num(m[i].fuel_l, 0)} L · Rs ${num(m[i].fuel_cost_lkr, 0)}` });
    barChart($("#rover"), { categories: m.map((r) => r.Method), horizontal: true, digits: 0, labelWidth: 230, series: [{ name: "Overflow bin-days", color: ORANGE, colors: m.map((r) => (ours(r) ? GREEN : ORANGE)), values: m.map((r) => r.overflow_bin_days) }],
      tip: (i) => `<br>festival days ${m[i].overflows_festival_days} · other days ${m[i].overflows_other_days}` });
  } else $("#rmethodsT").innerHTML = missing("r2_methods.csv");
  const tr = c.r2_tradeoff;
  if (tr.length) {
    const meth = [...new Set(tr.map((r) => r.Method))];
    scatterChart($("#rtrade"), { xLabel: "km in 30 days", yLabel: "overflow bin-days", height: 280,
      series: meth.map((x, i) => ({ name: x, color: /fixed/i.test(x) ? "#52514e" : SERIES[i], connect: true, big: /fixed/i.test(x),
        points: tr.filter((r) => r.Method === x).map((r) => ({ x: r.km, y: r["overflow bin-days"], label: r.threshold || "" })) })) });
  } else $("#rtrade").innerHTML = missing("r2_tradeoff.csv");
  const rp = c.r2_replanning;
  if (rp.length) {
    barChart($("#rreplan"), { categories: rp.map((r) => "test " + r.test), digits: 3, unit: " s", height: 200, max: Math.max(0.05, ...rp.map((r) => r.replan_seconds)) * 1.3,
      series: [{ name: "Re-plan seconds", color: GREEN, values: rp.map((r) => r.replan_seconds) }],
      tip: (i) => `<br>${rp[i].closed_roads} roads closed · ${rp[i].bins_left} bins left · new plan ${num(rp[i].new_plan_minutes, 0)} min` });
    const mx = Math.max(...rp.map((r) => r.replan_seconds));
    $("#rreplan").insertAdjacentHTML("beforeend", `<p class="small"><span class="pill lv-normal">✓</span> slowest re-plan ${num(mx, 3)} s – far under the 5 s target.</p>`);
  } else $("#rreplan").innerHTML = missing("r2_replanning.csv");
  const dd = c.r2_daily;
  if (dd.length) {
    const meth = [...new Set(dd.map((r) => r.method))];
    lineChart($("#rdaily"), { series: meth.map((x, i) => ({ name: x, color: SERIES[i], points: dd.filter((r) => r.method === x).map((r) => [new Date(r.day + "T12:00:00").getTime(), r.km]) })),
      unit: " km", height: 260, gap: 2 * 86400000, dots: false, xFormat: (v) => new Date(v).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }) });
  } else $("#rdaily").innerHTML = missing("r2_daily.csv");
}

async function drawSUS() {
  let d;
  try { d = await api.get("/api/sus"); } catch (e) { $("#susChart").innerHTML = `<div class="error-bar">${esc(e.message)}</div>`; return; }
  const rows = d.rows;
  const avg = rows.length ? rows.reduce((s, r) => s + r.score, 0) / rows.length : null;
  const by = (role) => { const x = rows.filter((r) => r.role === role); return x.length ? `${num(x.reduce((s, r) => s + r.score, 0) / x.length, 1)} (${x.length})` : "–"; };
  $("#susK").innerHTML = `<div class="card kpi"><div><div class="lab">Average SUS score</div><div class="val">${avg == null ? "–" : num(avg, 1)}</div><div class="sub2">${avg == null ? "no answers yet" : avg >= d.target ? "✓ meets the target " + d.target : "▲ below the target " + d.target}</div></div></div>
    <div class="card kpi"><div><div class="lab">Answers</div><div class="val">${rows.length}</div><div class="sub2">officers ${by("officer")} · drivers ${by("driver")} · citizens ${by("citizen")}</div></div></div>
    <div class="card kpi"><div><div class="lab">Grade</div><div class="val">${avg == null ? "–" : avg >= 80.3 ? "A" : avg >= 68 ? "B–C" : avg >= 51 ? "D" : "F"}</div><div class="sub2">68 = average, 80.3+ = excellent</div></div></div>`;
  barChart($("#susChart"), { categories: rows.map((r, i) => String(i + 1)), digits: 1, height: 220, max: 100, emptyTitle: "No answers yet", emptyText: "Ask testers to fill in the questionnaire.",
    series: [{ name: "SUS score", color: BLUE, colors: rows.map((r) => (r.score >= d.target ? GREEN : ORANGE)), values: rows.map((r) => r.score) }], markers: [{ name: `target ${d.target}`, color: "#0b0b0b", values: rows.map(() => d.target) }],
    tipTitle: (i) => `Answer ${i + 1} (${rows[i].role})`, tip: (i) => `<br>${dt(rows[i].ts)}` });
  $("#susT").innerHTML = rows.length ? table(rows.slice().reverse(), [{ label: "When", get: (r) => dt(r.ts) }, { label: "Role", key: "role" }, { label: "Score", key: "score", d: 1 }, { label: "Comment", key: "comment" }]) : '<p class="muted">No answers yet.</p>';
}

function drawPNG() {
  const list = [...A.charts.c2.map((f) => ["c2", f]), ...A.charts.c3.map((f) => ["c3", f])];
  $("#pngs").innerHTML = list.length ? list.map(([c, f]) => `<figure class="card figure" style="margin:0"><a href="/results/${c}/${encodeURIComponent(f)}" target="_blank" rel="noopener"><img loading="lazy" src="/results/${c}/${encodeURIComponent(f)}" alt="${esc(f)}"></a><figcaption>${c === "c2" ? "smart_bin_ml" : "waste_forecast_routes"}/results/${esc(f)}</figcaption></figure>`).join("")
    : empty("No PNG charts found", "They appear after the training scripts run (results folders).");
}

function show(t) {
  if (!["c2", "fc", "rt", "sus", "png"].includes(t)) t = "c2";
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === t));
  $$("section[data-p]").forEach((s) => s.classList.toggle("hidden", s.dataset.p !== t));
  if (!A) return;
  if (!drawn[t] || t === "sus") {
    ({ c2: drawC2, fc: drawFC, rt: drawRT, sus: drawSUS, png: drawPNG })[t]();
    drawn[t] = true;
  }
  try { history.replaceState(null, "", "#" + t); } catch { /* ignore */ }
}

async function load() {
  try {
    A = await api.get("/api/analytics");
    const i = A.info;
    const part = (k, name) => `${name}: ${i[k].files} files${i[k].updated ? ", updated " + i[k].updated : ""}${i[k].sample ? ' <span class="pill rk-medium">sample copy shipped with the app – run the scripts for your own results</span>' : ""}`;
    $("#src").innerHTML = `Results read from the ML folders. ${part("c2", "smart_bin_ml")} · ${part("c3", "waste_forecast_routes")}. Synthetic test data unless you replaced it with real data.`;
  } catch (e) {
    showError($("#err"), e);
    return;
  }
  show((location.hash || "#c2").slice(1));
}
$$("#tabs button").forEach((b) => (b.onclick = () => show(b.dataset.t)));
window.addEventListener("hashchange", () => show(location.hash.slice(1)));
load();
