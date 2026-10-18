"""
F2 - TRAIN AND COMPARE THE FORECASTING MODELS
=============================================
Forecast: tonnes of waste per area for TOMORROW, using only what is known today
(waste up to today, tomorrow's calendar and planned events, the weather forecast).

  Baselines (proposal 3.3): Moving average (last 7 days), Same day last week, Linear Regression
  ML models (proposal):     XGBoost, LSTM

The data is split by TIME, never at random: first 70% of the days = training, next 15% =
validation (to tune XGBoost and pick the best model), last 15% = test (the numbers you report).

It also runs (for the report):
  - errors on holidays and festivals vs normal days
  - a check on 4 other test periods (rolling), so the result does not depend on one split
  - which inputs help: A past waste -> B + holidays/festivals/events -> C + weather -> D + area facts
  - high-waste days ("area overflow risk"): does the forecast warn before the 10% busiest days?
  - forecasts for up to 7 days ahead (each day's forecast is fed back in)
  - which inputs the XGBoost model uses most

At the end, the best model on the validation days is trained again on ALL days and saved for
steps F3, R2 and R3.

Note: for past days the REAL rain of the day is used, as if the weather forecast were perfect.
Live forecasts (step F3) use the Open-Meteo weather forecast, so live errors will be a bit bigger.

Run:  python f2_train_forecast.py          (about 2-4 minutes)
Needs: data/*.csv (from f1_make_data.py)
Makes: results/forecast_model.joblib, results/f2_*.csv, results/chart_f2_*.png
"""
import os

import joblib
import numpy as np
import pandas as pd

import charts
import settings as S
from forecasting import FEATURE_SET_NAMES, FEATURE_SETS, FEATURES, GBM_SETTINGS, NICE, Forecaster, \
    forecast_ahead, high_waste_thresholds, load_everything, make_gbm, make_linear, ready_rows, scores, \
    special_day_mask, split_days, timer, within_area_r2
from wastelib import DATA_DIR, RESULTS_DIR, ensure_dirs, load_holidays

BASELINES = ("Moving average (7 days)", "Same day last week", "Linear Regression")


def make_all(gbm_params):
    gbm_name, gbm = make_gbm(*gbm_params)
    return [Forecaster("ma7", "Moving average (7 days)"),
            Forecaster("last_week", "Same day last week"),
            Forecaster("linear", "Linear Regression", make_linear()),
            Forecaster("gbm", gbm_name, gbm),
            Forecaster("lstm", "LSTM")]


def flag_scores(actual_high, said_high):
    from sklearn.metrics import f1_score, precision_score, recall_score
    return dict(recall=100 * recall_score(actual_high, said_high, zero_division=0),
                precision=100 * precision_score(actual_high, said_high, zero_division=0),
                F1=100 * f1_score(actual_high, said_high, zero_division=0),
                warnings=int(np.sum(said_high)))


def rolling_periods(rows, n=4, days=60):
    end = rows.date.max()
    out = []
    for k in range(n, 0, -1):
        start = end - pd.Timedelta(days=days * k) + pd.Timedelta(days=1)
        out.append((start, start + pd.Timedelta(days=days)))
    return out


def main():
    ensure_dirs()
    print("F2 - train and compare the forecasting models")
    clock = timer()
    data = load_everything(until=S.HISTORY_END)
    table = data["table"]
    a, b = split_days(table["date"])
    rows = ready_rows(table)
    train, val, test = rows[rows.date < a], rows[(rows.date >= a) & (rows.date < b)], rows[rows.date >= b]
    synthetic = (pd.read_csv(os.path.join(DATA_DIR, "waste_daily.csv"), usecols=["source"])["source"]
                 == "synthetic").all()
    print(f"Days: training {train.date.min():%d %b %Y} to {(a - pd.Timedelta(days=1)):%d %b %Y}, "
          f"validation to {(b - pd.Timedelta(days=1)):%d %b %Y}, test to {test.date.max():%d %b %Y}")
    print(f"Rows (area-days): {len(train):,} training, {len(val):,} validation, {len(test):,} test.  "
          f"Wrong records removed: {int(data['wrong'].sum().sum())}, missing days filled: "
          f"{int(data['raw'].isna().sum().sum())}")

    # ---------------- 0. tune XGBoost on the validation days ----------------
    tuning = []
    for depth, trees in GBM_SETTINGS:
        name, model = make_gbm(depth, trees)
        fc = Forecaster("gbm", name, model).fit(data, train)
        tuning.append((scores(val["actual"], fc.predict(data, val))["MAE"], depth, trees))
    _, depth, trees = min(tuning)
    gbm_params = (depth, trees)
    print(f"{make_gbm()[0]} settings picked on the validation days: tree depth {depth}, {trees} trees")

    # ---------------- 1. the models ----------------
    print()
    print("1) Models - forecast for tomorrow, test days (lower error is better)")
    special_test = special_day_mask(test)
    fitted, preds_test, results = {}, {}, []
    for fc in make_all(gbm_params):
        t = timer()
        fc.fit(data, train, val)
        secs = t()
        pv, pt = fc.predict(data, val), fc.predict(data, test)
        fitted[fc.name], preds_test[fc.name] = fc, pt
        s = scores(test["actual"], pt)
        engine = f"  [{fc.engine}]" if fc.kind == "lstm" else ""
        results.append({"Model": fc.name, "MAE (t)": s["MAE"], "RMSE (t)": s["RMSE"], "R2 all areas": s["R2"],
                        "R2 within area": within_area_r2(test, pt),
                        "MAE % of average": 100 * s["MAE"] / test["actual"].mean(),
                        "MAE holidays and festivals (t)": scores(test["actual"][special_test], pt[special_test])["MAE"],
                        "MAE normal days (t)": scores(test["actual"][~special_test], pt[~special_test])["MAE"],
                        "Validation MAE (t)": scores(val["actual"], pv)["MAE"], "Train seconds": secs})
        print(f"   {fc.name:<44} MAE {s['MAE']:.3f} t  RMSE {s['RMSE']:.3f} t  R2 {s['R2']:.3f} "
              f"(inside one area {results[-1]['R2 within area']:.2f}){engine}")
    res = pd.DataFrame(results)
    res.round(4).to_csv(os.path.join(RESULTS_DIR, "f2_models.csv"), index=False)
    ml = res[~res["Model"].isin(BASELINES)]
    best_name = ml.sort_values("Validation MAE (t)").iloc[0]["Model"]
    base_best = res[res["Model"].isin(BASELINES)].sort_values("MAE (t)").iloc[0]
    best_row = res.set_index("Model").loc[best_name]
    print(f"   Best ML model on the validation days: {best_name}. Test MAE {best_row['MAE (t)']:.3f} t "
          f"= {best_row['MAE % of average']:.1f}% of an average day ({test['actual'].mean():.1f} t)")
    print(f"   Best baseline: {base_best['Model']}, MAE {base_best['MAE (t)']:.3f} t "
          f"-> the ML model's error is {100 * (1 - best_row['MAE (t)'] / base_best['MAE (t)']):.0f}% smaller")
    print(f"   On the {int(special_test.sum())} holiday/festival area-days: "
          + ", ".join(f"{r['Model'].split(' (')[0]} {r['MAE holidays and festivals (t)']:.2f} t" for _, r in res.iterrows()))

    # ---------------- 2. 4 other test periods ----------------
    print()
    print("2) Check on 4 other test periods (60 days each; each model trained on all days before the period)")
    periods = rolling_periods(rows)
    fold_rows, pooled = [], {}
    for start, stop in periods:
        tr, te = rows[rows.date < start], rows[(rows.date >= start) & (rows.date < stop)]
        line = {"Test period": f"{start:%d %b %Y} - {(stop - pd.Timedelta(days=1)):%d %b %Y}"}
        for fc in make_all(gbm_params)[:4]:  # the LSTM is left out here to save time
            fc.fit(data, tr)
            p = fc.predict(data, te)
            line[fc.name] = scores(te["actual"], p)["MAE"]
            pooled.setdefault(fc.name, []).append(pd.DataFrame({"actual": te["actual"].to_numpy(), "pred": p,
                                                                "special": special_day_mask(te)}))
        fold_rows.append(line)
    folds = pd.DataFrame(fold_rows)
    folds.round(4).to_csv(os.path.join(RESULTS_DIR, "f2_rolling_check.csv"), index=False)
    for col in folds.columns[1:]:
        allp = pd.concat(pooled[col])
        sp = allp[allp.special]
        print(f"   {col:<44} MAE {folds[col].mean():.3f} t (periods from {folds[col].min():.3f} to "
              f"{folds[col].max():.3f})   holidays/festivals {np.mean(np.abs(sp.actual - sp.pred)):.3f} t")

    # ---------------- 3. which inputs help (same 4 periods: they include New Year and Vesak) ----------------
    gbm_name = [n for n in fitted if fitted[n].kind == "gbm"][0]
    print()
    print(f"3) Which inputs help ({gbm_name}, the same 4 test periods, MAE)")
    ft = []
    for key, cols in FEATURE_SETS.items():
        parts = []
        for start, stop in periods:
            tr, te = rows[rows.date < start], rows[(rows.date >= start) & (rows.date < stop)]
            _, model = make_gbm(*gbm_params)
            fc = Forecaster("gbm", key, model, cols).fit(data, tr)
            parts.append(pd.DataFrame({"actual": te["actual"].to_numpy(), "pred": fc.predict(data, te),
                                       "special": special_day_mask(te)}))
        allp = pd.concat(parts)
        err = np.abs(allp.actual - allp.pred)
        ft.append({"Inputs": FEATURE_SET_NAMES[key], "MAE all days (t)": err.mean(),
                   "MAE holidays and festivals (t)": err[allp.special].mean(),
                   "MAE normal days (t)": err[~allp.special].mean(), "Number of inputs": len(cols)})
        print(f"   {FEATURE_SET_NAMES[key]:<36} all days {err.mean():.3f} t   holidays/festivals "
              f"{err[allp.special].mean():.3f} t   normal days {err[~allp.special].mean():.3f} t")
    ft = pd.DataFrame(ft)
    ft.round(4).to_csv(os.path.join(RESULTS_DIR, "f2_feature_test.csv"), index=False)

    # ---------------- 4. high-waste days ----------------
    # A day is "high-waste" when the real waste is above the area's 90th percentile. Each method warns
    # when its forecast is above (limit x k); k is picked on the VALIDATION days for the best F1
    # (forecasts are smoother than real days, so a slightly lower warning line works better).
    thr = high_waste_thresholds(data["clean"], a)
    limit = test["zone"].map(thr).to_numpy()
    limit_v = val["zone"].map(thr).to_numpy()
    actual_high = test["actual"].to_numpy() >= limit
    actual_high_v = val["actual"].to_numpy() >= limit_v
    print()
    print(f"4) High-waste days (area overflow risk): {int(actual_high.sum())} of {len(test)} test area-days were "
          f"above the area's {S.HIGH_WASTE_PERCENTILE}th percentile")
    hw = []
    for name in fitted:
        pv = fitted[name].predict(data, val)
        best_k = max(np.arange(0.92, 1.041, 0.005), key=lambda k: flag_scores(actual_high_v, pv >= limit_v * k)["F1"])
        sc = flag_scores(actual_high, preds_test[name] >= limit * best_k)
        hw.append({"Method": name, **sc, "warning line (x the 90th percentile)": round(float(best_k), 3)})
        print(f"   {name:<44} recall {sc['recall']:5.1f}%  precision {sc['precision']:5.1f}%  F1 {sc['F1']:5.1f}%"
              f"  ({sc['warnings']} warnings, line x{best_k:.3f})")
    hw = pd.DataFrame(hw)
    hw.round(1).to_csv(os.path.join(RESULTS_DIR, "f2_high_waste.csv"), index=False)

    # ---------------- 5. 1 to 7 days ahead ----------------
    print()
    print("5) Forecasts for 1 to 7 days ahead (each forecast fed back in), test days, MAE (t)")
    origins = pd.date_range(b - pd.Timedelta(days=1), test.date.max() - pd.Timedelta(days=S.FORECAST_DAYS), freq="3D")
    clean = data["clean"]
    horizon = {}
    for name in ("Moving average (7 days)", "Same day last week", best_name):
        errs = {h: [] for h in range(1, S.FORECAST_DAYS + 1)}
        for o in origins:
            f = forecast_ahead(fitted[name], data, o, S.FORECAST_DAYS)
            f["h"] = (f["date"] - o).dt.days
            f["actual"] = [clean.loc[d, z] if d in clean.index else np.nan for d, z in zip(f["date"], f["zone"])]
            for h, part in f.dropna(subset=["actual"]).groupby("h"):
                errs[h].extend(np.abs(part["forecast_t"] - part["actual"]))
        horizon[name] = [float(np.mean(errs[h])) for h in range(1, S.FORECAST_DAYS + 1)]
        print(f"   {name:<44} " + "  ".join(f"{h}d {v:.2f}" for h, v in zip(range(1, 8), horizon[name])))
    pd.DataFrame(horizon, index=pd.Index(range(1, S.FORECAST_DAYS + 1), name="Days ahead")).round(4).to_csv(
        os.path.join(RESULTS_DIR, "f2_days_ahead.csv"))

    # ---------------- 6. which inputs the XGBoost model uses ----------------
    rng = np.random.default_rng(S.SEED)
    fc = fitted[gbm_name]
    base_mae = scores(test["actual"], preds_test[gbm_name])["MAE"]
    imp = []
    for col in FEATURES:
        shuffled = test.copy()
        shuffled[col] = rng.permutation(shuffled[col].to_numpy())
        imp.append((col, scores(test["actual"], fc.predict(data, shuffled))["MAE"] - base_mae))
    imp = sorted(imp, key=lambda x: x[1], reverse=True)
    pd.DataFrame(imp, columns=["Input", "MAE increase (t)"]).round(4).to_csv(
        os.path.join(RESULTS_DIR, "f2_inputs.csv"), index=False)
    print()
    print("6) Inputs the model uses most: " + ", ".join(f"{NICE.get(c, c)} (+{v:.3f} t)" for c, v in imp[:5]))

    # ---------------- 7. save the best model, trained on ALL days ----------------
    final = [f for f in make_all(gbm_params) if f.name == best_name][0]
    last60 = rows[rows.date > rows.date.max() - pd.Timedelta(days=60)]
    first = rows if final.kind != "lstm" else rows[rows.date <= rows.date.max() - pd.Timedelta(days=60)]
    final.fit(data, first, last60)
    pack = {"forecaster": final, "name": best_name, "kind": final.kind,
            "thresholds": high_waste_thresholds(data["clean"], data["clean"].index.max() + pd.Timedelta(days=1)),
            "trained_until": str(rows.date.max().date()), "test_mae": float(best_row["MAE (t)"]),
            "engine": getattr(final, "engine", ""), "gbm_params": gbm_params}
    joblib.dump(pack, os.path.join(RESULTS_DIR, "forecast_model.joblib"))
    out = test[["date", "zone", "actual"]].copy()
    for name, p in preds_test.items():
        out[name] = np.round(p, 3)
    out.to_csv(os.path.join(RESULTS_DIR, "f2_test_predictions.csv"), index=False)

    # ---------------- charts ----------------
    tag = ", synthetic data" if synthetic else ""
    sub = f"Test days {test.date.min():%d %b} - {test.date.max():%d %b %Y}, 6 areas{tag}"
    charts.hbars(list(res["Model"]), list(res["MAE (t)"]), [m not in BASELINES for m in res["Model"]],
                 os.path.join(RESULTS_DIR, "chart_f2_models.png"), "Which model forecasts tomorrow's waste best?",
                 sub, "Average error per area per day, MAE (tonnes) - lower is better", fmt="{:.3f}")
    zone = test.groupby("zone")["actual"].std().idxmax()
    mask = (test.zone == zone).to_numpy()
    part = test[mask]
    order = np.argsort(part["date"].to_numpy())
    second = "LSTM" if best_name != "LSTM" else gbm_name
    hol = load_holidays()
    hol = hol[(hol.date >= part.date.min()) & (hol.date <= part.date.max())]
    labels = {r.date: r.name.replace(" Full Moon Poya Day", " Poya").replace(" Festival Day", "")[:22]
              for r in hol.itertuples()}
    charts.forecast_lines(part["date"].to_numpy()[order], part["actual"].to_numpy()[order],
                          {best_name: preds_test[best_name][mask][order], second: preds_test[second][mask][order]},
                          labels, os.path.join(RESULTS_DIR, "chart_f2_example.png"),
                          f"{zone}: real waste and the forecasts made the day before", sub)
    charts.grouped_bars([r.split("  ")[0] + "\n" + r.split("  ")[1] for r in ft["Inputs"]],
                        ["All days", "Holidays and festivals"],
                        [list(ft["MAE all days (t)"]), list(ft["MAE holidays and festivals (t)"])],
                        os.path.join(RESULTS_DIR, "chart_f2_inputs_test.png"),
                        "Do holidays, weather and area facts help the forecast?",
                        f"{gbm_name}, 4 test periods of 60 days ({periods[0][0]:%b %Y} - "
                        f"{(periods[-1][1] - pd.Timedelta(days=1)):%b %Y}){tag}",
                        "Average error, MAE (tonnes) - lower is better", fmt="{:.2f}")
    show = list(dict.fromkeys([best_name, "Linear Regression", "Same day last week"]))
    hw_i = hw.set_index("Method")
    charts.grouped_bars(["Recall\n(busy days warned)", "Precision\n(warnings that were right)", "F1"],
                        show, [[hw_i.loc[m, "recall"], hw_i.loc[m, "precision"], hw_i.loc[m, "F1"]] for m in show],
                        os.path.join(RESULTS_DIR, "chart_f2_high_waste.png"),
                        "Does the forecast warn before high-waste days?",
                        f"{int(actual_high.sum())} high-waste area-days in the test period "
                        f"(above each area's {S.HIGH_WASTE_PERCENTILE}th percentile){tag}", "%", fmt="{:.0f}%",
                        ymax=110)
    top = imp[:12]
    charts.hbars([NICE.get(c, c) for c, _ in top], [max(v, 0) for _, v in top], [True] * len(top),
                 os.path.join(RESULTS_DIR, "chart_f2_inputs.png"), "Which inputs does the model use most?",
                 f"{gbm_name}: how much the error grows when one input is scrambled",
                 "MAE increase (tonnes)", fmt="{:.3f}", legend=None, lower_is_better=False)
    print()
    print(f"Saved: results/forecast_model.joblib ({best_name}, trained on all days), results/f2_*.csv, 5 charts")
    print(f"Done in {clock():.0f} s. Next: python f3_forecasts_to_firebase.py  (or go on with r1_road_map.py)")


if __name__ == "__main__":
    main()
