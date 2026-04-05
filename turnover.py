import requests

BYBIT_TICKERS_URL = "https://api.bybit.com/v5/market/tickers"


def _format_turnover_value(value: float) -> str:
    """Formats a turnover value with K / M / B suffix."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.2f} M"
    else:
        return f"{value:,.0f}"


def get_lowest_turnover(category="linear", total=30):
    """
    Returns two formatted report strings with the lowest-turnover symbols
    on Bybit linear perpetuals.

    Returns:
        tuple[str, str]: (report_1_to_15, report_16_to_30)
    """
    try:
        params = {"category": category, "limit": 1000}
        response = requests.get(BYBIT_TICKERS_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data["retCode"] != 0:
            return "⚠️ Error: API returned an error.", None

        tickers = data.get("result", {}).get("list", [])
    except Exception as e:
        print(f"[Turnover] Error fetching data: {e}")
        return "⚠️ Error: Could not fetch ticker data.", None

    # Parse turnover and collect valid entries
    parsed = []
    for t in tickers:
        turnover_str = t.get("turnover24h", "")
        if turnover_str:
            try:
                turnover = float(turnover_str)
                parsed.append((t["symbol"], turnover))
            except ValueError:
                continue

    if not parsed:
        return "ℹ️ No turnover data available.", None

    # Sort ascending (smallest first)
    parsed.sort(key=lambda x: x[1])
    top = parsed[:total]

    # Split into two halves
    half = total // 2  # 15
    first_half = top[:half]
    second_half = top[half:]

    # Build first message (1-15)
    report_1 = "📉 *Lowest 24H turnover (1-15)*\n\n"
    for i, (symbol, turnover) in enumerate(first_half, 1):
        report_1 += (
            f"{i}. [{symbol}](https://www.bybit.com/trade/usdt/{symbol}): "
            f"{_format_turnover_value(turnover)} USDT\n"
        )

    # Build second message (16-30)
    if second_half:
        report_2 = "📉 *Lowest 24H turnover (16-30)*\n\n"
        for i, (symbol, turnover) in enumerate(second_half, half + 1):
            report_2 += (
                f"{i}. [{symbol}](https://www.bybit.com/trade/usdt/{symbol}): "
                f"{_format_turnover_value(turnover)} USDT\n"
            )
    else:
        report_2 = None

    return report_1, report_2
