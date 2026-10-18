"""
B5 - LIVE PREDICTIONS FROM THE REAL BIN (RQ5)
=============================================
Every 5 minutes, for every bin in Firebase:
  1. reads the last 8 hours of readings, the last emptying time and the bin location
  2. puts them on the 15-minute grid and makes the same inputs the model was trained with
  3. predicts the fill level in 6 hours, the overflow risk, the hours until full and the urgency score
  4. writes the result to  predictions/<bin_id>  in Firebase (Component 3 and the dashboard read it)

It also prints the end-to-end delay: from the newest sensor reading to the stored prediction.

Before you run it: set FIREBASE_DB_URL in settings.py, and keep the bin running (Part A, Stage 8).
Demo bins made by b6_demo_bins.py (ids starting with "sim_") are skipped: they get their
predictions from b6_demo_bins.py.

Run:  python b5_live_predictions.py           (runs until you press Ctrl+C)
      python b5_live_predictions.py --once    (one round, then stops)
Needs: results/model.joblib (from b3_train_models.py)
"""
import argparse
import os
import time

import joblib
import numpy as np
import pandas as pd

import settings as S
from binlib import FEATURE_SETS, LIVE_DEFAULTS, RESULTS_DIR, Firebase, add_features, hours_to_full, \
    need_file, overflow_risk, to_grid, urgency


def predict_bin(fb, pack, bin_id):
    now_ms = int(time.time() * 1000)
    since = now_ms - 8 * 3600 * 1000
    readings = fb.readings_since(bin_id, since)
    info = fb.get(f"bins/{bin_id}/info") or {}
    out = {"bin_id": bin_id, "updated_at": {".sv": "timestamp"}, "model": pack["name"]}
    if isinstance(info, dict):
        for k in ("lat", "lng", "zone"):
            if k in info:
                out[k] = info[k]

    if readings.empty or "ts" not in readings.columns:
        latest = fb.get(f"bins/{bin_id}/latest") or {}
        out.update(status="no_recent_data", based_on_ts=latest.get("ts") if isinstance(latest, dict) else None)
        if isinstance(latest, dict) and "fill_pct" in latest:
            out["current_fill_pct"] = latest["fill_pct"]
        return out, None

    newest_ts = int(pd.to_numeric(readings["ts"], errors="coerce").max())
    out["based_on_ts"] = newest_ts
    last_collected = fb.get(f"bins/{bin_id}/last_collected")
    coll = [last_collected] if isinstance(last_collected, (int, float)) else []

    grid = to_grid(readings)
    feats = add_features(grid, coll, live=True)
    feats = feats[feats["fill"].notna()]
    if feats.empty:
        out.update(status="no_recent_data")
        return out, newest_ts
    row = feats.iloc[[-1]].copy()
    for col, value in LIVE_DEFAULTS.items():
        row[col] = row[col].fillna(value)
    if not isinstance(last_collected, (int, float)):
        # never emptied yet: count from the bin's very first reading
        first = fb.get(f"bins/{bin_id}/readings", orderBy='"$key"', limitToFirst=1) or {}
        first_ts = min((int(k) for k in first.keys() if str(k).isdigit()), default=None)
        if first_ts is not None:
            row["hours_since_collection"] = max(0.0, (row.index[0].value // 1_000_000 - first_ts) / 3.6e6)
    x = row[pack["features"]].to_numpy(dtype=float)
    if np.isnan(x).any():
        out.update(status="no_recent_data", current_fill_pct=round(float(row["fill"].iloc[0]), 1))
        return out, newest_ts

    fill_now = float(row["fill"].iloc[0])
    age_minutes = (now_ms - newest_ts) / 60000
    if age_minutes > S.NO_DATA_MINUTES:
        # old data: show the last known fill, but no prediction (proposal: no unreliable predictions)
        out.update(status="no_recent_data", current_fill_pct=round(fill_now, 1))
        return out, newest_ts
    pred = float(np.clip(pack["model"].predict(x)[0], 0, 100))
    hsc = float(row["hours_since_collection"].iloc[0])
    gas = float(row["gas"].iloc[0])
    hum = float(row["humidity"].iloc[0])
    status = "warming_up" if float(row["history_hours"].iloc[0]) < S.HORIZON_HOURS else "ok"
    out.update(current_fill_pct=round(fill_now, 1), predicted_fill_6h=round(pred, 1),
               overflow_risk=overflow_risk(pred),
               urgency_score=int(round(float(urgency(pred, gas, hum, hsc)))),
               gas_index=round(gas, 1), humidity_pct=round(hum, 1),
               hours_since_collection=round(hsc, 1), status=status)
    htf = hours_to_full(fill_now, pred)
    if htf is not None:
        out["hours_to_full"] = htf
    return out, newest_ts


def one_round(fb, pack):
    ids = [b for b in fb.bin_ids() if not b.startswith("sim_")]
    if not ids:
        print("No bins found under 'bins' in Firebase. Is the bin running (Part A, Stage 8)?")
        return
    for bin_id in ids:
        t0 = time.time()
        out, newest_ts = predict_bin(fb, pack, bin_id)
        fb.put(f"predictions/{bin_id}", out)
        done_ms = int(time.time() * 1000)
        stamp = time.strftime("%H:%M:%S")
        if "predicted_fill_6h" in out:
            full = f"{out['hours_to_full']:.1f} h" if "hours_to_full" in out else "not filling"
            delay = (done_ms - newest_ts) / 1000
            print(f"[{stamp}] {bin_id}: fill {out['current_fill_pct']:.1f}% -> in 6 h {out['predicted_fill_6h']:.1f}% "
                  f"| risk {out['overflow_risk']} | urgency {out['urgency_score']} | full in {full} "
                  f"| {out['status']} | reading to prediction {delay:.1f} s (model {time.time() - t0:.1f} s)")
        else:
            last = f" (last fill {out['current_fill_pct']:.1f}%)" if "current_fill_pct" in out else ""
            print(f"[{stamp}] {bin_id}: no_recent_data - no reading in the last {S.NO_DATA_MINUTES} minutes{last}. "
                  "Is the bin switched on and online?")


def main():
    ap = argparse.ArgumentParser(description="Live fill predictions into Firebase")
    ap.add_argument("--once", action="store_true", help="one round, then stop")
    args = ap.parse_args()
    need_file(os.path.join(RESULTS_DIR, "model.joblib"), "Run first:  python b3_train_models.py")
    pack = joblib.load(os.path.join(RESULTS_DIR, "model.joblib"))
    if pack["features"] != FEATURE_SETS["B4"]:
        raise SystemExit("The model file is from another version. Run b3_train_models.py again.")
    fb = Firebase()
    print(f"B5 - live predictions with {pack['name']} every {S.LIVE_EVERY_MINUTES} min (Ctrl+C to stop)")
    while True:
        one_round(fb, pack)
        if args.once:
            break
        time.sleep(S.LIVE_EVERY_MINUTES * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
