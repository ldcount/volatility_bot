from datetime import datetime

from bot.models import (
    FundingDiffEntry,
    FundingEntry,
    FundingSnapshot,
    TurnoverEntry,
    VolatilityStats,
)


def format_okx_bracket(okx_rate: float | None) -> str:
    if okx_rate is None:
        return "(x)"
    return f"({okx_rate * 100:.4f}%)"


def format_threshold_percent(threshold: float) -> str:
    return f"{threshold * 100:.2f}%"


def format_turnover_value(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} B USDT"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} M USDT"
    return f"{value:,.0f} USDT"


def format_funding_report(entries: list[FundingEntry], title: str) -> str:
    if not entries:
        return "No matching funding data found."

    lines = [title, ""]
    for index, entry in enumerate(entries, start=1):
        lines.append(
            f"{index}. [{entry.symbol}](https://www.bybit.com/trade/usdt/{entry.symbol}): "
            f"{entry.bybit_rate * 100:.4f}% {format_okx_bracket(entry.okx_rate)}"
        )
    return "\n".join(lines)


def format_funding_snapshot(snapshot: FundingSnapshot) -> str:
    interval = snapshot.interval_hours or 8.0
    normalized_rate = snapshot.rate * 8 / interval
    return f"{normalized_rate * 100:.3f}%/8h"


def _format_funding_time(value: datetime | None) -> str:
    return value.strftime("%d %b %H:%M UTC") if value is not None else "unknown"


def _format_rate(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.3f}%"


def _format_usdt(value: float | None) -> str:
    return "N/A" if value is None else format_turnover_value(value)


def _funding_decision(entry: FundingDiffEntry) -> str:
    if entry.safety_adjusted_edge is None:
        return "WATCH - execution costs unavailable"
    if entry.safety_adjusted_edge <= 0:
        return "SKIP - costs exceed edge"
    if entry.persistence_ratio is None or entry.persistence_ratio < 0.5:
        return "WATCH - weak or missing persistence"
    return "ACTIONABLE CANDIDATE"


def _format_liquidity(entry: FundingDiffEntry) -> str:
    bybit_depth = (
        _format_usdt(entry.bybit_liquidity.depth_near_market_usdt)
        if entry.bybit_liquidity is not None
        else "N/A"
    )
    okx_depth = (
        _format_usdt(entry.okx_liquidity.depth_near_market_usdt)
        if entry.okx_liquidity is not None
        else "N/A"
    )
    bybit_oi = (
        _format_usdt(entry.bybit_liquidity.open_interest_usdt)
        if entry.bybit_liquidity is not None
        else "N/A"
    )
    okx_oi = (
        _format_usdt(entry.okx_liquidity.open_interest_usdt)
        if entry.okx_liquidity is not None
        else "N/A"
    )
    return f"depth B/O {bybit_depth}/{okx_depth}; OI B/O {bybit_oi}/{okx_oi}"


def format_funding_diff_report(entries: list[FundingDiffEntry]) -> str:
    if not entries:
        return "No funding arbitrage data found."

    first = entries[0]
    lines = [
        "💱 *Funding arbitrage decision screen*",
        (
            f"Assumptions: ${first.notional_usdt:,.0f}/leg, taker round trip "
            f"{first.round_trip_fee_rate * 100:.3f}%, "
            f"{first.safety_haircut_ratio * 100:.0f}% funding haircut"
        ),
        (
            f"Screen: {first.screened_contracts}/{first.shared_contracts} shared contracts "
            "prefiltered by Bybit funding magnitude."
        ),
        "Rates and edges normalized to 8 hours.",
        "",
    ]
    shown = 0
    for index, entry in enumerate(entries, start=1):
        gross_usdt = entry.funding_diff * entry.notional_usdt
        adjusted_usdt = (
            entry.safety_adjusted_edge * entry.notional_usdt
            if entry.safety_adjusted_edge is not None
            else None
        )
        persistence = (
            f"{entry.persistence_ratio * 100:.0f}%/{entry.history_samples}; "
            f"avg {_format_rate(entry.historical_avg_edge)}"
            if entry.persistence_ratio is not None
            else "unavailable"
        )
        safe_text = (
            f"{_format_rate(entry.safety_adjusted_edge)} (${adjusted_usdt:,.2f})"
            if adjusted_usdt is not None
            else "N/A"
        )
        block = [
            f"*{index}. {entry.symbol} - {_funding_decision(entry)}*",
            f"Trade: short {entry.short_exchange} / long {entry.long_exchange}",
            (
                f"Rates B/O: `{format_funding_snapshot(entry.bybit)}` / "
                f"`{format_funding_snapshot(entry.okx)}` | next B/O: "
                f"{_format_funding_time(entry.bybit.next_funding_at)} "
                f"({entry.bybit.interval_hours or 8:g}h) / "
                f"{_format_funding_time(entry.okx.next_funding_at)} "
                f"({entry.okx.interval_hours or 8:g}h)"
            ),
            (
                f"Gross `{entry.funding_diff * 100:.3f}%` (${gross_usdt:,.2f}) | "
                f"net `{_format_rate(entry.net_edge)}` | safe `{safe_text}`"
            ),
            (
                f"Costs fee/spread/slip: `{entry.round_trip_fee_rate * 100:.3f}%`/"
                f"`{_format_rate(entry.spread_cost_rate)}`/"
                f"`{_format_rate(entry.slippage_cost_rate)}`"
            ),
            f"Persistence: {persistence} | {_format_liquidity(entry)}",
        ]
        if entry.warnings:
            block.append(f"Caution: {'; '.join(entry.warnings)}")
        block.append("")

        candidate = "\n".join(lines + block).rstrip()
        if len(candidate) > 3900:
            break
        lines.extend(block)
        shown += 1

    if shown < len(entries):
        lines.append(f"{len(entries) - shown} additional candidates omitted for message length.")
    return "\n".join(lines).rstrip()


def format_extreme_funding_alert(entries: list[FundingEntry]) -> str | None:
    if not entries:
        return None

    lines = ["🚨 *EXTREME FUNDING ALERT*", ""]
    for entry in entries:
        lines.append(
            f"[{entry.symbol}](https://www.bybit.com/trade/usdt/{entry.symbol}): "
            f"{entry.bybit_rate * 100:.4f}% {format_okx_bracket(entry.okx_rate)}"
        )
    return "\n".join(lines)


def format_turnover_reports(
    entries: list[TurnoverEntry],
    order: str,
    offset: int,
) -> tuple[str, str | None]:
    if not entries:
        return "No turnover data available.", None

    half = 15
    first_half = entries[:half]
    second_half = entries[half:]
    order_label = "Highest" if order == "max" else "Lowest"

    lines_1 = [f"*{order_label} 24H turnover ({offset + 1}-{offset + len(first_half)})*", ""]
    for index, entry in enumerate(first_half, start=offset + 1):
        lines_1.append(
            f"{index}. [{entry.symbol}](https://www.bybit.com/trade/usdt/{entry.symbol}): "
            f"{format_turnover_value(entry.turnover_24h)}"
        )
    report_1 = "\n".join(lines_1)

    if not second_half:
        return report_1, None

    lines_2 = [f"*{order_label} 24H turnover ({offset + half + 1}-{offset + len(entries)})*", ""]
    for index, entry in enumerate(second_half, start=offset + half + 1):
        lines_2.append(
            f"{index}. [{entry.symbol}](https://www.bybit.com/trade/usdt/{entry.symbol}): "
            f"{format_turnover_value(entry.turnover_24h)}"
        )
    return report_1, "\n".join(lines_2)


def format_avg_price(val: float | None) -> str:
    if val is None:
        return "N/A"
    if val >= 100.0:
        return f"{val:.2f}"
    if val >= 1.0:
        return f"{val:.4f}"
    if val >= 0.0001:
        return f"{val:.6f}"
    return f"{val:.8f}"


def format_volatility_report(
    symbol: str,
    candles_count: int,
    stats: VolatilityStats,
    turnover_text: str,
) -> str:
    return (
        f"📊 *{symbol} based on {candles_count} candles*\n\n"
        "📝 *DAILY STATS (close to close)*\n"
        f"Volatility (Day): {stats.vol_day * 100:.2f}%\n"
        f"Volatility (Week): {stats.vol_week * 100:.2f}%\n"
        f"Max daily surge: {stats.max_daily_surge * 100:.2f}%\n"
        f"Max daily crash: {stats.max_daily_crash * 100:.2f}%\n\n"
        "⬆️ *INTRADAY PUMP EXTREMES*\n"
        "=> open / high\n"
        f"Biggest Pump: {stats.max_pump_val * 100:.2f}% on {stats.max_pump_date}\n"
        f"Average Pump: {stats.avg_pump * 100:.2f}%\n"
        f"Pump Deviation (Std): {stats.std_pump * 100:.2f}%\n\n"
        "⬇️ *INTRADAY DUMP EXTREMES*\n"
        "=> open / low\n"
        f"Worst Dump: {stats.max_dump_val * 100:.2f}% on {stats.max_dump_date}\n"
        f"Average Dump: {stats.avg_dump * 100:.2f}%\n"
        f"Dump Deviation (Std): {stats.std_dump * 100:.2f}%\n\n"
        "↕️ *ATR (Average True Range)*\n"
        f"ATR 14: {stats.atr_14:.6f}\n"
        f"ATR 28: {stats.atr_28:.6f}\n"
        f"ATR 28 to close: {stats.atr_relative * 100:.2f}%\n\n"
        "📈 *MARTINGALE BASED ON PERCENTILES*\n"
        f"1st DCA (75%): {stats.p75_pump * 100:.2f}%\n"
        f"2nd DCA (80%): {stats.p80_pump * 100:.2f}%\n"
        f"3rd DCA (85%): {stats.p85_pump * 100:.2f}%\n"
        f"4th DCA (90%): {stats.p90_pump * 100:.2f}%\n"
        f"5th DCA (95%): {stats.p95_pump * 100:.2f}%\n"
        f"6th DCA (99%): {stats.p99_pump * 100:.2f}%\n\n"
        "*DECISION CONTEXT*\n"
        f"Coverage: {stats.sample_start} to {stats.sample_end} ({stats.data_confidence})\n"
        f"Downside deviation: {stats.downside_deviation * 100:.2f}%\n"
        f"Maximum drawdown: {stats.max_drawdown * 100:.2f}%\n"
        f"Close vs SMA 30: {_format_rate(stats.distance_to_sma_30)}\n"
        f"Close vs VWAP 30: {_format_rate(stats.distance_to_vwap_30)}\n"
        f"Average daily turnover (30D): {_format_usdt(stats.avg_turnover_30)}\n"
        f"Liquidity-adjusted ATR: {stats.liquidity_adjusted_atr * 100:.2f}%\n\n"
        "🔄 *ROLLING 24H TURNOVER*\n"
        f"{turnover_text}\n\n"
        "✖️ *AVG DAILY PRICE LAST*\n"
        f"10 days: `{format_avg_price(stats.avg_price_10)}`\n"
        f"30 days: `{format_avg_price(stats.avg_price_30)}`\n"
        f"60 days: `{format_avg_price(stats.avg_price_60)}`\n"
        f"90 days: `{format_avg_price(stats.avg_price_90)}`"
    )


def format_scan_report(results: list[tuple[str, float]]) -> str:
    if not results:
        return "No volatile markets found during scan."

    lines = ["*Top Volatile Markets (by ATR)*", ""]
    for index, (symbol, atr) in enumerate(results, start=1):
        lines.append(
            f"{index}. [{symbol}](https://www.bybit.com/trade/usdt/{symbol}): "
            f"{atr * 100:.2f}% ATR"
        )
    return "\n".join(lines)


def format_surge_report(symbol: str, surge_pct: float, date_str: str) -> str:
    return f"MAX SURGE {symbol.upper()}\n{surge_pct * 100:.0f}%\n{date_str}"
