"""
Forecasting code shared by f2, f3 and r2. You do not need to edit this file.

  - load_series():     waste per area per day, cleaned (wrong records removed, gaps filled)
  - build_features():  the model inputs for every area and day (only data known the day before)
  - models:            moving average, same day last week, Linear Regression, XGBoost, LSTM
  - forecast_ahead():  forecasts for the next 1 to 7 days (feeds each forecast back in)

The LSTM is trained with PyTorch when it is installed. If PyTorch is not installed (or fails), the
same LSTM design is trained with NumPy instead, so the step always finishes. Either way the trained
weights are stored as NumPy arrays, so steps F3, R2 and R3 do not need PyTorch.
"""
import copy
import os
import time
import warnings

import numpy as np
import pandas as pd

import settings as S
from wastelib import DATA_DIR, calendar_table, event_table, load_weather, need_file, zone_names

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Inputs (features) and the 4 feature sets for the "which inputs help" test
# ---------------------------------------------------------------------------
DOW_COLS = [f"dow_{i}" for i in range(7)]
HIST_COLS = ["lag1_rel", "lag2_rel", "lag3_rel", "lag7_rel", "lag14_rel", "roll7_rel", "roll7_std_rel",
             "same_dow_rel"]
SEASON_COLS = DOW_COLS + ["is_weekend", "doy_sin", "doy_cos"]
CAL_COLS = ["is_poya", "is_public_holiday", "is_holiday", "fest_avurudu", "fest_vesak", "fest_poson",
            "fest_christmas", "fest_other_festival", "avurudu_before", "avurudu_after", "christmas_season",
            "year_end", "day_before_holiday", "day_after_holiday", "days_to_holiday", "days_since_holiday",
            "event_extra_pct"]
WEATHER_COLS = ["rain_mm", "rain_prev_mm", "temp_c"]
AREA_COLS = ["people_k", "shops_share"]
FEATURE_SETS = {"A": HIST_COLS + SEASON_COLS}
FEATURE_SETS["B"] = FEATURE_SETS["A"] + CAL_COLS
FEATURE_SETS["C"] = FEATURE_SETS["B"] + WEATHER_COLS
FEATURE_SETS["D"] = FEATURE_SETS["C"] + AREA_COLS
FEATURE_SET_NAMES = {"A": "A  past waste + day of week", "B": "B  + holidays, festivals, events",
                     "C": "C  + weather", "D": "D  + area facts (people, shops)"}
FEATURES = FEATURE_SETS["D"]
NICE = {"lag1_rel": "Waste yesterday", "lag2_rel": "Waste 2 days ago", "lag3_rel": "Waste 3 days ago",
        "lag7_rel": "Waste same day last week", "lag14_rel": "Waste 2 weeks ago", "roll7_rel": "Average, last 7 days",
        "roll7_std_rel": "Ups and downs, last 7 days", "same_dow_rel": "Average of the same weekday",
        "is_weekend": "Weekend", "doy_sin": "Time of year (sin)", "doy_cos": "Time of year (cos)",
        "is_poya": "Poya day", "is_public_holiday": "Public holiday", "is_holiday": "Any holiday",
        "fest_avurudu": "New Year days", "fest_vesak": "Vesak", "fest_poson": "Poson", "fest_christmas": "Christmas",
        "fest_other_festival": "Other festival", "avurudu_before": "Days before New Year",
        "avurudu_after": "Days after New Year", "christmas_season": "Christmas shopping week",
        "year_end": "31 Dec / 1 Jan", "day_before_holiday": "Day before a holiday",
        "day_after_holiday": "Day after a holiday", "days_to_holiday": "Days to next holiday",
        "days_since_holiday": "Days since last holiday", "event_extra_pct": "Planned event",
        "rain_mm": "Rain (that day)", "rain_prev_mm": "Rain (day before)", "temp_c": "Temperature",
        "people_k": "People in the area", "shops_share": "Share of shops"}
NICE.update({f"dow_{i}": f"Day of week = {d}" for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])})

LEVEL_DAYS = 28  # "normal level" = average of the last 28 days


# ---------------------------------------------------------------------------
# Data: cleaning and features
# ---------------------------------------------------------------------------
def load_series(until=None, extra_csv=None):
    """data/waste_daily.csv -> (raw, clean, filled) tables: one column per area, one row per day.
    until: ignore days after this date. extra_csv: more days to add (F3 demo days).

    clean  = raw with wrong records removed (more than 65% above or 45% below the local median)
    filled = clean with the gaps filled in (used only to make inputs, never as an answer to learn)
    """
    path = os.path.join(DATA_DIR, "waste_daily.csv")
    need_file(path, "Run first:  python f1_make_data.py")
    w = pd.read_csv(path, parse_dates=["date"])
    if extra_csv and os.path.exists(extra_csv):
        extra = pd.read_csv(extra_csv, parse_dates=["date"])
        w = pd.concat([w, extra[~extra["date"].isin(w["date"])]], ignore_index=True)
    if until is not None:
        w = w[w["date"] <= pd.Timestamp(until)]
    raw = w.pivot(index="date", columns="zone", values="waste_t")
    raw = raw.reindex(pd.date_range(raw.index.min(), raw.index.max()))
    raw = raw[[z for z in zone_names() if z in raw.columns]]
    med = raw.rolling(15, center=True, min_periods=7).median()
    ratio = raw / med
    wrong = (ratio > 1.65) | (ratio < 0.45)
    clean = raw.mask(wrong)
    filled = clean.interpolate(limit_direction="both")
    return raw, clean, filled, wrong


def _zone_info():
    zones = zone_names()
    zt_path = os.path.join(DATA_DIR, "zones.csv")
    if os.path.exists(zt_path):
        zt = pd.read_csv(zt_path).set_index("zone")
    else:
        zt = pd.DataFrame({"people": [S.ZONES[z][2] for z in zones], "shops_share": 0.25}, index=zones)
    return zt


def build_features(filled, clean, cal, weather, events, dates=None, zones=None):
    """Model inputs for each (day, area). Everything uses only data up to the day BEFORE.

    filled : waste per day per area with gaps filled (may also contain forecasts for future days)
    clean  : the real values (NaN where unknown) -> the answer the models learn (target)
    """
    zones = zones or list(filled.columns)
    zt = _zone_info()
    frames = []
    for z in zones:
        s = filled[z]
        level = s.shift(1).rolling(LEVEL_DAYS, min_periods=LEVEL_DAYS).mean()
        f = pd.DataFrame(index=s.index)
        f["zone"] = z
        f["level"] = level
        for k in (1, 2, 3, 7, 14):
            f[f"lag{k}_rel"] = s.shift(k) / level
        f["roll7_rel"] = s.shift(1).rolling(7).mean() / level
        f["roll7_std_rel"] = s.shift(1).rolling(7).std() / level
        f["same_dow_rel"] = (s.shift(7) + s.shift(14) + s.shift(21) + s.shift(28)) / 4 / level
        f["lag7"] = s.shift(7)
        f["roll7"] = s.shift(1).rolling(7).mean()
        f["same_dow"] = (s.shift(7) + s.shift(14) + s.shift(21) + s.shift(28)) / 4
        f["actual"] = clean[z].reindex(s.index) if clean is not None else np.nan
        f["people_k"] = float(zt.loc[z, "people"]) / 1000 if z in zt.index else np.nan
        f["shops_share"] = float(zt.loc[z, "shops_share"]) if z in zt.index else 0.25
        frames.append(f)
    df = pd.concat(frames).rename_axis("date").reset_index()
    c = cal.copy()
    for i in range(7):
        c[f"dow_{i}"] = (c["day_of_week"] == i).astype(int)
    df = df.merge(c, left_on="date", right_index=True, how="left")
    w = weather.copy()
    w["rain_prev_mm"] = w["rain_mm"].shift(1)
    df = df.merge(w[["rain_mm", "rain_prev_mm", "temp_c"]], left_on="date", right_index=True, how="left")
    ev = events.stack().rename("event_extra_pct").reset_index()
    ev.columns = ["date", "zone", "event_extra_pct"]
    df = df.merge(ev, on=["date", "zone"], how="left")
    df["event_extra_pct"] = df["event_extra_pct"].fillna(0.0)
    df["target_rel"] = df["actual"] / df["level"]
    if dates is not None:
        df = df[df["date"].isin(pd.DatetimeIndex(dates))]
    return df.reset_index(drop=True)


def load_everything(until=None, extra_csv=None):
    """Everything F2 needs: series, calendar, weather, events and the feature table."""
    raw, clean, filled, wrong = load_series(until, extra_csv)
    start, end = filled.index.min(), filled.index.max()
    cal = calendar_table(start - pd.Timedelta(days=60), end + pd.Timedelta(days=60))
    weather = load_weather()
    events = event_table(start - pd.Timedelta(days=60), end + pd.Timedelta(days=60))
    table = build_features(filled, clean, cal, weather, events)
    return dict(raw=raw, clean=clean, filled=filled, wrong=wrong, cal=cal, weather=weather,
                events=events, table=table)


def split_days(dates):
    """First 70% of the days = training, next 15% = validation, last 15% = test."""
    days = pd.DatetimeIndex(sorted(pd.unique(dates)))
    n = len(days)
    a, b = days[int(n * 0.70)], days[int(n * 0.85)]
    return a, b  # train: date < a, validation: a <= date < b, test: date >= b


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
GBM_SETTINGS = [(3, 300), (3, 600), (4, 300), (4, 600), (6, 300)]  # (tree depth, number of trees) to try


def make_gbm(depth=4, trees=500):
    """XGBoost if installed, otherwise scikit-learn's Gradient Boosting (same kind of model)."""
    try:
        from xgboost import XGBRegressor
        return "XGBoost", XGBRegressor(n_estimators=trees, learning_rate=0.03, max_depth=depth, subsample=0.8,
                                       colsample_bytree=0.8, min_child_weight=5, reg_lambda=1.0,
                                       random_state=S.SEED, n_jobs=2)
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingRegressor
        return "Gradient Boosting (XGBoost not installed)", HistGradientBoostingRegressor(
            max_iter=trees, learning_rate=0.03, max_depth=depth, max_leaf_nodes=2 ** depth, min_samples_leaf=20,
            l2_regularization=1.0, early_stopping=False, random_state=S.SEED)


SPECIAL_COLS = ["is_holiday", "fest_avurudu", "fest_vesak", "fest_poson", "fest_christmas", "fest_other_festival",
                "avurudu_before", "avurudu_after", "christmas_season", "year_end", "day_after_holiday"]


def special_day_mask(rows):
    """Holidays, festivals, festival weeks, the day after a holiday, and planned events."""
    return ((rows[SPECIAL_COLS].sum(axis=1) > 0) | (rows["event_extra_pct"] > 0)).to_numpy()


def make_linear():
    from sklearn.linear_model import LinearRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), LinearRegression())


# ---------------------------------------------------------------------------
# LSTM: the last 28 days of one area -> the waste of the next day
# ---------------------------------------------------------------------------
SEQ_COLS = ["waste", "day of week (sin)", "day of week (cos)", "holiday", "rain"]
FUTURE_FLAGS = DOW_COLS + ["is_poya", "is_public_holiday", "fest_avurudu", "fest_vesak", "fest_poson",
                           "fest_christmas", "fest_other_festival", "avurudu_before", "avurudu_after",
                           "christmas_season", "year_end", "day_before_holiday", "day_after_holiday"]
Y_SCALE = 10.0  # the LSTM learns (waste / normal level - 1) x 10, numbers around -1 ... +1


def lstm_arrays(filled, cal, weather, rows):
    """For each row (date, zone, level):
         sequence = the last 28 days of that area (waste, day of week, holiday, rain) -> 28 x 5
         next day = the target day's calendar, event, weather and area facts       -> 24 numbers
    """
    T = S.LOOKBACK_DAYS
    pos = {d: i for i, d in enumerate(filled.index)}
    vals = {z: filled[z].to_numpy(dtype=float) for z in filled.columns}
    days = filled.index
    dow = cal["day_of_week"].reindex(days).to_numpy(dtype=float)
    hol = cal["is_holiday"].reindex(days).fillna(0).to_numpy(dtype=float)
    rain = (weather["rain_mm"].reindex(days).fillna(0).clip(upper=60) / 20.0).to_numpy()
    seq = np.zeros((len(rows), T, len(SEQ_COLS)))
    for n, (d, z, level) in enumerate(zip(rows["date"], rows["zone"], rows["level"])):
        e = pos[pd.Timestamp(d)]
        sl = slice(e - T, e)
        seq[n, :, 0] = (vals[z][sl] / level - 1.0) * Y_SCALE
        seq[n, :, 1] = np.sin(2 * np.pi * dow[sl] / 7)
        seq[n, :, 2] = np.cos(2 * np.pi * dow[sl] / 7)
        seq[n, :, 3] = hol[sl]
        seq[n, :, 4] = rain[sl]
    fut = np.column_stack([rows[FUTURE_FLAGS].to_numpy(dtype=float),
                           rows["event_extra_pct"].to_numpy(dtype=float) / 100.0,
                           rows["rain_mm"].clip(upper=60).to_numpy(dtype=float) / 20.0,
                           (rows["temp_c"].to_numpy(dtype=float) - 27.5) / 2.0,
                           rows["shops_share"].to_numpy(dtype=float)])
    return np.nan_to_num(seq), np.nan_to_num(fut)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


class NumpyLSTM:
    """A small LSTM written with NumPy: LSTM(hidden) over the 28 days, then a small network that also
    sees the next day's calendar and weather. Same design as the PyTorch version below."""

    def __init__(self, n_in, n_fut, hidden=32, head=32, seed=42):
        rng = np.random.default_rng(seed)
        H = hidden
        k = 1 / np.sqrt(H)
        self.p = {"W": rng.uniform(-k, k, (n_in + H, 4 * H)), "b": np.zeros(4 * H),
                  "W1": rng.uniform(-1, 1, (H + n_fut, head)) / np.sqrt(H + n_fut), "b1": np.zeros(head),
                  "W2": rng.uniform(-1, 1, (head, 1)) / np.sqrt(head), "b2": np.zeros(1)}
        self.p["b"][H:2 * H] = 1.0  # forget gate starts open
        self.H = H

    def forward(self, seq, fut, keep=False):
        p, H = self.p, self.H
        B, T, _ = seq.shape
        h = np.zeros((B, H))
        c = np.zeros((B, H))
        cache = []
        for t in range(T):
            xh = np.concatenate([seq[:, t, :], h], axis=1)
            z = xh @ p["W"] + p["b"]
            i, f, g, o = _sigmoid(z[:, :H]), _sigmoid(z[:, H:2 * H]), np.tanh(z[:, 2 * H:3 * H]), _sigmoid(z[:, 3 * H:])
            c_prev = c
            c = f * c_prev + i * g
            tc = np.tanh(c)
            h = o * tc
            if keep:
                cache.append((xh, i, f, g, o, c_prev, tc))
        hz = np.concatenate([h, fut], axis=1)
        a = hz @ p["W1"] + p["b1"]
        r = np.maximum(a, 0)
        out = (r @ p["W2"] + p["b2"])[:, 0]
        if keep:
            self._cache = (cache, hz, a, r)
        return out

    def backward(self, seq, d_out):
        p, H = self.p, self.H
        cache, hz, a, r = self._cache
        g = {k: np.zeros_like(v) for k, v in p.items()}
        d_out = d_out[:, None]
        g["W2"] = r.T @ d_out
        g["b2"] = d_out.sum(0)
        da = (d_out @ p["W2"].T) * (a > 0)
        g["W1"] = hz.T @ da
        g["b1"] = da.sum(0)
        dh = (da @ p["W1"].T)[:, :H]
        dc = np.zeros_like(dh)
        for t in range(len(cache) - 1, -1, -1):
            xh, i, f, gg, o, c_prev, tc = cache[t]
            do = dh * tc
            dc = dc + dh * o * (1 - tc ** 2)
            di, dg, df = dc * gg, dc * i, dc * c_prev
            dz = np.concatenate([di * i * (1 - i), df * f * (1 - f), dg * (1 - gg ** 2), do * o * (1 - o)], axis=1)
            g["W"] += xh.T @ dz
            g["b"] += dz.sum(0)
            dxh = dz @ p["W"].T
            dh = dxh[:, -H:]
            dc = dc * f
        return g

    def fit(self, seq, fut, y, seq_v, fut_v, y_v, epochs=60, batch=128, lr=0.002, patience=8, seed=42, log=None):
        rng = np.random.default_rng(seed)
        m = {k: np.zeros_like(v) for k, v in self.p.items()}
        v = {k: np.zeros_like(val) for k, val in self.p.items()}
        step, best, best_p, bad = 0, np.inf, None, 0
        for ep in range(epochs):
            order = rng.permutation(len(y))
            for s in range(0, len(y), batch):
                idx = order[s:s + batch]
                out = self.forward(seq[idx], fut[idx], keep=True)
                grads = self.backward(seq[idx], 2 * (out - y[idx]) / len(idx))
                norm = np.sqrt(sum((gr ** 2).sum() for gr in grads.values()))
                scale = min(1.0, 5.0 / (norm + 1e-12))
                step += 1
                for k in self.p:
                    gk = grads[k] * scale
                    m[k] = 0.9 * m[k] + 0.1 * gk
                    v[k] = 0.999 * v[k] + 0.001 * gk ** 2
                    self.p[k] -= lr * (m[k] / (1 - 0.9 ** step)) / (np.sqrt(v[k] / (1 - 0.999 ** step)) + 1e-8)
            val = float(np.mean(np.abs(self.forward(seq_v, fut_v) - y_v)))
            if log:
                log(ep, val)
            if val < best - 1e-4:
                best, best_p, bad = val, copy.deepcopy(self.p), 0
            else:
                bad += 1
                if bad >= patience:
                    break
        self.p = best_p
        self._cache = None  # free the memory used for training
        return best

    def predict(self, seq, fut):
        self._cache = None
        return self.forward(seq, fut)


def train_lstm_torch(seq, fut, y, seq_v, fut_v, y_v, hidden=32, head=32, epochs=60, batch=128, lr=0.002,
                     patience=8, seed=42, log=None):
    """The same LSTM in PyTorch. Returns the weights as NumPy arrays (same layout as NumpyLSTM)."""
    import torch
    from torch import nn
    torch.manual_seed(seed)
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(seq.shape[2], hidden, batch_first=True)
            self.head = nn.Sequential(nn.Linear(hidden + fut.shape[1], head), nn.ReLU(), nn.Linear(head, 1))
            with torch.no_grad():
                self.lstm.bias_ih_l0[hidden:2 * hidden].fill_(1.0)  # forget gate starts open
                self.lstm.bias_hh_l0[hidden:2 * hidden].fill_(0.0)

        def forward(self, s, f):
            _, (h, _) = self.lstm(s)
            return self.head(torch.cat([h[-1], f], dim=1)).squeeze(1)

    net = Net()
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    S_t, F_t, Y_t = (torch.tensor(a, dtype=torch.float32) for a in (seq, fut, y))
    Sv, Fv, Yv = (torch.tensor(a, dtype=torch.float32) for a in (seq_v, fut_v, y_v))
    gen = torch.Generator().manual_seed(seed)
    best, best_state, bad = np.inf, None, 0
    for ep in range(epochs):
        net.train()
        order = torch.randperm(len(Y_t), generator=gen)
        for s in range(0, len(Y_t), batch):
            idx = order[s:s + batch]
            opt.zero_grad()
            loss = torch.mean((net(S_t[idx], F_t[idx]) - Y_t[idx]) ** 2)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
            opt.step()
        net.eval()
        with torch.no_grad():
            val = float(torch.mean(torch.abs(net(Sv, Fv) - Yv)))
        if log:
            log(ep, val)
        if val < best - 1e-4:
            best, best_state, bad = val, copy.deepcopy(net.state_dict()), 0
        else:
            bad += 1
            if bad >= patience:
                break
    st = {k: v.detach().cpu().numpy().astype(np.float64) for k, v in best_state.items()}
    p = {"W": np.concatenate([st["lstm.weight_ih_l0"].T, st["lstm.weight_hh_l0"].T], axis=0),
         "b": st["lstm.bias_ih_l0"] + st["lstm.bias_hh_l0"],
         "W1": st["head.0.weight"].T, "b1": st["head.0.bias"], "W2": st["head.2.weight"].T, "b2": st["head.2.bias"]}
    return p, best


def train_lstm(seq, fut, y, seq_v, fut_v, y_v, log=None):
    """PyTorch if installed (else NumPy). Returns (NumpyLSTM with the trained weights, engine name)."""
    net = NumpyLSTM(seq.shape[2], fut.shape[1], seed=S.SEED)
    try:
        import torch  # noqa: F401
        p, _ = train_lstm_torch(seq, fut, y, seq_v, fut_v, y_v, seed=S.SEED, log=log)
        net.p = p
        return net, "PyTorch"
    except ImportError:
        engine = "NumPy (PyTorch not installed)"
    except Exception as e:  # PyTorch installed but something went wrong: still finish the step
        engine = f"NumPy (PyTorch failed: {type(e).__name__}: {e})"
    net.fit(seq, fut, y, seq_v, fut_v, y_v, seed=S.SEED, log=log)
    return net, engine


# ---------------------------------------------------------------------------
# One model "pack" = everything needed to make forecasts later
# ---------------------------------------------------------------------------
class Forecaster:
    """kind: 'ma7', 'last_week', 'linear', 'gbm' or 'lstm'."""

    def __init__(self, kind, name, model=None, features=None):
        self.kind, self.name, self.model, self.features = kind, name, model, features or FEATURES

    def fit(self, data, train_rows, val_rows=None, log=None):
        if self.kind in ("ma7", "last_week"):
            return self
        if self.kind == "lstm":
            seq, fut = lstm_arrays(data["filled"], data["cal"], data["weather"], train_rows)
            y = (train_rows["target_rel"].to_numpy() - 1.0) * Y_SCALE
            vr = val_rows if val_rows is not None and len(val_rows) else train_rows.tail(300)
            seq_v, fut_v = lstm_arrays(data["filled"], data["cal"], data["weather"], vr)
            y_v = (vr["target_rel"].to_numpy() - 1.0) * Y_SCALE
            self.model, self.engine = train_lstm(seq, fut, y, seq_v, fut_v, y_v, log=log)
            return self
        x = train_rows[self.features].to_numpy(dtype=float)
        try:
            self.model.fit(x, train_rows["target_rel"].to_numpy())
        except Exception as e:
            if self.kind != "gbm" or not self.name.startswith("XGBoost"):
                raise
            # XGBoost is installed but failed: use scikit-learn's Gradient Boosting so the step finishes
            from sklearn.ensemble import HistGradientBoostingRegressor
            print(f"NOTE: XGBoost failed ({type(e).__name__}: {e}). Using Gradient Boosting instead.")
            self.name = "Gradient Boosting (XGBoost failed)"
            self.model = HistGradientBoostingRegressor(max_iter=500, learning_rate=0.03, max_depth=4,
                                                       max_leaf_nodes=16, min_samples_leaf=20, l2_regularization=1.0,
                                                       random_state=S.SEED).fit(x, train_rows["target_rel"].to_numpy())
        return self

    def predict(self, data, rows, filled=None):
        """Forecast in tonnes for each row (date, zone). filled: series to use for the LSTM inputs."""
        if self.kind == "ma7":
            return rows["roll7"].to_numpy()
        if self.kind == "last_week":
            return rows["lag7"].to_numpy()
        if self.kind == "lstm":
            seq, fut = lstm_arrays(data["filled"] if filled is None else filled, data["cal"],
                                   data["weather"], rows)
            rel = 1.0 + self.model.predict(seq, fut) / Y_SCALE
        else:
            rel = self.model.predict(rows[self.features].to_numpy(dtype=float))
        return np.asarray(rel) * rows["level"].to_numpy()


def ready_rows(table, features=FEATURES, need_target=True):
    ok = table[features + ["level"]].notna().all(axis=1)
    if need_target:
        ok &= table["target_rel"].notna()
    return table[ok]


def forecast_ahead(fc, data, origin, days, weather_future=None):
    """Forecasts for the `days` days after `origin` (the last day with real data), for every area.

    Each day's forecast is fed back in as "yesterday" for the next day (recursive forecasting).
    weather_future: weather for the coming days (forecast); otherwise the normal weather for the month.
    """
    origin = pd.Timestamp(origin)
    filled = data["filled"].loc[:origin].copy()
    weather = data["weather"][["rain_mm", "temp_c"]].copy()
    future_days = pd.date_range(origin + pd.Timedelta(days=1), periods=days)
    if weather_future is not None:  # a weather forecast (date index, rain_mm, temp_c) wins for those days
        weather = weather_future[["rain_mm", "temp_c"]].combine_first(weather)
    missing = [d for d in future_days if d not in weather.index or pd.isna(weather.loc[d, "rain_mm"])]
    if missing:  # no forecast for these days: use the normal weather of that month
        normal = weather.groupby(weather.index.month)[["rain_mm", "temp_c"]].mean()
        add = pd.DataFrame({"rain_mm": [normal.loc[d.month, "rain_mm"] for d in missing],
                            "temp_c": [normal.loc[d.month, "temp_c"] for d in missing]},
                           index=pd.DatetimeIndex(missing))
        weather = pd.concat([weather[~weather.index.isin(missing)], add]).sort_index()
    work = dict(data, weather=weather)
    out = []
    for d in future_days:
        filled.loc[d] = np.nan
        window = filled.loc[d - pd.Timedelta(days=LEVEL_DAYS + 30):d]
        rows = build_features(window, None, data["cal"], weather, data["events"], dates=[d])
        pred = fc.predict(work, rows, filled=filled)
        filled.loc[d, list(rows["zone"])] = pred
        out.append(pd.DataFrame({"date": d, "zone": rows["zone"].to_numpy(), "forecast_t": pred,
                                 "normal_t": rows["same_dow"].to_numpy(),
                                 "rain_mm": rows["rain_mm"].to_numpy()}))
    return pd.concat(out, ignore_index=True)


def high_waste_thresholds(clean, until):
    """A 'high-waste day' for an area = more waste than on 90% of its days before `until`."""
    part = clean.loc[:pd.Timestamp(until) - pd.Timedelta(days=1)]
    return part.quantile(S.HIGH_WASTE_PERCENTILE / 100.0).to_dict()


def scores(actual, pred):
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    return dict(MAE=mean_absolute_error(actual, pred), RMSE=float(np.sqrt(mean_squared_error(actual, pred))),
                R2=r2_score(actual, pred))


def within_area_r2(rows, pred):
    """R2 inside each area (harder than R2 over all areas together, where big areas vs small areas
    already explain a lot), averaged over the areas."""
    from sklearn.metrics import r2_score
    vals = []
    for z, part in rows.assign(p=pred).groupby("zone"):
        if len(part) > 5:
            vals.append(r2_score(part["actual"], part["p"]))
    return float(np.mean(vals)) if vals else np.nan


def timer():
    t0 = time.time()
    return lambda: time.time() - t0
