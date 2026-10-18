"""
F3 - FORECASTS FOR THE NEXT 7 DAYS -> FIREBASE
==============================================
Uses the saved model (step F2) to forecast the waste of every area for the next 7 days and writes
them to Firebase, where the route planner (R3), the crew tips (E2) and the dashboard read them:

  forecasts/<area>/<YYYY-MM-DD>   forecast_t, normal_t, change_pct, high_waste, holiday, rain_mm ...
  forecasts/_info                 model, made_at, first and last day

Run it once a day (for example every evening). The weather forecast comes from Open-Meteo.

Your waste data must reach yesterday for real forecasts. With the SYNTHETIC data (it ends on
HISTORY_END in settings.py), this script makes synthetic days up to yesterday first, so the
demo shows the real coming week (with its real holidays). They are saved separately
(data/waste_recent_demo.csv) and never used for training or for the report.

Run:  python f3_forecasts_to_firebase.py               (needs FIREBASE_DB_URL in settings.py)
      python f3_forecasts_to_firebase.py --no-firebase (only print and save the CSV)
Makes: results/forecast_next7.csv (+ Firebase)
"""
import argparse
import os

import joblib
import numpy as np
import pandas as pd

import settings as S
from forecasting import forecast_ahead, load_everything
from wastelib import DATA_DIR, RESULTS_DIR, Firebase, calendar_table, download_weather, event_table, \
    ensure_dirs, load_events, load_holidays, need_file, synthetic_weather, today_local

DEMO_CSV = os.path.join(DATA_DIR, "waste_recent_demo.csv")


def recent_weather(rng, first_needed, last_needed):
    """Real recent weather + forecast if possible, else synthetic past days and normal weather ahead."""
    try:
        w = download_weather(None, None, forecast=True)
        w["source"] = "open-meteo forecast"
        msg = f"Weather: Open-Meteo, {w['date'].min():%d %b} to {w['date'].max():%d %b} (past days + forecast)"
    except Exception as e:
        w = synthetic_weather(first_needed, today_local() - pd.Timedelta(days=1), rng)  # no forecast: normal weather ahead
        w["source"] = "synthetic"
        msg = f"Weather: SYNTHETIC (no internet: {type(e).__name__}) - forecasts use normal weather"
    w.to_csv(os.path.join(DATA_DIR, "weather_recent.csv"), index=False)
    return msg


def make_demo_days(last_day, yesterday, rng):
    """Synthetic waste from the day after the data ends up to yesterday (demo only)."""
    from f1_make_data import make_synthetic_waste
    from wastelib import load_weather
    days = pd.date_range(last_day + pd.Timedelta(days=1), yesterday)
    cal = calendar_table(days[0], days[-1])
    events = event_table(days[0], days[-1])
    weather = load_weather().reset_index()
    weather = weather[weather["date"].isin(days)]
    if len(weather) < len(days):  # fill any missing day with synthetic weather
        extra = synthetic_weather(days[0], days[-1], rng)
        weather = pd.concat([weather, extra[~extra["date"].isin(weather["date"])]]).sort_values("date")
    df, _, _ = make_synthetic_waste(cal, weather, events, rng, trend_start=S.HISTORY_START, with_errors=False)
    df["source"] = "synthetic-demo"
    df.to_csv(DEMO_CSV, index=False)
    return len(days)


def main():
    ap = argparse.ArgumentParser(description="Forecasts for the next 7 days")
    ap.add_argument("--no-firebase", action="store_true", help="only print and save the CSV")
    args = ap.parse_args()
    ensure_dirs()
    need_file(os.path.join(RESULTS_DIR, "forecast_model.joblib"), "Run first:  python f2_train_forecast.py")
    print("F3 - forecasts for the next 7 days")
    pack = joblib.load(os.path.join(RESULTS_DIR, "forecast_model.joblib"))
    rng = np.random.default_rng(S.SEED + 1)
    waste = pd.read_csv(os.path.join(DATA_DIR, "waste_daily.csv"), parse_dates=["date"])
    last_day = waste["date"].max()
    yesterday = today_local() - pd.Timedelta(days=1)
    synthetic = (waste["source"] == "synthetic").all()
    print(recent_weather(rng, last_day, today_local() + pd.Timedelta(days=S.FORECAST_DAYS)))
    extra = None
    if last_day < yesterday:
        if synthetic:
            n = make_demo_days(last_day, yesterday, rng)
            extra = DEMO_CSV
            print(f"Waste data: synthetic, ends {last_day:%d %b %Y} -> made {n} synthetic DEMO days up to yesterday "
                  f"({yesterday:%d %b}) in {DEMO_CSV}")
        else:
            print(f"WARNING: your waste data ends on {last_day:%d %b %Y} ({(yesterday - last_day).days + 1} days ago). "
                  "Add the newest days to data/council_waste.csv and run f1_make_data.py again. "
                  "Forecasting from the last day you have.")
    elif os.path.exists(DEMO_CSV):
        os.remove(DEMO_CSV)

    data = load_everything(extra_csv=extra)
    origin = data["filled"].index.max()
    fut = forecast_ahead(pack["forecaster"], data, origin, S.FORECAST_DAYS)
    hol = load_holidays().set_index("date")["name"]
    ev = load_events()
    thr = pack["thresholds"]
    fut["change_pct"] = 100 * (fut["forecast_t"] / fut["normal_t"] - 1)
    fut["high_waste"] = [f >= thr.get(z, np.inf) for f, z in zip(fut["forecast_t"], fut["zone"])]
    fut["holiday"] = [hol.get(d, "") for d in fut["date"]]
    fut["event"] = [", ".join(ev[(ev["date"] == d) & (ev["zone"] == z)]["name"]) if len(ev) else ""
                    for d, z in zip(fut["date"], fut["zone"])]
    out = fut.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.round(3).to_csv(os.path.join(RESULTS_DIR, "forecast_next7.csv"), index=False)

    # print a small table: areas x days
    table = fut.pivot(index="zone", columns="date", values="forecast_t")
    print()
    print(f"Forecast (tonnes) with {pack['name']}, made from data up to {origin:%a %d %b %Y}:")
    print("   " + f"{'Area':<14}" + "".join(f"{d:%a %d}".rjust(9) for d in table.columns))
    for z, row in table.iterrows():
        flags = fut[fut.zone == z].set_index("date")["high_waste"]
        print("   " + f"{z:<14}" + "".join((f"{v:.1f}" + ("*" if flags[d] else " ")).rjust(9) for d, v in row.items()))
    print(f"   * = high-waste day (above the area's {S.HIGH_WASTE_PERCENTILE}th percentile)")
    for d in table.columns:
        if hol.get(d, ""):
            print(f"   {d:%a %d %b}: {hol.get(d)}")

    if args.no_firebase:
        print("Not written to Firebase (--no-firebase). Saved: results/forecast_next7.csv")
        return
    fb = Firebase()
    update = {}
    for r in fut.itertuples():
        update[f"forecasts/{r.zone}/{r.date:%Y-%m-%d}"] = {
            "forecast_t": round(float(r.forecast_t), 2), "normal_t": round(float(r.normal_t), 2),
            "change_pct": round(float(r.change_pct), 1), "high_waste": bool(r.high_waste),
            "holiday": r.holiday, "event": r.event, "rain_mm": round(float(r.rain_mm), 1),
            "synthetic": bool(synthetic)}
    update["forecasts/_info"] = {"model": pack["name"], "made_at": {".sv": "timestamp"},
                                 "data_until": f"{origin:%Y-%m-%d}", "first_day": f"{fut.date.min():%Y-%m-%d}",
                                 "last_day": f"{fut.date.max():%Y-%m-%d}", "synthetic": bool(synthetic)}
    fb.patch("", update)
    print(f"Written to Firebase: forecasts/<area>/<date> for {fut.zone.nunique()} areas x {S.FORECAST_DAYS} days")
    print("Done. Next: python r3_live_routes.py   (and e2_crew_tips.py)")


if __name__ == "__main__":
    main()
