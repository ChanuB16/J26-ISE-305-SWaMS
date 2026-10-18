"""
Reads the result files (CSV tables and PNG charts) that the ML scripts saved:
  c2 = ../smart_bin_ml/results           (Component 2: fill prediction, overflow, urgency, nearest bin)
  c3 = ../waste_forecast_routes/results  (Component 3: waste forecast and truck routes)
"""
import csv
import math
import os
import time

import settings as S

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "demo", "results")   # copies shipped with the app (used if the folders are missing)


def folder(comp):
    base = S.SMART_BIN_ML_DIR if comp == "c2" else S.WASTE_FORECAST_DIR
    real = os.path.normpath(os.path.join(HERE, base, "results"))
    if os.path.isdir(real) and any(f.endswith(".csv") for f in os.listdir(real)):
        return real, False
    return os.path.join(SAMPLE, comp), True


def _value(v):
    if v is None:
        return None
    s = v.strip()
    if s == "":
        return ""
    try:
        f = float(s)
        if math.isinf(f) or math.isnan(f):
            return s
        return int(f) if f.is_integer() and "." not in s and "e" not in s.lower() else f
    except ValueError:
        return s


class Results:
    def __init__(self):
        self.cache = {}

    def table(self, comp, name):
        path = os.path.join(folder(comp)[0], name)
        if not os.path.isfile(path):
            return []
        mtime = os.path.getmtime(path)
        hit = self.cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = [{(k or "").strip(): _value(v) for k, v in r.items()} for r in csv.DictReader(f)]
        self.cache[path] = (mtime, rows)
        return rows

    def charts(self, comp):
        d = folder(comp)[0]
        if not os.path.isdir(d):
            return []
        return sorted(f for f in os.listdir(d) if f.lower().endswith(".png"))

    def info(self):
        out = {}
        for comp in ("c2", "c3"):
            d, sample = folder(comp)
            files = [f for f in os.listdir(d) if f.endswith(".csv")] if os.path.isdir(d) else []
            newest = max((os.path.getmtime(os.path.join(d, f)) for f in files), default=None)
            out[comp] = {"folder": d, "sample": sample, "files": len(files),
                         "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(newest)) if newest else None}
        return out

    def chart_path(self, comp, name):
        d = folder(comp)[0]
        safe = os.path.basename(name)
        p = os.path.join(d, safe)
        return p if safe.lower().endswith(".png") and os.path.isfile(p) else None


C2_FILES = ["rq2_models.csv", "rq2_overflow.csv", "rq2_feature_test.csv", "rq2_inputs.csv", "rq3_urgency.csv",
            "rq4_nearest.csv"]
C3_FILES = ["f2_models.csv", "f2_feature_test.csv", "f2_high_waste.csv", "f2_days_ahead.csv", "f2_inputs.csv",
            "f2_rolling_check.csv", "f2_test_predictions.csv", "forecast_next7.csv", "r2_methods.csv",
            "r2_daily.csv", "r2_replanning.csv", "r2_tradeoff.csv"]


def analytics(res):
    return {
        "info": res.info(),
        "c2": {f[:-4]: res.table("c2", f) for f in C2_FILES},
        "c3": {f[:-4]: res.table("c3", f) for f in C3_FILES},
        "charts": {"c2": res.charts("c2"), "c3": res.charts("c3")},
    }
