"""Chart helpers for the report (PNG files in the results folder). You do not need to edit this file."""
import matplotlib

matplotlib.use("Agg")  # draw to files, no window needed
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"     # series 1
ORANGE = "#eb6834"   # series 2
BLUE_LIGHT = "#9ec5f4"


def _style(ax, title, subtitle=None):
    fig = ax.figure
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK_2, labelsize=9, length=0)
    ax.title.set_color(INK)
    fig.text(0.012, 0.965, title, fontsize=13, fontweight="bold", color=INK, ha="left", va="top")
    if subtitle:
        fig.text(0.012, 0.905, subtitle, fontsize=9.5, color=INK_2, ha="left", va="top")


def model_bars(names, mae, is_ml, path, subtitle):
    """Horizontal bars: test MAE per model (lower is better)."""
    order = sorted(range(len(names)), key=lambda i: mae[i], reverse=True)
    names = [names[i] for i in order]
    mae = [mae[i] for i in order]
    is_ml = [is_ml[i] for i in order]
    fig, ax = plt.subplots(figsize=(8, 0.55 * len(names) + 1.6), dpi=150)
    colors = [BLUE if m else AXIS for m in is_ml]
    bars = ax.barh(range(len(names)), mae, height=0.7, color=colors, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(range(len(names)), names)
    for b, v in zip(bars, mae):
        ax.text(b.get_width() + max(mae) * 0.01, b.get_y() + b.get_height() / 2, f"{v:.2f}",
                va="center", ha="left", fontsize=9, color=INK)
    ax.set_xlim(0, max(mae) * 1.15)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel("Average error of the 6-hour prediction, MAE (fill % points)", color=INK_2, fontsize=9)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=BLUE, label="ML model"), Patch(color=AXIS, label="Simple baseline")],
              loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, frameon=False, fontsize=9, labelcolor=INK_2)
    _style(ax, "Which model predicts the fill level best?", subtitle)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def example_lines(times, actual, pred_times, pred, path, title, subtitle, overflow_pct):
    """Line chart: the real fill level and the fill level the model predicted 6 hours earlier."""
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
    ax.axhline(overflow_pct, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(times[-1], overflow_pct + 1.5, f"Overflow line ({overflow_pct}%)", color=INK_2, fontsize=8.5,
            ha="right")
    ax.plot(times, actual, color=BLUE, linewidth=2, label="Real fill level")
    ax.plot(pred_times, pred, color=ORANGE, linewidth=2, label="Predicted 6 hours earlier")
    ax.set_ylim(0, 108)
    ax.set_ylabel("Fill (%)", color=INK_2, fontsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M", tz=times[0].tz))
    ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK_2, ncol=2,
              bbox_to_anchor=(1.0, 1.0))
    _style(ax, title, subtitle)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def importance_bars(names, values, path, subtitle):
    """Horizontal bars: how much worse the model gets without each input."""
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(names) + 1.6), dpi=150)
    y = list(range(len(names)))[::-1]
    bars = ax.barh(y, values, height=0.7, color=BLUE, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(y, names)
    top = max(values) if len(values) else 1
    for b, v in zip(bars, values):
        ax.text(b.get_width() + top * 0.01, b.get_y() + b.get_height() / 2, f"{v:.2f}",
                va="center", ha="left", fontsize=9, color=INK)
    ax.set_xlim(0, top * 1.15)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel("How much the error grows when this input is scrambled (MAE, % points)",
                  color=INK_2, fontsize=9)
    _style(ax, "Which inputs does the model use most?", subtitle)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def grouped_bars(groups, series_names, values, path, title, subtitle, ylabel):
    """Grouped vertical bars, 2 series (values[series][group]), values 0 to 100."""
    import numpy as np
    fig, ax = plt.subplots(figsize=(8, 4.4), dpi=150)
    x = np.arange(len(groups))
    width = 0.36
    for k, (name, color) in enumerate(zip(series_names, (BLUE, ORANGE))):
        pos = x + (k - 0.5) * (width + 0.02)
        bars = ax.bar(pos, values[k], width=width, color=color, edgecolor=SURFACE, linewidth=2, label=name)
        for b, v in zip(bars, values[k]):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5, f"{v:.0f}%",
                    ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_xticks(x, groups)
    ax.set_ylim(0, 110)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, frameon=False, fontsize=9, labelcolor=INK_2)
    _style(ax, title, subtitle)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
