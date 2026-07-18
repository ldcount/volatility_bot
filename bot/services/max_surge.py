from __future__ import annotations

from bot.models import Candle


def calculate_max_surge(candles: list[Candle], days_window: int) -> tuple[float, str] | None:
    if not candles or days_window < 1:
        return None

    # Handle the case where the user asks for a window bigger than available data
    if len(candles) < days_window:
        return None

    max_surge = -float("inf")
    best_date = ""

    # Iterate over all possible N-day windows in the list of candles
    for i in range(len(candles) - days_window + 1):
        day_one_low = candles[i].low
        day_n_high = candles[i + days_window - 1].high

        # Prevent division by zero or invalid prices
        if day_one_low <= 0:
            continue

        surge = (day_n_high - day_one_low) / day_one_low

        if surge > max_surge:
            max_surge = surge
            best_date = candles[i].date

    if max_surge == -float("inf"):
        return None

    return max_surge, best_date
