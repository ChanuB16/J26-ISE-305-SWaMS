"""
B4 - TEST THE URGENCY SCORE (RQ3) AND THE NEAREST-BIN FINDER (RQ4)
=================================================================
Uses the model from b3_train_models.py on the TEST days only.

RQ3 - which bins should the truck empty first? Every test day at 06:00 and 14:00 all bins are
ranked three ways (proposal, Table 8):
  U0 = current fill only
  U1 = predicted fill (6 hours ahead) only
  U2 = the proposal's urgency score:
       0.5 x predicted fill + 0.2 x gas index + 0.1 x humidity + 0.2 x time score
  A bin "needs early collection" if, in the next 6 hours, it reaches 90% fill OR its gas index
  reaches 60 (strong smell). This rule is our assumption - write it in the report.
  Top-5 recall = of the bins that needed early collection, how many were in the top 5.

RQ4 - a citizen wants the nearest bin with space. 500 test requests at random places and times:
  R0 = the nearest bin, full or not
  R1 = the nearest bin whose current fill is below 80% AND predicted fill is below 90%
       (within 2 km; if none, the nearest bin below 80%)
  Success = the recommended bin is still below 90% one hour later.

Run:  python b4_test_urgency_and_nearest.py
Needs: data/*.csv (b2) and results/model.joblib (b3)
Makes: results/rq3_urgency.csv, results/rq4_nearest.csv, results/chart_urgency.png
"""
import os

import joblib
import numpy as np
import pandas as pd

import charts
import settings as S
from binlib import DATA_DIR, RESULTS_DIR, distance_km, load_dataset, need_file, predict_rows, urgency

TOP_K = 5


def main():
    need_file(os.path.join(DATA_DIR, "readings.csv"), "Run first:  python b2_make_data.py")
    need_file(os.path.join(RESULTS_DIR, "model.joblib"), "Run first:  python b3_train_models.py")
    print("B4 - test the urgency score (RQ3) and the nearest-bin finder (RQ4)")
    pack = joblib.load(os.path.join(RESULTS_DIR, "model.joblib"))
    bins = pd.read_csv(os.path.join(DATA_DIR, "bins.csv")).set_index("bin_id")
    df = load_dataset(os.path.join(DATA_DIR, "readings.csv"), os.path.join(DATA_DIR, "collections.csv"))

    first_day = df["time"].min().normalize()
    n_days = int(np.ceil((df["time"].max() - first_day) / pd.Timedelta(days=1)))
    test_start = first_day + pd.Timedelta(days=round(0.85 * n_days))
    test_end = df["time"].max() - pd.Timedelta(hours=S.HORIZON_HOURS)  # need the next 6 hours to judge
    test = df[(df["time"] >= test_start) & (df["time"] <= test_end)].copy()
    test = test.dropna(subset=pack["features"])
    test["pred"] = predict_rows(pack, test)
    print(f"Model: {pack['name']}   Test days: {test_start:%d %b} to {test_end:%d %b}")

    # ---------------- RQ3: urgency ranking ----------------
    test["U0"] = test["fill"]
    test["U1"] = test["pred"]
    test["U2"] = urgency(test["pred"], test["gas"], test["humidity"], test["hours_since_collection"])
    test["needs_early"] = (test["max_fill_next_6h"] >= S.OVERFLOW_PCT) | (test["max_gas_next_6h"] >= S.SMELL_INDEX)
    test["overflows"] = test["max_fill_next_6h"] >= S.OVERFLOW_PCT
    decisions = test[test["time"].dt.strftime("%H:%M").isin(["06:00", "14:00"])]
    results = {m: {"needs_early": [], "overflows": []} for m in ("U0", "U1", "U2")}
    n_times, n_needing = 0, 0
    for _, snap in decisions.groupby("time"):
        n_times += 1
        for truth in ("needs_early", "overflows"):
            needing = set(snap.loc[snap[truth], "bin_id"])
            if truth == "needs_early":
                n_needing += len(needing)
            if not needing:
                continue
            for m in ("U0", "U1", "U2"):
                top = set(snap.nlargest(TOP_K, m)["bin_id"])
                results[m][truth].append(len(needing & top) / len(needing))
    names = {"U0": "U0 current fill only", "U1": "U1 predicted fill only", "U2": "U2 urgency score (proposal)"}
    rq3 = pd.DataFrame([{"Ranking": names[m],
                         "Top-5 recall, needs early collection (%)": 100 * np.mean(results[m]["needs_early"]),
                         "Top-5 recall, overflow only (%)": 100 * np.mean(results[m]["overflows"])}
                        for m in ("U0", "U1", "U2")])
    rq3.round(1).to_csv(os.path.join(RESULTS_DIR, "rq3_urgency.csv"), index=False)
    print()
    print(f"1) RQ3 - which bins to empty first? {n_times} decision times (06:00 and 14:00), "
          f"{n_needing} cases of a bin needing early collection")
    print(f"   {'Ranking':<30}{'Top-5 recall':>14}{'Overflow only':>15}")
    for _, r in rq3.iterrows():
        print(f"   {r['Ranking']:<30}{r.iloc[1]:>13.0f}%{r.iloc[2]:>14.0f}%")
    print("   Top-5 recall: of the bins that needed early collection, the share that was in the top 5.")

    # ---------------- RQ4: nearest bin with space ----------------
    rng = np.random.default_rng(S.SEED)
    centres = bins.groupby("zone")[["lat", "lng"]].mean().to_numpy()
    by_time = {t: snap.set_index("bin_id") for t, snap in test.groupby("time")}
    day_times = [t for t in by_time if 6 <= t.hour <= 21]
    rows = []
    for _ in range(500):
        t = day_times[rng.integers(len(day_times))]
        snap = by_time[t]
        lat, lng = centres[rng.integers(len(centres))] + rng.normal(0, 0.006, 2)
        cand = snap.join(bins[["lat", "lng"]], how="inner")
        cand = cand.assign(km=[distance_km(lat, lng, a, b) for a, b in zip(cand["lat"], cand["lng"])])
        cand = cand.sort_values("km")
        r0 = cand.index[0]
        ok = cand[(cand["fill"] < S.SPACE_LIMIT_PCT) & (cand["pred"] < S.OVERFLOW_PCT) & (cand["km"] <= S.MAX_WALK_KM)]
        if len(ok) == 0:
            ok = cand[cand["fill"] < S.SPACE_LIMIT_PCT]
        r1 = ok.index[0] if len(ok) else r0
        for method, b in (("R0", r0), ("R1", r1)):
            later = cand.loc[b, "fill_next_1h"]
            rows.append({"method": method, "bin": b, "km": cand.loc[b, "km"],
                         "success": bool(pd.notna(later) and later < S.OVERFLOW_PCT)})
    rec = pd.DataFrame(rows)
    rq4 = rec.groupby("method").agg(success=("success", "mean"), km=("km", "mean")).reset_index()
    changed = (rec[rec.method == "R0"]["bin"].to_numpy() != rec[rec.method == "R1"]["bin"].to_numpy()).mean()
    rq4["success"] *= 100
    rq4 = rq4.rename(columns={"method": "Method", "success": "Success (%)", "km": "Average distance (km)"})
    rq4["Method"] = rq4["Method"].map({"R0": "R0 nearest bin only", "R1": "R1 nearest bin with space (proposal)"})
    rq4.round(2).to_csv(os.path.join(RESULTS_DIR, "rq4_nearest.csv"), index=False)
    print()
    print("2) RQ4 - nearest bin with space: 500 test requests")
    print(f"   {'Method':<40}{'Success':>8}{'Avg distance':>14}")
    for _, r in rq4.iterrows():
        print(f"   {r['Method']:<40}{r['Success (%)']:>7.0f}%{r['Average distance (km)']:>11.2f} km")
    print(f"   R1 chose a different bin than R0 in {changed * 100:.0f}% of the requests.")
    print("   Success: the bin was still below 90% one hour later. Distance: straight line.")

    charts.grouped_bars(["U0\ncurrent fill", "U1\npredicted fill", "U2\nurgency score"],
                        ["Needs early collection (full or smelly)", "Overflow only"],
                        [list(rq3.iloc[:, 1]), list(rq3.iloc[:, 2])],
                        os.path.join(RESULTS_DIR, "chart_urgency.png"),
                        "Which ranking finds the bins that need the truck first?",
                        f"Top-5 recall over {n_times} decision times on the test days, 20 synthetic bins",
                        "Top-5 recall (%)")
    print()
    print("Saved: results/rq3_urgency.csv, results/rq4_nearest.csv, results/chart_urgency.png")
    print("Done. Next: live predictions with  python b5_live_predictions.py  (needs the real bin running)")


if __name__ == "__main__":
    main()
