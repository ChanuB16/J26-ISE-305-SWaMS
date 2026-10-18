"""
B6 - NEAREST BIN WITH SPACE FOR A CITIZEN (RQ4, live)
=====================================================
Give a location (latitude longitude). The script reads every bin's location and prediction from
Firebase and prints two answers:
  R0 = the nearest bin (full or not)
  R1 = the nearest bin that has space now (fill below 80%) and in 6 hours (predicted below 90%),
       within 2 km. If there is none, the nearest bin below 80%.

Every bin needs a location: bins/<bin_id>/info with lat and lng (Part A, Stage 10, step 8).
b5_live_predictions.py copies it into predictions/<bin_id>.

Run:  python b6_nearest_bin.py 6.9061 79.9696
      (find a latitude and longitude: Google Maps > right-click a place > click the numbers to copy)
"""
import sys
import time

import settings as S
from binlib import Firebase, distance_km


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Use like this:  python b6_nearest_bin.py 6.9061 79.9696   (latitude longitude)")
    lat, lng = float(sys.argv[1]), float(sys.argv[2])
    t0 = time.time()
    fb = Firebase()
    preds = fb.get("predictions") or {}
    bins = []
    for bin_id, p in preds.items():
        if not isinstance(p, dict):
            continue
        if "lat" not in p or "lng" not in p:
            info = fb.get(f"bins/{bin_id}/info") or {}
            if not isinstance(info, dict) or "lat" not in info:
                print(f"  (skipped {bin_id}: no location. Add bins/{bin_id}/info with lat and lng.)")
                continue
            p = {**p, "lat": info["lat"], "lng": info["lng"]}
        if p.get("current_fill_pct") is None:
            continue
        p["bin_id"] = bin_id
        p["km"] = distance_km(lat, lng, float(p["lat"]), float(p["lng"]))
        bins.append(p)
    if not bins:
        raise SystemExit("No bins with a location and a prediction yet. Run b5_live_predictions.py "
                         "(and b6_demo_bins.py --add for demo bins) first.")
    bins.sort(key=lambda b: b["km"])
    r0 = bins[0]
    ok = [b for b in bins if b["current_fill_pct"] < S.SPACE_LIMIT_PCT
          and b.get("predicted_fill_6h", b["current_fill_pct"]) < S.OVERFLOW_PCT and b["km"] <= S.MAX_WALK_KM]
    if not ok:
        ok = [b for b in bins if b["current_fill_pct"] < S.SPACE_LIMIT_PCT]
    r1 = ok[0] if ok else r0

    def line(b):
        pred = f", in 6 h {b['predicted_fill_6h']:.0f}%" if "predicted_fill_6h" in b else ""
        name = b.get("zone", "")
        return f"{b['bin_id']} {name} - {b['km'] * 1000:.0f} m away, fill now {b['current_fill_pct']:.0f}%{pred}"

    print(f"Citizen at {lat:.5f}, {lng:.5f} - {len(bins)} bins checked")
    print(f"  R0 nearest bin:          {line(r0)}")
    print(f"  R1 nearest with space:   {line(r1)}" + ("" if ok else "   (no bin with space found)"))
    print(f"  Answer in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
