"""
B3 - TRAIN AND COMPARE THE MODELS (RQ2)
=======================================
Predicts the fill level 6 hours ahead and compares models on the SAME data split, as the
proposal asks (section 3.3 and Table 8):

  Baselines : Persistence (the fill stays the same) and Trend (last 3 hours' fill speed)
  ML models : Linear Regression, Random Forest, Gradient Boosting, Neural Network (MLP)
              (+ XGBoost if you run:  python b3_train_models.py --xgboost  after  pip install xgboost)

The data is split by TIME, never at random (proposal, Strand 2):
  first 70% of the days = training, next 15% = validation (to pick the model), last 15% = test.

It also runs:
  - the feature test B1 -> B4 (fill only, + weight, + gas/humidity, + time and emptying history)
  - the overflow test: B0 (alert when the current fill >= 75%) vs the ML model
  - which inputs matter most

Run:  python b3_train_models.py
Needs: data/readings.csv (from b2_make_data.py)
Makes: results/model.joblib, results/rq2_*.csv, results/chart_models.png,
       results/chart_example.png, results/chart_inputs.png
"""
import argparse
import os
import time
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import f1_score, mean_absolute_error, mean_squared_error, precision_score, r2_score, \
    recall_score
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import charts
import settings as S
from binlib import DATA_DIR, FEATURE_SET_NAMES, FEATURE_SETS, NICE_NAMES, RESULTS_DIR, ensure_dirs, \
    load_dataset, need_file

warnings.filterwarnings("ignore")
FEATURES = FEATURE_SETS["B4"]
TARGET = "target_fill_6h"


def make_models(use_xgboost):
    models = {
        "Linear Regression": LinearRegression(),
        "Random Forest": RandomForestRegressor(n_estimators=120, min_samples_leaf=10, max_features=0.5,
                                               n_jobs=-1, random_state=S.SEED),
        "Gradient Boosting": HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                                           min_samples_leaf=40, l2_regularization=1.0,
                                                           early_stopping=False, random_state=S.SEED),
        "Neural Network (MLP)": make_pipeline(StandardScaler(), MLPRegressor(
            hidden_layer_sizes=(64, 32), alpha=1e-3, max_iter=80, early_stopping=True,
            n_iter_no_change=8, random_state=S.SEED)),
    }
    if use_xgboost:
        try:
            from xgboost import XGBRegressor
        except ImportError:
            raise SystemExit("XGBoost is not installed. Run:  pip install xgboost   then try again.")
        models["XGBoost"] = XGBRegressor(n_estimators=400, learning_rate=0.05, max_depth=6, subsample=0.8,
                                         colsample_bytree=0.8, n_jobs=-1, random_state=S.SEED)
    return models


def scores(y, p):
    return {"MAE": mean_absolute_error(y, p), "RMSE": float(np.sqrt(mean_squared_error(y, p))),
            "R2": r2_score(y, p)}


def split_by_time(df):
    """Training, validation and test rows, split by date. A row's 6-hour target may not cross a split."""
    first_day = df["time"].min().normalize()
    n_days = int(np.ceil((df["time"].max() - first_day) / pd.Timedelta(days=1)))
    train_end = first_day + pd.Timedelta(days=round(0.70 * n_days))
    val_end = first_day + pd.Timedelta(days=round(0.85 * n_days))
    horizon = pd.Timedelta(hours=S.HORIZON_HOURS)
    train = df[df["time"] + horizon <= train_end]
    val = df[(df["time"] >= train_end) & (df["time"] + horizon <= val_end)]
    test = df[df["time"] >= val_end]
    return train, val, test, train_end, val_end


def overflow_scores(actual_full, alert):
    return {"Precision": precision_score(actual_full, alert, zero_division=0) * 100,
            "Recall": recall_score(actual_full, alert, zero_division=0) * 100,
            "F1": f1_score(actual_full, alert, zero_division=0) * 100,
            "Alerts": int(np.sum(alert))}


def main():
    ap = argparse.ArgumentParser(description="Train and compare fill-level prediction models")
    ap.add_argument("--xgboost", action="store_true", help="also train XGBoost (pip install xgboost first)")
    args = ap.parse_args()
    ensure_dirs()
    need_file(os.path.join(DATA_DIR, "readings.csv"), "Run first:  python b2_make_data.py")
    print("B3 - train and compare the models (RQ2)")
    started = time.time()

    df = load_dataset(os.path.join(DATA_DIR, "readings.csv"), os.path.join(DATA_DIR, "collections.csv"))
    usable = df.dropna(subset=FEATURES + [TARGET])
    train, val, test, train_end, val_end = split_by_time(usable)
    last_day = test["time"].max()
    print(f"Rows with a known 6-hour future: {len(usable):,}  (bins: {usable['bin_id'].nunique()})")
    print(f"  training   {len(train):>7,} rows  {train['time'].min():%d %b} to {train_end - pd.Timedelta(days=1):%d %b}")
    print(f"  validation {len(val):>7,} rows  {train_end:%d %b} to {val_end - pd.Timedelta(days=1):%d %b}")
    print(f"  test       {len(test):>7,} rows  {val_end:%d %b} to {last_day:%d %b}")

    y_train, y_val, y_test = train[TARGET].to_numpy(), val[TARGET].to_numpy(), test[TARGET].to_numpy()
    rows = []

    # 1. Baselines (no learning)
    base = {
        "Persistence (fill stays the same)": lambda d: d["fill"].to_numpy(),
        "Trend (last 3 h fill speed)": lambda d: np.clip(d["fill"] + d["rate_3h"] * S.HORIZON_HOURS, 0, 100).to_numpy(),
    }
    for name, f in base.items():
        rows.append({"Model": name, "Type": "baseline", **scores(y_test, f(test)),
                     "Validation MAE": mean_absolute_error(y_val, f(val))})

    # 2. ML models, all on the B4 features and the same split
    fitted = {}
    for name, model in make_models(args.xgboost).items():
        t0 = time.time()
        print(f"Training {name} ...", end=" ", flush=True)
        model.fit(train[FEATURES].to_numpy(), y_train)
        p_val = np.clip(model.predict(val[FEATURES].to_numpy()), 0, 100)
        p_test = np.clip(model.predict(test[FEATURES].to_numpy()), 0, 100)
        fitted[name] = model
        rows.append({"Model": name, "Type": "ML", **scores(y_test, p_test),
                     "Validation MAE": mean_absolute_error(y_val, p_val)})
        print(f"done in {time.time() - t0:.0f} s")

    table = pd.DataFrame(rows)
    ml = table[table["Type"] == "ML"]
    best_name = ml.sort_values("Validation MAE").iloc[0]["Model"]
    best = fitted[best_name]
    table.round(3).to_csv(os.path.join(RESULTS_DIR, "rq2_models.csv"), index=False)

    print()
    print(f"1) Predicting the fill level 6 hours ahead - test days ({len(test):,} rows)")
    print(f"   {'Model':<36}{'MAE':>7}{'RMSE':>8}{'R2':>8}")
    for _, r in table.iterrows():
        mark = "  <- chosen" if r["Model"] == best_name else ""
        print(f"   {r['Model']:<36}{r['MAE']:>7.2f}{r['RMSE']:>8.2f}{r['R2']:>8.3f}{mark}")
    print("   MAE and RMSE are in fill % points (lower is better). R2: 1.0 is perfect (higher is better).")
    print(f"   Chosen model: {best_name} (lowest MAE on the validation days, not the test days)")

    # 3. Feature test B1 -> B4 with the chosen kind of model
    print()
    print(f"2) Which sensor data helps? Feature test with {best_name} (test days)")
    abl = []
    for key in ("B1", "B2", "B3", "B4"):
        cols = FEATURE_SETS[key]
        if key == "B4":
            m = best
        else:
            m = clone(best)
            m.fit(train[cols].to_numpy(), y_train)
        p = np.clip(m.predict(test[cols].to_numpy()), 0, 100)
        abl.append({"Feature set": FEATURE_SET_NAMES[key], "Inputs": len(cols), **scores(y_test, p)})
        print(f"   {FEATURE_SET_NAMES[key]:<44}{abl[-1]['MAE']:>7.2f}{abl[-1]['RMSE']:>8.2f}{abl[-1]['R2']:>8.3f}")
    pd.DataFrame(abl).round(3).to_csv(os.path.join(RESULTS_DIR, "rq2_feature_test.csv"), index=False)

    # 4. Overflow test: will the bin be 90% or more full in 6 hours?
    p_val = np.clip(best.predict(val[FEATURES].to_numpy()), 0, 100)
    p_test = np.clip(best.predict(test[FEATURES].to_numpy()), 0, 100)
    full_val = y_val >= S.OVERFLOW_PCT
    full_test = y_test >= S.OVERFLOW_PCT
    best_thr, best_f1 = S.OVERFLOW_PCT, -1.0
    for thr in range(60, 96):
        f1 = f1_score(full_val, p_val >= thr, zero_division=0)
        if f1 > best_f1:
            best_thr, best_f1 = thr, f1
    trend_test = np.clip(test["fill"] + test["rate_3h"] * S.HORIZON_HOURS, 0, 100).to_numpy()
    ov = [
        {"Method": f"B0 threshold (current fill >= {S.ALERT_PCT}%)",
         **overflow_scores(full_test, test["fill"].to_numpy() >= S.ALERT_PCT)},
        {"Method": f"Trend (predicted >= {S.OVERFLOW_PCT}%)", **overflow_scores(full_test, trend_test >= S.OVERFLOW_PCT)},
        {"Method": f"{best_name} (predicted >= {best_thr}%)", **overflow_scores(full_test, p_test >= best_thr)},
    ]
    pd.DataFrame(ov).round(1).to_csv(os.path.join(RESULTS_DIR, "rq2_overflow.csv"), index=False)
    print()
    print(f"3) Overflow warning: will the bin be {S.OVERFLOW_PCT}% full or more in 6 hours? "
          f"({int(full_test.sum()):,} of {len(test):,} test rows: yes)")
    print(f"   {'Method':<44}{'Precision':>10}{'Recall':>8}{'F1':>6}{'Alerts':>8}")
    for r in ov:
        print(f"   {r['Method']:<44}{r['Precision']:>9.0f}%{r['Recall']:>7.0f}%{r['F1']:>5.0f}%{r['Alerts']:>8,}")
    print("   Precision: of the alerts, how many were right. Recall: of the real overflows, how many got an alert.")

    # 5. Which inputs matter most (permutation importance on 3,000 validation rows)
    sample = val.sample(n=min(3000, len(val)), random_state=S.SEED)
    imp = permutation_importance(best, sample[FEATURES].to_numpy(), sample[TARGET].to_numpy(),
                                 scoring="neg_mean_absolute_error", n_repeats=3, random_state=S.SEED)
    importance = pd.Series(imp.importances_mean, index=FEATURES).sort_values(ascending=False)
    importance.round(3).rename("MAE increase").to_csv(os.path.join(RESULTS_DIR, "rq2_inputs.csv"))
    top = importance.head(10)
    print()
    print("4) Most useful inputs (how much the error grows when the input is scrambled):")
    print("   " + ", ".join(f"{NICE_NAMES[k]} {v:.2f}" for k, v in top.head(5).items()))

    # 6. Check on the real bin, if its data is there (from b2_make_data.py)
    real_csv = os.path.join(DATA_DIR, "real_readings.csv")
    if os.path.exists(real_csv):
        real = load_dataset(real_csv, os.path.join(DATA_DIR, "real_collections.csv"))
        real = real.dropna(subset=FEATURES + [TARGET])
        print()
        if len(real) >= 12:
            pr = np.clip(best.predict(real[FEATURES].to_numpy()), 0, 100)
            print(f"5) Check on your REAL bin ({len(real)} rows): MAE {mean_absolute_error(real[TARGET], pr):.2f}"
                  f"  (persistence {mean_absolute_error(real[TARGET], real['fill']):.2f})")
        else:
            print(f"5) Real bin: only {len(real)} rows with a known 6-hour future (12 needed). "
                  "Let the bin run longer, export again and re-run b2 and b3.")

    # 7. Save the model and the charts
    pack = {"model": best, "name": best_name, "features": FEATURES, "overflow_threshold": best_thr,
            "horizon_hours": S.HORIZON_HOURS, "step_minutes": S.STEP_MINUTES,
            "trained_on": f"synthetic data, {S.N_DAYS} days x {usable['bin_id'].nunique()} bins",
            "created": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}
    joblib.dump(pack, os.path.join(RESULTS_DIR, "model.joblib"), compress=3)

    subtitle = f"Test days {val_end:%d %b} to {last_day:%d %b}, {usable['bin_id'].nunique()} synthetic bins"
    charts.model_bars(list(table["Model"]), list(table["MAE"]), list(table["Type"] == "ML"),
                      os.path.join(RESULTS_DIR, "chart_models.png"), subtitle)
    charts.importance_bars([NICE_NAMES[k] for k in top.index], list(top.values),
                           os.path.join(RESULTS_DIR, "chart_inputs.png"),
                           f"{best_name}, 3,000 validation rows")
    # example: a bin that gets close to full often but is rarely stuck at 100%, first 3 test days
    window = df[(df["time"] >= val_end) & (df["time"] < val_end + pd.Timedelta(days=3))]
    score = window.groupby("bin_id")["fill"].apply(lambda s: (s >= S.OVERFLOW_PCT).sum() - 2 * (s >= 99).sum())
    example_bin = score.idxmax()
    ex = window[window["bin_id"] == example_bin].reset_index(drop=True)
    pred = np.full(len(ex), np.nan)
    ok = ex[FEATURES].notna().all(axis=1) & ex[TARGET].notna()  # no emptying in the next 6 hours
    pred[ok.to_numpy()] = np.clip(best.predict(ex.loc[ok, FEATURES].to_numpy()), 0, 100)
    pred_times = ex["time"] + pd.Timedelta(hours=S.HORIZON_HOURS)
    keep = (pred_times <= ex["time"].max()).to_numpy()
    charts.example_lines(list(ex["time"]), list(ex["fill"]), list(pred_times[keep]), list(pred[keep]),
                         os.path.join(RESULTS_DIR, "chart_example.png"),
                         f"Real fill vs the prediction made 6 hours earlier - bin {example_bin}",
                         f"{best_name}, 3 test days. Gaps: the bin was emptied inside those 6 hours.",
                         S.OVERFLOW_PCT)
    print()
    print("Saved: results/model.joblib, results/rq2_models.csv, results/rq2_feature_test.csv,")
    print("       results/rq2_overflow.csv, results/rq2_inputs.csv,")
    print("       results/chart_models.png, results/chart_example.png, results/chart_inputs.png")
    print(f"Done in {time.time() - started:.0f} s. Next: python b4_test_urgency_and_nearest.py")


if __name__ == "__main__":
    main()
