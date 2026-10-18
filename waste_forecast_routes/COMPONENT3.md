# Component 3 — Waste forecasting + truck routes

**SLIIT IT4010 · J26-ISE-305 · Kaduwela Municipal Council**

Component 3 answers: **how much waste will each area produce in the next 7 days?** and **which bins should which truck visit today, in what order, on real roads?** It also drives **crew tips**, **reward rules** on busy days, and the **live re-planning** demo (road closed, truck broken).

This guide covers **synthetic vs real data**, **script pipeline**, **Firebase outputs**, and **which UI pages show each feature**.

---

## 1. Role in the full system

```
f1_make_data.py  → 2 years daily waste per zone (+ weather, calendar)
f2_train_forecast.py  → results/forecast_model.joblib
f3_forecasts_to_firebase.py  → forecasts/<zone>/<date>
e2_crew_tips.py  → guidance/<date>/<zone>

r1_road_map.py  → OpenStreetMap graph (data/roads_*.csv)
r2_test_routes.py  → 30-day method comparison (report / Analytics)
r3_live_routes.py  → routes/<today>/<truck>  +  _summary

Reads from Firebase:
  bins/, predictions/ (C2), forecasts/, trucks/, traffic/, control/replan
```

Component 2 supplies **per-bin fill and urgency**; Component 3 uses **area tonnage forecasts** to scale bin growth and plan **truck paths**.

---

## 2. Research questions answered here

| RQ / goal | Question | Script / UI |
|-----------|----------|-------------|
| **RQ6** (forecast + routes) | Which forecast + routing method saves km / fuel / missed bins? | `f2_*`, `r2_test_routes.py` → **Analytics → Component 3** |
| **NFR01** | Re-plan within 5 s after road change? | `r2` replan test + live **Routes** page `replan_seconds` |
| **Objective 5** | Crew guidance on busy / festival days? | `e2_crew_tips.py` → **Forecast**, **Community** |
| **Operations** | Plan today’s collections | **Operations**, **Routes**, **Driver** |

---

## 3. Which UI pages use Component 3

| Page | URL | What from C3 |
|------|-----|----------------|
| **Operations** | `/officer` | 7-day forecast summary, **today’s routes** snippet, link to Routes |
| **Forecast** | `/officer/forecast` | Tonnes per zone per day, busy days, holidays, rain, **crew tips** |
| **Routes** | `/officer/routes` | Route map, KPIs (km, diesel, re-plan time), road closure / jam tools, truck timelines, skipped bins |
| **Analytics** | `/officer/analytics` (tabs C3 / routes) | F2 model comparison, forecast vs actual, R2 method trade-offs, re-plan speed chart |
| **Reports** | `/officer/reports` | CSV: forecast, routes |
| **Community** | `/officer/community` | **Tips for crews** (next busy days) from `guidance/` |
| **Driver** | `/driver` | Today’s route stops, ETAs, Navigate, mark emptied |
| **Citizen Home** | `/citizen` | Static + **today’s crew tips** when `guidance/` exists (`/api/citizen`) |
| **System** | `/officer/system` | Jobs: **7-day forecast**, **crew tips**, **Live route planner**, road map setup (r1), truck simulator (r4) |

Rewards (`e1_rewards.py`): uses **forecast high-waste days** for bonus points — background job, not a main page.

---

## 4. When data is created vs when it is used

| When | Script | Output |
|------|--------|--------|
| **Once (setup)** | `f1_make_data.py` | `data/waste_daily.csv`, `weather.csv`, `calendar.csv`, `zones.csv` |
| **Once (setup)** | `f2_train_forecast.py` | `results/forecast_model.joblib`, `f2_*.csv`, charts |
| **Once (setup)** | `r1_road_map.py` | Road network files (needs internet) |
| **Once (setup)** | `r2_test_routes.py` | `r2_*.csv`, maps for report |
| **Daily ~05:00** (auto) or manual | `f3_forecasts_to_firebase.py` | `forecasts/<zone>/<date>` for next 7 days |
| **After F3** | `e2_crew_tips.py` | `guidance/<date>/<zone>` |
| **Every 15 s check** (service) | `r3_live_routes.py` | `routes/<YYYY-MM-DD>/truck_*`, `_summary` |
| **Officer clicks** | Flask APIs | `traffic/`, `control/replan`, `trucks/<id>/status` → triggers R3 |

**Demo mode:** `demo/demo_db.json` includes sample `forecasts/`, `routes/`, `guidance/` so pages work offline.

**Live mode:** F3 and R3 must run (System → Automatic mode or start jobs manually).

---

## 5. Synthetic data — how `f1_make_data.py` builds it

### 5.1 Why synthetic waste data exists

Kaduwela council may not give you **two years of daily tonnes per zone** before the project deadline. F1 therefore builds **plausible daily waste** unless you provide `data/council_waste.csv` (`date`, `zone`, `waste_t`).

**Say to examiners:**

> Area-level **training data is synthetic** (unless council CSV is supplied), grounded in **published total waste** (~71 t/day council-wide, UTS 2018 fact sheet), **population per zone**, **Sri Lankan calendar** (Poya, Avurudu, Vesak, Christmas), and **weather** (Open-Meteo when online).

### 5.2 What F1 generates

| File | Content |
|------|---------|
| `weather.csv` | Daily rain + temperature — **real** from Open-Meteo if possible, else **synthetic** Colombo-like climate |
| `calendar.csv` | Holidays, Poya, festival flags from `holidays_lk.csv` |
| `zones.csv` | Six areas: centre, population, commercial share |
| `waste_daily.csv` | **Tonnes per zone per day** for ~2 years (`HISTORY_START` … `HISTORY_END`) |

**Synthetic waste formula (simplified):**

- Split **71 t/day** across zones by population × commercial activity.  
- **Homes** ↑ weekends; **shops/markets** ↓ Sundays and Poya.  
- **Festivals:** Avurudu shopping, Vesak dansal, Christmas season, etc. (`SPECIAL` multipliers).  
- **Rain:** slightly heavier wet waste (+ up to ~6%).  
- **Trend:** ~2% growth per year.  
- **Noise:** random day-to-day variation; optional **missing days** and **bad records** (data-cleaning practice).

`events.csv` adds **planned events / road closures** (examples — replace with real council data).

### 5.3 Why synthetic area data is **valuable**

1. **Train F2** with enough days for LSTM lookback (28 days) and seasonal patterns (New Year, Vesak).  
2. **Compare models** fairly (moving average vs XGBoost vs LSTM) on the same held-out **time** slice.  
3. **Link to routing:** R2/R3 multiply bin fill speed by `forecast_t / normal_t` per zone — busy festival days collect more bins.  
4. **Demo the product:** F3 can extend synthetic history to “yesterday” and forecast a **real calendar week** ahead (`waste_recent_demo.csv` — not used for training).  
5. **Transparent:** report labels data as synthetic; swap in `council_waste.csv` when available.

**Limitation:** forecast accuracy numbers are **method comparison** on synthetic ground truth, not an official Kaduwela statistic until real council data is used.

---

## 6. Forecasting pipeline (F1 → F2 → F3)

### 6.1 `f2_train_forecast.py`

- **Task:** Predict **tomorrow’s tonnes** per zone using only information available **today**.  
- **Baselines:** 7-day moving average, same weekday last week, linear regression.  
- **ML:** Gradient boosting (XGBoost if installed) and LSTM (PyTorch or NumPy fallback).  
- **Split:** 70% / 15% / 15% by **time**.  
- **Reports:** holiday errors, high-waste-day warnings, feature ablation, 7-day ahead roll-forward.  
- **Saves:** `forecast_model.joblib` for F3, R2, R3.

### 6.2 `f3_forecasts_to_firebase.py`

Writes for each **zone** and **date** (next 7 days):

```
forecasts/<zone>/<YYYY-MM-DD>  {
  forecast_t, normal_t, change_pct, high_waste,
  holiday, rain_mm, ...
}
forecasts/_info  { model, made_at, ... }
```

Uses Open-Meteo **forecast** for rain when online. If synthetic history ends before “today”, F3 can append **demo recent days** so the live dashboard still shows a sensible week (see script header).

### 6.3 `e2_crew_tips.py`

**Rule-based** tips (not a chatbot) triggered by forecast + calendar + `events.csv` + heavy rain:

```
guidance/<YYYY-MM-DD>/<zone>  → [ "tip text", ... ]
```

Shown on **Forecast** and **Community** (and citizen tips when present).

---

## 7. Routing pipeline (R1 → R2 → R3)

### 7.1 `r1_road_map.py`

Downloads **OpenStreetMap** roads around Kaduwela, builds a drivable graph with speeds by road type and **rush-hour slowdown**. Required before R2/R3.

### 7.2 `r2_test_routes.py` (offline evaluation)

Simulates **30 days** (`ROUTE_TEST_START`) with the same waste arriving for all methods:

| Method | Idea |
|--------|------|
| Fixed schedule | Empty every N days regardless of fill |
| Reactive | Collect if ≥70% full at 6:00 |
| Predictive | Collect if predicted ≥90% by next round |
| Predictive + **area forecast** | Same, but growth scaled by F2 `forecast_t/normal_t` |
| + simple nearest-neighbour route | Shows value of optimiser |

Measures: km, diesel, cost, overflows, service level, **re-plan seconds** after fake road closure.

Outputs: `r2_methods.csv`, trade-off charts, `map_r2_vesak.html`.

### 7.3 `r3_live_routes.py` (production planner)

Every **15 s**, checks Firebase for changes (traffic, broken truck, urgent bins, `control/replan`). At least every **5 min** (`LIVE_EVERY_MINUTES`), replans **today**:

1. Build bin table from `bins/` + `predictions/`.  
2. `choose_bins("predictive", …)` — must-collect if predicted ≥90%, urgency ≥60, smell rule, etc.  
3. Apply **traffic** incidents to road network.  
4. **VRP solve** (OR-Tools or built-in), trucks from `trucks/`, depot from settings.  
5. Write `routes/<date>/<truck_id>` with stops (ETA, fill %), path polyline, km, fuel.  
6. Write `routes/<date>/_summary` with `replan_seconds`, `skipped`, `solver`.

Officer **Routes** page only **displays** this; buttons write `traffic/` or `control/replan`.

### 7.4 Other scripts

| Script | Role |
|--------|------|
| `r4_truck_simulator.py` | Demo: move trucks, auto-empty `sim_*` bins |
| `e1_rewards.py` | Points for scans, reports, classifications; high-waste day bonus |
| `dashboard/` | Standalone C2+C3 dashboard (optional; main UI is Flask) |

---

## 8. Firebase paths (Component 3)

```
forecasts/<zone>/<date>     daily tonnes, high_waste flag, holiday, rain
forecasts/_info             metadata

routes/<date>/<truck_id>    stops[], path[], km, fuel_l, cost_lkr, start, made_at
routes/<date>/_summary      planned, skipped[], replan_seconds, solver, total_km, ...

trucks/<truck_id>           status, lat, lng, ts
traffic/<id>                closure | jam, lat, lng, radius_m, until, note
control/replan              timestamp when officer clicks Re-plan

guidance/<date>/<zone>      [ crew tip strings ]
rewards/<user>              (E1 — uses forecast flags)
```

---

## 9. How C2 and C3 connect

| C2 provides | C3 uses it for |
|-------------|----------------|
| `predictions/<bin>.predicted_fill_6h` | Predictive bin selection |
| `predictions/<bin>.urgency_score` | Force collection if ≥60 |
| `bins/<bin>/latest.fill_pct` | Reactive thresholds, stop display |
| `bins/*/info` (zone, lat, lng) | Map stops, zone forecast ratio |

| C3 provides | C2 / UI uses it for |
|-------------|---------------------|
| `forecasts/` | Operations forecast cards; route planner busy-day scaling |
| `routes/` | Driver + Officer Routes |
| `guidance/` | Forecast, Community, Citizen tips |

---

## 10. Settings that matter (`waste_forecast_routes/settings.py`)

| Setting | Meaning |
|---------|---------|
| `TONNES_PER_DAY` | Council-wide baseline (71) |
| `ZONES` | Six Kaduwela-area names + coordinates |
| `N_TRUCKS`, `TRUCK_CAPACITY_KG`, `SHIFT_HOURS` | Fleet capacity |
| `PREDICT_FILL_PCT`, `URGENT_SCORE` | Match C2 / routing `choose_bins` |
| `LIVE_EVERY_MINUTES` | R3 periodic replan |
| `SOLVER_SECONDS` | VRP time limit (&lt;5 s target) |

---

## 11. How to run (student checklist)

```powershell
cd waste_forecast_routes
pip install -r requirements.txt

python f1_make_data.py
python f2_train_forecast.py
python r1_road_map.py          # internet required once
python r2_test_routes.py

# Firebase URL in settings.py
python f3_forecasts_to_firebase.py
python e2_crew_tips.py
python r3_live_routes.py       # keep running
```

Or in `smartwaste_app`: **System → Run all setup steps**, then enable **Automatic mode** (forecast daily, routes + predictions live).

Ensure C2 demo bins exist (`b6_demo_bins.py --add`) or real bins with locations so the map is not empty.

---

## 12. 30-second explanation for classmates

> “We forecast how many tonnes of waste each area will produce for the next seven days using calendar events, weather, and machine learning trained on two years of daily data — synthetic unless the council gives real records. That forecast feeds crew tips and makes the route planner expect busier bins on festival days. Every day the planner reads live bin fill and predictions from Firebase, solves a vehicle routing problem on OpenStreetMap roads, and writes truck stop lists. If an officer marks a road closed, the planner rebuilds routes in a few seconds.”

---

## 13. Viva Q&A

**Q: Is the forecast real council data?**  
A: **Synthetic by default** from F1; replace with `council_waste.csv` for real training.

**Q: Who draws the route lines on the map?**  
A: **R3** stores GPS polylines in `routes/.../path`; Flask JS draws them — not hand-drawn.

**Q: Fixed vs predictive routes?**  
A: **R2** compares methods offline; **live system uses predictive + forecast** (method 4 in R2).

**Q: What if R3 is not running?**  
A: Routes page shows last plan and a **warning**; closures will not update until the job starts.

**Q: OR-Tools required?**  
A: **Optional** — built-in solver runs if OR-Tools is missing (slower or slightly worse routes, still demoable).

---

## 14. Related files

| Path | Purpose |
|------|---------|
| `waste_forecast_routes/README.txt` | Short command list |
| `waste_forecast_routes/routing.py` | `choose_bins`, VRP solvers |
| `waste_forecast_routes/roads.py` | OSM network, incidents |
| `smart_bin_ml/COMPONENT2.md` | Bin ML + `predictions/` |
| `waste_classifier/COMPONENT1.md` | Image scan (rewards only tie-in) |
| `README.md` (project root) | Whole-system overview |

---

*Aligned with Flask officer/citizen/driver UI and Firebase integration.*
