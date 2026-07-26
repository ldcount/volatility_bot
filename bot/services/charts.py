from __future__ import annotations

import io
from datetime import UTC, datetime

import matplotlib
matplotlib.use("Agg")  # Thread-safe non-interactive backend
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


def format_money_compact(x: float, pos: int | None = None) -> str:
    if x >= 1e9:
        return f"${x * 1e-9:.2f}B"
    elif x >= 1e6:
        return f"${x * 1e-6:.2f}M"
    elif x >= 1e3:
        return f"${x * 1e-3:.1f}K"
    return f"${x:.2f}"


def generate_turnover_chart(symbol: str, data: list[dict], mode: str) -> bytes:
    """
    Generates a dark-themed PNG chart of the turnover history.
    Each item in data is expected to have 'timestamp' and 'turnover'.
    """
    timestamps = [d["timestamp"] for d in data]
    turnovers = [d["turnover"] for d in data]
    dates = [datetime.fromtimestamp(ts, tz=UTC) for ts in timestamps]

    # Use a dark background style
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    # Clean styling
    color = "#00f2fe"  # Neon cyan color for line
    series_label = "Hourly Turnover" if mode == "hours" else "Daily Turnover"
    ax.plot(
        dates,
        turnovers,
        color=color,
        linewidth=2.5,
        marker="o",
        markersize=4,
        label=series_label,
    )
    ax.fill_between(dates, turnovers, color=color, alpha=0.15)

    # Gridlines and spines styling
    ax.grid(True, which="both", linestyle="--", linewidth=0.5, color="#333333")
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#444444")
    ax.spines["bottom"].set_color("#444444")

    # Format Y-axis
    ax.yaxis.set_major_formatter(FuncFormatter(format_money_compact))
    ax.tick_params(colors="#cccccc", labelsize=9)

    # Format X-axis depending on mode (hourly vs daily)
    if mode == "hours":
        if len(data) <= 24:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=UTC))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, len(data) // 6)))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M", tz=UTC))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(4, len(data) // 6)))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d", tz=UTC))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(data) // 6)))

    # Adjust Y-axis limit to add headroom at the top for labels, ensuring no negative values
    if turnovers:
        ymin, ymax = min(turnovers), max(turnovers)
        yrange = ymax - ymin
        if yrange == 0:
            yrange = ymax * 0.1 if ymax > 0 else 1.0
        ax.set_ylim(max(0.0, ymin - yrange * 0.15), ymax + yrange * 0.25)

    # Annotate points with exact values.
    # To prevent visual clutter, label all points if <= 24, otherwise label only first, last, min, and max.
    if len(data) <= 24:
        for date, val in zip(dates, turnovers):
            label = format_money_compact(val)
            ax.annotate(
                label,
                xy=(date, val),
                xytext=(0, 6),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
                color="#00f2fe",
                fontweight="bold",
            )
    else:
        min_val = min(turnovers)
        max_val = max(turnovers)
        min_idx = turnovers.index(min_val)
        max_idx = turnovers.index(max_val)
        special_indices = {0, len(data) - 1, min_idx, max_idx}
        
        for idx in special_indices:
            date = dates[idx]
            val = turnovers[idx]
            label = format_money_compact(val)
            ax.annotate(
                label,
                xy=(date, val),
                xytext=(0, 6),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
                color="#00f2fe",
                fontweight="bold",
            )

    fig.autofmt_xdate()

    # Title & Legend
    title_suffix = f"({len(data)} Hours)" if mode == "hours" else f"({len(data)} Days)"
    ax.set_title(
        f"{symbol} {series_label} {title_suffix}",
        fontsize=13,
        pad=15,
        fontweight="bold",
        color="#ffffff",
    )

    # Save to in-memory bytes stream
    buf = io.BytesIO()
    plt.savefig(
        buf,
        format="png",
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()
