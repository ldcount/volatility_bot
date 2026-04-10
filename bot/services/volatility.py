from __future__ import annotations

import math
import statistics

from bot.clients.bybit import fetch_candles, instrument_exists
from bot.models import Candle, VolatilityStats


def normalize_symbol(user_text: str) -> str:
    symbol = user_text.strip().upper()
    if not symbol.endswith("USDT"):
        return f"{symbol}USDT"
    return symbol


def validate_ticker(symbol: str) -> tuple[bool, str | None]:
    return instrument_exists(symbol)


def fetch_market_data(symbol: str, category: str, interval: str = "D") -> list[Candle] | None:
    return fetch_candles(symbol, category, interval)


def analyze_market_data(candles: list[Candle]) -> VolatilityStats | None:
    if not candles or len(candles) < 30:
        print("[Volatility] Not enough data to compute statistics.")
        return None

    pump_data: list[tuple[float, str]] = []
    dump_data: list[tuple[float, str]] = []
    log_returns: list[float] = []
    true_ranges: list[float] = []

    for index, candle in enumerate(candles):
        if candle.open > 0:
            pump_data.append(((candle.high - candle.open) / candle.open, candle.date))
            dump_data.append(((candle.low - candle.open) / candle.open, candle.date))

        if index == 0:
            continue

        previous_close = candles[index - 1].close
        if previous_close > 0 and candle.close > 0:
            log_returns.append(math.log(candle.close / previous_close))

        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )

    if len(log_returns) > 1:
        stdev_log = statistics.stdev(log_returns)
        vol_day = stdev_log
        vol_week = stdev_log * (7**0.5)
    else:
        vol_day = 0.0
        vol_week = 0.0

    max_log = max(log_returns) if log_returns else 0.0
    min_log = min(log_returns) if log_returns else 0.0

    if pump_data:
        max_pump_val, max_pump_date = max(pump_data, key=lambda item: item[0])
        pump_values = [value for value, _ in pump_data]
        avg_pump = statistics.mean(pump_values)
        std_pump = statistics.stdev(pump_values) if len(pump_values) > 1 else 0.0
        sorted_pumps = sorted(pump_values)
    else:
        max_pump_val, max_pump_date = 0.0, "N/A"
        avg_pump = 0.0
        std_pump = 0.0
        sorted_pumps = []

    if dump_data:
        max_dump_val, max_dump_date = min(dump_data, key=lambda item: item[0])
        dump_values = [value for value, _ in dump_data]
        avg_dump = statistics.mean(dump_values)
        std_dump = statistics.stdev(dump_values) if len(dump_values) > 1 else 0.0
    else:
        max_dump_val, max_dump_date = 0.0, "N/A"
        avg_dump = 0.0
        std_dump = 0.0

    current_close = candles[-1].close
    atr_14 = statistics.mean(true_ranges[-14:]) if len(true_ranges) >= 14 else 0.0
    atr_28 = statistics.mean(true_ranges[-28:]) if len(true_ranges) >= 28 else 0.0
    atr_relative = atr_28 / current_close if current_close > 0 and atr_28 else 0.0

    def get_percentile(percent: float) -> float:
        if not sorted_pumps:
            return 0.0
        return sorted_pumps[int(len(sorted_pumps) * percent)]

    return VolatilityStats(
        vol_day=vol_day,
        vol_week=vol_week,
        max_daily_surge=math.exp(max_log) - 1,
        max_daily_crash=math.exp(min_log) - 1,
        max_pump_val=max_pump_val,
        max_pump_date=max_pump_date,
        avg_pump=avg_pump,
        std_pump=std_pump,
        max_dump_val=max_dump_val,
        max_dump_date=max_dump_date,
        avg_dump=avg_dump,
        std_dump=std_dump,
        atr_14=atr_14,
        atr_28=atr_28,
        atr_relative=atr_relative,
        p75_pump=get_percentile(0.75),
        p80_pump=get_percentile(0.80),
        p85_pump=get_percentile(0.85),
        p90_pump=get_percentile(0.90),
        p95_pump=get_percentile(0.95),
        p99_pump=get_percentile(0.99),
    )
