from __future__ import annotations

import math
import statistics

from bot.clients.bybit import fetch_all_tickers, fetch_candles, instrument_exists
from bot.models import Candle, VolatilityStats


LIQUIDITY_REFERENCE_TURNOVER_USDT = 10_000_000.0


def normalize_symbol(user_text: str) -> str:
    symbol = user_text.strip().upper()
    if not symbol.endswith("USDT"):
        return f"{symbol}USDT"
    return symbol


def validate_ticker(symbol: str) -> tuple[bool, str | None]:
    return instrument_exists(symbol)


def fetch_market_data(symbol: str, category: str, interval: str = "D", limit: int = 1000) -> list[Candle] | None:
    return fetch_candles(symbol, category, interval, limit)


def analyze_market_data(candles: list[Candle]) -> VolatilityStats | None:
    if not candles or len(candles) < 30:
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

    avg_price_10 = (
        statistics.mean(c.open for c in candles[-10:])
        if len(candles) >= 10
        else None
    )
    avg_price_30 = (
        statistics.mean(c.open for c in candles[-30:])
        if len(candles) >= 30
        else None
    )
    avg_price_60 = (
        statistics.mean(c.open for c in candles[-60:])
        if len(candles) >= 60
        else None
    )
    avg_price_90 = (
        statistics.mean(c.open for c in candles[-90:])
        if len(candles) >= 90
        else None
    )

    negative_returns = [min(value, 0.0) for value in log_returns]
    downside_deviation = (
        math.sqrt(statistics.mean(value * value for value in negative_returns))
        if negative_returns
        else 0.0
    )

    peak_close = 0.0
    max_drawdown = 0.0
    for candle in candles:
        if candle.close <= 0:
            continue
        peak_close = max(peak_close, candle.close)
        if peak_close > 0:
            max_drawdown = min(max_drawdown, candle.close / peak_close - 1)

    recent_30 = candles[-30:]
    sma_30 = statistics.mean(c.close for c in recent_30) if recent_30 else None
    total_volume_30 = sum(c.volume for c in recent_30 if c.volume > 0)
    total_turnover_30 = sum(c.turnover for c in recent_30 if c.turnover > 0)
    vwap_30 = (
        total_turnover_30 / total_volume_30
        if total_volume_30 > 0 and total_turnover_30 > 0
        else None
    )
    avg_turnover_30 = (
        statistics.mean(c.turnover for c in recent_30)
        if recent_30
        else None
    )
    distance_to_sma_30 = (
        current_close / sma_30 - 1
        if sma_30 is not None and sma_30 > 0 and current_close > 0
        else None
    )
    distance_to_vwap_30 = (
        current_close / vwap_30 - 1
        if vwap_30 is not None and vwap_30 > 0 and current_close > 0
        else None
    )
    liquidity_penalty = 1.0
    if avg_turnover_30 is not None and avg_turnover_30 > 0:
        liquidity_penalty = max(
            1.0,
            math.sqrt(LIQUIDITY_REFERENCE_TURNOVER_USDT / avg_turnover_30),
        )
    liquidity_adjusted_atr = atr_relative * liquidity_penalty

    if len(candles) >= 365:
        data_confidence = "High"
    elif len(candles) >= 90:
        data_confidence = "Moderate"
    else:
        data_confidence = "Limited"

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
        avg_price_10=avg_price_10,
        avg_price_30=avg_price_30,
        avg_price_60=avg_price_60,
        avg_price_90=avg_price_90,
        downside_deviation=downside_deviation,
        max_drawdown=max_drawdown,
        current_close=current_close,
        sma_30=sma_30,
        vwap_30=vwap_30,
        distance_to_sma_30=distance_to_sma_30,
        distance_to_vwap_30=distance_to_vwap_30,
        avg_turnover_30=avg_turnover_30,
        liquidity_adjusted_atr=liquidity_adjusted_atr,
        sample_start=candles[0].date,
        sample_end=candles[-1].date,
        data_confidence=data_confidence,
    )



def scan_market_volatility(top_n: int = 50) -> list[tuple[str, float]]:
    tickers = fetch_all_tickers("linear")

    valid_tickers: list[tuple[str, float]] = []
    for ticker in tickers:
        symbol = ticker.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue

        turnover_value = ticker.get("turnover24h")
        if not turnover_value:
            continue

        try:
            turnover = float(turnover_value)
            valid_tickers.append((symbol, turnover))
        except ValueError:
            continue

    valid_tickers.sort(key=lambda item: item[1], reverse=True)
    top_tickers = valid_tickers[:top_n]

    results: list[tuple[str, float]] = []
    skipped_coins: list[str] = []
    
    for symbol, _ in top_tickers:
        candles = fetch_candles(symbol, "linear", "D", limit=50)
        if not candles:
            skipped_coins.append(symbol)
            continue

        stats = analyze_market_data(candles)
        if not stats:
            skipped_coins.append(symbol)
            continue

        if stats.atr_relative > 0:
            results.append((symbol, stats.atr_relative))

    if skipped_coins:
        print(f"[Volatility] Not enough data to compute statistics. Coins skipped: {', '.join(skipped_coins)}")

    results.sort(key=lambda item: item[1], reverse=True)
    return results[:15]
