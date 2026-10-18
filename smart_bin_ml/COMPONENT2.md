# Component 2 — IoT smart bin + fill-level ML

**SLIIT IT4010 · J26-ISE-305 · Kaduwela Municipal Council**

Component 2 connects the **physical smart bin** (ESP32 sensors) to **machine learning** that predicts how full a bin will be in **6 hours**, estimates **overflow risk**, computes an **urgency score**, and helps citizens find the **nearest bin with space**.

This guide explains **where data comes from**, **how synthetic training data is built**, **why that is valid for the project**, **which scripts run when**, and **which web pages show each feature**.

---

## 1. Role in the full system

```
ESP32 bin (every 30 s)
        │
        ▼
Firebase  bins/<id>/latest, readings/, last_collected
        │
        ├─► b5_live_predictions.py  (every 5 min)
        │         │
        │         ▼
        │   predictions/<id>  { predicted_fill_6h, overflow_risk, urgency_score, ... }
        │
        └─► Flask app (data.py) reads bins + predictions → dashboard

Training (offline, once or after new export):
  b2_make_data.py → b3_train_models.py → results/model.joblib
  b4_test_urgency_and_nearest.py → RQ3/RQ4 CSVs for Analytics
```

Component 3 **reads** `predictions/` when planning truck routes (urgency, predicted fill). Component 1 (image scan) is separate.

---

## 2. Research questions answered here

| RQ | Question | Script / UI |
|----|----------|-------------|
| **RQ1** | Is the real bin’s sensor data reliable? | Live from Firebase → **Analytics** tab (`/api/rq1`, logic in `data.py`) |
| **RQ2** | Which model predicts fill 6 h ahead best? | `b3_train_models.py` → **Analytics → Component 2** |
| **RQ3** | Which urgency ranking picks “early collection” bins best? | `b4_test_urgency_and_nearest.py` → **Analytics** |
| **RQ4** | Can citizens get a useful “nearest bin with space”? | Same script + `data.nearest_with_space()` → **Citizen Home**, **Bin detail** |
| **RQ5** | Does the live loop react in time? | `b5_live_predictions.py` → **Operations**, **Bin detail**, delay in B5 logs |

---

## 3. Which UI pages use Component 2

| Page | URL | What from C2 |
|------|-----|----------------|
| **Operations** | `/officer` | Live map colours (fill %), KPI tiles, early warnings (overflow / ML prediction / 75%+ fill) |
| **Bin fleet** | `/officer/bins` | Fill level, predicted fill, risk, urgency per bin |
| **Bin detail** | `/officer/bins/bin_01` | Fill ring, **6 h prediction**, overflow risk, hours to full, **urgency score + 4 parts**, all sensors, history charts, **nearest bin with space** |
| **Analytics** | `/officer/analytics` | RQ1 live reliability, RQ2 model tables/charts, RQ3 urgency, RQ4 nearest-bin (from `results/*.csv`) |
| **Reports** | `/officer/reports` | CSV exports of readings / warnings |
| **Driver route** | `/driver` | Stop list shows **fill %** at each bin (from live/predictions) |
| **Routes** | `/officer/routes` | Stop `fill_pct` on map (sensor + prediction context) |
| **Citizen Home** | `/citizen` | Map of bins; **Find nearest with space** (`/api/nearest` uses fill + predicted fill) |
| **System** | `/officer/system` | Jobs: **Live bin predictions**, setup steps b2–b4, demo bins b6 |

Fill colours (everywhere): Normal &lt;50% · Filling 50–74% · Warning 75–89% · Critical ≥90%.

---

## 4. When data is created vs when it is used

| When | What happens | Where it lives |
|------|----------------|----------------|
| **Every 30 s** (hardware) | ESP32 sends fill, weight, gas, temp, humidity, battery | `bins/<id>/latest`, `bins/<id>/readings/<ts>` |
| **Once (setup)** | Synthetic 60-day history for 20 bins | `smart_bin_ml/data/readings.csv` (+ collections, bins) |
| **Once (setup)** | Train model on synthetic CSV | `smart_bin_ml/results/model.joblib` |
| **Every 5 min** (job) | Live prediction for each real bin | `predictions/<id>` |
| **Optional** | Copy 20 synthetic bins into Firebase for demos | `bins/sim_01…sim_20`, `predictions/sim_*` via `b6_demo_bins.py --add` |
| **On page load / poll** | Flask merges `latest` + `predictions` | Browser JSON APIs |

**Demo mode** (`demo/demo_db.json`): includes pre-built predictions and synthetic bin history so the UI works **without** Firebase or the ESP32. Timestamps are shifted to “now” when the app starts.

**Live mode**: real `bin_01` readings drive `b5`; demo `sim_*` bins are skipped by B5 (their predictions come from B6).

---

## 5. Synthetic data — how `b2_make_data.py` builds it

### 5.1 Why synthetic data exists

You have **one physical bin** and only **weeks** of real readings. To train and compare ML models (RQ2–RQ4), the proposal needs **many bins** and **months** of consistent 15-minute samples.

**Tell examiners clearly:**

> The **models are trained on synthetic data** that mimics Kaduwela bin types and sensor behaviour. The **real bin** is used to calibrate **sensor noise** (optional export) and to **prove the live pipeline** (RQ1, RQ5) in the demo.

That is standard for student IoT + ML projects: simulate the world, validate on held-out synthetic test days, then deploy on real hardware.

### 5.2 What is simulated (20 bins × 60 days × every 15 min)

For each synthetic bin `sim_01` … `sim_20`:

| Mechanism | Detail |
|-----------|--------|
| **Location** | Six zones (Malabe, Kaduwela, …); lat/lng jitter around zone centre |
| **Bin type** | market, bus_stop, residential, school, office, temple — each with different fill **rate**, **organic share**, **density**, **emptying interval** |
| **Time of day** | Hour profiles (e.g. market peaks ~9:00 and ~16:00; residential evening peak) |
| **Weekday / weekend** | Schools/offices quiet on weekends; temples busier on weekends |
| **Rain / warm days** | Random multipliers across days |
| **Collection** | Scheduled every 1–3 days by type; sometimes **missed**; sometimes **extra** trip after overflow |
| **Overflow** | Fill can hit 100%; waste still “arrives” (realistic stress) |
| **Sensors** | Weight, temp, humidity, gas index derived from fill + time since emptying + organic fraction |
| **Noise & gaps** | Gaussian noise on fill (scaled from **real bin export** if `data/smart-bin-export.json` exists); occasional bad readings and **lost** transmissions |

Outputs:

- `data/readings.csv` — all 15-minute rows  
- `data/collections.csv` — emptying events  
- `data/bins.csv` — metadata for `sim_01`…`sim_20`  
- Optional: `real_readings.csv`, `real_collections.csv` from Firebase export  

Settings: `N_DAYS = 60`, `START_DATE`, `SEED = 42` in `settings.py` (same seed → same CSVs → reproducible thesis numbers).

### 5.3 Why synthetic data is **valuable** (not “fake useless data”)

1. **Enough volume** to split by **time** (70% train / 15% val / 15% test) without cheating.  
2. **Controlled ground truth** — you know future fill because you generated it; you can test overflow rules and urgency fairly.  
3. **Diversity** — 20 bins × 6 types × 60 days beats one real bin for comparing Random Forest vs MLP.  
4. **Linked to reality** — noise from your real `bin_01` export; same 15-minute grid and features as live B5.  
5. **Feeds Component 3** — `b6_demo_bins.py` pushes synthetic bins to Firebase so **routes and maps** work before PP1.  
6. **Ethics / safety** — you do not need to dump real rubbish for months to train; you disclose synthesis in the report.

**Limitation (say this too):** synthetic bins are not a substitute for a long **real** deployment study; RQ1/RQ5 and live demo close that gap.

---

## 6. Training and evaluation scripts

### 6.1 `b3_train_models.py` (RQ2)

- **Input:** `data/readings.csv` from B2.  
- **Target:** `target_fill_6h` (fill six hours ahead on the 15-minute grid).  
- **Models:** Persistence, Trend, Linear Regression, Random Forest, Gradient Boosting, MLP (+ optional XGBoost).  
- **Split:** by **calendar time**, not random rows.  
- **Extras:** feature sets B1–B4; overflow detection vs simple 75% threshold (B0).  
- **Output:** `results/model.joblib` (best model + feature list), `rq2_*.csv`, PNG charts.

The **live job B5** loads this `model.joblib`.

### 6.2 `b4_test_urgency_and_nearest.py` (RQ3, RQ4)

- **RQ3:** At 06:00 and 14:00 on test days, rank bins with U0 (fill now), U1 (predicted fill), U2 (full urgency formula). Measure top-5 recall for bins that need early collection (≥90% fill or gas ≥60 in next 6 h).  
- **RQ4:** 500 random citizen locations; compare R0 (nearest any) vs R1 (nearest with space: fill &lt;80%, pred &lt;90%, within 2 km).  
- **Output:** `rq3_urgency.csv`, `rq4_nearest.csv`, charts.

Urgency weights match firmware and proposal (`W_FILL=0.5`, `W_GAS=0.2`, `W_HUMIDITY=0.1`, `W_TIME=0.2`).

### 6.3 `b5_live_predictions.py` (RQ5)

Every **5 minutes** (config `LIVE_EVERY_MINUTES`):

1. Read last **8 hours** of readings from Firebase.  
2. Resample to 15-minute grid; build same features as training.  
3. Predict fill in **6 h**, overflow risk, hours to full, **urgency_score**.  
4. Write `predictions/<bin_id>`.  
5. Skip `sim_*` (demo bins).  
6. If no reading for **30 min**, status `no_recent_data` (no fake prediction).

Started from **System → Live bin predictions** or `python b5_live_predictions.py`.

### 6.4 `b6_nearest_bin.py` (CLI test)

`python b6_nearest_bin.py <lat> <lng>` — same logic as the web `/api/nearest`.

### 6.5 `b6_demo_bins.py` (Firebase demo fleet)

`--add` copies synthetic bins + one-shot predictions into Firebase; `--remove` deletes `sim_01`…`sim_20`. **Mark as synthetic** in reports.

---

## 7. Firebase paths (Component 2)

**Written by ESP32:**

```
bins/bin_01/latest          { fill_pct, weight_kg, gas_index, temp_c, ... }
bins/bin_01/readings/<ts>   history
bins/bin_01/last_collected  timestamp
bins/bin_01/info            name, zone, type, lat, lng
```

**Written by B5 / B6:**

```
predictions/<bin_id>  {
  current_fill_pct, predicted_fill_6h, overflow_risk,
  urgency_score, hours_to_full, gas_index, humidity_pct,
  hours_since_collection, status, model, based_on_ts, updated_at, ...
}
```

---

## 8. Flask integration (no separate C2 server)

| File | Role |
|------|------|
| `smartwaste_app/data.py` | Merges `bins` + `predictions`; levels, alerts, urgency parts, nearest bin, RQ1 |
| `smartwaste_app/jobs.py` | Starts B5; setup steps for b2–b4 |
| `smartwaste_app/results.py` | Serves C2 CSV/PNG to Analytics |
| `smart_bin_ml/binlib.py` | Shared features, urgency, Firebase helper |

---

## 9. How to run (student checklist)

```powershell
cd smart_bin_ml
pip install -r requirements.txt

# One-time pipeline (or use System → Run all setup steps)
python b2_make_data.py
python b3_train_models.py
python b4_test_urgency_and_nearest.py

# Live (Firebase URL in settings.py)
python b5_live_predictions.py

# Optional demo bins for routes map
python b6_demo_bins.py --add
```

In `smartwaste_app`: start `python app.py`, enable **Live bin predictions** on System.

Optional: export Firebase JSON to `smart_bin_ml/data/smart-bin-export.json` before B2 so noise matches your real bin.

---

## 10. 30-second explanation for classmates

> “Our bin sends fill and environmental readings every 30 seconds. Because we only have one real bin for a short time, we generated 60 days of synthetic data for 20 public bins around Kaduwela — with realistic daily patterns, collections, and sensor noise from our real device. We trained a model to predict fill six hours ahead and rank urgency. A background job updates Firebase every five minutes; the officer dashboard and citizen ‘nearest bin’ map read those predictions.”

---

## 11. Viva Q&A

**Q: Did you train on real or synthetic data?**  
A: **Synthetic** for bulk training (B2); **real** `bin_01` for live demo, RQ1 reliability, and optional noise calibration.

**Q: Why 15-minute steps?**  
A: Matches resampling in `binlib.to_grid()` — stable features without using every 30 s raw point twice.

**Q: What if predictions are missing?**  
A: UI falls back to current fill from `latest`; urgency may use fill-now; status shows “no prediction yet”.

**Q: Does the ESP32 run the ML model?**  
A: **No.** ESP32 sends raw/calibrated sensors; **Python on the server** runs `model.joblib`.

---

## 12. Related files

| Path | Purpose |
|------|---------|
| `smart_bin_ml/README.txt` | Short command list |
| `smart_bin_ml/settings.py` | Firebase, thresholds, urgency weights, B2 seed |
| `firmware/smart_bin/` | Hardware that produces `bins/` data |
| `waste_classifier/COMPONENT1.md` | Image classification (not C2) |
| `waste_forecast_routes/COMPONENT3.md` | Forecast + routes (consumes `predictions/`) |

---

*Aligned with integrated Flask app, Firebase, and ESP32 firmware v1.3.0.*
