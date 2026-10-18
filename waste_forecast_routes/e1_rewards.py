"""
E1 - CITIZEN REWARDS (proposal objective 4)
===========================================
Gives points to citizens and saves them in Firebase:

  +10 points  a waste photo classified by Component 1 (classifications/<id>, confidence 70% or more)
  +5 points   a report of a full bin (reports/<id>, type "overflowing_bin"), CONFIRMED by the bin's
              own sensor: the bin was 80% full or more (Part A/B data) - so fake reports get no points
  x2          on a forecast high-waste day in that area (step F3), to get help on busy days

It reads:  classifications/<id>   {user, waste_type, confidence, ts, zone (optional)}   (Component 1)
           reports/<id>           {user, bin_id, type, ts, note}                         (citizen app)
It writes: rewards/<user>/points, rewards/<user>/history/<id>, rewards/_processed/<id>

Each photo or report is counted only once (rewards/_processed), so you can run it as often as you
like (for example every 10 minutes).

Run:  python e1_rewards.py           (process new photos and reports)
      python e1_rewards.py --demo    (first adds 3 EXAMPLE photos and 3 EXAMPLE reports to test)
"""
import argparse
import time

import pandas as pd

import settings as S
from wastelib import TZ, Firebase


def add_demo_items(fb):
    now = int(time.time() * 1000)
    bins = fb.get("bins", shallow="true") or {}
    some_bins = sorted(bins)[:3] or ["sim_01", "sim_02", "sim_03"]
    for i, (user, kind, conf) in enumerate([("demo_user_1", "plastic", 0.91), ("demo_user_2", "paper", 0.84),
                                            ("demo_user_1", "glass", 0.55)]):
        fb.post("classifications", {"user": user, "waste_type": kind, "confidence": conf, "ts": now - i * 60000,
                                    "zone": "Malabe", "example": True})
    for i, b in enumerate(some_bins):
        fb.post("reports", {"user": f"demo_user_{i % 2 + 1}", "bin_id": b, "type": "overflowing_bin",
                            "ts": now - i * 60000, "note": "EXAMPLE report", "example": True})
    print(f"Added 3 example photos and {len(some_bins)} example reports (marked example: true).")


def bin_fill_at(fb, bin_id, ts):
    """The bin's fill level around the time of the report (latest reading, or the readings near ts)."""
    latest = fb.get(f"bins/{bin_id}/latest") or {}
    if isinstance(latest, dict) and latest.get("ts") and abs(float(latest["ts"]) - ts) < 2 * 3600 * 1000:
        return latest.get("fill_pct")
    near = fb.get(f"bins/{bin_id}/readings", orderBy='"$key"', startAt=f'"{int(ts - 3600 * 1000)}"',
                  endAt=f'"{int(ts + 3600 * 1000)}"') or {}
    fills = [r.get("fill_pct") for r in near.values() if isinstance(r, dict) and r.get("fill_pct") is not None]
    if fills:
        return max(fills)
    return latest.get("fill_pct") if isinstance(latest, dict) else None


def high_waste_day(fb, zone, ts, cache):
    if not zone:
        return False
    day = pd.Timestamp(ts, unit="ms", tz="UTC").tz_convert(TZ).strftime("%Y-%m-%d")
    key = (zone, day)
    if key not in cache:
        f = fb.get(f"forecasts/{zone}/{day}") or {}
        cache[key] = bool(f.get("high_waste")) if isinstance(f, dict) else False
    return cache[key]


def main():
    ap = argparse.ArgumentParser(description="Citizen reward points")
    ap.add_argument("--demo", action="store_true", help="add example photos and reports first")
    args = ap.parse_args()
    fb = Firebase()
    print("E1 - citizen rewards")
    if args.demo:
        add_demo_items(fb)
    processed = fb.get("rewards/_processed", shallow="true") or {}
    photos = fb.get("classifications") or {}
    reports = fb.get("reports") or {}
    bins = fb.get("bins", shallow="true") or {}
    cache, update, points = {}, {}, {}
    given = 0
    for pid, c in photos.items():
        if pid in processed or not isinstance(c, dict) or not c.get("user"):
            continue
        ts = int(c.get("ts") or time.time() * 1000)
        ok = float(c.get("confidence") or 0) >= 0.70
        pts = S.POINTS_SEGREGATION_PHOTO if ok else 0
        double = ok and high_waste_day(fb, c.get("zone"), ts, cache)
        pts *= S.HIGH_WASTE_DAY_BONUS if double else 1
        note = f"{c.get('waste_type', 'waste')} photo" + ("" if ok else " (confidence below 70%, no points)") + \
            (" - busy day x2" if double else "")
        update[f"rewards/{c['user']}/history/{pid}"] = {"ts": ts, "action": "segregation_photo", "points": pts,
                                                       "note": note}
        update[f"rewards/_processed/{pid}"] = True
        points[c["user"]] = points.get(c["user"], 0) + pts
        given += 1
    for rid, r in reports.items():
        if rid in processed or not isinstance(r, dict) or not r.get("user"):
            continue
        ts = int(r.get("ts") or time.time() * 1000)
        b = r.get("bin_id")
        pts, note = 0, "report"
        if r.get("type") == "overflowing_bin" and b in bins:
            fill = bin_fill_at(fb, b, ts)
            if fill is not None and float(fill) >= 80:
                info = fb.get(f"bins/{b}/info") or {}
                double = high_waste_day(fb, info.get("zone"), ts, cache)
                pts = S.POINTS_OVERFLOW_REPORT * (S.HIGH_WASTE_DAY_BONUS if double else 1)
                note = f"full bin {b} confirmed by its sensor ({float(fill):.0f}%)" + (" - busy day x2" if double else "")
            else:
                note = f"bin {b} not confirmed by its sensor ({'no data' if fill is None else f'{float(fill):.0f}%'})"
        else:
            note = "report without a known bin"
        update[f"rewards/{r['user']}/history/{rid}"] = {"ts": ts, "action": "overflow_report", "points": pts,
                                                       "note": note}
        update[f"rewards/_processed/{rid}"] = True
        points[r["user"]] = points.get(r["user"], 0) + pts
        given += 1
    for user, add in points.items():
        old = fb.get(f"rewards/{user}/points") or 0
        update[f"rewards/{user}/points"] = int(old) + add
    if update:
        fb.patch("", update)
    print(f"Processed {given} new photos/reports, {sum(points.values())} points given.")
    board = fb.get("rewards") or {}
    top = sorted(((u, v.get("points", 0)) for u, v in board.items() if u != "_processed" and isinstance(v, dict)),
                 key=lambda x: -x[1])[:5]
    if top:
        print("Top citizens: " + ", ".join(f"{u} {p} points" for u, p in top))


if __name__ == "__main__":
    main()
