from bot.models import FundingDiffEntry, FundingEntry, FundingSnapshot, TurnoverEntry, VolatilityStats


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
    formatted_rate = f"{snapshot.rate * 100:.2f}%"
    if not snapshot.details:
        return formatted_rate
    #return f"{formatted_rate} {snapshot.details}"
    return f"{formatted_rate}"


def format_funding_diff_report(entries: list[FundingDiffEntry]) -> str:
    if not entries:
        return "No funding arbitrage data found."

    lines = ["💱*Funding arbitrage: Bybit - OKX*", ""]
    for index, entry in enumerate(entries, start=1):
        lines.append(f"*{entry.symbol}*")
        lines.append(
            f"Diff: `{entry.funding_diff * 100:.2f}%` | "
            f"`{format_funding_snapshot(entry.bybit)}` | "
            f"`{format_funding_snapshot(entry.okx)}`"
        )
        if entry.bybit.rate > entry.okx.rate:
            direction = "Short Bybit / Long OKX"
        elif entry.okx.rate > entry.bybit.rate:
            direction = "Short OKX / Long Bybit"
        else:
            direction = "No funding edge"
        lines.append(f"Direction: `{direction}`")
        #lines.append("")

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
    elif val >= 1.0:
        return f"{val:.4f}"
    elif val >= 0.0001:
        return f"{val:.6f}"
    else:
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
        "🔄 *24H TURNOVER*\n"
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
    return (
        f"MAX SURGE {symbol.upper()}\n"
        f"{surge_pct * 100:.0f}%\n"
        f"{date_str}"
    )
