from datetime import datetime
from html import escape
from urllib.parse import quote

from bot.models import (
    FundingDiffEntry,
    FundingEntry,
    FundingSnapshot,
    TurnoverEntry,
    VolatilityStats,
)


def _bold(value: object) -> str:
    return f"<b>{escape(str(value))}</b>"


def _code(value: object) -> str:
    return f"<code>{escape(str(value))}</code>"


def _symbol_link(symbol: str) -> str:
    return (
        f'<a href="https://www.bybit.com/trade/usdt/{quote(symbol, safe="")}">'
        f"{escape(symbol)}</a>"
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


def format_funding_report(
    entries: list[FundingEntry],
    title: str,
    offset: int = 0,
) -> str:
    if not entries:
        return "No matching funding data found."

    lines = [_bold(title), ""]
    for index, entry in enumerate(entries, start=offset + 1):
        lines.append(
            f"{index}. {_symbol_link(entry.symbol)}: "
            f"{_code(f'{entry.bybit_rate * 100:.4f}%')} "
            f"{escape(format_okx_bracket(entry.okx_rate))}"
        )
    lines.extend(("", "Bybit rate; OKX comparison is shown in parentheses."))
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
        f"💱 {_bold('Funding arbitrage decision screen')}",
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
            _bold(f"{index}. {entry.symbol} - {_funding_decision(entry)}"),
            (
                f"Trade: short {escape(entry.short_exchange)} / "
                f"long {escape(entry.long_exchange)}"
            ),
            (
                f"Rates B/O: {_code(format_funding_snapshot(entry.bybit))} / "
                f"{_code(format_funding_snapshot(entry.okx))} | next B/O: "
                f"{_format_funding_time(entry.bybit.next_funding_at)} "
                f"({entry.bybit.interval_hours or 8:g}h) / "
                f"{_format_funding_time(entry.okx.next_funding_at)} "
                f"({entry.okx.interval_hours or 8:g}h)"
            ),
            (
                f"Gross {_code(f'{entry.funding_diff * 100:.3f}%')} "
                f"(${gross_usdt:,.2f}) | net {_code(_format_rate(entry.net_edge))} | "
                f"safe {_code(safe_text)}"
            ),
            (
                "Costs fee/spread/slip: "
                f"{_code(f'{entry.round_trip_fee_rate * 100:.3f}%')}/"
                f"{_code(_format_rate(entry.spread_cost_rate))}/"
                f"{_code(_format_rate(entry.slippage_cost_rate))}"
            ),
            f"Persistence: {persistence} | {_format_liquidity(entry)}",
        ]
        if entry.warnings:
            block.append(f"Caution: {escape('; '.join(entry.warnings))}")
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

    lines = [f"🚨 {_bold('EXTREME FUNDING ALERT')}", ""]
    for index, entry in enumerate(entries, start=1):
        candidate = (
            f"{index}. {_symbol_link(entry.symbol)}: "
            f"{_code(f'{entry.bybit_rate * 100:.4f}%')} "
            f"{escape(format_okx_bracket(entry.okx_rate))}"
        )
        if len("\n".join(lines + [candidate])) > 3900:
            lines.append("Additional alerts omitted for message length.")
            break
        lines.append(candidate)
    return "\n".join(lines)


def format_turnover_reports(
    entries: list[TurnoverEntry],
    order: str,
    offset: int,
) -> tuple[str, str | None]:
    if not entries:
        return "No turnover data available.", None

    half = 15
    reports: list[str] = []
    for part_index, part in enumerate((entries[:half], entries[half:])):
        if not part:
            continue
        part_offset = offset + part_index * half
        order_label = "Highest" if order == "max" else "Lowest"
        lines = [
            _bold(
                f"{order_label} rolling 24H turnover "
                f"({part_offset + 1}-{part_offset + len(part)})"
            ),
            "",
        ]
        for index, entry in enumerate(part, start=part_offset + 1):
            lines.append(
                f"{index}. {_symbol_link(entry.symbol)}: "
                f"{_code(format_turnover_value(entry.turnover_24h))}"
            )
        reports.append("\n".join(lines))
    return reports[0], reports[1] if len(reports) > 1 else None


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
        f"📊 {_bold(f'{symbol} based on {candles_count} candles')}\n\n"
        f"📝 {_bold('DAILY STATS (close to close)')}\n"
        f"Volatility (Day): {stats.vol_day * 100:.2f}%\n"
        f"Volatility (Week): {stats.vol_week * 100:.2f}%\n"
        f"Max daily surge: {stats.max_daily_surge * 100:.2f}%\n"
        f"Max daily crash: {stats.max_daily_crash * 100:.2f}%\n\n"
        f"⬆️ {_bold('INTRADAY PUMP EXTREMES')}\n"
        "=&gt; open / high\n"
        f"Biggest Pump: {stats.max_pump_val * 100:.2f}% on {escape(stats.max_pump_date)}\n"
        f"Average Pump: {stats.avg_pump * 100:.2f}%\n"
        f"Pump Deviation (Std): {stats.std_pump * 100:.2f}%\n\n"
        f"⬇️ {_bold('INTRADAY DUMP EXTREMES')}\n"
        "=&gt; open / low\n"
        f"Worst Dump: {stats.max_dump_val * 100:.2f}% on {escape(stats.max_dump_date)}\n"
        f"Average Dump: {stats.avg_dump * 100:.2f}%\n"
        f"Dump Deviation (Std): {stats.std_dump * 100:.2f}%\n\n"
        f"↕️ {_bold('ATR (Average True Range)')}\n"
        f"ATR 14: {stats.atr_14:.6f}\n"
        f"ATR 28: {stats.atr_28:.6f}\n"
        f"ATR 28 to close: {stats.atr_relative * 100:.2f}%\n\n"
        f"📈 {_bold('MARTINGALE BASED ON PERCENTILES')}\n"
        f"1st DCA (75%): {stats.p75_pump * 100:.2f}%\n"
        f"2nd DCA (80%): {stats.p80_pump * 100:.2f}%\n"
        f"3rd DCA (85%): {stats.p85_pump * 100:.2f}%\n"
        f"4th DCA (90%): {stats.p90_pump * 100:.2f}%\n"
        f"5th DCA (95%): {stats.p95_pump * 100:.2f}%\n"
        f"6th DCA (99%): {stats.p99_pump * 100:.2f}%\n\n"
        f"{_bold('DECISION CONTEXT')}\n"
        f"Coverage: {escape(stats.sample_start)} to {escape(stats.sample_end)} "
        f"({escape(stats.data_confidence)})\n"
        f"Downside deviation: {stats.downside_deviation * 100:.2f}%\n"
        f"Maximum drawdown: {stats.max_drawdown * 100:.2f}%\n"
        f"Close vs SMA 30: {_format_rate(stats.distance_to_sma_30)}\n"
        f"Close vs VWAP 30: {_format_rate(stats.distance_to_vwap_30)}\n"
        f"Average daily turnover (30D): {_format_usdt(stats.avg_turnover_30)}\n"
        f"Liquidity-adjusted ATR: {stats.liquidity_adjusted_atr * 100:.2f}%\n\n"
        f"🔄 {_bold('ROLLING 24H TURNOVER')}\n"
        f"{escape(turnover_text)}\n\n"
        f"✖️ {_bold('AVG DAILY PRICE LAST')}\n"
        f"10 days: {_code(format_avg_price(stats.avg_price_10))}\n"
        f"30 days: {_code(format_avg_price(stats.avg_price_30))}\n"
        f"60 days: {_code(format_avg_price(stats.avg_price_60))}\n"
        f"90 days: {_code(format_avg_price(stats.avg_price_90))}"
    )


def format_scan_report(results: list[tuple[str, float]]) -> str:
    if not results:
        return "No volatile markets found during scan."

    lines = [_bold("Top Volatile Markets (by ATR)"), ""]
    for index, (symbol, atr) in enumerate(results, start=1):
        lines.append(
            f"{index}. {_symbol_link(symbol)}: {_code(f'{atr * 100:.2f}% ATR')}"
        )
    return "\n".join(lines)


def format_surge_report(symbol: str, surge_pct: float, date_str: str) -> str:
    return (
        f"{_bold(f'MAX SURGE {symbol.upper()}')}\n"
        f"{_code(f'{surge_pct * 100:.0f}%')}\n"
        f"{escape(date_str)}"
    )
