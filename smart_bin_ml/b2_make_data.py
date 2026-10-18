"""
B2 - MAKE THE TRAINING DATA
===========================
One real bin cannot give months of data in a few days, so this script makes 60 days of realistic
SYNTHETIC data for 20 bins in the Kaduwela area (as the students' project guide asks). Say this
clearly to the examiners: the model is trained on synthetic data, and the real bin is used to set
the sensor noise and for the live demo.

What it simulates for every bin, every 15 minutes:
  - waste arriving in small "bags", more at busy hours (market mornings, home evenings...)
  - weekdays vs weekends (schools and offices are quiet on weekends)
  - emptying by the council every 1, 2 or 3 days, sometimes missed (the truck did not come)
  - overflow when the bin is full and waste keeps coming
  - weight, temperature, humidity and gas (smell grows with time since emptying and with
    the share of food waste)
  - sensor noise, a few wrong readings and a few lost readings

Optional: put your Firebase export (smart-bin-export.json) in the data folder first. Then this
script also saves your real bin data and uses its real sensor noise.

Run:  python b2_make_data.py
Makes: data/readings.csv, data/collections.csv, data/bins.csv
       (and data/real_readings.csv, data/real_collections.csv if the export is there)
"""
import os

import numpy as np
import pandas as pd

import settings as S
from binlib import CAPACITY_L, DATA_DIR, TZ, ensure_dirs, read_export

# Area centres in the Kaduwela Municipal Council area (approximate)
ZONES = {
    "Malabe": (6.9061, 79.9696), "Kaduwela": (6.9358, 79.9840), "Battaramulla": (6.9000, 79.9180),
    "Athurugiriya": (6.8731, 79.9970), "Thalangama": (6.9150, 79.9330), "Hokandara": (6.8890, 79.9690),
}
BIN_PLAN = [
    ("Malabe", "market"), ("Malabe", "bus_stop"), ("Malabe", "residential"), ("Malabe", "school"),
    ("Malabe", "office"), ("Kaduwela", "market"), ("Kaduwela", "bus_stop"), ("Kaduwela", "residential"),
    ("Kaduwela", "temple"), ("Battaramulla", "office"), ("Battaramulla", "residential"),
    ("Battaramulla", "market"), ("Battaramulla", "school"), ("Athurugiriya", "residential"),
    ("Athurugiriya", "bus_stop"), ("Athurugiriya", "temple"), ("Thalangama", "residential"),
    ("Thalangama", "school"), ("Hokandara", "residential"), ("Hokandara", "market"),
]
# rate = average fill % per hour over a whole day; organic = share of food waste;
# density = kg per litre; every = days between emptyings
TYPES = {
    "market":      dict(rate=2.2, organic=0.90, density=0.15, every=1),
    "bus_stop":    dict(rate=1.9, organic=0.40, density=0.08, every=1),
    "residential": dict(rate=1.35, organic=0.70, density=0.14, every=2),
    "school":      dict(rate=1.5, organic=0.35, density=0.09, every=2),
    "office":      dict(rate=1.0, organic=0.20, density=0.07, every=3),
    "temple":      dict(rate=1.1, organic=0.60, density=0.10, every=2),
}
DAY_FACTOR = RAIN = TEMP_OFFSET = None  # set in main(): busy/quiet days, rainy days, warm days

WEEK = {  # Monday ... Sunday
    "market": [1, 1, 1, 1, 1, 1.3, 1.25], "bus_stop": [1, 1, 1, 1, 1, 0.8, 0.7],
    "residential": [1, 1, 1, 1, 1, 1.15, 1.25], "school": [1, 1, 1, 1, 1, 0.1, 0.1],
    "office": [1, 1, 1, 1, 1, 0.25, 0.15], "temple": [1, 1, 1, 1, 1, 1.2, 1.4],
}


def hour_profile(kind):
    """How busy each hour of the day is (average 1.0)."""
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


def real_noise(real):
    """Sensor noise (%) of the real bin: typical jump between neighbouring fill readings."""
    noise = []
    for _, part in real.groupby("bin_id"):
        f = pd.to_numeric(part.sort_values("ts")["fill_pct"], errors="coerce").dropna()
        d = f.diff().abs().dropna()
        d = d[d < 10]  # ignore real changes (waste added, emptied)
        if len(d) >= 30:
            noise.append(1.4826 * float(d.median()) / np.sqrt(2))
    return float(np.clip(np.median(noise), 0.3, 3.0)) if noise else None


def simulate_bin(number, zone, kind, rng, days, noise_sd):
    t_cfg = TYPES[kind]
    prof = hour_profile(kind)
    week = WEEK[kind]
    bin_id = f"sim_{number:02d}"
    lat0, lng0 = ZONES[zone]
    info = dict(bin_id=bin_id, name=f"{zone} {kind.replace('_', ' ')}", zone=zone, type=kind,
                lat=round(lat0 + rng.normal(0, 0.006), 6), lng=round(lng0 + rng.normal(0, 0.006), 6),
                capacity_l=CAPACITY_L, organic_share=t_cfg["organic"], emptied_every_days=t_cfg["every"])

    start = pd.Timestamp(S.START_DATE, tz=TZ)
    steps = days * 24 * 4
    times = start + pd.to_timedelta(np.arange(1, steps + 1) * 15, unit="min")
    bin_factor = rng.lognormal(0, 0.2)
    base_density = t_cfg["density"] * rng.uniform(0.85, 1.15)
    organic = t_cfg["organic"]

    fill = rng.uniform(0, 4)
    density = base_density * rng.uniform(0.9, 1.1)
    last_emptied = start
    next_due = start + pd.Timedelta(days=t_cfg["every"]) + pd.Timedelta(hours=rng.uniform(6, 11))
    full_steps = 0
    rows, emptyings = [], []

    def empty_bin(when, kind_of_emptying):
        nonlocal fill, density, last_emptied, full_steps
        before = fill
        fill = rng.uniform(0, 4)
        emptyings.append(dict(bin_id=bin_id, ts=int(when.value // 1_000_000),
                              fill_before_pct=round(before, 1), fill_after_pct=round(fill, 1),
                              weight_before_kg=round(before / 100 * CAPACITY_L * density, 2),
                              weight_after_kg=round(fill / 100 * CAPACITY_L * density, 2),
                              type=kind_of_emptying))
        density = base_density * rng.uniform(0.9, 1.1)
        last_emptied = when
        full_steps = 0

    for k, t in enumerate(times):
        h = t.hour + t.minute / 60.0
        d = (t - start).days
        # 1. emptying by the council (sometimes missed), or an extra trip after complaints
        if t >= next_due:
            if rng.random() < 0.12:
                next_due = next_due + pd.Timedelta(days=1)  # truck did not come; try tomorrow
            else:
                empty_bin(next_due, "scheduled")
                next_due = next_due.normalize() + pd.Timedelta(days=t_cfg["every"]) \
                    + pd.Timedelta(hours=rng.uniform(6, 11))
        elif full_steps >= 8 and 7 <= h < 18 and rng.random() < 0.15:
            empty_bin(t - pd.Timedelta(minutes=7), "extra")
        # 2. waste arriving in bags (about 2% of the bin each)
        expected = t_cfg["rate"] * bin_factor * prof[int(h)] * week[t.dayofweek] * DAY_FACTOR[number][d] * 0.25
        bags = rng.poisson(expected / 2.0)
        if bags:
            fill += float(rng.gamma(4.0, 0.5, size=bags).sum())
        fill = min(fill, 100.0)  # more waste than this overflows onto the ground
        full_steps = full_steps + 1 if fill >= 95 else 0
        # 3. what the sensors would measure
        hs = (t - last_emptied).total_seconds() / 3600.0
        temp = (27.5 + 3.5 * np.sin(2 * np.pi * (h - 9) / 24) + TEMP_OFFSET[d]
                + 1.5 * organic * min(1.0, hs / 48) + rng.normal(0, 0.3))
        hum_air = 78 - 10 * np.sin(2 * np.pi * (h - 9) / 24) + 8 * RAIN[d] + rng.normal(0, 1.5)
        hum = min(99.0, hum_air + 10 * organic * min(1.0, hs / 36) * (fill / 100 + 0.3))
        gas = (4 + abs(rng.normal(0, 3))
               + 100 * organic * (1 - np.exp(-hs / 30)) * (0.5 + 0.5 * fill / 100) * (1 + 0.04 * (temp - 28))
               + rng.normal(0, 3))
        weight = max(0.0, fill / 100 * CAPACITY_L * density + rng.normal(0, 0.03))
        fill_read = fill + rng.normal(0, noise_sd)
        if rng.random() < 0.003:
            fill_read += rng.uniform(20, 60)  # something in front of the sensor for one reading
        row = dict(bin_id=bin_id, ts=int(t.value // 1_000_000), time_local=t.strftime("%Y-%m-%d %H:%M:%S"),
                   fill_pct=round(float(np.clip(fill_read, 0, 100)), 1), weight_kg=round(weight, 2),
                   gas_index=round(float(np.clip(gas, 0, 100)), 1), humidity_pct=round(float(hum), 1),
                   temp_c=round(float(temp), 1), source="synthetic")
        if rng.random() < 0.01:
            row["fill_pct"] = np.nan  # no echo
        if rng.random() < 0.005:
            row["gas_index"] = np.nan
        if rng.random() < 0.02:
            continue  # reading lost on the way
        rows.append(row)
    return info, rows, emptyings


def main():
    ensure_dirs()
    print("B2 - make the training data")
    rng = np.random.default_rng(S.SEED)

    export = os.path.join(DATA_DIR, "smart-bin-export.json")
    noise_sd = 1.0
    if os.path.exists(export):
        real, real_col = read_export(export)
        real.to_csv(os.path.join(DATA_DIR, "real_readings.csv"), index=False)
        real_col.to_csv(os.path.join(DATA_DIR, "real_collections.csv"), index=False)
        n = real_noise(real)
        if n is not None:
            noise_sd = n
        print(f"Real bin export: {len(real)} readings, {len(real_col)} emptyings "
              f"-> data/real_readings.csv, data/real_collections.csv")
        print(f"Sensor noise from your real bin: {noise_sd:.2f} %"
              + ("" if n is not None else " (not enough steady readings, using the default)"))
    else:
        print(f"Real bin export: not found (optional: {export}) -> sensor noise {noise_sd:.1f} %")

    global DAY_FACTOR, RAIN, TEMP_OFFSET
    days = S.N_DAYS
    RAIN = rng.random(days + 1) < 0.4
    TEMP_OFFSET = rng.normal(0, 0.8, days + 1)
    DAY_FACTOR = {i + 1: rng.lognormal(0, 0.2, days + 1) for i in range(len(BIN_PLAN))}

    infos, all_rows, all_empty = [], [], []
    for i, (zone, kind) in enumerate(BIN_PLAN, start=1):
        info, rows, emptyings = simulate_bin(i, zone, kind, rng, days, noise_sd)
        infos.append(info)
        all_rows += rows
        all_empty += emptyings

    readings = pd.DataFrame(all_rows)
    collections = pd.DataFrame(all_empty)
    bins = pd.DataFrame(infos)
    readings.to_csv(os.path.join(DATA_DIR, "readings.csv"), index=False)
    collections.to_csv(os.path.join(DATA_DIR, "collections.csv"), index=False)
    bins.to_csv(os.path.join(DATA_DIR, "bins.csv"), index=False)

    end = pd.Timestamp(S.START_DATE) + pd.Timedelta(days=days - 1)
    full = (readings["fill_pct"] >= 99).mean() * 100
    missed = 100 * (1 - len(readings) / (len(BIN_PLAN) * days * 96))
    print(f"Made {len(BIN_PLAN)} synthetic bins x {days} days ({S.START_DATE} to {end:%Y-%m-%d}), "
          f"one reading every 15 minutes")
    print(f"  readings:    {len(readings):>7,} rows -> data/readings.csv")
    print(f"  emptyings:   {len(collections):>7,} rows -> data/collections.csv "
          f"({(collections['type'] == 'extra').sum()} extra trips after overflow)")
    print(f"  bins:        {len(bins):>7} rows -> data/bins.csv")
    print(f"Readings lost on the way: {missed:.1f} %   Bin full (99%+): {full:.1f} % of readings")
    print("Done. Next: python b3_train_models.py")


if __name__ == "__main__":
    main()
