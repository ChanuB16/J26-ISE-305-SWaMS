"""
F1 - MAKE THE WASTE DATA (2 years, 6 areas, one row per area per day)
======================================================================
What it makes:
  data/weather.csv      daily rain and temperature (REAL from Open-Meteo if there is internet,
                        otherwise synthetic weather based on the Colombo climate)
  data/calendar.csv     holidays, Poya days, festivals and festival "windows" for every day
  data/waste_daily.csv  tonnes of waste per area per day
  data/zones.csv        the 6 areas (centre, people, share of shops and markets)

Waste data: if you got real records from the council, save them as data/council_waste.csv with
the columns  date, zone, waste_t  (one row per area per day, tonnes) and this script uses them.
Otherwise it makes 2 years of SYNTHETIC data (say this clearly to the examiners), built from:
  - 71 tonnes per day for the whole council (UTS fact sheet, 2018), split by the people per area
  - homes make more waste at weekends, shops and markets less on Sundays and Poya days
  - festivals: shopping before Sinhala and Tamil New Year and Christmas, dansal waste at Vesak,
    shops closed on New Year days, events from events.csv (EXAMPLES - replace with real ones)
  - rain makes the waste heavier (wet food waste, up to +6%), slow growth of 2% per year
  - random day-to-day changes, a few missing days and a few wrong records (to practise cleaning)

Run:  python f1_make_data.py
"""
import os

import numpy as np
import pandas as pd

import settings as S
from wastelib import DATA_DIR, calendar_table, download_weather, ensure_dirs, event_table, \
    synthetic_weather, zone_names

# Share of the waste that comes from shops, markets and offices (the rest is from homes). Our estimate.
COMMERCIAL_SHARE = {"Malabe": 0.35, "Kaduwela": 0.30, "Battaramulla": 0.40, "Athurugiriya": 0.25,
                    "Thalangama": 0.20, "Hokandara": 0.20}
WEEK_HOMES = [0.96, 0.95, 0.96, 0.97, 1.00, 1.07, 1.10]   # Monday ... Sunday
WEEK_SHOPS = [1.05, 1.04, 1.04, 1.04, 1.08, 1.00, 0.70]
# (homes, shops) multipliers on special days
SPECIAL = {
    "is_poya": (1.05, 0.70), "is_public_holiday": (1.06, 0.78),
    "fest_avurudu": (1.25, 0.45), "avurudu_before": (1.08, 1.18), "avurudu_after": (1.12, 0.95),
    "fest_vesak": (1.20, 1.30), "fest_poson": (1.08, 1.12), "fest_christmas": (1.15, 0.60),
    "christmas_season": (1.04, 1.12), "year_end": (1.08, 0.85), "fest_other_festival": (1.06, 0.95),
    "day_after_holiday": (1.00, 1.06),
}


def get_weather(rng):
    """Real weather if possible (Open-Meteo), otherwise synthetic. Returns (table, source)."""
    path = os.path.join(DATA_DIR, "weather.csv")
    start = pd.Timestamp(S.HISTORY_START) - pd.Timedelta(days=60)
    end = pd.Timestamp(S.HISTORY_END)
    if os.path.exists(path):
        old = pd.read_csv(path, parse_dates=["date"])
        covers = old["date"].min() <= start and old["date"].max() >= end
        if covers and (old.get("source", pd.Series(["real"])) == "real").all():
            return old, "real (already downloaded)"
    try:
        w = download_weather(start, end)
        w["source"] = "real"
        if w["date"].min() > start or w["date"].max() < end:
            raise ValueError("the download does not cover all days")
        return w, "real (downloaded from Open-Meteo)"
    except Exception as e:  # no internet, site blocked...
        w = synthetic_weather(start, end, rng)
        w["source"] = "synthetic"
        return w, f"SYNTHETIC (could not download real weather: {type(e).__name__})"


def make_synthetic_waste(cal, weather, events, rng, trend_start=None, with_errors=True):
    zones = zone_names()
    people = np.array([S.ZONES[z][2] for z in zones], dtype=float)
    shops = np.array([COMMERCIAL_SHARE.get(z, 0.25) for z in zones])
    weight = people * (1 + 0.5 * shops)
    base = S.TONNES_PER_DAY * weight / weight.sum()  # tonnes per day per area on an average day

    days = cal.index
    start = pd.Timestamp(trend_start) if trend_start is not None else days[0]
    w = weather.set_index("date").reindex(days)
    rain = w["rain_mm"].fillna(0).to_numpy()
    city_noise = rng.lognormal(0, 0.02, len(days))
    rows = []
    for k, z in enumerate(zones):
        c = shops[k]
        noise = rng.lognormal(0, 0.03, len(days))
        for i, d in enumerate(days):
            row = cal.iloc[i]
            homes = WEEK_HOMES[d.dayofweek]
            shop = WEEK_SHOPS[d.dayofweek]
            for col, (mh, ms) in SPECIAL.items():
                if row[col]:
                    homes *= mh
                    shop *= ms
            mix = (1 - c) * homes + c * shop
            trend = 1.02 ** ((d - start).days / 365.25)
            wet = 1 + 0.002 * min(rain[i], 30.0)
            event = 1 + events.loc[d, z] / 100.0
            tonnes = base[k] * trend * mix * wet * event * noise[i] * city_noise[i]
            tonnes *= rng.normal(1, 0.01)  # weighing error
            rows.append({"date": d, "zone": z, "waste_t": round(float(tonnes), 2)})
    df = pd.DataFrame(rows)
    if not with_errors:
        df["source"] = "synthetic"
        return df, base, shops
    # data problems, like real records: missing days and a few wrong numbers
    n = len(df)
    missing = rng.random(n) < 0.005
    wrong = (rng.random(n) < 0.002) & ~missing
    df.loc[missing, "waste_t"] = np.nan
    df.loc[wrong, "waste_t"] = (df.loc[wrong, "waste_t"] * rng.choice([1.9, 0.3], wrong.sum())).round(2)
    df["source"] = "synthetic"
    return df, base, shops


def read_real_waste(path):
    real = pd.read_csv(path)
    need = {"date", "zone", "waste_t"}
    if not need.issubset(real.columns):
        raise SystemExit(f"{path} must have the columns: date, zone, waste_t (tonnes). Found: {list(real.columns)}")
    real["date"] = pd.to_datetime(real["date"])
    unknown = sorted(set(real["zone"]) - set(zone_names()))
    if unknown:
        raise SystemExit(f"These areas in {path} are not in settings.py ZONES: {unknown}\n"
                         "Add them to ZONES (centre point and people) or rename them.")
    real = real.groupby(["date", "zone"], as_index=False)["waste_t"].sum(min_count=1)
    days = pd.date_range(real["date"].min(), real["date"].max())
    full = pd.MultiIndex.from_product([days, zone_names()], names=["date", "zone"])
    real = real.set_index(["date", "zone"]).reindex(full).reset_index()
    real["source"] = "real"
    return real


def main():
    ensure_dirs()
    rng = np.random.default_rng(S.SEED)
    print("F1 - make the waste data")

    weather, wsource = get_weather(rng)
    weather.to_csv(os.path.join(DATA_DIR, "weather.csv"), index=False)
    print(f"Weather: {wsource} -> data/weather.csv ({len(weather)} days)")

    cal_end = pd.Timestamp(S.HISTORY_END) + pd.Timedelta(days=400)  # also the coming year (for forecasts)
    cal = calendar_table(pd.Timestamp(S.HISTORY_START) - pd.Timedelta(days=60), cal_end)
    cal.to_csv(os.path.join(DATA_DIR, "calendar.csv"))
    print(f"Calendar: holidays, Poya days, festivals -> data/calendar.csv "
          f"({int(cal['is_holiday'].sum())} holidays from {cal.index[0]:%Y-%m-%d} to {cal.index[-1]:%Y-%m-%d})")

    hist = cal.loc[S.HISTORY_START:S.HISTORY_END]
    events = event_table(hist.index[0], hist.index[-1])
    real_path = os.path.join(DATA_DIR, "council_waste.csv")
    zones = zone_names()
    if os.path.exists(real_path):
        waste = read_real_waste(real_path)
        base = waste.groupby("zone")["waste_t"].mean().reindex(zones).to_numpy()
        shops = np.array([COMMERCIAL_SHARE.get(z, 0.25) for z in zones])
        print(f"Waste: REAL council data from {real_path}")
    else:
        waste, base, shops = make_synthetic_waste(hist, weather, events, rng)
        print("Waste: SYNTHETIC (no data/council_waste.csv found) - say this clearly in the report")
    waste.to_csv(os.path.join(DATA_DIR, "waste_daily.csv"), index=False)

    zt = pd.DataFrame({"zone": zones, "lat": [S.ZONES[z][0] for z in zones], "lng": [S.ZONES[z][1] for z in zones],
                       "people": [S.ZONES[z][2] for z in zones], "shops_share": shops,
                       "average_t": np.round(base, 2)})
    zt.to_csv(os.path.join(DATA_DIR, "zones.csv"), index=False)

    total = waste.groupby("date")["waste_t"].sum(min_count=1)
    per_zone = waste.pivot(index="date", columns="zone", values="waste_t")
    top = waste.dropna().sort_values("waste_t", ascending=False).iloc[0]
    print(f"  {len(zones)} areas x {per_zone.shape[0]} days ({per_zone.index[0]:%Y-%m-%d} to "
          f"{per_zone.index[-1]:%Y-%m-%d}) -> data/waste_daily.csv ({len(waste):,} rows)")
    print(f"  whole council: {total.mean():.1f} t per day on average "
          f"(lowest {total.min():.1f} t, highest {total.max():.1f} t)")
    print(f"  biggest single area-day: {top['zone']} {top['date']:%a %d %b %Y}, {top['waste_t']:.1f} t")
    print(f"  missing days: {int(waste['waste_t'].isna().sum())} (F2 fills them in)")
    print("Done. Next: python f2_train_forecast.py")


if __name__ == "__main__":
    main()
