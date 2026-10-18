"""
Shared code for the smart-bin ML scripts. You do not need to edit this file.

What is in here:
  - to_grid():       readings of one bin -> one row every 15 minutes
  - add_features():  the model inputs (features) and the 6-hour target
  - urgency() etc.:  the proposal's urgency score, overflow risk, hours until full
  - distance_km():   straight-line distance between two GPS points
  - Firebase:        read and write the Firebase Realtime Database (REST, optional login)
"""
import json
import math
import os
import time

import numpy as np
import pandas as pd

import settings as S

TZ = "Asia/Colombo"
STEPS_PER_HOUR = 60 // S.STEP_MINUTES
H_STEPS = S.HORIZON_HOURS * STEPS_PER_HOUR
DATA_DIR = "data"
RESULTS_DIR = "results"
CAPACITY_L = 25  # the prototype bin, about 25 litres

# Feature sets B1 to B4 from the proposal (Table 8, baseline and ablation plan)
FEATURE_SETS = {
    "B1": ["fill", "fill_lag_1h", "fill_lag_3h", "fill_lag_6h", "rate_1h", "rate_3h", "rate_6h"],
}
FEATURE_SETS["B2"] = FEATURE_SETS["B1"] + ["weight", "weight_rate_3h"]
FEATURE_SETS["B3"] = FEATURE_SETS["B2"] + ["gas", "humidity", "temp"]
FEATURE_SETS["B4"] = FEATURE_SETS["B3"] + ["hours_since_collection", "hour_sin", "hour_cos",
                                           "day_of_week", "is_weekend"]
FEATURE_SET_NAMES = {
    "B1": "B1 fill only",
    "B2": "B2 + weight",
    "B3": "B3 + gas, humidity, temperature",
    "B4": "B4 + time of day, day, hours since emptied",
}
NICE_NAMES = {
    "fill": "Fill now", "fill_lag_1h": "Fill 1 h ago", "fill_lag_3h": "Fill 3 h ago",
    "fill_lag_6h": "Fill 6 h ago", "rate_1h": "Fill speed, last 1 h", "rate_3h": "Fill speed, last 3 h",
    "rate_6h": "Fill speed, last 6 h", "weight": "Weight now", "weight_rate_3h": "Weight speed, last 3 h",
    "gas": "Gas index", "humidity": "Humidity", "temp": "Temperature",
    "hours_since_collection": "Hours since emptied", "hour_sin": "Time of day (sin)",
    "hour_cos": "Time of day (cos)", "day_of_week": "Day of week", "is_weekend": "Weekend",
}
# Used only in live mode when a sensor value is missing (for example the gas sensor is warming up)
LIVE_DEFAULTS = {"weight": 0.0, "weight_rate_3h": 0.0, "gas": 0.0, "humidity": 75.0, "temp": 28.0}


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)


def need_file(path, how_to_make):
    if not os.path.exists(path):
        raise SystemExit(f"Missing file: {path}\n{how_to_make}")


# ---------------------------------------------------------------------------
# Readings -> 15-minute grid -> features
# ---------------------------------------------------------------------------
SENSOR_COLUMNS = {"fill_pct": "fill", "weight_kg": "weight", "gas_index": "gas",
                  "humidity_pct": "humidity", "temp_c": "temp"}


def to_grid(readings):
    """Readings of ONE bin (columns ts in ms + sensor columns) -> one row per 15 minutes.

    Each grid row is labelled with the END of its 15 minutes and holds the median of the readings
    inside it, so a row never contains data from the future. Gaps of up to 30 minutes are filled
    with the last value; longer gaps stay empty (NaN).
    """
    ts = pd.to_numeric(readings["ts"], errors="coerce")
    ok = ts.notna() & (ts > 1e12)  # skip readings without a real time
    readings = readings.loc[ok]
    t = pd.to_datetime(ts[ok].astype("int64"), unit="ms", utc=True).dt.tz_convert(TZ)
    data = {}
    for old, new in SENSOR_COLUMNS.items():
        if old in readings.columns:
            data[new] = pd.to_numeric(readings[old], errors="coerce").to_numpy()
        else:
            data[new] = np.full(len(readings), np.nan)
    d = pd.DataFrame(data, index=pd.DatetimeIndex(t))
    d = d.sort_index()
    g = d.resample(f"{S.STEP_MINUTES}min", label="right", closed="right").median()
    return g.ffill(limit=2)


def add_features(g, collection_ms, live=False):
    """Adds the model inputs (features) and the targets to a 15-minute grid of one bin.

    collection_ms: times (ms) when the bin was emptied. Before the first known emptying, the start
    of the data counts as the last emptying.
    live=True: for a bin with less than 6 hours of data, missing history is filled with the
    oldest value we have (status "warming_up").
    """
    g = g.copy()
    idx = g.index
    t_ns = idx.as_unit("ns").asi8  # nanoseconds (pandas 3 may store milliseconds)
    coll = np.array(sorted(int(c) * 1_000_000 for c in collection_ms), dtype=np.int64)
    pos = np.searchsorted(coll, t_ns, side="right") - 1
    if len(coll):
        last_ns = np.where(pos >= 0, coll[np.clip(pos, 0, len(coll) - 1)], t_ns[0])
    else:
        last_ns = np.full(len(t_ns), t_ns[0])
    hsc = pd.Series((t_ns - last_ns) / 3.6e12, index=idx)
    g["hours_since_collection"] = hsc
    g["segment"] = pos

    first_fill = g.groupby("segment")["fill"].transform("first")
    first_weight = g.groupby("segment")["weight"].transform("first")
    if g["fill"].notna().any():
        first_valid = g["fill"].first_valid_index()
        hist_hours = pd.Series((t_ns - first_valid.value) / 3.6e12, index=idx)
        oldest_fill = g["fill"].dropna().iloc[0]
    else:
        hist_hours = pd.Series(0.0, index=idx)
        oldest_fill = np.nan

    for hours in (1, 3, 6):
        k = hours * STEPS_PER_HOUR
        lag = g["fill"].shift(k)
        crossed = hsc < hours  # the bin was emptied inside this window
        lag = lag.where(~crossed, first_fill)
        span = np.where(crossed, np.maximum(hsc, 1.0), float(hours))
        if live:
            missing = lag.isna() & ~crossed
            lag = lag.fillna(oldest_fill)
            span = np.where(missing, np.maximum(np.minimum(hist_hours, hours), 1.0), span)
        g[f"fill_lag_{hours}h"] = lag
        g[f"rate_{hours}h"] = (g["fill"] - lag) / span

    wlag = g["weight"].shift(3 * STEPS_PER_HOUR)
    crossed3 = hsc < 3
    wlag = wlag.where(~crossed3, first_weight)
    wspan = np.where(crossed3, np.maximum(hsc, 1.0), 3.0)
    if live:
        wmissing = wlag.isna() & ~crossed3
        oldest_w = g["weight"].dropna().iloc[0] if g["weight"].notna().any() else np.nan
        wlag = wlag.fillna(oldest_w)
        wspan = np.where(wmissing, np.maximum(np.minimum(hist_hours, 3.0), 1.0), wspan)
    g["weight_rate_3h"] = (g["weight"] - wlag) / wspan

    hour = idx.hour + idx.minute / 60.0
    g["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    g["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    g["day_of_week"] = idx.dayofweek
    g["is_weekend"] = (idx.dayofweek >= 5).astype(int)
    g["history_hours"] = hist_hours

    # Targets (only for training and testing; unknown in live mode)
    future = g["fill"].shift(-H_STEPS)
    same_segment = g["segment"].shift(-H_STEPS) == g["segment"]  # not emptied in the next 6 hours
    g["target_fill_6h"] = future.where(same_segment)
    g["max_fill_next_6h"] = g["fill"][::-1].rolling(H_STEPS, min_periods=1).max()[::-1].shift(-1)
    g["max_gas_next_6h"] = g["gas"][::-1].rolling(H_STEPS, min_periods=1).max()[::-1].shift(-1)
    g["fill_next_1h"] = g["fill"].shift(-STEPS_PER_HOUR)
    return g


def load_dataset(readings_csv, collections_csv):
    """All bins in a readings CSV -> one table of features, one row per bin per 15 minutes."""
    r = pd.read_csv(readings_csv)
    c = pd.read_csv(collections_csv) if os.path.exists(collections_csv) else pd.DataFrame(columns=["bin_id", "ts"])
    frames = []
    for bin_id, part in r.groupby("bin_id"):
        g = to_grid(part)
        coll = c.loc[c["bin_id"] == bin_id, "ts"].tolist() if len(c) else []
        f = add_features(g, coll)
        f["bin_id"] = bin_id
        frames.append(f.rename_axis("time").reset_index())
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Urgency score, overflow risk, hours until full, distance
# ---------------------------------------------------------------------------
def time_score(hours):
    return np.clip(np.asarray(hours, dtype=float) / S.FULL_TIME_HOURS * 100.0, 0, 100)


def urgency(fill_like, gas, humidity, hours_since_collection):
    """The proposal's urgency score (0 to 100). fill_like = predicted fill (U2) or current fill."""
    gas = np.nan_to_num(np.asarray(gas, dtype=float), nan=0.0)
    hum = np.nan_to_num(np.asarray(humidity, dtype=float), nan=0.0)
    u = (S.W_FILL * np.asarray(fill_like, dtype=float) + S.W_GAS * gas + S.W_HUMIDITY * hum
         + S.W_TIME * time_score(hours_since_collection))
    return np.clip(u, 0, 100)


def overflow_risk(predicted_fill):
    if predicted_fill >= S.OVERFLOW_PCT:
        return "high"
    if predicted_fill >= S.ALERT_PCT:
        return "medium"
    return "low"


def hours_to_full(fill_now, predicted_fill):
    """Hours until the bin reaches OVERFLOW_PCT, from the predicted fill speed. None = not filling."""
    if fill_now >= S.OVERFLOW_PCT:
        return 0.0
    speed = (predicted_fill - fill_now) / S.HORIZON_HOURS  # % per hour
    if speed <= 0.05:
        return None
    hours = (S.OVERFLOW_PCT - fill_now) / speed
    return round(hours, 1) if hours <= 72 else None


def distance_km(lat1, lng1, lat2, lng2):
    """Straight-line distance on the earth (haversine formula)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def predict_rows(model_pack, rows):
    """Predicted fill in 6 hours for a table of feature rows (clipped to 0..100)."""
    x = rows[model_pack["features"]].to_numpy(dtype=float)
    return np.clip(model_pack["model"].predict(x), 0, 100)


# ---------------------------------------------------------------------------
# Real data from a Firebase export (JSON)
# ---------------------------------------------------------------------------
def read_export(path):
    """Firebase export JSON -> (readings DataFrame, collections DataFrame) for every bin in it."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    bins = data.get("bins", data) if isinstance(data, dict) else {}
    if isinstance(bins, dict) and "readings" in bins:
        bins = {"bin_01": bins}
    rows, cols = [], []
    for bin_id, node in (bins or {}).items():
        if not isinstance(node, dict):
            continue
        for r in (node.get("readings") or {}).values():
            if isinstance(r, dict) and r.get("ts"):
                rows.append({"bin_id": bin_id, "ts": r.get("ts"), "fill_pct": r.get("fill_pct"),
                             "weight_kg": r.get("weight_kg"), "gas_index": r.get("gas_index"),
                             "humidity_pct": r.get("humidity_pct"), "temp_c": r.get("temp_c"),
                             "source": "real"})
        for c in (node.get("collections") or {}).values():
            if isinstance(c, dict) and c.get("ts"):
                cols.append({"bin_id": bin_id, "ts": c.get("ts"),
                             "fill_before_pct": c.get("fill_before_pct"), "fill_after_pct": c.get("fill_after_pct"),
                             "weight_before_kg": c.get("weight_before_kg"), "weight_after_kg": c.get("weight_after_kg")})
    readings = pd.DataFrame(rows, columns=["bin_id", "ts", "fill_pct", "weight_kg", "gas_index",
                                           "humidity_pct", "temp_c", "source"])
    collections = pd.DataFrame(cols, columns=["bin_id", "ts", "fill_before_pct", "fill_after_pct",
                                              "weight_before_kg", "weight_after_kg"])
    return readings.sort_values(["bin_id", "ts"]), collections.sort_values(["bin_id", "ts"])


# ---------------------------------------------------------------------------
# Firebase Realtime Database (REST API)
# ---------------------------------------------------------------------------
class Firebase:
    def __init__(self):
        import requests
        self.requests = requests
        self.url = S.FIREBASE_DB_URL.rstrip("/")
        self.token = None
        self.token_time = 0.0
        if "YOUR-PROJECT" in self.url:
            raise SystemExit("Open settings.py and set FIREBASE_DB_URL to your database URL first.")

    def _params(self, extra=None):
        p = dict(extra or {})
        if S.USE_LOGIN:
            if self.token is None or time.time() - self.token_time > 50 * 60:
                url = ("https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key="
                       + S.FIREBASE_API_KEY)
                r = self.requests.post(url, json={"email": S.FIREBASE_EMAIL, "password": S.FIREBASE_PASSWORD,
                                                  "returnSecureToken": True}, timeout=20)
                if r.status_code != 200:
                    raise SystemExit("Login failed. Check FIREBASE_API_KEY, FIREBASE_EMAIL and "
                                     f"FIREBASE_PASSWORD in settings.py.\n{r.text[:300]}")
                self.token = r.json()["idToken"]
                self.token_time = time.time()
            p["auth"] = self.token
        return p

    def _url(self, path):
        path = path.strip("/")
        return f"{self.url}/{path}.json" if path else f"{self.url}/.json"

    @staticmethod
    def _check(r):
        if r.status_code == 401:
            raise SystemExit("Firebase answered 401 (permission denied): test mode has ended, or the login "
                             "settings in settings.py are wrong.")
        if r.status_code == 404:
            raise SystemExit("Firebase answered 404: FIREBASE_DB_URL in settings.py is wrong.")
        if r.status_code >= 300:
            raise SystemExit(f"Firebase error {r.status_code}: {r.text[:300]}")

    def get(self, path, **query):
        r = self.requests.get(self._url(path), params=self._params(query), timeout=30)
        self._check(r)
        return r.json()

    def put(self, path, value):
        r = self.requests.put(self._url(path), params=self._params({"print": "silent"}),
                              data=json.dumps(value), timeout=30)
        self._check(r)

    def patch(self, path, value):
        r = self.requests.patch(self._url(path), params=self._params({"print": "silent"}),
                                data=json.dumps(value), timeout=30)
        self._check(r)

    def bin_ids(self):
        ids = self.get("bins", shallow="true") or {}
        return sorted(ids.keys())

    def readings_since(self, bin_id, since_ms):
        data = self.get(f"bins/{bin_id}/readings", orderBy='"$key"', startAt=f'"{int(since_ms)}"') or {}
        rows = [v for v in data.values() if isinstance(v, dict)]
        return pd.DataFrame(rows)
