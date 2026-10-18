"""
Route planning code shared by r2 and r3. You do not need to edit this file.

  - choose_bins():   which bins go on today's round (fixed schedule / reactive / predictive)
  - solve():         the truck routes - Google OR-Tools if installed, otherwise a built-in solver
                     (cheapest insertion + local search) so the step always finishes
  - drive():         drives the planned routes with rush-hour speeds -> km, time, arrival times
  - BinWorld:        the 30-day test: bins filling hour by hour (same waste for every method)
"""
import time

import numpy as np
import pandas as pd

import settings as S
from wastelib import shift_start_hour

MANDATORY = 10 ** 7          # skip "cost" of a bin that MUST be collected (seconds; = never skip)
UNREACHABLE = 10 ** 6

# Bin types - the same numbers as Part B (b2_make_data.py)
TYPES = {
    "market":      dict(rate=2.2, organic=0.90, density=0.15, every=1),
    "bus_stop":    dict(rate=1.9, organic=0.40, density=0.08, every=1),
    "residential": dict(rate=1.35, organic=0.70, density=0.14, every=2),
    "school":      dict(rate=1.5, organic=0.35, density=0.09, every=2),
    "office":      dict(rate=1.0, organic=0.20, density=0.07, every=3),
    "temple":      dict(rate=1.1, organic=0.60, density=0.10, every=2),
}
WEEK = {  # Monday ... Sunday
    "market": [1, 1, 1, 1, 1, 1.3, 1.25], "bus_stop": [1, 1, 1, 1, 1, 0.8, 0.7],
    "residential": [1, 1, 1, 1, 1, 1.15, 1.25], "school": [1, 1, 1, 1, 1, 0.1, 0.1],
    "office": [1, 1, 1, 1, 1, 0.25, 0.15], "temple": [1, 1, 1, 1, 1, 1.2, 1.4],
}
FOOD_BINS = {k for k, v in TYPES.items() if v["organic"] >= 0.6}  # smell rule applies to these


def hour_profile(kind):
    """How busy each hour of the day is (average 1.0) - same as Part B."""
    h = np.arange(24)

    def bump(centre, width, height):
        return height * np.exp(-0.5 * ((h - centre) / width) ** 2)

    p = 0.05 + 0 * h
    if kind == "market":
        p = p + bump(9, 2.5, 2.2) + bump(16, 2.5, 1.2)
    elif kind == "bus_stop":
        p = p + bump(7.5, 1.5, 2.0) + bump(17.5, 1.5, 2.0) + bump(12.5, 3, 0.6)
    elif kind == "residential":
        p = p + bump(7, 1.5, 1.6) + bump(19, 2, 2.0) + bump(13, 3, 0.4)
    elif kind == "school":
        p = p + bump(10.5, 2.5, 2.0)
    elif kind == "office":
        p = p + bump(12.5, 3, 1.6)
    elif kind == "temple":
        p = p + bump(6.5, 1.5, 1.5) + bump(18.5, 1.5, 1.8)
    return p / p.mean()


def bin_kg(fill_pct, kind):
    return fill_pct / 100.0 * S.BIN_LITRES * TYPES.get(kind, TYPES["residential"])["density"]


# ---------------------------------------------------------------------------
# Which bins to collect
# ---------------------------------------------------------------------------
def choose_bins(method, state, threshold=None):
    """Returns {bin_index: penalty_seconds} for today's round.

    state: DataFrame with columns fill (now), growth (expected % per day, from Part B / the sensor),
           ratio (forecast waste of the area today / a normal day, 1.0 = no forecast), kind,
           days_since (days since emptied), due (fixed schedule says today), urgency (Part B, optional)
    """
    pick = {}
    for i, r in state.iterrows():
        smell = r["kind"] in FOOD_BINS and r["days_since"] >= S.MAX_DAYS_WITHOUT_EMPTYING
        urgent = r.get("urgency", 0) >= S.URGENT_SCORE if not pd.isna(r.get("urgency", np.nan)) else False
        if method == "fixed":
            if r["due"]:
                pick[i] = MANDATORY
        elif method == "reactive":
            limit = S.REACTIVE_FILL_PCT if threshold is None else threshold
            if r["fill"] >= limit or smell or urgent:
                pick[i] = MANDATORY
        else:  # predictive: the fill level the bin WILL have at the next round (24 hours later)
            limit = S.PREDICT_FILL_PCT if threshold is None else threshold
            predicted = r["fill"] + r["growth"] * r["ratio"]
            if predicted >= limit or smell or urgent:
                pick[i] = MANDATORY
            elif predicted >= S.OPTIONAL_FILL_PCT:
                pick[i] = 300  # collect if the detour is less than 5 minutes of driving
    return pick


# ---------------------------------------------------------------------------
# The route solver
# ---------------------------------------------------------------------------
class Problem:
    """Nodes 0..n-1. T = driving seconds between nodes. Trucks start at starts[k] and end at ends[k]."""

    def __init__(self, T, service, demand, penalty, starts, ends, capacity, max_seconds, fixed_cost=1800):
        self.T = np.where(np.isfinite(T), T, UNREACHABLE)
        self.service = np.asarray(service, dtype=float)
        self.demand = np.asarray(demand, dtype=float)
        self.penalty = {int(n): v for n, v in dict(penalty).items()}  # node -> seconds
        self.starts, self.ends = [int(x) for x in starts], [int(x) for x in ends]
        self.capacity, self.max_seconds = list(capacity), list(max_seconds)
        self.K = len(self.starts)
        # cost of using a truck at all (a list = one value per truck; 0 for a truck already on the road)
        self.fixed = list(fixed_cost) if isinstance(fixed_cost, (list, tuple)) else [fixed_cost] * self.K

    def route_seconds(self, k, r):
        t, cur = 0.0, self.starts[k]
        for n in r:
            t += self.T[cur, n] + self.service[n]
            cur = n
        return t + self.T[cur, self.ends[k]]

    def ok(self, k, r):
        return self.route_seconds(k, r) <= self.max_seconds[k] and \
            sum(self.demand[n] for n in r) <= self.capacity[k]

    def cost(self, routes):
        c = 0.0
        for k, r in enumerate(routes):
            if r:
                c += self.route_seconds(k, r) + self.fixed[k]
        visited = {n for r in routes for n in r}
        return c + sum(p for n, p in self.penalty.items() if n not in visited)


def solve_builtin(p, time_limit):
    """Cheapest insertion, then local search (move, swap, 2-opt, add/drop optional bins)."""
    t0 = time.time()
    routes = [[] for _ in range(p.K)]
    todo = sorted(p.penalty, key=lambda n: (-p.penalty[n], -p.T[p.starts[0], n]))

    def best_insert(n, routes):
        best = None
        for k, r in enumerate(routes):
            base = p.route_seconds(k, r) if r else 0.0
            for pos in range(len(r) + 1):
                cand = r[:pos] + [n] + r[pos:]
                if not p.ok(k, cand):
                    continue
                add = p.route_seconds(k, cand) - base + (p.fixed[k] if not r else 0)
                if best is None or add < best[0]:
                    best = (add, k, pos)
        return best

    for n in todo:
        b = best_insert(n, routes)
        if b is not None and b[0] < p.penalty[n]:
            routes[b[1]].insert(b[2], n)
    best_cost = p.cost(routes)
    improved = True
    while improved and time.time() - t0 < time_limit:
        improved = False
        # 2-opt inside each route
        for k, r in enumerate(routes):
            for i in range(len(r) - 1):
                for j in range(i + 1, len(r)):
                    cand = r[:i] + r[i:j + 1][::-1] + r[j + 1:]
                    if p.ok(k, cand) and p.route_seconds(k, cand) < p.route_seconds(k, r) - 1e-6:
                        routes[k] = r = cand
                        improved = True
        # move one bin to its best place (any route), or drop it if it is optional and costs too much
        for k in range(p.K):
            for n in list(routes[k]):
                trial = [list(x) for x in routes]
                trial[k].remove(n)
                b = best_insert(n, trial)
                options = [trial] if p.penalty[n] < MANDATORY else []
                if b is not None:
                    t2 = [list(x) for x in trial]
                    t2[b[1]].insert(b[2], n)
                    options.append(t2)
                for t in options:
                    c = p.cost(t)
                    if c < best_cost - 1e-6:
                        routes, best_cost, improved = t, c, True
                        break
        # swap two bins between routes
        for k1 in range(p.K):
            for k2 in range(k1 + 1, p.K):
                for a in list(routes[k1]):
                    for b in list(routes[k2]):
                        r1 = [b if x == a else x for x in routes[k1]]
                        r2 = [a if x == b else x for x in routes[k2]]
                        if p.ok(k1, r1) and p.ok(k2, r2):
                            t = [list(x) for x in routes]
                            t[k1], t[k2] = r1, r2
                            c = p.cost(t)
                            if c < best_cost - 1e-6:
                                routes, best_cost, improved = t, c, True
        # add skipped bins if it pays
        visited = {n for r in routes for n in r}
        for n in todo:
            if n in visited:
                continue
            b = best_insert(n, routes)
            if b is not None and b[0] < p.penalty[n]:
                routes[b[1]].insert(b[2], n)
                best_cost = p.cost(routes)
                improved = True
    return routes


def _ortools_api():
    """OR-Tools moved its routing library in version 9.12; this works with the new and the old place."""
    try:
        from ortools.routing import enums_pb2 as enums
        from ortools.routing import pywraprouting as rw
        return rw.RoutingIndexManager, rw.RoutingModel, rw.DefaultRoutingSearchParameters, enums
    except ImportError:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
        return (pywrapcp.RoutingIndexManager, pywrapcp.RoutingModel, pywrapcp.DefaultRoutingSearchParameters,
                routing_enums_pb2)


def solve_ortools(p, time_limit, thorough):
    Manager, Model, default_parameters, enums = _ortools_api()
    n = len(p.T)
    manager = Manager(n, p.K, [int(x) for x in p.starts], [int(x) for x in p.ends])
    routing = Model(manager)
    T = np.round(p.T).astype(np.int64)
    serv = np.round(p.service).astype(np.int64)
    dem = np.round(p.demand).astype(np.int64)

    def time_cb(from_index, to_index):
        a, b = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
        return int(T[a, b] + serv[b])

    def demand_cb(index):
        return int(dem[manager.IndexToNode(index)])

    transit = routing.RegisterTransitCallback(time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)
    routing.AddDimension(transit, 0, int(max(p.max_seconds)), True, "Time")
    time_dim = routing.GetDimensionOrDie("Time")
    for k in range(p.K):
        time_dim.CumulVar(routing.End(k)).SetMax(int(p.max_seconds[k]))
    load = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(load, 0, [int(c) for c in p.capacity], True, "Load")
    for node, pen in p.penalty.items():
        routing.AddDisjunction([manager.NodeToIndex(int(node))], int(pen))
    for k in range(p.K):
        routing.SetFixedCostOfVehicle(int(p.fixed[k]), k)
    params = default_parameters()
    params.first_solution_strategy = enums.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = (enums.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH if thorough
                                         else enums.LocalSearchMetaheuristic.GREEDY_DESCENT)
    params.time_limit.FromMilliseconds(int(time_limit * 1000))
    solution = routing.SolveWithParameters(params)
    if solution is None:
        return None
    routes = []
    for k in range(p.K):
        index = solution.Value(routing.NextVar(routing.Start(k)))
        r = []
        while not routing.IsEnd(index):
            r.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        routes.append(r)
    return routes


ORTOOLS = {"ok": None, "why": ""}  # None = not tried yet


def solver_name():
    if ORTOOLS["ok"] is None:
        try:
            _ortools_api()
            return "Google OR-Tools"
        except ImportError:
            return "built-in solver (OR-Tools not installed)"
    return "Google OR-Tools" if ORTOOLS["ok"] else f"built-in solver ({ORTOOLS['why']})"


def solve(p, time_limit=None, thorough=True):
    """Truck routes (lists of nodes, without start/end). thorough=False: quicker search (30-day test).
    Uses OR-Tools when it works; otherwise the built-in solver, so the step always finishes."""
    time_limit = S.SOLVER_SECONDS if time_limit is None else time_limit
    t0 = time.time()
    if not p.penalty:
        return [[] for _ in range(p.K)], 0.0
    routes = None
    if ORTOOLS["ok"] is not False:
        try:
            routes = solve_ortools(p, time_limit, thorough)
            ORTOOLS["ok"] = True
        except ImportError:
            ORTOOLS.update(ok=False, why="OR-Tools not installed")
        except Exception as e:  # OR-Tools installed but something is different: keep going
            ORTOOLS.update(ok=False, why=f"OR-Tools error: {type(e).__name__}")
            print(f"NOTE: OR-Tools did not work ({type(e).__name__}: {e}). Using the built-in solver instead.")
    if routes is None:
        routes = solve_builtin(p, time_limit)
    return routes, time.time() - t0


def nearest_neighbour(p):
    """A simple driver's rule: always go to the nearest bin that is still to be collected."""
    todo = set(p.penalty)
    routes = [[] for _ in range(p.K)]
    for k in range(p.K):
        cur, r = p.starts[k], []
        while todo:
            n = min(todo, key=lambda x: p.T[cur, x])
            if not p.ok(k, r + [n]):
                break
            r.append(n)
            todo.discard(n)
            cur = n
        routes[k] = r
    if todo:  # bins that did not fit in the shifts: add them to the last truck anyway (overtime)
        routes[-1] += sorted(todo, key=lambda x: p.T[routes[-1][-1] if routes[-1] else p.starts[-1], x])
    return routes


# ---------------------------------------------------------------------------
# Driving a plan with rush-hour speeds
# ---------------------------------------------------------------------------
def drive(routes, starts, ends, T_at, D_at, service_s, start_hour):
    """Drives the planned routes. T_at(h) / D_at(h) -> the time (s) and distance (m) matrices for a leg
    that starts at hour h (rush hours are slower). Returns per truck: dict(km, hours, arrivals {node: hour})."""
    out = []
    for k, r in enumerate(routes):
        if not r:
            out.append(dict(km=0.0, hours=0.0, arrivals={}))
            continue
        clock, km, arrivals, cur = start_hour, 0.0, {}, starts[k]
        for n in r:
            clock += T_at(clock)[cur, n] / 3600.0
            km += D_at(clock)[cur, n] / 1000.0
            arrivals[n] = clock
            clock += service_s / 3600.0
            cur = n
        clock += T_at(clock)[cur, ends[k]] / 3600.0
        km += D_at(clock)[cur, ends[k]] / 1000.0
        out.append(dict(km=km, hours=clock - start_hour, arrivals=arrivals))
    return out


# ---------------------------------------------------------------------------
# The 30-day test world
# ---------------------------------------------------------------------------
class BinWorld:
    """Bins filling hour by hour. The waste that arrives is fixed in advance (same seed), so every
    method faces exactly the same waste - only the collections differ."""

    def __init__(self, bins, days, activity, cal, seed=42):
        self.bins = bins.reset_index(drop=True)
        self.days = pd.DatetimeIndex(days)
        rng = np.random.default_rng(seed)
        nb, nd = len(self.bins), len(self.days)
        self.deposit = np.zeros((nb, nd * 24))
        for i, b in self.bins.iterrows():
            kind = b["type"] if b["type"] in TYPES else "residential"
            prof = hour_profile(kind)
            bin_factor = rng.lognormal(0, 0.15)
            for d, day in enumerate(self.days):
                act = float(activity.loc[day, b["zone"]]) if day in activity.index else 1.0
                cal_row = cal.loc[day] if day in cal.index else None
                extra = 1.0
                if cal_row is not None:
                    if kind == "temple" and (cal_row["is_poya"] or cal_row["fest_vesak"]):
                        extra *= 1.3   # temple visits on Poya and Vesak
                    if kind == "market" and cal_row["is_holiday"] and not cal_row["fest_vesak"]:
                        extra *= 0.7   # markets partly closed on holidays
                day_factor = rng.lognormal(0, 0.15)
                expected = (TYPES[kind]["rate"] * bin_factor * prof * WEEK[kind][day.dayofweek] * act * extra
                            * day_factor)  # % per hour
                bags = rng.poisson(expected / 2.0)
                self.deposit[i, d * 24:(d + 1) * 24] = [rng.gamma(4.0, 0.5, k).sum() if k else 0.0 for k in bags]
        self.start_fill = rng.uniform(5, 40, nb)
        # sensor noise, estimate noise and what is left after emptying: also fixed in advance
        self.sensor_noise = rng.normal(0, 1.0, (nd, nb))
        self.growth_noise = rng.lognormal(0, 0.1, (nd, nb))
        self.residue = rng.uniform(0, 3, (nd, nb))

    def growth_estimate(self, i, hour_index, day):
        """Expected fill growth (% per day) for the next 24 hours, as Part B would estimate it:
        the bin's own average of the last 7 days, adjusted for the day of the week of its type."""
        past = self.deposit[i, max(0, hour_index - 7 * 24):hour_index]
        if len(past) < 24:
            return 30.0
        avg = past.sum() / (len(past) / 24.0)
        kind = self.bins.loc[i, "type"]
        week = WEEK.get(kind, WEEK["residential"])
        return avg * week[day.dayofweek] / np.mean(week)


def run_method(world, method, matrices, ratio_by_day, first_test_day, fixed_routes=None, threshold=None,
               routing="optimised", keep_plans=False):
    """Simulates every day: 06:00 choose bins -> plan routes -> trucks empty the bins at their arrival
    times -> waste keeps arriving every hour. Days before first_test_day are a warm-up (fixed schedule
    for everyone, not counted)."""
    nb = len(world.bins)
    fill = world.start_fill.copy()
    last_emptied = np.full(nb, -24.0)
    start_h = shift_start_hour()
    service_s = S.SERVICE_MINUTES * 60
    depot = nb  # node index of the depot in the matrices
    T0, D0, Tr, Dr = matrices

    def rush(h):
        return any(a <= h % 24 < b for a, b in S.RUSH_HOURS)

    def T_at(h):
        return Tr if rush(h) else T0

    def D_at(h):
        return Dr if rush(h) else D0

    every = [TYPES.get(k, TYPES["residential"])["every"] for k in world.bins["type"]]
    rows, overflow_days, plans = [], set(), {}
    overflow_l = 0.0
    full_hours = 0
    for d, day in enumerate(world.days):
        h_plan = d * 24 + int(start_h)
        testing = day >= first_test_day
        # -------- 1. choose bins and plan at 06:00 --------
        state = pd.DataFrame({
            "fill": np.clip(fill + world.sensor_noise[d], 0, 100),
            "growth": [world.growth_estimate(i, h_plan, day) * world.growth_noise[d, i] for i in range(nb)],
            "ratio": [ratio_by_day.get((day, z), 1.0) for z in world.bins["zone"]],
            "kind": world.bins["type"].to_numpy(),
            "days_since": (h_plan - last_emptied) / 24.0,
            "due": [(d + i) % every[i] == 0 for i in range(nb)]})  # schedules are spread over the days
        use = method if testing else "fixed"
        pick = choose_bins(use, state, threshold if testing else None)
        demand = np.array([bin_kg(min(100.0, f + 10), k) for f, k in zip(state["fill"], world.bins["type"])] + [0])
        p = Problem(T0, [service_s] * nb + [0], demand, pick, [depot] * S.N_TRUCKS, [depot] * S.N_TRUCKS,
                    [S.TRUCK_CAPACITY_KG] * S.N_TRUCKS, [S.SHIFT_HOURS * 3600] * S.N_TRUCKS)
        t0 = time.time()
        if use == "fixed" and fixed_routes is not None:
            routes = [[n for n in fr if n in pick] for fr in fixed_routes]
        elif routing == "nearest":
            # the same bins as the optimised plan, but driven in "nearest bin next" order
            chosen, _ = solve(p, time_limit=S.SOLVER_SECONDS, thorough=False)
            same = {n for r in chosen for n in r}
            p.penalty = {n: MANDATORY for n in same}
            routes = nearest_neighbour(p)
        else:
            routes, _ = solve(p, time_limit=S.SOLVER_SECONDS, thorough=False)
        solve_s = time.time() - t0
        result = drive(routes, [depot] * S.N_TRUCKS, [depot] * S.N_TRUCKS, T_at, D_at, service_s, start_h)
        if keep_plans:
            plans[day] = dict(fill=state["fill"].to_numpy().copy(), routes=[list(r) for r in routes], result=result,
                              pick=dict(pick))
        empty_at = {}
        for r in result:
            for n, hr in r["arrivals"].items():
                if n < nb:
                    empty_at[n] = d * 24 + hr
        # -------- 2. the next 24 hours --------
        collected_fill = []
        for h in range(h_plan, min(h_plan + 24, world.deposit.shape[1])):
            for n, when in list(empty_at.items()):
                if h <= when < h + 1:
                    collected_fill.append(fill[n])
                    fill[n] = world.residue[d, n]
                    last_emptied[n] = when
                    del empty_at[n]
            fill += world.deposit[:, h]
            over = fill > 100.0
            if testing and over.any():
                overflow_l += float(((fill[over] - 100.0) / 100.0 * S.BIN_LITRES).sum())
                full_hours += int(over.sum())
                for n in np.where(over)[0]:
                    overflow_days.add((n, d))
            fill = np.minimum(fill, 100.0)
        if testing:
            km = sum(r["km"] for r in result)
            hours = sum(r["hours"] for r in result)
            rows.append(dict(day=day, km=km, hours=hours, trucks=sum(1 for r in routes if r),
                             bins=sum(len(r) for r in routes), skipped=len(pick) - sum(len(r) for r in routes),
                             avg_fill_collected=float(np.mean(collected_fill)) if collected_fill else np.nan,
                             solve_s=solve_s, overtime_h=sum(max(0.0, r["hours"] - S.SHIFT_HOURS) for r in result)))
    daily = pd.DataFrame(rows)
    n_days = len(daily)
    summary = dict(km=daily.km.sum(), hours=daily.hours.sum(), fuel_l=daily.km.sum() * S.FUEL_L_PER_KM,
                   bins_emptied=int(daily.bins.sum()), trucks_per_day=daily.trucks.mean(),
                   avg_fill_collected=daily.avg_fill_collected.mean(), overflow_bin_days=len(overflow_days),
                   overflow_litres=overflow_l, full_bin_hours=full_hours,
                   service_level=100 * (1 - len(overflow_days) / (nb * n_days)),
                   solve_max_s=daily.solve_s.max(), solve_mean_s=daily.solve_s.mean(),
                   overtime_h=daily.overtime_h.sum(), days=n_days)
    summary["fuel_cost_lkr"] = summary["fuel_l"] * S.DIESEL_PRICE_LKR
    by_day = pd.Series([world.days[d] for _, d in overflow_days], dtype="datetime64[ns]").value_counts()
    summary["overflow_by_day"] = {pd.Timestamp(k): int(v) for k, v in by_day.items()}
    return (summary, daily, plans) if keep_plans else (summary, daily)
