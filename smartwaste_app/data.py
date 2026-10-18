"""
Reads the database and turns it into what the pages show.
Firebase paths are the same as the ESP32 firmware and the Python scripts write (README, part 4).
"""
import math
import threading
import time
from datetime import date, datetime, timedelta

import settings as S

# The real bin from Part A, in case it has no /info yet (same as REAL_BIN in waste_forecast_routes/settings.py)
KNOWN_BINS = {
    "bin_01": {"name": "SLIIT Malabe (real smart bin)", "zone": "Malabe", "type": "school",
               "lat": 6.9147, "lng": 79.9729},
}

REPORT_TYPES = {
    "overflowing_bin": "Overflowing bin",
    "illegal_dumping": "Illegal dumping",
    "damaged_bin": "Damaged bin",
    "other": "Other problem",
}
REPORT_STATUS = ("new", "in_progress", "resolved")
REWARD_LEVELS = [(0, "Eco Starter"), (50, "Eco Contributor"), (150, "Green Champion"), (400, "Kaduwela Eco Hero")]


def now_ms():
    return int(time.time() * 1000)


def today(offset=0):
    return (date.today() + timedelta(days=offset)).isoformat()


def num(v):
    try:
        if v is None or v == "" or isinstance(v, bool):
            return None
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def as_list(v):
    if isinstance(v, list):
        return [x for x in v if x is not None]
    if isinstance(v, dict):
        return [v[k] for k in sorted(v, key=lambda k: int(k) if str(k).isdigit() else 0) if v[k] is not None]
    return []


# ---------------------------------------------------------------------------
# small cache so many open browser tabs do not hit Firebase again and again
# ---------------------------------------------------------------------------
class Cache:
    def __init__(self):
        self.items = {}
        self.lock = threading.Lock()

    def get(self, key, seconds, make):
        with self.lock:
            hit = self.items.get(key)
            if hit and time.time() - hit[0] < seconds:
                return hit[1]
        value = make()
        with self.lock:
            self.items[key] = (time.time(), value)
        return value

    def clear(self):
        with self.lock:
            self.items.clear()


cache = Cache()


# ---------------------------------------------------------------------------
# levels (also used for alerts)
# ---------------------------------------------------------------------------
def fill_level(f):
    if f is None:
        return "none"
    if f >= S.OVERFLOW_PCT:
        return "critical"
    if f >= S.ALERT_PCT:
        return "warning"
    if f >= S.FILLING_PCT:
        return "filling"
    return "normal"


def time_score(hours):
    if hours is None:
        return 0.0
    return max(0.0, min(100.0, hours / S.FULL_TIME_HOURS * 100.0))


def urgency_parts(row):
    """The 4 parts of the proposal's urgency score, so the page can show WHY a bin is urgent."""
    fill = row["pred"] if row["pred"] is not None else (row["fill"] or 0.0)
    gas = 0.0 if row.get("gas_ready") is False else (row["gas_index"] or 0.0)
    hum = row["humidity"] or 0.0
    tsc = time_score(row["hours_since"])
    parts = [
        {"key": "fill", "label": "Predicted fill in 6 h" if row["pred"] is not None else "Fill now",
         "value": fill, "weight": S.W_FILL},
        {"key": "gas", "label": "Gas / smell index", "value": gas, "weight": S.W_GAS},
        {"key": "humidity", "label": "Humidity", "value": hum, "weight": S.W_HUMIDITY},
        {"key": "time", "label": "Time since emptied", "value": tsc, "weight": S.W_TIME},
    ]
    for p in parts:
        p["points"] = round(p["value"] * p["weight"], 1)
    return parts


def make_row(bin_id, info, latest, pred, last_collected):
    info = {**KNOWN_BINS.get(bin_id, {}), **(info or {})}
    l, p = latest or {}, pred or {}
    ts = num(l.get("ts")) or num(p.get("based_on_ts"))
    fill = num(l.get("fill_pct"))
    if fill is None:
        fill = num(p.get("current_fill_pct"))
    lc = num(last_collected)
    hours_since = num(p.get("hours_since_collection"))
    if lc is None and hours_since is not None and ts:
        lc = ts - hours_since * 3600000
    if lc is not None and (hours_since is None or lc > (ts or 0)):
        hours_since = max(0.0, (now_ms() - lc) / 3600000)
    synthetic = bool(info.get("synthetic") or p.get("synthetic") or l.get("synthetic") or bin_id.startswith("sim_"))
    errors = l.get("errors") or []
    if isinstance(errors, dict):
        errors = list(errors.values())
    row = {
        "id": bin_id,
        "name": info.get("name") or bin_id,
        "zone": info.get("zone") or p.get("zone") or "",
        "type": info.get("type") or "",
        "lat": num(info.get("lat")) if num(info.get("lat")) is not None else num(p.get("lat")),
        "lng": num(info.get("lng")) if num(info.get("lng")) is not None else num(p.get("lng")),
        "capacity_l": num(info.get("capacity_l")),
        "fill": fill,
        "level": fill_level(fill),
        "distance_cm": num(l.get("distance_cm")),
        "weight_kg": num(l.get("weight_kg")),
        "gas_index": num(l.get("gas_index")) if num(l.get("gas_index")) is not None else num(p.get("gas_index")),
        "gas_mv": num(l.get("gas_mv")),
        "gas_ready": l.get("gas_ready"),
        "temp_c": num(l.get("temp_c")),
        "humidity": num(l.get("humidity_pct")) if num(l.get("humidity_pct")) is not None else num(p.get("humidity_pct")),
        "battery_v": num(l.get("battery_v")),
        "battery_pct": num(l.get("battery_pct")),
        "rssi": num(l.get("rssi")),
        "errors": [str(e) for e in errors if e],
        "urgency_now": num(l.get("urgency_now")),
        "ts": ts,
        "time_local": l.get("time_local") or "",
        "pred": num(p.get("predicted_fill_6h")),
        "risk": p.get("overflow_risk") or "",
        "hours_to_full": num(p.get("hours_to_full")),
        "urgency": num(p.get("urgency_score")),
        "hours_since": hours_since,
        "pred_status": p.get("status") or ("ok" if pred else "no prediction yet"),
        "pred_at": num(p.get("updated_at")),
        "model": p.get("model") or "",
        "last_collected": lc,
        "collected_recorded": num(last_collected),
        "synthetic": synthetic,
        "has_sensors": bool(l),
        "stale": (not ts) or (now_ms() - ts > S.NO_DATA_MINUTES * 60000),
    }
    return row


def _bins_raw(db):
    keys = db.get("bins", shallow=True) or {}
    preds = db.get("predictions") or {}
    ids = sorted({*keys.keys(), *preds.keys()} - {k for k in keys if k.startswith("_")})
    infos = cache.get(("infos", tuple(sorted(keys))), 300,
                      lambda: {i: db.get(f"bins/{i}/info") for i in keys})
    rows = []
    for i in ids:
        latest = db.get(f"bins/{i}/latest") if i in keys else None
        lastc = db.get(f"bins/{i}/last_collected") if i in keys else None
        rows.append(make_row(i, infos.get(i), latest, preds.get(i), lastc))
    rows.sort(key=lambda r: (-(r["urgency"] if r["urgency"] is not None else -1),
                             -(r["fill"] if r["fill"] is not None else -1)))
    return rows


def bins(db):
    return cache.get("bins", 4, lambda: _bins_raw(db))


def alerts(rows, fc_days=None, trucks=None):
    """Early warnings for the municipal team (Component 2 FR: early warning; Component 3: busy days)."""
    out = []
    for r in rows:
        name = f'{r["id"]} ({r["name"]})' if r["name"] != r["id"] else r["id"]
        if r["fill"] is not None and r["fill"] >= S.OVERFLOW_PCT:
            out.append({"level": "critical", "bin": r["id"], "title": f"{name} is full",
                        "text": f'{r["fill"]:.0f}% full now. Collect it as soon as possible.'})
        elif r["risk"] == "high" or (r["pred"] is not None and r["pred"] >= S.OVERFLOW_PCT):
            h = r["hours_to_full"]
            when = f"in about {h:.1f} hours" if h is not None and h < 48 else "within 6 hours"
            out.append({"level": "warning", "bin": r["id"], "title": f"{name} will overflow {when}",
                        "text": f'ML prediction: {r["pred"]:.0f}% in 6 hours (now {r["fill"] or 0:.0f}%).'})
        elif r["fill"] is not None and r["fill"] >= S.ALERT_PCT:
            out.append({"level": "serious", "bin": r["id"], "title": f"{name} is nearly full",
                        "text": f'{r["fill"]:.0f}% full now.'})
        if r["gas_index"] is not None and r["gas_index"] >= S.SMELL_INDEX and r.get("gas_ready") is not False:
            out.append({"level": "serious", "bin": r["id"], "title": f"Strong smell at {name}",
                        "text": f'Gas index {r["gas_index"]:.0f} (limit {S.SMELL_INDEX}). Food waste may be rotting.'})
        if not r["synthetic"]:
            if r["stale"]:
                out.append({"level": "info", "bin": r["id"], "title": f"No data from {name}",
                            "text": "No reading for more than %d minutes. Check power and WiFi." % S.NO_DATA_MINUTES})
            if r["battery_pct"] is not None and r["battery_pct"] < S.LOW_BATTERY_PCT:
                out.append({"level": "serious", "bin": r["id"], "title": f"Low battery at {name}",
                            "text": f'Battery {r["battery_pct"]:.0f}% ({r["battery_v"] or 0:.2f} V). Charge it.'})
            for e in r["errors"]:
                out.append({"level": "info", "bin": r["id"], "title": f"Sensor problem at {name}", "code": e, "text": e})
    for d in fc_days or []:
        if d.get("busy"):
            out.append({"level": "info", "title": f'Busy day {d["label"]}: {", ".join(d["busy"])}',
                        "text": f'Forecast {d["forecast"]:.1f} t in all areas ({d["change"]:+.0f}% vs a normal day).'
                                + (f' {d["holiday"]}.' if d.get("holiday") else "")})
    for t in trucks or []:
        if t.get("status") == "broken":
            out.append({"level": "critical", "title": f'{t["name"]} is broken',
                        "text": "Its bins were moved to the other trucks by the route planner (if it is running)."})
    order = {"critical": 0, "warning": 1, "serious": 2, "info": 3}
    out.sort(key=lambda a: order.get(a["level"], 9))
    return out


def kpis(rows, trucks):
    with_fill = [r for r in rows if r["fill"] is not None]
    return {
        "total": len(rows),
        "real": sum(1 for r in rows if not r["synthetic"]),
        "critical": sum(1 for r in with_fill if r["fill"] >= S.OVERFLOW_PCT),
        "warning": sum(1 for r in with_fill if S.ALERT_PCT <= r["fill"] < S.OVERFLOW_PCT),
        "filling": sum(1 for r in with_fill if S.FILLING_PCT <= r["fill"] < S.ALERT_PCT),
        "normal": sum(1 for r in with_fill if r["fill"] < S.FILLING_PCT),
        "high_risk": sum(1 for r in rows if r["risk"] == "high"),
        "avg_fill": round(sum(r["fill"] for r in with_fill) / len(with_fill), 1) if with_fill else None,
        "trucks_total": len(trucks),
        "trucks_on_route": sum(1 for t in trucks if t["status"] == "on_route"),
        "trucks_broken": sum(1 for t in trucks if t["status"] == "broken"),
    }


# ---------------------------------------------------------------------------
# one bin
# ---------------------------------------------------------------------------
def bin_detail(db, bin_id):
    rows = {r["id"]: r for r in bins(db)}
    row = rows.get(bin_id)
    if row is None:
        return None
    device = db.get(f"bins/{bin_id}/device")
    cols = db.get(f"bins/{bin_id}/collections", last=100) or {}
    collections = sorted(({**(c or {}), "ts": num((c or {}).get("ts")) or num(k)} for k, c in cols.items()),
                         key=lambda c: -(c["ts"] or 0))
    nearest = nearest_with_space(list(rows.values()), row["lat"], row["lng"], exclude=bin_id) \
        if row["lat"] is not None else None
    return {"bin": row, "device": device, "collections": collections, "urgency_parts": urgency_parts(row),
            "nearest": nearest}


READING_FIELDS = ["ts", "fill_pct", "distance_cm", "weight_kg", "gas_index", "gas_mv", "gas_ready", "temp_c",
                  "humidity_pct", "battery_v", "battery_pct", "urgency_now", "rssi", "errors"]


def readings(db, bin_id, start_ms, end_ms=None):
    data = db.get(f"bins/{bin_id}/readings", start=int(start_ms), end=int(end_ms) if end_ms else None) or {}
    if isinstance(data, list):
        data = {str(i): v for i, v in enumerate(data) if v}
    out = []
    for k, r in data.items():
        if not isinstance(r, dict):
            continue
        ts = num(r.get("ts")) or num(k)
        if not ts:
            continue
        row = {f: r.get(f) for f in READING_FIELDS}
        row["ts"] = int(ts)
        if isinstance(row["errors"], dict):
            row["errors"] = list(row["errors"].values())
        out.append(row)
    out.sort(key=lambda r: r["ts"])
    return out


def bucket(rows, seconds):
    """Averages readings into time buckets (for long ranges). Keeps the highest fill in each bucket."""
    if not rows:
        return rows
    size = seconds * 1000
    groups = {}
    for r in rows:
        groups.setdefault(r["ts"] // size, []).append(r)
    out = []
    for k in sorted(groups):
        g = groups[k]
        row = {"ts": int(g[-1]["ts"]), "n": len(g)}
        for f in READING_FIELDS[1:]:
            vals = [num(x.get(f)) for x in g]
            vals = [v for v in vals if v is not None]
            if f == "errors":
                row[f] = sorted({e for x in g for e in (x.get("errors") or [])})
            elif f == "gas_ready":
                row[f] = all(x.get("gas_ready") is not False for x in g)
            elif f == "fill_pct":
                row[f] = round(max(vals), 1) if vals else None
            else:
                row[f] = round(sum(vals) / len(vals), 2) if vals else None
        out.append(row)
    return out


def reading_stats(rows):
    def col(f):
        return [v for v in (num(r.get(f)) for r in rows) if v is not None]
    out = {}
    for f in ("fill_pct", "weight_kg", "gas_index", "temp_c", "humidity_pct", "battery_pct"):
        v = col(f)
        out[f] = {"min": min(v), "max": max(v), "avg": sum(v) / len(v), "last": v[-1]} if v else None
    out["count"] = len(rows)
    out["first_ts"] = rows[0]["ts"] if rows else None
    out["last_ts"] = rows[-1]["ts"] if rows else None
    return out


# ---------------------------------------------------------------------------
# nearest bin with space (Component 2, method R1)
# ---------------------------------------------------------------------------
def km(lat1, lng1, lat2, lng2):
    r = math.pi / 180
    a = math.sin((lat2 - lat1) * r / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lng2 - lng1) * r / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def nearest_with_space(rows, lat, lng, exclude=None):
    cands = []
    for r in rows:
        if r["lat"] is None or r["lng"] is None or r["id"] == exclude:
            continue
        d = km(lat, lng, r["lat"], r["lng"])
        cands.append({**r, "km": round(d, 3)})
    cands.sort(key=lambda r: r["km"])
    ok = [r for r in cands if r["fill"] is not None and r["fill"] < S.SPACE_LIMIT_PCT
          and (r["pred"] is None or r["pred"] < S.OVERFLOW_PCT) and r["km"] <= S.MAX_WALK_KM]
    return {"best": ok[0] if ok else None, "others": ok[1:5], "nearest_any": cands[0] if cands else None,
            "rule": f"below {S.SPACE_LIMIT_PCT}% now, below {S.OVERFLOW_PCT}% in 6 hours, within {S.MAX_WALK_KM:g} km"}


# ---------------------------------------------------------------------------
# forecasts (Component 3)
# ---------------------------------------------------------------------------
def _day_label(d):
    return datetime.fromisoformat(d).strftime("%a %d %b")


def forecasts(db, results):
    def make():
        start = today(0)
        zones = sorted(k for k in (db.get("forecasts", shallow=True) or {}) if not k.startswith("_"))
        by_zone = {z: db.get(f"forecasts/{z}", start=start, first=7) or {} for z in zones}
        info = db.get("forecasts/_info") or {}
        source = "firebase"
        if not any(by_zone.values()):
            by_zone, source = {}, "none"
            for r in results.table("c3", "forecast_next7.csv"):
                if str(r.get("date", "")) < start:
                    continue
                by_zone.setdefault(r["zone"], {})[r["date"]] = {
                    "forecast_t": r.get("forecast_t"), "normal_t": r.get("normal_t"), "change_pct": r.get("change_pct"),
                    "rain_mm": r.get("rain_mm"), "high_waste": str(r.get("high_waste")).lower() == "true",
                    "holiday": r.get("holiday") or r.get("event") or ""}
                source = "file"
            if source == "file":
                info = {"model": "saved file results/forecast_next7.csv (Firebase has no forecasts)"}
        zones = sorted(by_zone)
        days = sorted({d for z in zones for d in by_zone[z]})[:7]
        totals = []
        for d in days:
            t = n = 0.0
            busy, hol, rain = [], "", None
            for z in zones:
                f = by_zone[z].get(d)
                if not f:
                    continue
                t += num(f.get("forecast_t")) or 0
                n += num(f.get("normal_t")) or 0
                if f.get("high_waste"):
                    busy.append(z)
                if f.get("holiday"):
                    hol = f["holiday"]
                if num(f.get("rain_mm")) is not None:
                    rain = num(f.get("rain_mm"))
            totals.append({"date": d, "label": _day_label(d), "forecast": round(t, 2), "normal": round(n, 2),
                           "change": round((t - n) / n * 100, 1) if n else 0.0, "busy": busy, "holiday": hol,
                           "rain_mm": rain})
        guidance = {d: v for d, v in (db.get("guidance", start=start, first=8) or {}).items()
                    if not d.startswith("_") and isinstance(v, dict) and any(v.values())}
        return {"by_zone": by_zone, "zones": zones, "days": days, "totals": totals, "info": info,
                "source": source, "guidance": guidance}
    return cache.get("forecasts", 30, make)


# ---------------------------------------------------------------------------
# routes (Component 3)
# ---------------------------------------------------------------------------
def routes(db, day):
    def make():
        r = db.get(f"routes/{day}") or {}
        trucks = db.get("trucks") or {}
        traffic = db.get("traffic") or {}
        replan = db.get("control/replan")
        ids = sorted({*[k for k in r if not k.startswith("_")], *trucks.keys()})
        out = []
        for i, t in enumerate(ids):
            route = r.get(t) or {}
            truck = trucks.get(t) or {}
            stops = as_list(route.get("stops"))
            status = truck.get("status") or ("available" if stops else "at_depot")
            out.append({"id": t, "index": i, "name": route.get("truck") or truck.get("name") or t, "status": status,
                        "lat": num(truck.get("lat")), "lng": num(truck.get("lng")), "gps_ts": num(truck.get("ts")),
                        "stops": stops, "done": sum(1 for s in stops if s.get("done")),
                        "km": num(route.get("km")), "minutes": num(route.get("minutes")),
                        "fuel_l": num(route.get("fuel_l")), "cost_lkr": num(route.get("cost_lkr")),
                        "start": route.get("start") or "", "path": as_list(route.get("path")),
                        "note": route.get("note"), "made_at": num(route.get("made_at"))})
        zones = []
        for k, z in (traffic or {}).items():
            if isinstance(z, dict) and z.get("lat") is not None and (not z.get("until") or num(z.get("until")) > now_ms()):
                zones.append({"id": k, **z})
        summary = r.get("_summary")
        if summary:
            summary["skipped"] = as_list(summary.get("skipped"))
        return {"date": day, "summary": summary, "trucks": out, "traffic": zones, "replan_asked": replan,
                "depot": list(S.DEPOT), "depot_name": S.DEPOT_NAME}
    return cache.get(("routes", day), 4, make)


def mark_stop_done(db, day, truck_id, index):
    route = db.get(f"routes/{day}/{truck_id}") or {}
    stops = as_list(route.get("stops"))
    if index < 0 or index >= len(stops):
        raise ValueError("That stop is not in today's route (the route may have changed). Reload the page.")
    stop = stops[index]
    t = now_ms()
    up = {f"routes/{day}/{truck_id}/stops/{index}/done": True,
          f"routes/{day}/{truck_id}/stops/{index}/done_at": t}
    b = str(stop.get("bin_id"))
    # Demo bins have no sensor, so we "empty" them here (same as r4_truck_simulator.py).
    # The real bin sees the emptying with its own sensor and records it itself.
    if b.startswith("sim_"):
        up.update({f"bins/{b}/latest/fill_pct": 2.0, f"bins/{b}/latest/ts": t, f"bins/{b}/last_collected": t,
                   f"predictions/{b}/current_fill_pct": 2.0, f"predictions/{b}/predicted_fill_6h": 8.0,
                   f"predictions/{b}/overflow_risk": "low", f"predictions/{b}/urgency_score": 0,
                   f"predictions/{b}/based_on_ts": t + 1})
    db.patch("", up)
    cache.clear()
    return stop


# ---------------------------------------------------------------------------
# community: rewards, citizen reports, Component 1 photos
# ---------------------------------------------------------------------------
def reward_level(points):
    cur, nxt = REWARD_LEVELS[0], None
    for i, lv in enumerate(REWARD_LEVELS):
        if points >= lv[0]:
            cur, nxt = lv, (REWARD_LEVELS[i + 1] if i + 1 < len(REWARD_LEVELS) else None)
    return {"name": cur[1], "min": cur[0], "next_name": nxt[1] if nxt else None, "next_min": nxt[0] if nxt else None}


def community(db):
    def make():
        rewards = db.get("rewards") or {}
        reports = db.get("reports") or {}
        photos = db.get("classifications") or {}
        users = []
        for u, v in rewards.items():
            if u.startswith("_") or not isinstance(v, dict):
                continue
            hist = sorted(({"id": k, **h} for k, h in (v.get("history") or {}).items() if isinstance(h, dict)),
                          key=lambda h: -(num(h.get("ts")) or 0))
            pts = int(num(v.get("points")) or 0)
            users.append({"user": u, "points": pts, "level": reward_level(pts)["name"], "history": hist})
        users.sort(key=lambda x: -x["points"])
        processed = set((rewards.get("_processed") or {}).keys())
        rep = []
        for k, r in reports.items():
            if not isinstance(r, dict):
                continue
            item = {"id": k, **{x: y for x, y in r.items() if x != "photo"}}
            item["has_photo"] = bool(r.get("has_photo") or r.get("photo"))
            item["status"] = r.get("status") or "new"
            item["type_label"] = REPORT_TYPES.get(r.get("type"), str(r.get("type") or "report").replace("_", " "))
            item["points_checked"] = k in processed or f"report_{k}" in processed
            rep.append(item)
        rep.sort(key=lambda r: -(num(r.get("ts")) or 0))
        ph = sorted(({"id": k, **v} for k, v in photos.items() if isinstance(v, dict)), key=lambda r: -(num(r.get("ts")) or 0))
        return {"users": users, "reports": rep, "photos": ph}
    return cache.get("community", 5, make)


def citizen_view(db, user):
    c = community(db)
    me = next((u for u in c["users"] if u["user"] == user), None)
    pts = me["points"] if me else 0
    rank = next((i + 1 for i, u in enumerate(c["users"]) if u["user"] == user), None)
    return {"user": user, "points": pts, "level": reward_level(pts), "history": me["history"] if me else [],
            "rank": rank, "players": len(c["users"]),
            "top": [{"user": u["user"], "points": u["points"], "level": u["level"]} for u in c["users"][:10]],
            "reports": [r for r in c["reports"] if r.get("user") == user]}


# ---------------------------------------------------------------------------
# RQ1 (Component 2): is the smart bin's data reliable? Same numbers as smart_bin_code/tools/rq1_metrics.py
# ---------------------------------------------------------------------------
RQ1_SENSORS = [("Ultrasonic (fill)", "fill_pct"), ("Load cell (weight)", "weight_kg"), ("Gas (MQ-135)", "gas_mv"),
               ("Temperature (DHT22)", "temp_c"), ("Humidity (DHT22)", "humidity_pct")]


def _valid(r, field):
    if field == "gas_mv":
        return isinstance(r.get("gas_mv"), (int, float)) and r["gas_mv"] >= 5
    return r.get(field) is not None


def rq1(db, bin_id, start_ms):
    data = db.get(f"bins/{bin_id}/readings", start=int(start_ms)) or {}
    rows = sorted((r for r in (data.values() if isinstance(data, dict) else data) if isinstance(r, dict) and r.get("ts")),
                  key=lambda r: r["ts"])
    n = len(rows)
    out = {"bin": bin_id, "count": n, "first": rows[0]["ts"] if rows else None, "last": rows[-1]["ts"] if rows else None}
    if not n:
        return out
    out["sensors"] = [{"name": name, "field": f, "valid": sum(1 for r in rows if _valid(r, f)),
                       "pct": round(100 * sum(1 for r in rows if _valid(r, f)) / n, 1)} for name, f in RQ1_SENSORS]
    allv = sum(1 for r in rows if all(_valid(r, f) for _, f in RQ1_SENSORS))
    out["all_valid"] = {"valid": allv, "pct": round(100 * allv / n, 1)}
    by_boot = {}
    for r in rows:
        if r.get("seq") is not None and r.get("boot") is not None:
            by_boot.setdefault(r["boot"], set()).add(int(r["seq"]))
    rx = sum(len(s) for s in by_boot.values())
    exp = sum(max(s) - min(s) + 1 for s in by_boot.values())
    out["transmission"] = {"received": rx, "expected": exp, "pct": round(100 * rx / exp, 1) if exp else None,
                           "starts": len(by_boot)}
    live, queued = [], 0
    for r in rows:
        if isinstance(r.get("server_ts"), (int, float)):
            if (r.get("queue_s") or 0) <= 5:
                live.append((r["server_ts"] - r["ts"]) / 1000.0)
            else:
                queued += 1
    if live:
        live.sort()
        out["latency"] = {"count": len(live), "mean": round(sum(live) / len(live), 2), "median": round(live[len(live) // 2], 2),
                          "p95": round(live[min(len(live) - 1, int(round(0.95 * (len(live) - 1))))], 2),
                          "max": round(live[-1], 2), "queued": queued}
    else:
        out["latency"] = None
    return out
