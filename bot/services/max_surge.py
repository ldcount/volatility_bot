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

    # Find the largest low-to-later-high draw-up inside every N-day window.
    for i in range(len(candles) - days_window + 1):
        lowest_price = float("inf")
        lowest_price_date = ""

        for candle in candles[i : i + days_window]:
            if candle.low <= 0 or candle.high <= 0:
                continue

            if candle.low < lowest_price:
                lowest_price = candle.low
                lowest_price_date = candle.date

            surge = (candle.high - lowest_price) / lowest_price
            if surge > max_surge:
                max_surge = surge
                best_date = lowest_price_date

    if max_surge == -float("inf"):
        return None

    return max_surge, best_date
