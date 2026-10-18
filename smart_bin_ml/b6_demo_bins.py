"""
B6 - DEMO BINS FOR THE TEAM (optional)
======================================
There is only one real bin. To let Component 3 (route planning) and the dashboard test with many
bins before PP1, this script copies the 20 SYNTHETIC bins from step B2 into Firebase:

  bins/sim_01 ... sim_20/info     location, zone, type   (with "synthetic": true)
  bins/sim_01 ... sim_20/latest   the sensor values at one moment of the synthetic data
  predictions/sim_01 ... sim_20   predicted fill, overflow risk, urgency score (same format as B5)

The real bin (bin_01) is not touched. Tell the team these bins are synthetic, and remove them
before anyone exports data for the report.

Run:  python b6_demo_bins.py --add       (moment used: the last synthetic day at 14:00)
      python b6_demo_bins.py --remove    (deletes sim_01 ... sim_20 again)
Needs: data/*.csv (b2) and results/model.joblib (b3)
"""
import argparse
import os

import joblib
import numpy as np
import pandas as pd

import settings as S
from binlib import DATA_DIR, RESULTS_DIR, Firebase, hours_to_full, load_dataset, need_file, overflow_risk, \
    predict_rows, urgency


def main():
    ap = argparse.ArgumentParser(description="Add or remove the synthetic demo bins in Firebase")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", action="store_true")
    group.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    need_file(os.path.join(DATA_DIR, "bins.csv"), "Run first:  python b2_make_data.py")
    bins = pd.read_csv(os.path.join(DATA_DIR, "bins.csv")).set_index("bin_id")
    fb = Firebase()

    if args.remove:
        update = {}
        for bin_id in bins.index:
            update[f"bins/{bin_id}"] = None
            update[f"predictions/{bin_id}"] = None
        fb.patch("", update)
        print(f"Removed {len(bins)} demo bins (sim_01 to sim_{len(bins):02d}) from Firebase.")
        return

    need_file(os.path.join(RESULTS_DIR, "model.joblib"), "Run first:  python b3_train_models.py")
    pack = joblib.load(os.path.join(RESULTS_DIR, "model.joblib"))
    df = load_dataset(os.path.join(DATA_DIR, "readings.csv"), os.path.join(DATA_DIR, "collections.csv"))
    at_two = df.loc[(df["time"].dt.hour == 14) & (df["time"].dt.minute == 0), "time"]
    moment = at_two.max()  # the last 14:00 in the synthetic data
    snap = df[df["time"] == moment].dropna(subset=pack["features"]).copy()
    snap["pred"] = predict_rows(pack, snap)
    now = pd.Timestamp.now(tz="Asia/Colombo")
    update = {}
    for _, r in snap.iterrows():
        b = bins.loc[r["bin_id"]]
        pred = float(r["pred"])
        info = {"name": b["name"], "zone": b["zone"], "type": b["type"], "lat": float(b["lat"]),
                "lng": float(b["lng"]), "capacity_l": int(b["capacity_l"]), "synthetic": True}
        latest = {"bin_id": r["bin_id"], "ts": int(now.value // 1_000_000), "time_local": now.strftime("%Y-%m-%d %H:%M:%S"),
                  "fill_pct": round(float(r["fill"]), 1), "weight_kg": round(float(r["weight"]), 2),
                  "gas_index": round(float(r["gas"]), 1), "humidity_pct": round(float(r["humidity"]), 1),
                  "temp_c": round(float(r["temp"]), 1), "synthetic": True}
        prediction = {"bin_id": r["bin_id"], "current_fill_pct": latest["fill_pct"],
                      "predicted_fill_6h": round(pred, 1), "overflow_risk": overflow_risk(pred),
                      "urgency_score": int(round(float(urgency(pred, r["gas"], r["humidity"],
                                                                r["hours_since_collection"])))),
                      "gas_index": latest["gas_index"], "humidity_pct": latest["humidity_pct"],
                      "hours_since_collection": round(float(r["hours_since_collection"]), 1),
                      "lat": info["lat"], "lng": info["lng"], "zone": info["zone"], "status": "demo",
                      "based_on_ts": latest["ts"], "updated_at": {".sv": "timestamp"}, "model": pack["name"],
                      "synthetic": True}
        htf = hours_to_full(latest["fill_pct"], pred)
        if htf is not None:
            prediction["hours_to_full"] = htf
        update[f"bins/{r['bin_id']}/info"] = info
        update[f"bins/{r['bin_id']}/latest"] = latest
        update[f"predictions/{r['bin_id']}"] = prediction
    fb.patch("", update)
    top = snap.assign(u=urgency(snap["pred"], snap["gas"], snap["humidity"], snap["hours_since_collection"]))
    top = top.sort_values("u", ascending=False).head(3)
    print(f"Added {len(snap)} demo bins (synthetic moment {moment:%Y-%m-%d %H:%M}) to Firebase.")
    print("Most urgent: " + ", ".join(f"{r.bin_id} ({r.u:.0f})" for r in top.itertuples()))
    print("Remove them later with:  python b6_demo_bins.py --remove")


if __name__ == "__main__":
    main()
