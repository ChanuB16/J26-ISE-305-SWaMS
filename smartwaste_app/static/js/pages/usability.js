import { $, $$, api, num } from "../ui.js";

api.get("/api/status").catch(() => {});

const Q = [
  "I think that I would like to use this app frequently.",
  "I found the app unnecessarily complex.",
  "I thought the app was easy to use.",
  "I think that I would need the support of a technical person to be able to use this app.",
  "I found the various functions in this app were well integrated.",
  "I thought there was too much inconsistency in this app.",
  "I would imagine that most people would learn to use this app very quickly.",
  "I found the app very cumbersome to use.",
  "I felt very confident using the app.",
  "I needed to learn a lot of things before I could get going with this app.",
];
$("#qs").innerHTML = Q.map((q, i) => `<fieldset class="sus-q" style="border:0;margin:0"><legend><b>${i + 1}.</b> ${q}</legend>
  <div class="scale"><span class="end">Disagree</span>${[1, 2, 3, 4, 5].map((v) => `<label><input type="radio" name="q${i}" value="${v}" required>${v}</label>`).join("")}<span class="end">Agree</span></div></fieldset>`).join("");

$("#form").onsubmit = async (e) => {
  e.preventDefault();
  const answers = Q.map((_, i) => Number(($(`input[name=q${i}]:checked`) || {}).value || 0));
  const m = $("#msg");
  const miss = answers.findIndex((a) => !a);
  if (miss >= 0) { m.className = "msg bad"; m.textContent = `Please answer question ${miss + 1}.`; return; }
  $("#send").disabled = true;
  try {
    const r = await api.post("/api/sus", { answers, comment: $("#comment").value });
    m.className = "msg ok";
    m.textContent = "Thank you! Your answers were saved.";
    const s = r.score;
    $("#result").innerHTML = `<div class="mt"><div class="muted small">Your score</div><div class="bigscore">${num(s, 1)}</div>
      <p>${s >= 80.3 ? "Excellent" : s >= 68 ? "Good – above average" : s >= 51 ? "OK – below average" : "Poor"}</p></div>`;
    $$("#form input, #form textarea").forEach((x) => (x.disabled = true));
  } catch (err) {
    m.className = "msg bad";
    m.textContent = err.message;
    $("#send").disabled = false;
  }
};
