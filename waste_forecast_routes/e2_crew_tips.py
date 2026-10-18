"""
E2 - TIPS FOR THE COLLECTION CREWS (proposal objective 5)
=========================================================
Makes short tips for the next 7 days from:
  - the waste forecast of each area (step F3): busy days, how much above a normal day
  - the calendar: Poya days, Sinhala and Tamil New Year, Vesak, Christmas ...
  - planned events (events.csv), including road closures
  - the weather forecast (heavy rain)

The tips are made by RULES that are switched on by the ML forecast and the calendar (not by a
chatbot) - say it this way in the report: "forecast-triggered guidance".

It writes: guidance/<YYYY-MM-DD>/<area> = [tips]  and  guidance/_info   (the dashboard shows them)

Run:  python e2_crew_tips.py               (reads results/forecast_next7.csv from step F3)
      python e2_crew_tips.py --no-firebase (only print)
"""
import argparse
import os

import pandas as pd

import settings as S
from wastelib import RESULTS_DIR, Firebase, load_events, need_file

FESTIVAL_TIPS = {
    "vesak": "Vesak: dansal and lantern areas make a lot of waste. Put extra bins near dansal and collect "
             "them the same evening.",
    "avurudu": "Sinhala and Tamil New Year: shops and markets close. Collect market bins before the holiday "
               "and plan a catch-up round after it.",
    "poson": "Poson: dansal near temples and main roads. Check those bins in the evening.",
    "christmas": "Christmas: shopping areas are busy before the 25th. Extra pick-ups at markets and shops.",
}


def tips_for(row, holiday_kind, events_today):
    tips = []
    change = row["change_pct"]
    if change >= 8:  # clearly more than a normal day of the same weekday
        tips.append(f"Busy day: about {row['forecast_t']:.1f} t expected ({change:+.0f}% vs a normal "
                    f"{pd.Timestamp(row['date']).strftime('%A')})"
                    + (", one of the area's busiest days" if row["high_waste"] else "")
                    + ". Plan an extra trip or start 30 minutes earlier.")
    elif change <= -12:
        tips.append(f"Quiet day: about {row['forecast_t']:.1f} t ({change:+.0f}%). One truck may be enough.")
    if holiday_kind in FESTIVAL_TIPS:
        tips.append(FESTIVAL_TIPS[holiday_kind])
    elif holiday_kind == "poya":
        tips.append("Poya day: markets and shops are partly closed (fewer pick-ups there); temples are busier.")
    for e in events_today:
        t = f"Event: {e['name']} (+{e['extra_waste_pct']:.0f}% waste expected)."
        if e.get("road_closure"):
            t += (f" Road closed near ({e['lat']:.4f}, {e['lng']:.4f}) from {int(e['hour_from'])}:00 to "
                  f"{int(e['hour_to'])}:00 - the route planner avoids it; tell the drivers.")
        tips.append(t)
    if row.get("rain_mm", 0) >= 25:
        tips.append(f"Heavy rain expected ({row['rain_mm']:.0f} mm): wet waste is heavier - leave space in the "
                    "truck, and check drains near the bins.")
    return tips


def main():
    ap = argparse.ArgumentParser(description="Tips for the collection crews")
    ap.add_argument("--no-firebase", action="store_true", help="only print")
    args = ap.parse_args()
    path = os.path.join(RESULTS_DIR, "forecast_next7.csv")
    need_file(path, "Run first:  python f3_forecasts_to_firebase.py")
    print("E2 - tips for the collection crews")
    f = pd.read_csv(path, parse_dates=["date"])
    from wastelib import load_holidays
    hol = load_holidays().set_index("date")
    ev = load_events()
    update, n = {}, 0
    for (day, zone), row in f.set_index(["date", "zone"]).iterrows():
        kind = ""
        if day in hol.index:
            h = hol.loc[day]
            h = h.iloc[0] if isinstance(h, pd.DataFrame) else h
            kind = h["festival"] if h["festival"] in FESTIVAL_TIPS else ("poya" if h["kind"] == "poya" else "")
        events_today = ev[(ev["date"] == day) & (ev["zone"] == zone)].to_dict("records") if len(ev) else []
        r = row.to_dict()
        r["date"] = day
        tips = tips_for(r, kind, events_today)
        if tips:
            update[f"guidance/{day:%Y-%m-%d}/{zone}"] = tips
            n += len(tips)
            print(f"{day:%a %d %b} {zone}:")
            for t in tips:
                print(f"   - {t}")
    if not n:
        print("No special tips for the next 7 days (normal days everywhere).")
    if args.no_firebase:
        return
    fb = Firebase()
    days = sorted(f["date"].dt.strftime("%Y-%m-%d").unique())
    for d in days:  # areas without tips: remove old tips (None deletes in Firebase)
        for z in S.ZONES:
            update.setdefault(f"guidance/{d}/{z}", None)
    update["guidance/_info"] = {"made_at": {".sv": "timestamp"}, "first_day": days[0], "last_day": days[-1],
                                "how": "rules switched on by the waste forecast, the calendar and events"}
    fb.patch("", update)
    print(f"Written {n} tips to Firebase: guidance/<date>/<area>")


if __name__ == "__main__":
    main()
