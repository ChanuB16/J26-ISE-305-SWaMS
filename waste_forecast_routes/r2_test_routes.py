"""
R2 - TEST THE ROUTE PLANNING FOR 30 DAYS
========================================
The 21 bins (20 synthetic + your real bin) are simulated hour by hour for 30 days that include
Sinhala and Tamil New Year and Vesak (settings: ROUTE_TEST_START). Exactly the same waste arrives in
every method - only the way the trucks collect it changes:

  1. Fixed schedule     today's practice: every bin on fixed days (daily / every 2 / every 3 days),
                        in the same order every time, full or not
  2. Reactive           only bins that are 70%+ full at 6 am, best route (no prediction)
  3. Predictive         bins that WILL be 90%+ full by tomorrow's round, from each bin's own fill
                        speed (as Part B measures it), best route
  4. Predictive + forecast  (our method) the same, and each bin's speed is adjusted with the area
                        forecast from F2 (festivals, holidays, rain...)
  5. Predictive + forecast, but a simple "nearest bin next" route (shows what the optimiser adds)

Measures: km, hours, diesel and cost, bins emptied, how full the bins were when emptied, overflows
(bin-days when a bin was 100% full and waste fell outside), service level, route solving time.
Also: the trade-off between km and overflows for other thresholds, a road-closure re-planning test
(the proposal asks for a new route within 5 seconds) and a route map for Vesak day.

Run:  python r2_test_routes.py        (about 2-5 minutes)
Needs: data/*.csv (f1), results/forecast_model.joblib (f2), the road map (r1)
Makes: results/r2_*.csv, results/chart_r2_*.png, results/map_r2_vesak.html
"""
import os
import time

import joblib
import numpy as np
import pandas as pd

import charts
import maps
import settings as S
from forecasting import Forecaster, load_everything, make_gbm, make_linear, ready_rows
from roads import RoadNetwork
from routing import MANDATORY, BinWorld, Problem, choose_bins, drive, run_method, solve, solver_name
from wastelib import DATA_DIR, RESULTS_DIR, ensure_dirs, need_file, shift_start_hour

METHODS = [  # name, method, uses the forecast, routing
    ("Fixed schedule", "fixed", False, "fixed"),
    ("Reactive (70% now)", "reactive", False, "optimised"),
    ("Predictive (bin speed only)", "predictive", False, "optimised"),
    ("Predictive + forecast", "predictive", True, "optimised"),
    ("Predictive + forecast, nearest-bin route", "predictive", True, "nearest"),
]


def area_activity(data):
    """How busy each area was each day: real waste / a normal day (same weekday, last 4 weeks)."""
    t = data["table"]
    act = (t["actual"].fillna(t["level"] * t["same_dow_rel"]) / t["same_dow"]).clip(0.5, 2.0)
    return pd.Series(act.to_numpy(), index=pd.MultiIndex.from_arrays([t["date"], t["zone"]])).unstack()


def forecast_window(data, pack, start, days):
    """Trains the saved model type on the days BEFORE the test window, then forecasts each test day from
    the day before (as it would happen live). Returns {(day, zone): forecast / normal day}."""
    rows = ready_rows(data["table"])
    train = rows[rows.date < start - pd.Timedelta(days=60)]
    val = rows[(rows.date >= start - pd.Timedelta(days=60)) & (rows.date < start)]
    kind = pack["kind"]
    if kind == "gbm":
        name, model = make_gbm(*pack.get("gbm_params", (4, 500)))
        fc = Forecaster("gbm", name, model)
    elif kind == "linear":
        fc = Forecaster("linear", "Linear Regression", make_linear())
    else:
        fc = Forecaster(kind, pack["name"])
    fc.fit(data, pd.concat([train, val]) if kind != "lstm" else train, val)
    test_days = pd.date_range(start, periods=days)
    t = data["table"]
    rows_w = t[t.date.isin(test_days)]
    pred = fc.predict(data, rows_w)
    ratio = pred / rows_w["same_dow"].to_numpy()
    err = np.abs(pred - rows_w["actual"].to_numpy())
    return {(d, z): float(r) for d, z, r in zip(rows_w.date, rows_w.zone, ratio)}, float(np.nanmean(err)), fc.name


def fixed_routes_for(bins, T0, depot):
    """Today's practice: truck 1 serves Malabe, Kaduwela, Athurugiriya; truck 2 the other areas.
    Each truck always drives its bins in the same order (nearest bin next, decided once)."""
    groups = [set(["Malabe", "Kaduwela", "Athurugiriya"]), None]
    routes = []
    for g in groups:
        todo = [i for i, z in enumerate(bins.zone) if (z in g if g else z not in groups[0])]
        cur, r = depot, []
        while todo:
            n = min(todo, key=lambda x: T0[cur, x])
            r.append(n)
            todo.remove(n)
            cur = n
        routes.append(r)
    return routes


def replanning_test(net, bins, ids, ratio, n_tests=10, seed=3):
    """A road closes at 7:15 on a truck's way; the planner makes new routes from where the trucks are."""
    rng = np.random.default_rng(seed)
    nb = len(bins)
    depot = nb
    start_h = shift_start_hour()
    service = S.SERVICE_MINUTES * 60
    out = []
    for t in range(n_tests):
        net.clear_incidents()
        T0, D0, paths = net.matrices(ids, start_h, want_paths=True)
        fills = rng.uniform(20, 95, nb)
        state = pd.DataFrame({"fill": fills, "growth": rng.uniform(20, 55, nb), "ratio": 1.0,
                              "kind": bins.type.to_numpy(), "days_since": 1.0, "due": False})
        pick = choose_bins("predictive", state)
        p = Problem(T0, [service] * nb + [0], np.zeros(nb + 1), pick, [depot] * S.N_TRUCKS, [depot] * S.N_TRUCKS,
                    [S.TRUCK_CAPACITY_KG] * S.N_TRUCKS, [S.SHIFT_HOURS * 3600] * S.N_TRUCKS)
        routes, _ = solve(p)
        run = drive(routes, p.starts, p.ends, lambda h: T0, lambda h: D0, service, start_h)
        k = int(np.argmax([len(r) for r in routes]))
        r = routes[k]
        if len(r) < 3:
            continue
        clock = start_h + 1.25  # 07:15
        done = [n for n in r if run[k]["arrivals"][n] <= clock]
        nxt = [n for n in r if n not in done]
        prev = done[-1] if done else depot
        leg = paths.get((prev, nxt[0]))
        if not leg:
            continue
        mid = leg[len(leg) // 2]
        net.add_incident("closure", float(net.lat[mid]), float(net.lng[mid]), 300)
        # re-plan: truck k starts where it is, the other trucks from their last emptied bin
        t0 = time.time()
        starts = []
        remaining = []
        for kk, rr in enumerate(routes):
            d_kk = [n for n in rr if run[kk]["arrivals"][n] <= clock]
            starts.append(d_kk[-1] if d_kk else depot)
            remaining += [n for n in rr if n not in d_kk]
        node_list = sorted(set(remaining) | set(starts) | {depot})
        sub_ids = [ids[n] for n in node_list]
        T1, D1 = net.matrices(sub_ids, clock)
        pos = {n: i for i, n in enumerate(node_list)}
        pen = {pos[n]: pick.get(n, MANDATORY) for n in remaining}
        p2 = Problem(T1, [service if n < nb else 0 for n in node_list], np.zeros(len(node_list)), pen,
                     [pos[s] for s in starts], [pos[depot]] * S.N_TRUCKS, [S.TRUCK_CAPACITY_KG] * S.N_TRUCKS,
                     [S.SHIFT_HOURS * 3600 - (clock - start_h) * 3600] * S.N_TRUCKS)
        new_routes, solve_s = solve(p2)
        old_order = [[pos[n] for n in rr if n in remaining] for rr in routes]
        if p2.cost(old_order) < p2.cost(new_routes):  # keep the old order if it is still the best
            new_routes = old_order
        latency = time.time() - t0
        old_s = sum(p2.route_seconds(kk, rr) for kk, rr in enumerate(old_order) if rr)
        new_s = sum(p2.route_seconds(kk, rr) for kk, rr in enumerate(new_routes) if rr)
        reachable_old = all(np.isfinite(T1[a, b]) and T1[a, b] < 10 ** 6 for rr, s0 in
                            zip(old_order, [pos[s] for s in starts]) for a, b in zip([s0] + rr, rr + [pos[depot]]))
        out.append(dict(test=t + 1, closed_roads=int(net.blocked.sum()), bins_left=len(remaining),
                        replan_seconds=latency, solver_seconds=solve_s,
                        old_plan_minutes=old_s / 60 if reachable_old else np.inf, new_plan_minutes=new_s / 60,
                        skipped_now=len(pen) - sum(len(x) for x in new_routes)))
    net.clear_incidents()
    return pd.DataFrame(out)


def main():
    ensure_dirs()
    need_file(os.path.join(RESULTS_DIR, "forecast_model.joblib"), "Run first:  python f2_train_forecast.py")
    need_file(os.path.join(DATA_DIR, "bins.csv"), "Run first:  python r1_road_map.py")
    print("R2 - test the route planning for 30 days")
    t_all = time.time()
    data = load_everything(until=S.HISTORY_END)
    pack = joblib.load(os.path.join(RESULTS_DIR, "forecast_model.joblib"))
    bins = pd.read_csv(os.path.join(DATA_DIR, "bins.csv"))
    net = RoadNetwork()
    if "DEMO" in net.info.get("source", ""):
        print("NOTE: the road map is the DEMO grid (made up). Run  python r1_road_map.py  with internet "
              "for the real roads.")
    ids, _ = net.nearest(list(bins.lat) + [S.DEPOT[0]], list(bins.lng) + [S.DEPOT[1]])
    start_h = shift_start_hour()
    T0, D0 = net.matrices(ids, start_h)
    Tr, Dr = net.matrices(ids, 8.0)
    nb = len(bins)

    start = pd.Timestamp(S.ROUTE_TEST_START)
    test_days = pd.date_range(start, periods=S.ROUTE_TEST_DAYS)
    all_days = pd.date_range(start - pd.Timedelta(days=14), test_days[-1])
    activity = area_activity(data)
    ratio, fc_mae, fc_name = forecast_window(data, pack, start, S.ROUTE_TEST_DAYS)
    print(f"Test days: {test_days[0]:%d %b} - {test_days[-1]:%d %b %Y} (+14 warm-up days). "
          f"Route solver: {solver_name()}")
    print(f"Area forecasts for these days: {fc_name}, trained only on the days before; "
          f"error {fc_mae:.2f} t per area per day")
    world = BinWorld(bins, all_days, activity, data["cal"], seed=S.SEED)
    fixed = fixed_routes_for(bins, T0, nb)

    # ---------------- 1. the 5 methods ----------------
    print()
    print("1) The same 30 days, collected 5 ways")
    results, dailies, all_plans = [], [], {}
    for name, method, use_fc, routing_kind in METHODS:
        t0 = time.time()
        summ, daily, plans = run_method(world, method, (T0, D0, Tr, Dr), ratio if use_fc else {}, start,
                                        fixed_routes=fixed, routing="nearest" if routing_kind == "nearest"
                                        else "optimised", keep_plans=True)
        all_plans[name] = plans
        summ = {"Method": name, **summ}
        results.append(summ)
        daily["method"] = name
        dailies.append(daily)
        print(f"   {name:<42} {summ['km']:6.0f} km  {summ['fuel_cost_lkr']:9,.0f} Rs  {summ['bins_emptied']:4d} emptied"
              f" (avg {summ['avg_fill_collected']:3.0f}% full)  overflows {summ['overflow_bin_days']:3d}"
              f"  service {summ['service_level']:5.1f}%  ({time.time() - t0:.0f} s)")
    fest_days = {d for d in test_days if data["cal"].loc[d, ["fest_avurudu", "avurudu_before", "avurudu_after",
                                                             "fest_vesak"]].sum() > 0}
    for row in results:
        by_day = row.pop("overflow_by_day")
        row["overflows_festival_days"] = sum(v for k, v in by_day.items() if k in fest_days)
        row["overflows_other_days"] = sum(v for k, v in by_day.items() if k not in fest_days)
    res = pd.DataFrame(results)
    res.round(3).to_csv(os.path.join(RESULTS_DIR, "r2_methods.csv"), index=False)
    print(f"   Overflows on the {len(fest_days)} New Year and Vesak days / other days: "
          + ", ".join(f"{r['Method'].split(' (')[0]} {r['overflows_festival_days']}/{r['overflows_other_days']}"
                      for r in results))
    pd.concat(dailies).round(3).to_csv(os.path.join(RESULTS_DIR, "r2_daily.csv"), index=False)
    r = res.set_index("Method")
    fx, ours = r.loc["Fixed schedule"], r.loc["Predictive + forecast"]
    print(f"   Our method vs fixed schedule: {100 * (1 - ours.km / fx.km):.0f}% fewer km, "
          f"{fx.fuel_cost_lkr - ours.fuel_cost_lkr:,.0f} Rs less diesel in 30 days, overflows "
          f"{int(fx.overflow_bin_days)} -> {int(ours.overflow_bin_days)}")
    print(f"   Route solving time: at most {r['solve_max_s'].max():.2f} s per day")

    # ---------------- 2. trade-off ----------------
    print()
    print("2) Trade-off: km vs overflows for other thresholds")
    points = {}
    for name, method, use_fc, thresholds in (("Reactive (fill now)", "reactive", False, (50, 60, 70, 80)),
                                             ("Predictive + forecast", "predictive", True, (80, 90, 100, 110))):
        pts = []
        for th in thresholds:
            summ, _ = run_method(world, method, (T0, D0, Tr, Dr), ratio if use_fc else {}, start, fixed_routes=fixed,
                                 threshold=th)
            pts.append((summ["km"], summ["overflow_bin_days"], f"{th}%"))
            print(f"   {name:<24} threshold {th:3d}%: {summ['km']:6.0f} km, overflows {summ['overflow_bin_days']:3d}")
        points[name] = pts
    pts_fixed = [(fx.km, fx.overflow_bin_days, "")]
    points["Fixed schedule"] = pts_fixed
    pd.DataFrame([(k, x, y, lab) for k, v in points.items() for x, y, lab in v],
                 columns=["Method", "km", "overflow bin-days", "threshold"]).to_csv(
        os.path.join(RESULTS_DIR, "r2_tradeoff.csv"), index=False)

    # ---------------- 3. re-planning when a road closes ----------------
    print()
    print("3) A road closes at 7:15 on a truck's way: new routes from where the trucks are")
    rp = replanning_test(net, bins, ids, ratio)
    rp.round(3).to_csv(os.path.join(RESULTS_DIR, "r2_replanning.csv"), index=False)
    if len(rp):
        blocked = np.isinf(rp.old_plan_minutes).sum()
        print(f"   {len(rp)} tests: new routes ready in {rp.replan_seconds.mean():.2f} s on average "
              f"(slowest {rp.replan_seconds.max():.2f} s; the proposal asks for less than 5 s)")
        print(f"   the old route was blocked by the closure in {blocked} tests; where it was still possible, "
              f"the new route was {np.nanmean((rp.old_plan_minutes - rp.new_plan_minutes)[np.isfinite(rp.old_plan_minutes)]):.1f}"
              f" min shorter on average")

    # ---------------- 4. a route map for Vesak day ----------------
    day = pd.Timestamp("2026-05-01") if pd.Timestamp("2026-05-01") in test_days else test_days[len(test_days) // 2]
    plan = all_plans["Predictive + forecast"][day]
    routes, run, fills = plan["routes"], plan["result"], plan["fill"]
    _, _, paths = net.matrices(ids, start_h, want_paths=True)
    route_lines, route_xy = [], {}
    for k, rt in enumerate(routes):
        if not rt:
            continue
        seq = [nb] + rt + [nb]
        coords = []
        for a_, b_ in zip(seq[:-1], seq[1:]):
            coords += net.path_coords(paths.get((a_, b_), [ids[a_], ids[b_]]))
        label = f"Truck {k + 1}: {len(rt)} bins, {run[k]['km']:.1f} km, {run[k]['hours'] * 60:.0f} min"
        route_lines.append(dict(name=label, coords=coords))
        route_xy[label] = ([c[1] for c in coords], [c[0] for c in coords])
    visited = {n for rt in routes for n in rt}
    title = f"Planned routes for {day:%A %d %B %Y}"
    sub = ("Predictive + forecast. Filled dot = collected, empty = has space. "
           + ("DEMO road grid (not real roads)" if "DEMO" in net.info.get("source", "") else "OpenStreetMap roads"))
    charts.route_map(net.segments_for_drawing(), route_xy,
                     [dict(lng=bb.lng, lat=bb.lat, label=bb.bin_id, collected=i in visited)
                      for i, bb in enumerate(bins.itertuples())],
                     S.DEPOT, os.path.join(RESULTS_DIR, "chart_r2_route_map.png"), title, sub)
    maps.write_map(os.path.join(RESULTS_DIR, "map_r2_vesak.html"), title, sub, S.DEPOT, S.DEPOT_NAME,
                   [dict(lat=bb.lat, lng=bb.lng, label=f"{bb.bin_id} - {bb.name}", fill=float(fills[i]),
                         extra=f"{fills[i]:.0f}% full at 6 am - " + ("collected" if i in visited else "not today"))
                    for i, bb in enumerate(bins.itertuples())], route_lines)

    # ---------------- charts ----------------
    tag = "synthetic bins" + (", DEMO road grid" if "DEMO" in net.info.get("source", "") else ", OpenStreetMap roads")
    names = list(res["Method"])
    ours_flag = [n == "Predictive + forecast" for n in names]
    charts.hbars(names, list(res["km"]), ours_flag, os.path.join(RESULTS_DIR, "chart_r2_km.png"),
                 "How far do the trucks drive in 30 days?",
                 f"{test_days[0]:%d %b} - {test_days[-1]:%d %b %Y}, {nb} bins, {tag}", "Total distance (km)",
                 fmt="{:,.0f}", legend=("Our method", "Other methods"), sort=False)
    charts.hbars(names, list(res["overflow_bin_days"]), ours_flag, os.path.join(RESULTS_DIR, "chart_r2_overflows.png"),
                 "How often did a bin overflow?",
                 f"Bin-days when a bin was 100% full (out of {nb * S.ROUTE_TEST_DAYS}), {tag}", "Overflow bin-days",
                 fmt="{:.0f}", legend=("Our method", "Other methods"), sort=False)
    charts.tradeoff({k: v for k, v in points.items()}, os.path.join(RESULTS_DIR, "chart_r2_tradeoff.png"),
                    "Fewer km and fewer overflows: the trade-off",
                    "Each point = one threshold, 30 days. Down and to the left is better.", "Total distance (km)",
                    "Overflow bin-days")
    print()
    print("Saved: results/r2_*.csv, 4 charts, results/map_r2_vesak.html (open it in a web browser)")
    print(f"Done in {time.time() - t_all:.0f} s. Next: python f3_forecasts_to_firebase.py and r3_live_routes.py")


if __name__ == "__main__":
    main()
