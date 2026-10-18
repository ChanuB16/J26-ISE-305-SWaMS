"""
R3 - LIVE ROUTES WITH RE-PLANNING
=================================
Plans today's truck routes from the LIVE data in Firebase, and plans again when something changes
(a road closes, a truck breaks down, a bin becomes urgent, or someone presses "Re-plan" in the dashboard).

It reads:   bins/<id>/info and latest       (the real bin from Part A + demo bins from step B6)
            predictions/<id>                (Part B step B5: predicted fill in 6 hours, urgency score)
            forecasts/<area>/<today>        (step F3: is today a busy day in that area?)
            trucks/<truck_id>               (status "available" / "broken", GPS position when on the road)
            traffic/<id>                    (road closures and jams - from the dashboard, or by hand)
            control/replan                  (the dashboard's "Re-plan now" button)
It writes:  routes/<YYYY-MM-DD>/<truck_id>  stops in order with arrival times, km, minutes, diesel, the path
            routes/<YYYY-MM-DD>/_summary    bins planned and skipped (and why), solver, re-planning time

Every 15 seconds it checks for changes (cheap), and it plans again at least every LIVE_EVERY_MINUTES.
It prints how long each re-plan took (the proposal asks for less than 5 seconds).

Run:  python r3_live_routes.py           (runs until Ctrl+C)
      python r3_live_routes.py --once    (one plan, then stops)
Needs: the road map (r1). Optional: forecasts (f3), predictions (Part B step B5 / B6).
"""
import argparse
import hashlib
import json
import os
import time

import numpy as np
import pandas as pd

import maps
import settings as S
from roads import RoadNetwork
from routing import MANDATORY, TYPES, Problem, choose_bins, drive, solve, solver_name
from wastelib import RESULTS_DIR, TZ, Firebase, ensure_dirs

CHECK_SECONDS = 15
DEFAULT_GROWTH = {k: v["rate"] * 24 for k, v in TYPES.items()}  # % per day if Part B has no prediction yet


def now_local():
    return pd.Timestamp.now(tz=TZ)


def clock_text(hours):
    """10.5 -> '10:30'"""
    total = int(round(hours * 60))
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


def read_world(fb):
    bins = fb.get("bins") or {}
    preds = fb.get("predictions") or {}
    trucks = fb.get("trucks") or {}
    traffic = fb.get("traffic") or {}
    control = fb.get("control") or {}
    today = now_local().strftime("%Y-%m-%d")
    forecasts = {}
    for zone in S.ZONES:
        f = fb.get(f"forecasts/{zone}/{today}")
        if isinstance(f, dict) and f.get("normal_t"):
            forecasts[zone] = f
    return dict(bins=bins, preds=preds, trucks=trucks, traffic=traffic, control=control, forecasts=forecasts)


def ensure_trucks(fb, trucks):
    """Creates the trucks in Firebase the first time (all at the depot, available)."""
    if trucks:
        return trucks
    trucks = {f"truck_{k + 1}": {"name": f"Truck {k + 1}", "status": "available", "lat": S.DEPOT[0],
                                 "lng": S.DEPOT[1], "capacity_kg": S.TRUCK_CAPACITY_KG} for k in range(S.N_TRUCKS)}
    fb.patch("", {f"trucks/{k}": v for k, v in trucks.items()})
    return trucks


def active_incidents(traffic, now_ms):
    out = []
    for key, z in (traffic or {}).items():
        if not isinstance(z, dict) or "lat" not in z or "lng" not in z:
            continue
        if z.get("until") and float(z["until"]) < now_ms:
            continue
        out.append(dict(id=key, kind=z.get("kind", "closure"), lat=float(z["lat"]), lng=float(z["lng"]),
                        radius_m=float(z.get("radius_m", 300)), note=z.get("note", ""),
                        created=z.get("created_at")))
    return out


def signature(world, now_ms):
    """A short fingerprint of the things that should trigger a new plan."""
    inc = sorted((z["id"], z["kind"], round(z["lat"], 5), round(z["lng"], 5)) for z in
                 active_incidents(world["traffic"], now_ms))
    trucks = sorted((k, v.get("status") == "broken") for k, v in (world["trucks"] or {}).items()
                    if isinstance(v, dict))  # only "broken or not" matters (GPS moves all the time)
    urgent = sorted(k for k, p in (world["preds"] or {}).items()
                    if isinstance(p, dict) and (p.get("urgency_score") or 0) >= S.URGENT_SCORE)
    replan = (world["control"] or {}).get("replan")
    text = json.dumps([inc, trucks, urgent, replan], sort_keys=True, default=str)
    return hashlib.md5(text.encode()).hexdigest()


def bin_table(world, now_ms):
    rows = []
    for bin_id, node in (world["bins"] or {}).items():
        if not isinstance(node, dict):
            continue
        info = node.get("info") or {}
        latest = node.get("latest") or {}
        pred = (world["preds"] or {}).get(bin_id) or {}
        lat, lng = info.get("lat"), info.get("lng")
        if bin_id == S.REAL_BIN["bin_id"]:
            lat = lat if lat is not None else S.REAL_BIN["lat"]
            lng = lng if lng is not None else S.REAL_BIN["lng"]
        if lat is None or lng is None:
            continue
        kind = info.get("type", S.REAL_BIN["type"] if bin_id == S.REAL_BIN["bin_id"] else "residential")
        zone = info.get("zone", S.REAL_BIN["zone"] if bin_id == S.REAL_BIN["bin_id"] else "")
        fill = latest.get("fill_pct", pred.get("current_fill_pct"))
        ts = latest.get("ts") or pred.get("based_on_ts")
        age_h = (now_ms - float(ts)) / 3.6e6 if ts else np.inf
        p6 = pred.get("predicted_fill_6h")
        last = node.get("last_collected") or pred.get("last_collected")
        if last and pred.get("based_on_ts") and float(pred["based_on_ts"]) < float(last):
            p6 = None  # the prediction was made before the bin was emptied: too old
        if fill is not None and p6 is not None:
            growth = max(0.0, float(p6) - float(fill)) * 3.0  # about 3 x the next 6 hours (little waste at night)
        else:
            growth = DEFAULT_GROWTH.get(kind, 30.0)
        days_since = (now_ms - float(last)) / 8.64e7 if last else 1.0
        rows.append(dict(bin_id=bin_id, name=info.get("name", bin_id), lat=float(lat), lng=float(lng), kind=kind,
                         zone=zone, fill=float(fill) if fill is not None else np.nan, age_h=age_h,
                         growth=growth, urgency=pred.get("urgency_score", np.nan), days_since=days_since,
                         synthetic=bool(info.get("synthetic", bin_id.startswith("sim_")))))
    return pd.DataFrame(rows)


def plan(fb, net, world, trigger):
    t0 = time.time()
    now = now_local()
    now_ms = int(now.value // 1_000_000)
    hour = now.hour + now.minute / 60.0
    sh, sm = (int(x) for x in S.SHIFT_START.split(":"))
    start_hour = max(hour, sh + sm / 60.0)
    date = now.strftime("%Y-%m-%d")
    trucks = ensure_trucks(fb, world["trucks"])
    bins = bin_table(world, now_ms)
    skipped = []
    if bins.empty:
        print("No bins with a location in Firebase. Add the demo bins (Part B: python b6_demo_bins.py --add) "
              "or set the real bin's info (lat, lng).")
        return None
    known = bins[bins.fill.notna()].reset_index(drop=True)
    for b in bins[bins.fill.isna()].itertuples():
        skipped.append({"bin_id": b.bin_id, "reason": "no data yet"})
    ratio = []
    for z in known.zone:
        f = world["forecasts"].get(z)
        ratio.append(float(f["forecast_t"]) / float(f["normal_t"]) if f else 1.0)
    state = known.assign(ratio=ratio, due=False)
    pick = choose_bins("predictive", state)

    net.clear_incidents()
    incidents = active_incidents(world["traffic"], now_ms)
    for z in incidents:
        net.add_incident(z["kind"], z["lat"], z["lng"], z["radius_m"])

    avail = [(k, v) for k, v in sorted(trucks.items()) if isinstance(v, dict) and v.get("status") != "broken"]
    if not avail:
        print("All trucks are broken - nothing to plan.")
        return None
    nb = len(known)
    starts_ll, fixed = [], []
    for k, v in avail:
        on_road = v.get("status") == "on_route" and v.get("lat") is not None and \
            (now_ms - float(v.get("ts", 0))) < 15 * 60 * 1000
        starts_ll.append((float(v["lat"]), float(v["lng"])) if on_road else S.DEPOT)
        fixed.append(0 if on_road else 1800)  # prefer a truck that is already on the road
    lats = list(known.lat) + [S.DEPOT[0]] + [p[0] for p in starts_ll]
    lngs = list(known.lng) + [S.DEPOT[1]] + [p[1] for p in starts_ll]
    ids, _ = net.nearest(lats, lngs)
    T, D, paths = net.matrices(ids, start_hour, want_paths=True)
    depot = nb
    start_nodes = [nb + 1 + i for i in range(len(avail))]
    for n in list(pick):  # bins nobody can reach (road closed around them)
        if all(not np.isfinite(T[s, n]) for s in start_nodes) or not np.isfinite(T[n, depot]):
            skipped.append({"bin_id": known.bin_id[n], "reason": "road closed"})
            del pick[n]
    service = S.SERVICE_MINUTES * 60
    left_s = max(0.0, (sh + sm / 60.0 + S.SHIFT_HOURS - start_hour) * 3600) if hour >= sh + sm / 60.0 else \
        S.SHIFT_HOURS * 3600
    if left_s < 1800:  # the normal round is over: plan an extra round of the normal length
        left_s = S.SHIFT_HOURS * 3600
    demand = [min(100.0, f) / 100 * S.BIN_LITRES * TYPES.get(k, TYPES["residential"])["density"]
              for f, k in zip(known.fill, known.kind)] + [0] * (1 + len(avail))  # kg in each bin
    p = Problem(T, [service] * nb + [0] * (1 + len(avail)), demand, pick, start_nodes, [depot] * len(avail),
                [float(v.get("capacity_kg", S.TRUCK_CAPACITY_KG)) for _, v in avail], [left_s] * len(avail), fixed)
    routes, solve_s = solve(p)
    run = drive(routes, p.starts, p.ends, lambda h: T, lambda h: D, service, start_hour)
    visited = {n for r in routes for n in r}
    for n in pick:
        if n not in visited and pick[n] >= MANDATORY:
            skipped.append({"bin_id": known.bin_id[n], "reason": "no time left in the shifts"})

    update, map_lines = {}, []
    total_km = 0.0
    for (truck_id, tinfo), r, res, s_node in zip(avail, routes, run, start_nodes):
        stops = []
        coords = []
        seq = [s_node] + r + [depot]
        for a, b in zip(seq[:-1], seq[1:]):
            coords += net.path_coords(paths.get((a, b), [ids[a], ids[b]]))
        for n in r:
            eta = res["arrivals"][n]
            stops.append({"bin_id": known.bin_id[n], "name": known.name[n], "lat": known.lat[n], "lng": known.lng[n],
                          "eta": clock_text(eta),
                          "fill_pct": round(float(known.fill[n]), 1),
                          "reason": "must collect" if pick[n] >= MANDATORY else "on the way", "done": False})
        step = max(1, len(coords) // 400)
        path = coords[::step] + ([coords[-1]] if coords else [])
        total_km += res["km"]
        update[f"routes/{date}/{truck_id}"] = {
            "truck": tinfo.get("name", truck_id), "stops": stops, "km": round(res["km"], 2),
            "minutes": round(res["hours"] * 60, 1), "fuel_l": round(res["km"] * S.FUEL_L_PER_KM, 2),
            "cost_lkr": round(res["km"] * S.FUEL_L_PER_KM * S.DIESEL_PRICE_LKR),
            "start": clock_text(start_hour),
            "path": [[float(a), float(b)] for a, b in path], "made_at": {".sv": "timestamp"}}
        if r:
            map_lines.append(dict(name=f"{tinfo.get('name', truck_id)}: {len(r)} bins, {res['km']:.1f} km",
                                  coords=path))
    for k, v in trucks.items():  # trucks that are broken get an empty route
        if isinstance(v, dict) and v.get("status") == "broken":
            update[f"routes/{date}/{k}"] = {"truck": v.get("name", k), "stops": [], "km": 0, "minutes": 0,
                                            "note": "truck not available", "made_at": {".sv": "timestamp"}}
    replan_s = time.time() - t0
    update[f"routes/{date}/_summary"] = {
        "made_at": {".sv": "timestamp"}, "trigger": trigger, "replan_seconds": round(replan_s, 2),
        "solver": solver_name(), "solve_seconds": round(solve_s, 2), "roads": net.info.get("source", ""),
        "planned": len(visited), "skipped": skipped, "total_km": round(total_km, 2),
        "fuel_l": round(total_km * S.FUEL_L_PER_KM, 2),
        "cost_lkr": round(total_km * S.FUEL_L_PER_KM * S.DIESEL_PRICE_LKR),
        "incidents": [{k: z[k] for k in ("kind", "lat", "lng", "radius_m", "note")} for z in incidents]}
    fb.patch("", update)
    total_s = time.time() - t0
    maps.write_map(os.path.join(RESULTS_DIR, "map_live.html"), f"Live routes {date}",
                   f"Made {now:%H:%M:%S} ({trigger}); {len(visited)} bins planned, {len(skipped)} skipped",
                   S.DEPOT, S.DEPOT_NAME,
                   [dict(lat=b.lat, lng=b.lng, label=f"{b.bin_id} - {b.name}", fill=b.fill,
                         extra=f"{b.fill:.0f}% full" + (" - on today's route" if i in visited else ""))
                    for i, b in enumerate(known.itertuples())], map_lines,
                   [dict(lat=z["lat"], lng=z["lng"], radius=z["radius_m"], popup=f"{z['kind']}: {z['note']}")
                    for z in incidents])
    used = sum(1 for r in routes if r)
    print(f"[{now:%H:%M:%S}] {trigger}: {len(visited)} bins on {used} truck(s), {total_km:.1f} km, "
          f"{len(skipped)} skipped | new routes in Firebase {total_s:.2f} s after the change was noticed "
          f"(solver {solve_s:.2f} s)")
    for s in skipped:
        print(f"           skipped {s['bin_id']}: {s['reason']}")
    return total_s


def main():
    ap = argparse.ArgumentParser(description="Live truck routes with re-planning")
    ap.add_argument("--once", action="store_true", help="plan once, then stop")
    args = ap.parse_args()
    ensure_dirs()
    net = RoadNetwork()
    fb = Firebase()
    print(f"R3 - live routes ({solver_name()}, roads: {net.info.get('source')}). Ctrl+C to stop.")
    last_sig, last_plan = None, 0.0
    while True:
        world = read_world(fb)
        now_ms = int(now_local().value // 1_000_000)
        sig = signature(world, now_ms)
        due = time.time() - last_plan >= S.LIVE_EVERY_MINUTES * 60
        if last_sig is None or sig != last_sig or due:
            trigger = "first plan" if last_sig is None else ("change noticed" if sig != last_sig else "regular update")
            plan(fb, net, world, trigger)
            last_plan = time.time()
            last_sig = signature(read_world(fb), int(now_local().value // 1_000_000))
        if args.once:
            break
        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
