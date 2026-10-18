import { $, $$, api, poll, esc, icon, ago, dt, showError, toast, CFG } from "../ui.js";

const openLogs = new Set();
const STATE = { running: ["lv-normal", "● running"], finished: ["lv-info", "✓ finished"], failed: ["rk-high", "✖ failed"], stopped: ["lv-none", "stopped"], "not started": ["lv-none", "not started"], missing: ["rk-high", "script not found"] };
let editingAuto = false;

function jobCard(j, setup = false) {
  const st = STATE[j.state] || ["lv-none", j.state];
  const running = j.state === "running";
  const done = setup && j.done && j.done.exists;
  const pill = setup && !running ? (done ? `<span class="pill lv-normal">✓ done ${esc(dt(j.done.updated))}</span>` : j.state === "failed" ? `<span class="pill ${st[0]}">${st[1]}</span>` : '<span class="pill lv-none">not done</span>') : `<span class="pill ${st[0]}">${st[1]}</span>`;
  return `<div class="card flat" style="background:var(--surface-2)">
    <div class="card-head"><h2>${esc(j.title)} <span class="pill lv-brand">${esc(j.component)}</span></h2>${pill}</div>
    <p class="small" style="margin-top:-4px">${esc(j.what)}${j.minutes ? ` <span class="muted">(${j.minutes.startsWith("under") ? "" : "about "}${esc(j.minutes)} min${j.internet ? ", needs internet" : ""})</span>` : ""}</p>
    <p class="small muted"><code>python ${esc(j.script)} ${esc(j.args.join(" "))}</code>${j.started ? ` · started ${ago(j.started)}${j.by ? " by " + esc(j.by) : ""}` : ""}${!setup ? (j.service ? " · keeps running" : " · runs once") : ""}</p>
    ${j.blocked && !running ? `<p class="small" style="color:#8a3412">▲ ${esc(j.blocked)}</p>` : ""}
    ${j.last_line ? `<p class="small" style="font-family:ui-monospace,monospace;background:#fff;border:1px solid var(--line);border-radius:8px;padding:5px 8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(j.last_line)}">${esc(j.last_line)}</p>` : ""}
    <div class="row">${running ? `<button class="btn danger small" data-act="stop" data-job="${esc(j.name)}">${icon("stop")} Stop</button>` :
      `<button class="btn ${setup ? "ghost " : ""}small" data-act="start" data-job="${esc(j.name)}" ${j.state === "missing" || j.blocked ? "disabled" : ""}>${icon("play")} ${j.service ? "Start" : setup && done ? "Run again" : "Run"}</button>`}
      <button class="btn ghost small" data-log="${esc(j.name)}">${openLogs.has(j.name) ? "Hide" : "Show"} output</button></div>
    <div class="log mt ${openLogs.has(j.name) ? "" : "hidden"}" id="log-${esc(j.name)}"></div></div>`;
}

function renderHealth(checks) {
  const bad = checks.filter((c) => c.ok === false).length, warn = checks.filter((c) => c.ok === "warn").length;
  $("#healthSum").innerHTML = bad ? `<span class="pill rk-high">✖ ${bad} to fix</span>` : warn ? `<span class="pill rk-medium">▲ ${warn} warning</span>` : '<span class="pill lv-normal">✓ all good</span>';
  $("#health").innerHTML = `<div class="alerts">${checks.map((c) => {
    const cls = c.ok === true ? "" : c.ok === "warn" ? "warning" : "critical";
    const sym = c.ok === true ? "✓" : c.ok === "warn" ? "▲" : "✖";
    const fix = c.fix ? (c.fix.pipeline ? `<button class="btn small" data-pipe="${esc(c.fix.pipeline)}">${esc(c.fix.label)}</button>` : `<button class="btn small" data-act="start" data-job="${esc(c.fix.job)}">${esc(c.fix.label)}</button>`) : "";
    return `<div class="alert ${cls}" style="${c.ok === true ? "border-left-color:#0ca30c;background:#f6fbf6" : ""}"><span class="sym" style="${c.ok === true ? "background:#0ca30c" : ""}">${sym}</span>
      <div style="flex:1"><div class="t">${esc(c.title)}</div><div class="s">${esc(c.detail)}</div></div>${fix}</div>`;
  }).join("")}</div>`;
}

function renderAuto(a) {
  if (editingAuto) return;
  $("#a_autostart").checked = a.autostart;
  $("#a_forecast").checked = a.forecast_daily;
  $("#a_time").value = a.forecast_time;
  $("#a_rewards").value = a.rewards_minutes;
}

function renderPipe(p, setup) {
  const run = Object.values(p).sort((a, b) => b.started - a.started)[0];
  const busy = run && run.state === "running";
  $$("#setupBtns button").forEach((b) => (b.disabled = busy));
  const allDone = setup.filter((j) => j.name !== "c3_roads_demo").every((j) => j.done && j.done.exists) || (setup.find((j) => j.name === "c3_roads_demo") || {}).done?.exists && setup.filter((j) => !j.name.startsWith("c3_roads")).every((j) => j.done && j.done.exists);
  if (!run || (!busy && allDone && run.state !== "finished")) { $("#pipe").innerHTML = ""; return; }
  const pill = { running: '<span class="pill lv-normal">● running</span>', finished: '<span class="pill lv-info">✓ finished</span>', failed: '<span class="pill rk-high">✖ failed</span>', stopped: '<span class="pill lv-none">stopped</span>' }[run.state];
  $("#pipe").innerHTML = `<div class="card flat mb" style="background:var(--surface-2)"><div class="card-head"><h3>Setup “${esc(run.name === "all" ? "all steps" : run.name === "c2" ? "Component 2" : "Component 3")}” ${pill}</h3>
    ${busy ? `<button class="btn danger small" data-pstop="${esc(run.name)}">${icon("stop")} Stop</button>` : ""}</div>
    <div class="log" style="max-height:180px">${esc(run.log.join("\n"))}</div></div>`;
}

async function act(fn, okText) {
  try { await fn(); if (okText) toast(okText); } catch (e) { toast(e.message, true); }
  J.now();
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.act) {
    b.disabled = true;
    openLogs.add(b.dataset.job);
    act(() => api.post(`/api/jobs/${b.dataset.job}/${b.dataset.act}`), b.dataset.act === "start" ? "Started. Its output is shown below it." : "Stopped.");
  } else if (b.dataset.log) {
    const n = b.dataset.log;
    if (openLogs.has(n)) openLogs.delete(n); else openLogs.add(n);
    J.now();
  } else if (b.dataset.pipe) {
    act(() => api.post(`/api/setup/${b.dataset.pipe}/run`), "Setup started. It takes a few minutes – you can keep using the app.");
  } else if (b.dataset.pstop) {
    act(() => api.post(`/api/setup/${b.dataset.pstop}/stop`), "Stopping after the current step…");
  }
});

async function saveAuto() {
  const m = $("#amsg");
  try {
    const r = await api.post("/api/automation", { autostart: $("#a_autostart").checked, forecast_daily: $("#a_forecast").checked, forecast_time: $("#a_time").value.trim(), rewards_minutes: Number($("#a_rewards").value || 0) });
    m.className = "msg ok"; m.textContent = "Saved.";
    editingAuto = false;
    renderAuto(r.automation);
  } catch (err) { m.className = "msg bad"; m.textContent = err.message; }
}
["#a_autostart", "#a_forecast"].forEach((s) => ($(s).onchange = saveAuto));
["#a_time", "#a_rewards"].forEach((s) => { $(s).onfocus = () => (editingAuto = true); $(s).onchange = saveAuto; });

async function loadJobs() {
  let d, h;
  try { [d, h] = await Promise.all([api.get("/api/jobs"), api.get("/api/health")]); showError($("#err"), null); } catch (e) { showError($("#err"), e); return; }
  renderHealth(h.checks);
  renderAuto(d.automation);
  renderPipe(d.pipelines, d.setup);
  if (document.activeElement && document.activeElement.closest("#jobs,#setup")) document.activeElement.blur();
  $("#setup").innerHTML = d.setup.map((j) => jobCard(j, true)).join("");
  $("#jobs").innerHTML = d.jobs.map((j) => jobCard(j)).join("");
  for (const n of openLogs) {
    try {
      const l = await api.get(`/api/jobs/${n}/log`);
      const el = $("#log-" + n);
      if (el) { el.textContent = l.lines.join("\n") || "(no output yet)"; el.scrollTop = el.scrollHeight; }
    } catch { /* ignore */ }
  }
}

function renderUsers(d) {
  const trucks = d.trucks || [];
  $("#nt").innerHTML = '<option value="">– any –</option>' + trucks.map((t) => `<option>${esc(t)}</option>`).join("");
  $("#users").innerHTML = `<table class="tbl"><thead><tr><th>User name</th><th>Name</th><th>Role</th><th>Truck</th><th>Last login</th><th>Active</th><th></th></tr></thead><tbody>${d.users.map((u) => {
    const me = u.username === CFG.user.username;
    return `<tr><td><b>${esc(u.username)}</b>${me ? ' <span class="pill lv-brand">you</span>' : ""}</td><td>${esc(u.name)}</td>
      <td>${me ? esc(d.roles[u.role]) : `<select data-u="${esc(u.username)}" data-f="role" style="width:auto">${Object.entries(d.roles).map(([k, v]) => `<option value="${k}" ${k === u.role ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`}</td>
      <td>${u.role === "driver" && !me ? `<select data-u="${esc(u.username)}" data-f="truck" style="width:auto"><option value="">– any –</option>${[...new Set([...trucks, u.truck].filter(Boolean))].map((t) => `<option ${t === u.truck ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>` : esc(u.truck || "")}</td>
      <td class="small">${u.last_login ? dt(u.last_login) : "never"}</td>
      <td>${me ? "yes" : `<input type="checkbox" data-u="${esc(u.username)}" data-f="active" ${u.active ? "checked" : ""} aria-label="Active">`}</td>
      <td class="nowrap">${me ? "" : `<button class="btn ghost small" data-pw="${esc(u.username)}">New password</button> <button class="btn danger small" data-del="${esc(u.username)}">Remove</button>`}</td></tr>`;
  }).join("")}</tbody></table>`;
  $$("#users [data-f]").forEach((el) => (el.onchange = async () => {
    const v = el.type === "checkbox" ? el.checked : el.value;
    try { renderUsers(await api.patch(`/api/users/${encodeURIComponent(el.dataset.u)}`, { [el.dataset.f]: v }).then((r) => ({ ...d, ...r }))); toast("Saved."); } catch (e) { toast(e.message, true); }
  }));
  $$("#users [data-del]").forEach((b) => (b.onclick = async () => {
    if (!confirm(`Remove the account ${b.dataset.del}?`)) return;
    try { renderUsers({ ...d, ...(await api.del(`/api/users/${encodeURIComponent(b.dataset.del)}`)) }); toast("Removed."); } catch (e) { toast(e.message, true); }
  }));
  $$("#users [data-pw]").forEach((b) => (b.onclick = async () => {
    const pw = prompt(`New password for ${b.dataset.pw} (8 or more characters):`);
    if (!pw) return;
    try { await api.patch(`/api/users/${encodeURIComponent(b.dataset.pw)}`, { password: pw }); toast("Password changed."); } catch (e) { toast(e.message, true); }
  }));
}

async function loadUsers() {
  try { renderUsers(await api.get("/api/users")); } catch (e) { showError($("#err"), e); }
}

$("#addUser").onsubmit = async (e) => {
  e.preventDefault();
  const m = $("#umsg");
  try {
    const d = await api.post("/api/users", { username: $("#nu").value.trim().toLowerCase(), name: $("#nn").value.trim(), role: $("#nr").value, truck: $("#nr").value === "driver" ? $("#nt").value : "", password: $("#np").value });
    renderUsers(d);
    m.className = "msg ok";
    m.textContent = `Account ${$("#nu").value} added. They log in on the “Municipal staff” tab.`;
    e.target.reset();
  } catch (err) {
    m.className = "msg bad";
    m.textContent = err.message;
  }
};
const J = poll(loadJobs, 4);
loadUsers();
