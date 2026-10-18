"""
Shared code for the Component 3 scripts. You do not need to edit this file.

What is in here:
  - calendar_table():  holidays, Poya days, festivals and planned events for every day
  - load_weather():    daily rain and temperature
  - Firebase:          read and write the Firebase Realtime Database (same as Part B)
  - distance_km():     straight-line distance between two GPS points
"""
import json
import math
import os
import time

import numpy as np
import pandas as pd

import settings as S

TZ = "Asia/Colombo"
DATA_DIR = "data"
RESULTS_DIR = "results"
HERE = os.path.dirname(os.path.abspath(__file__))
HOLIDAYS_CSV = os.path.join(HERE, "holidays_lk.csv")
EVENTS_CSV = os.path.join(HERE, "events.csv")
FESTIVALS = ["avurudu", "vesak", "poson", "christmas", "other_festival"]


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)


def need_file(path, how_to_make):
    if not os.path.exists(path):
        raise SystemExit(f"Missing file: {path}\n{how_to_make}")


def zone_names():
    return list(S.ZONES.keys())


def today_local():
    return pd.Timestamp.now(tz=TZ).tz_localize(None).normalize()


# ---------------------------------------------------------------------------
# Calendar: holidays, Poya days, festivals, planned events
# ---------------------------------------------------------------------------
def load_holidays():
    h = pd.read_csv(HOLIDAYS_CSV, parse_dates=["date"])
    h["festival"] = h["festival"].fillna("")
    return h


def load_events():
    """events.csv -> one row per event per day (date, zone, extra_waste_pct, road_closure, ...)."""
    if not os.path.exists(EVENTS_CSV):
        return pd.DataFrame(columns=["date", "zone", "name", "extra_waste_pct", "road_closure"])
    e = pd.read_csv(EVENTS_CSV, parse_dates=["date_from", "date_to"])
    rows = []
    for _, r in e.iterrows():
        for d in pd.date_range(r["date_from"], r["date_to"], freq="D"):
            rows.append({"date": d, "zone": r["zone"], "name": r["name"],
                         "extra_waste_pct": float(r["extra_waste_pct"] or 0),
                         "road_closure": str(r.get("road_closure", "no")).strip().lower() == "yes",
                         "lat": r.get("lat"), "lng": r.get("lng"), "radius_m": r.get("radius_m"),
                         "hour_from": r.get("hour_from"), "hour_to": r.get("hour_to")})
    return pd.DataFrame(rows)


def calendar_table(start, end):
    """One row per day with everything we know about that day IN ADVANCE (no future waste data).

    Columns: day_of_week, is_weekend, month, doy_sin, doy_cos, is_poya, is_public_holiday, is_holiday,
    the festival flags, festival "windows" (days before and after), and days to / since a holiday.
    """
    days = pd.date_range(pd.Timestamp(start) - pd.Timedelta(days=30), pd.Timestamp(end) + pd.Timedelta(days=30))
    h = load_holidays()
    cal = pd.DataFrame(index=days)
    cal.index.name = "date"
    cal["day_of_week"] = days.dayofweek
    cal["is_weekend"] = (days.dayofweek >= 5).astype(int)
    cal["month"] = days.month
    doy = days.dayofyear.to_numpy()
    cal["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    cal["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    poya = set(h.loc[h["kind"] == "poya", "date"])
    public = set(h.loc[h["kind"] == "public", "date"])
    cal["is_poya"] = [int(d in poya) for d in days]
    cal["is_public_holiday"] = [int(d in public) for d in days]
    cal["is_holiday"] = ((cal["is_poya"] + cal["is_public_holiday"]) > 0).astype(int)
    for f in FESTIVALS:
        cal[f"fest_{f}"] = 0
    for _, r in h.iterrows():
        if r["date"] in cal.index and r["festival"]:
            name = r["festival"] if r["festival"] in FESTIVALS else "other_festival"
            cal.loc[r["date"], f"fest_{name}"] = 1

    # festival windows: shopping before Avurudu and Christmas, catching up after
    new_year = h.loc[h["name"].str.contains("New Year Day", case=False), "date"]
    cal["avurudu_before"] = 0
    cal["avurudu_after"] = 0
    for d in new_year:
        cal.loc[(cal.index >= d - pd.Timedelta(days=10)) & (cal.index < d - pd.Timedelta(days=1)), "avurudu_before"] = 1
        cal.loc[(cal.index > d) & (cal.index <= d + pd.Timedelta(days=3)) & (cal["fest_avurudu"] == 0),
                "avurudu_after"] = 1
    md = cal.index.month * 100 + cal.index.day
    cal["christmas_season"] = ((md >= 1218) & (md <= 1224)).astype(int)
    cal["year_end"] = ((md >= 1231) | (md <= 101)).astype(int)
    vesak = h.loc[h["festival"] == "vesak", "date"]
    cal["vesak_after"] = 0
    for d in vesak:
        nxt = d + pd.Timedelta(days=1)
        if nxt in cal.index and cal.loc[nxt, "fest_vesak"] == 0:
            cal.loc[nxt, "vesak_after"] = 1

    hol = cal["is_holiday"].to_numpy()
    n = len(cal)
    to_next = np.full(n, 14)
    since_last = np.full(n, 14)
    last = -999
    for i in range(n):
        if hol[i]:
            last = i
        since_last[i] = min(14, i - last)
    nxt = 999
    for i in range(n - 1, -1, -1):
        if hol[i]:
            nxt = i
        to_next[i] = min(14, nxt - i)
    cal["days_to_holiday"] = to_next
    cal["days_since_holiday"] = since_last
    cal["day_before_holiday"] = (cal["days_to_holiday"] == 1).astype(int)
    cal["day_after_holiday"] = (cal["days_since_holiday"] == 1).astype(int)
    return cal.loc[pd.Timestamp(start):pd.Timestamp(end)]


def event_table(start, end):
    """Planned events: extra waste (%) per zone per day, and road closures."""
    days = pd.date_range(start, end)
    out = pd.DataFrame(0.0, index=days, columns=zone_names())
    ev = load_events()
    for _, r in ev.iterrows():
        if r["date"] in out.index and r["zone"] in out.columns:
            out.loc[r["date"], r["zone"]] += r["extra_waste_pct"]
    out.index.name = "date"
    return out


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
def load_weather():
    """data/weather.csv (+ data/weather_recent.csv from step F3: the last days and the forecast)."""
    path = os.path.join(DATA_DIR, "weather.csv")
    need_file(path, "Run first:  python f1_make_data.py")
    w = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    recent = os.path.join(DATA_DIR, "weather_recent.csv")
    if os.path.exists(recent):
        r = pd.read_csv(recent, parse_dates=["date"]).set_index("date").sort_index()
        r = r[r.index > w.index.max()]  # only the days after weather.csv (history never changes)
        w = pd.concat([w[["rain_mm", "temp_c"]], r[["rain_mm", "temp_c"]]]).sort_index()
    return w


def download_weather(start, end, forecast=False):
    """Daily rain (mm) and mean temperature (C) for the council area from Open-Meteo (free, no key).

    forecast=False: past weather (archive). forecast=True: the last 31 days and the next 16 days.
    Returns a DataFrame (date, rain_mm, temp_c) or raises an error if there is no internet.
    """
    import requests
    lat = float(np.mean([z[0] for z in S.ZONES.values()]))
    lng = float(np.mean([z[1] for z in S.ZONES.values()]))
    params = {"latitude": round(lat, 4), "longitude": round(lng, 4), "timezone": TZ,
              "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min"}
    if forecast:
        url = "https://api.open-meteo.com/v1/forecast"
        params["forecast_days"] = 16
        params["past_days"] = 31
    else:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params["start_date"] = pd.Timestamp(start).strftime("%Y-%m-%d")
        params["end_date"] = pd.Timestamp(end).strftime("%Y-%m-%d")
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    d = r.json()["daily"]
    w = pd.DataFrame({"date": pd.to_datetime(d["time"]),
                      "rain_mm": pd.to_numeric(pd.Series(d["precipitation_sum"]), errors="coerce"),
                      "temp_c": (pd.to_numeric(pd.Series(d["temperature_2m_max"]), errors="coerce")
                                 + pd.to_numeric(pd.Series(d["temperature_2m_min"]), errors="coerce")) / 2})
    return w.dropna(subset=["rain_mm"]).reset_index(drop=True)


# Approximate Colombo climate (monthly rain in mm, rainy days, mean temperature). Used only when
# real weather cannot be downloaded.
CLIMATE = {1: (62, 7, 26.9), 2: (63, 6, 27.3), 3: (131, 10, 28.0), 4: (254, 16, 28.4), 5: (392, 19, 28.3),
           6: (184, 18, 27.8), 7: (125, 13, 27.6), 8: (115, 12, 27.6), 9: (236, 15, 27.5), 10: (365, 19, 27.0),
           11: (310, 16, 26.9), 12: (146, 11, 26.8)}


def synthetic_weather(start, end, rng):
    days = pd.date_range(start, end)
    rain, temp = [], []
    for d in days:
        total, wet_days, t = CLIMATE[d.month]
        p = wet_days / d.days_in_month
        amount = rng.gamma(0.8, (total / wet_days) / 0.8) if rng.random() < p else 0.0
        rain.append(round(float(amount), 1))
        temp.append(round(float(t + rng.normal(0, 0.7) - 0.03 * min(amount, 40)), 1))
    return pd.DataFrame({"date": days, "rain_mm": rain, "temp_c": temp})


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def distance_km(lat1, lng1, lat2, lng2):
    """Straight-line distance on the earth (haversine formula)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def shift_start_hour():
    h, m = S.SHIFT_START.split(":")
    return int(h) + int(m) / 60.0


# ---------------------------------------------------------------------------
# Firebase Realtime Database (REST API) - the same code as Part B
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

    def post(self, path, value):
        r = self.requests.post(self._url(path), params=self._params(), data=json.dumps(value), timeout=30)
        self._check(r)
        return r.json().get("name")

    def delete(self, path):
        r = self.requests.delete(self._url(path), params=self._params(), timeout=30)
        self._check(r)
