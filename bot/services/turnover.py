from __future__ import annotations

from bot.clients.bybit import fetch_all_tickers, fetch_symbol_ticker
from bot.models import TurnoverEntry
from bot.reports import format_turnover_value
from bot.services.db import save_hourly_snapshots


def rank_turnover_entries(
    tickers: list[dict],
    *,
    order: str = "min",
    offset: int = 0,
    total: int = 30,
) -> list[TurnoverEntry]:
    ranked: list[TurnoverEntry] = []
    for ticker in tickers:
        symbol = ticker.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue

        turnover_value = ticker.get("turnover24h")
        if not turnover_value:
            continue

        try:
            ranked.append(
                TurnoverEntry(symbol=symbol, turnover_24h=float(turnover_value))
            )
        except ValueError:
            continue

    ranked.sort(key=lambda entry: entry.turnover_24h, reverse=order == "max")
    return ranked[offset : offset + total]


def get_ranked_turnover(order: str = "min", offset: int = 0, total: int = 30) -> list[TurnoverEntry]:
    tickers = fetch_all_tickers()
    return rank_turnover_entries(tickers, order=order, offset=offset, total=total)


def get_symbol_turnover_text(symbol: str, category: str = "linear") -> str:
    ticker = fetch_symbol_ticker(symbol, category)
    if ticker is None:
        return "N/A"

    # Refresh this symbol's current-hour snapshot before its chart is read.
    # INSERT OR REPLACE updates an existing point in the same hourly bucket.
    try:
        save_hourly_snapshots([ticker])
    except Exception as exc:
        # A persistence problem should not suppress the otherwise valid report.
        print(f"[Turnover] Could not refresh snapshot for {symbol}: {exc}")
    turnover = ticker.get("turnover24h")
    try:
        return format_turnover_value(float(turnover))
    except (TypeError, ValueError):
        return "N/A"
