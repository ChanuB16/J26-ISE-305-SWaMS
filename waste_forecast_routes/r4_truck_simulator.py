"""
R4 - TRUCK SIMULATOR (optional, for the demo)
=============================================
There is no real truck, so this script drives the trucks along today's routes (made by R3) and
writes their GPS position to Firebase every 2 seconds, like a GPS tracker in a truck would:

  trucks/<truck_id>   lat, lng, ts, status ("on_route" / "at_depot")

When a truck reaches a DEMO bin (sim_01 ... sim_20) it "empties" it: bins/<id>/latest fill_pct -> 2,
bins/<id>/last_collected = now, and the stop is marked done in routes/<date>/<truck>/stops.
The real bin (bin_01) is never changed - its own sensor sees the emptying.

Keep r3_live_routes.py running in another window: when you close a road in the dashboard, R3 makes
new routes from where the trucks are, and this simulator follows the new routes.

Run:  python r4_truck_simulator.py             (20 x faster than real time; Ctrl+C to stop)
      python r4_truck_simulator.py --speed 5   (5 x faster)
"""
import argparse
import time

import numpy as np
import pandas as pd

import settings as S
from roads import haversine_m
from wastelib import TZ, Firebase

TICK = 2.0          # seconds between GPS updates
AVG_KMH = 22.0      # average driving speed for the simulation


def load_routes(fb, date):
    data = fb.get(f"routes/{date}") or {}
    return {k: v for k, v in data.items() if k != "_summary" and isinstance(v, dict)}


class Truck:
    def __init__(self, truck_id, route):
        self.id = truck_id
        self.set_route(route)

    def set_route(self, route):
        self.route = route
        self.made_at = route.get("made_at")
        path = route.get("path") or []
        self.path = np.array(path, dtype=float) if path else np.zeros((0, 2))
        if len(self.path) >= 2:
            seg = haversine_m(self.path[:-1, 0], self.path[:-1, 1], self.path[1:, 0], self.path[1:, 1])
            self.cum = np.concatenate([[0.0], np.cumsum(seg)])
        else:
            self.cum = np.zeros(len(self.path))
        self.pos_m = 0.0
        stops = route.get("stops") or []
        self.stop_at = []  # distance along the path where each stop is
        last = 0
        for s in stops:
            if len(self.path) == 0:
                break
            d = haversine_m(self.path[last:, 0], self.path[last:, 1], s["lat"], s["lng"])
            i = last + int(np.argmin(d))
            self.stop_at.append(self.cum[i])
            last = i
        self.done = [bool(s.get("done")) for s in stops]

    def where(self):
        if len(self.path) == 0:
            return S.DEPOT
        m = min(self.pos_m, self.cum[-1])
        i = int(np.searchsorted(self.cum, m, side="right") - 1)
        i = min(i, len(self.path) - 2) if len(self.path) > 1 else 0
        if len(self.path) == 1:
            return tuple(self.path[0])
        f = (m - self.cum[i]) / max(1e-9, self.cum[i + 1] - self.cum[i])
        p = self.path[i] + f * (self.path[i + 1] - self.path[i])
        return float(p[0]), float(p[1])

    def finished(self):
        return len(self.path) == 0 or self.pos_m >= self.cum[-1]


def main():
    ap = argparse.ArgumentParser(description="Drive the trucks along today's routes (demo)")
    ap.add_argument("--speed", type=float, default=20.0, help="how many times faster than real time")
    args = ap.parse_args()
    fb = Firebase()
    date = pd.Timestamp.now(tz=TZ).strftime("%Y-%m-%d")
    print(f"R4 - truck simulator, {args.speed:g} x real time. Ctrl+C to stop.")
    trucks = {}
    while True:
        now_ms = int(time.time() * 1000)
        routes = load_routes(fb, date)
        if not routes:
            print("No routes for today yet. Start  python r3_live_routes.py  first.")
            time.sleep(10)
            continue
        update = {}
        for tid, route in routes.items():
            if tid not in trucks or route.get("made_at") != trucks[tid].made_at:
                new = Truck(tid, route)
                if tid in trucks:
                    print(f"{tid}: new route received ({len(route.get('stops') or [])} stops)")
                trucks[tid] = new
            t = trucks[tid]
            if not route.get("stops"):
                update[f"trucks/{tid}/status"] = "at_depot" if route.get("note") is None else "broken"
                continue
            t.pos_m += AVG_KMH / 3.6 * TICK * args.speed
            for i, at in enumerate(t.stop_at):
                if not t.done[i] and t.pos_m >= at:
                    t.done[i] = True
                    stop = route["stops"][i]
                    update[f"routes/{date}/{tid}/stops/{i}/done"] = True
                    if str(stop["bin_id"]).startswith("sim_"):
                        update[f"bins/{stop['bin_id']}/latest/fill_pct"] = 2.0
                        update[f"bins/{stop['bin_id']}/latest/ts"] = now_ms
                        update[f"bins/{stop['bin_id']}/last_collected"] = now_ms
                        update[f"predictions/{stop['bin_id']}/current_fill_pct"] = 2.0
                        update[f"predictions/{stop['bin_id']}/predicted_fill_6h"] = 8.0
                        update[f"predictions/{stop['bin_id']}/overflow_risk"] = "low"
                        update[f"predictions/{stop['bin_id']}/urgency_score"] = 0
                        update[f"predictions/{stop['bin_id']}/based_on_ts"] = now_ms + 1
                    print(f"{tid}: emptied {stop['bin_id']} ({stop.get('name', '')})")
            lat, lng = t.where()
            status = "at_depot" if t.finished() else "on_route"
            update[f"trucks/{tid}/lat"] = round(lat, 6)
            update[f"trucks/{tid}/lng"] = round(lng, 6)
            update[f"trucks/{tid}/ts"] = now_ms
            current = fb.get(f"trucks/{tid}/status")
            if current != "broken":
                update[f"trucks/{tid}/status"] = status
        if update:
            fb.patch("", update)
        time.sleep(TICK)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
