"""
SMART BIN - RQ1 METRICS + DATASET EXPORT
========================================
Reads a Firebase Realtime Database export (JSON) and prints the numbers the
C2 proposal asks for under RQ1:
  - valid sensor reading rate (per sensor and overall)
  - transmission success rate (readings received / readings taken)
  - end-to-end latency (board time -> Firebase arrival time)
It also writes readings.csv and collections.csv for the prediction (ML) part.

How to get the export:
  Firebase console > Realtime Database > Data > the 3-dot menu > Export JSON

Run (Python 3, no extra packages needed):
  python rq1_metrics.py smart-bin-export.json
  python rq1_metrics.py smart-bin-export.json --bin bin_01
"""
import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone

SL_TIME = timezone(timedelta(hours=5, minutes=30))
SENSORS = [
    ("Ultrasonic (fill)", "fill_pct"),
    ("Load cell (weight)", "weight_kg"),
    ("Gas (MQ-135)", "gas_mv"),
    ("Temperature (DHT22)", "temp_c"),
    ("Humidity (DHT22)", "humidity_pct"),
]
CSV_FIELDS = ["bin_id", "ts", "time_local", "fill_pct", "distance_cm", "weight_kg", "gas_mv", "gas_index",
              "gas_ready", "temp_c", "humidity_pct", "battery_v", "battery_pct", "urgency_now", "boot", "seq",
              "server_ts", "queue_s", "errors"]


def find_bins(data):
    """Accepts a whole-database export, the 'bins' node, or one bin node."""
    if isinstance(data, dict) and "bins" in data:
        return data["bins"]
    if isinstance(data, dict) and "readings" in data:
        return {"bin": data}
    return data


def pct(a, b):
    return 100.0 * a / b if b else 0.0


def gas_ok(r):
    return isinstance(r.get("gas_mv"), (int, float)) and r["gas_mv"] >= 5


def sensor_valid(r, field):
    if field == "gas_mv":
        return gas_ok(r)
    return field in r and r[field] is not None


def fmt_time(ms):
    return datetime.fromtimestamp(ms / 1000, SL_TIME).strftime("%Y-%m-%d %H:%M:%S")


def report(bin_id, node, out_prefix):
    readings = node.get("readings") or {}
    rows = sorted(readings.values(), key=lambda r: r.get("ts", 0))
    if not rows:
        print(f"[{bin_id}] no readings found")
        return
    n = len(rows)
    print(f"\n=== {bin_id}: {n} readings, {fmt_time(rows[0]['ts'])} to {fmt_time(rows[-1]['ts'])} (Sri Lanka time) ===")

    # 1. valid reading rate
    print("\n1) Valid sensor reading rate")
    for name, field in SENSORS:
        good = sum(1 for r in rows if sensor_valid(r, field))
        print(f"   {name:<22} {good:>6}/{n:<6} {pct(good, n):6.1f} %")
    all_good = sum(1 for r in rows if all(sensor_valid(r, f) for _, f in SENSORS))
    print(f"   {'All sensors valid':<22} {all_good:>6}/{n:<6} {pct(all_good, n):6.1f} %")

    # 2. transmission success (per power-on, using the reading number 'seq')
    print("\n2) Transmission success rate (readings received / readings taken)")
    by_boot = {}
    for r in rows:
        if "seq" in r and "boot" in r:
            by_boot.setdefault(r["boot"], set()).add(r["seq"])
    tot_rx = tot_exp = 0
    for boot, seqs in sorted(by_boot.items()):
        expected = max(seqs)  # numbers start at 1 after every power-on
        tot_rx += len(seqs)
        tot_exp += expected
        print(f"   start #{boot:<4} received {len(seqs):>6} of {expected:<6} {pct(len(seqs), expected):6.1f} %")
    if tot_exp:
        print(f"   {'Overall':<11} received {tot_rx:>6} of {tot_exp:<6} {pct(tot_rx, tot_exp):6.1f} %")
        print("   (readings taken in the last minutes before a power cut, or more than 4 hours offline, can be lost)")
    else:
        print("   no 'seq' numbers found (firmware older than 1.1.0)")

    # 3. latency
    print("\n3) End-to-end latency: board measurement -> stored in Firebase")
    live, queued = [], 0
    for r in rows:
        if isinstance(r.get("server_ts"), (int, float)) and r.get("ts"):
            delay = (r["server_ts"] - r["ts"]) / 1000.0
            if r.get("queue_s", 0) <= 5:
                live.append(delay)
            else:
                queued += 1
    if live:
        live.sort()
        p95 = live[min(len(live) - 1, int(round(0.95 * (len(live) - 1))))]
        print(f"   sent at once: {len(live)} readings  mean {statistics.mean(live):.2f} s  "
              f"median {statistics.median(live):.2f} s  95th pct {p95:.2f} s  max {live[-1]:.2f} s")
        print("   (board and Firebase clocks can differ by up to about 1 s; report this as a limitation)")
    else:
        print("   no 'server_ts' values found (firmware older than 1.1.0)")
    print(f"   sent later from the offline buffer: {queued} readings")

    # 4. collections
    cols = sorted((node.get("collections") or {}).values(), key=lambda c: c.get("ts", 0))
    print(f"\n4) Collection (emptying) events: {len(cols)}")
    for c in cols[-5:]:
        print(f"   {fmt_time(c['ts'])}  fill {c.get('fill_before_pct', '-')} -> {c.get('fill_after_pct', '-')} %  "
              f"weight {c.get('weight_before_kg', '-')} -> {c.get('weight_after_kg', '-')} kg")

    # 5. CSV files for the ML part
    rpath, cpath = f"{out_prefix}{bin_id}_readings.csv", f"{out_prefix}{bin_id}_collections.csv"
    with open(rpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = dict(r)
            row["errors"] = ";".join(r.get("errors", []))
            row.setdefault("bin_id", bin_id)
            w.writerow(row)
    with open(cpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "time_local", "fill_before_pct", "weight_before_kg",
                                          "fill_after_pct", "weight_after_kg"], extrasaction="ignore")
        w.writeheader()
        for c in cols:
            w.writerow(c)
    print(f"\n5) Dataset written: {rpath}, {cpath}")


def main():
    ap = argparse.ArgumentParser(description="RQ1 metrics from a Firebase export")
    ap.add_argument("export_json")
    ap.add_argument("--bin", help="only this bin id, e.g. bin_01")
    ap.add_argument("--out", default="", help="prefix for the CSV file names")
    a = ap.parse_args()
    with open(a.export_json, encoding="utf-8") as f:
        bins = find_bins(json.load(f))
    if not isinstance(bins, dict) or not bins:
        sys.exit("No bins found in this file. Export the whole database, or the 'bins' node.")
    for bin_id, node in bins.items():
        if a.bin and bin_id != a.bin:
            continue
        report(bin_id, node, a.out)


if __name__ == "__main__":
    main()
