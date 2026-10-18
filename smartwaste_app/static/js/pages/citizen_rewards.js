import { $, api, poll, esc, num, ago, showError } from "../ui.js";

async function load() {
  let d;
  try { d = await api.get("/api/citizen"); showError($("#err"), null); } catch (e) { showError($("#err"), e); return; }
  const lv = d.level;
  const span = lv.next_min ? lv.next_min - lv.min : 1;
  const prog = lv.next_min ? Math.min(100, ((d.points - lv.min) / span) * 100) : 100;
  $("#hero").innerHTML = `<div class="muted">MY GREEN REWARDS · ${esc(d.user)}</div>
    <div class="row" style="align-items:flex-end;margin-top:8px"><div class="points-big">${num(d.points)}</div><div style="padding-bottom:6px">green points</div></div>
    <div style="margin-top:10px"><span class="pill" style="background:#fff;color:#154d2b">${esc(lv.name)}</span>${d.rank ? ` <span class="muted small">#${d.rank} of ${d.players} citizens</span>` : ""}</div>
    <div class="lvl-track"><span style="width:${prog}%"></span></div>
    <div class="small muted">${lv.next_name ? `${num(lv.next_min - d.points)} more points to ${esc(lv.next_name)}` : "Top level reached – thank you!"}</div>`;
  $("#hist").innerHTML = d.history.length ? `<table class="tbl"><tbody>${d.history.slice(0, 20).map((h) => `<tr><td>${esc(h.note || h.action)}<div class="muted small">${ago(h.ts)}</div></td><td class="num right"><b>${h.points > 0 ? "+" + h.points : "0"}</b></td></tr>`).join("")}</tbody></table>`
    : '<div class="empty"><b>No points yet</b>Report a full bin or scan your sorted waste to start.</div>';
  $("#board").innerHTML = d.top.length ? `<table class="tbl"><tbody>${d.top.map((u, i) => `<tr${u.user === d.user ? ' style="background:#eef7ef;font-weight:650"' : ""}><td>${i + 1}</td><td>${esc(u.user)}${u.user === d.user ? " (you)" : ""}<div class="muted small">${esc(u.level)}</div></td><td class="num right">${num(u.points)}</td></tr>`).join("")}</tbody></table>`
    : '<p class="muted">Nobody has points yet.</p>';
}
poll(load, 30);
