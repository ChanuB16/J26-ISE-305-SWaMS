"""Chart helpers for the report (PNG files in the results folder). You do not need to edit this file."""
import matplotlib

matplotlib.use("Agg")  # draw to files, no window needed
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"     # series 1
ORANGE = "#eb6834"   # series 2
AQUA = "#1baf7a"     # series 3 (below 3:1 contrast: always shown with value labels)
YELLOW = "#eda100"   # series 4 (below 3:1 contrast: always shown with value labels)
SERIES = [BLUE, ORANGE, AQUA, YELLOW]


def _style(ax, title, subtitle=None):
    fig = ax.figure
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK_2, labelsize=9, length=0)
    fig.text(0.012, 0.965, title, fontsize=13, fontweight="bold", color=INK, ha="left", va="top")
    if subtitle:
        fig.text(0.012, 0.905, subtitle, fontsize=9.5, color=INK_2, ha="left", va="top")


def _save(fig, path):
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def hbars(names, values, highlight, path, title, subtitle, xlabel, fmt="{:.2f}", legend=("ML model", "Simple baseline"),
          lower_is_better=True, sort=True):
    """Horizontal bars, best at the top (or in the given order, top to bottom, if sort=False).
    highlight[i] True = blue, False = grey."""
    if sort:
        order = sorted(range(len(names)), key=lambda i: values[i], reverse=lower_is_better)
    else:
        order = list(range(len(names)))[::-1]
    names = [names[i] for i in order]
    values = [values[i] for i in order]
    highlight = [highlight[i] for i in order]
    fig, ax = plt.subplots(figsize=(8, 0.55 * len(names) + 1.7), dpi=150)
    colors = [BLUE if h else AXIS for h in highlight]
    bars = ax.barh(range(len(names)), values, height=0.7, color=colors, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(range(len(names)), names)
    top = max(values) if values else 1
    for b, v in zip(bars, values):
        ax.text(b.get_width() + top * 0.01, b.get_y() + b.get_height() / 2, fmt.format(v),
                va="center", ha="left", fontsize=9, color=INK)
    ax.set_xlim(0, top * 1.17)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel(xlabel, color=INK_2, fontsize=9)
    if legend and not all(highlight):
        ax.legend(handles=[Patch(color=BLUE, label=legend[0]), Patch(color=AXIS, label=legend[1])],
                  loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, frameon=False, fontsize=9, labelcolor=INK_2)
    _style(ax, title, subtitle)
    _save(fig, path)


def forecast_lines(dates, actual, forecasts, holidays, path, title, subtitle):
    """Real waste per day and one or two forecasts made the day before. holidays: {date: label}."""
    fig, ax = plt.subplots(figsize=(9.5, 4.6), dpi=150)
    ax.plot(dates, actual, color=INK_2, linewidth=1.6, label="Real waste")
    for (name, values), color in zip(forecasts.items(), (BLUE, ORANGE)):
        ax.plot(dates, values, color=color, linewidth=1.8, label=f"{name} (forecast the day before)")
    lo, hi = np.nanmin(actual), np.nanmax(actual)
    for d, label in holidays.items():
        ax.axvline(d, color=GRID, linewidth=1.2, zorder=0)
        ax.text(d, hi + (hi - lo) * 0.04, label, rotation=90, fontsize=7.5, color=MUTED, ha="center", va="bottom")
    ax.set_ylim(lo - (hi - lo) * 0.1, hi + (hi - lo) * 0.45)
    ax.set_ylabel("Tonnes per day", color=INK_2, fontsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.legend(loc="lower right", frameon=False, fontsize=8.5, labelcolor=INK_2, ncol=3, bbox_to_anchor=(1.0, 1.0))
    _style(ax, title, subtitle)
    _save(fig, path)


def grouped_bars(groups, series_names, values, path, title, subtitle, ylabel, fmt="{:.0f}", ymax=None):
    """Grouped vertical bars (values[series][group])."""
    fig, ax = plt.subplots(figsize=(8.5, 4.5), dpi=150)
    x = np.arange(len(groups))
    k = len(series_names)
    width = 0.8 / k
    top = max(max(v) for v in values) if values else 1
    for s, (name, color) in enumerate(zip(series_names, SERIES)):
        pos = x + (s - (k - 1) / 2) * width
        bars = ax.bar(pos, values[s], width=width * 0.92, color=color, edgecolor=SURFACE, linewidth=1.5, label=name)
        for b, v in zip(bars, values[s]):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + top * 0.015, fmt.format(v),
                    ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_xticks(x, groups)
    ax.set_ylim(0, ymax or top * 1.18)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if k > 1:  # one series needs no legend - the title names it
        ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=min(k, 4), frameon=False, fontsize=9,
                  labelcolor=INK_2)
    _style(ax, title, subtitle)
    _save(fig, path)


def lines_by_x(x, series, path, title, subtitle, xlabel, ylabel, highlight=None):
    """Simple line chart: series = {name: values}. highlight = name drawn in blue, others in grey/orange."""
    fig, ax = plt.subplots(figsize=(8, 4.4), dpi=150)
    others = [ORANGE, AQUA, YELLOW, MUTED]
    j = 0
    for name, values in series.items():
        if name == highlight:
            color, lw = BLUE, 2.4
        else:
            color, lw = others[j % len(others)], 1.6
            j += 1
        ax.plot(x, values, color=color, linewidth=lw, marker="o", markersize=3.5, label=name)
    ax.set_xticks(x)
    ax.set_xlabel(xlabel, color=INK_2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=3, frameon=False, fontsize=8.5, labelcolor=INK_2)
    _style(ax, title, subtitle)
    _save(fig, path)


def tradeoff(points, path, title, subtitle, xlabel, ylabel):
    """points = {method: [(x, y, label), ...]} -> one line per method (e.g. km vs overflows)."""
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=150)
    for (name, pts), color in zip(points.items(), SERIES):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=5, label=name)
        for xv, yv, lab in pts:
            if lab:
                ax.annotate(lab, (xv, yv), textcoords="offset points", xytext=(5, 5), fontsize=7.5, color=INK_2)
    ax.set_xlabel(xlabel, color=INK_2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=4, frameon=False, fontsize=9, labelcolor=INK_2)
    _style(ax, title, subtitle)
    _save(fig, path)


def route_map(roads_xy, routes, bins, depot, path, title, subtitle):
    """A simple map: grey roads, coloured truck routes, bins (filled = collected) and the depot.

    roads_xy: list of (lons, lats) segments. routes: {truck: (lons, lats)}.
    bins: list of dict(lng, lat, label, collected, fill). depot: (lat, lng).
    """
    fig, ax = plt.subplots(figsize=(9, 7.4), dpi=150)
    for xs, ys in roads_xy:
        ax.plot(xs, ys, color=GRID, linewidth=0.6, zorder=1)
    for (truck, (xs, ys)), color in zip(routes.items(), SERIES):
        ax.plot(xs, ys, color=color, linewidth=2.6, alpha=0.9, zorder=3, label=truck)
    for b in bins:
        face = INK if b["collected"] else SURFACE
        ax.scatter([b["lng"]], [b["lat"]], s=46, color=face, edgecolor=INK, linewidth=1.2, zorder=4)
        ax.annotate(b["label"], (b["lng"], b["lat"]), textcoords="offset points", xytext=(5, 4), fontsize=7,
                    color=INK_2, zorder=5)
    ax.scatter([depot[1]], [depot[0]], s=140, marker="s", color=ORANGE, edgecolor=INK, zorder=5)
    ax.annotate("Depot", (depot[1], depot[0]), textcoords="offset points", xytext=(7, -10), fontsize=8.5,
                color=INK, fontweight="bold")
    ax.set_aspect(1 / np.cos(np.radians(depot[0])))
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines["bottom"].set_visible(False)
    handles = [Patch(color=c, label=t) for t, c in zip(routes.keys(), SERIES)]
    if routes:
        handles += [plt.Line2D([], [], marker="o", color="none", markerfacecolor=INK, markeredgecolor=INK,
                               label="Bin collected"),
                    plt.Line2D([], [], marker="o", color="none", markerfacecolor=SURFACE, markeredgecolor=INK,
                               label="Bin skipped (has space)")]
    else:
        handles += [plt.Line2D([], [], marker="o", color="none", markerfacecolor=INK, markeredgecolor=INK,
                               label="Smart bin")]
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=4, frameon=False, fontsize=8.5,
              labelcolor=INK_2)
    _style(ax, title, subtitle)
    _save(fig, path)
