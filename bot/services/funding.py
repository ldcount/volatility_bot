from __future__ import annotations

from bot.clients.bybit import fetch_all_tickers
from bot.clients.okx import fetch_funding_rate
from bot.models import FundingEntry


def rank_funding_entries(
    tickers: list[dict],
    *,
    positive: bool,
    limit: int = 10,
) -> list[tuple[str, float]]:
    ranked: list[tuple[str, float]] = []
    for ticker in tickers:
        symbol = ticker.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue

        funding_rate = ticker.get("fundingRate")
        if not funding_rate:
            continue

        try:
            parsed_rate = float(funding_rate)
        except ValueError:
            continue

        if positive and parsed_rate > 0:
            ranked.append((symbol, parsed_rate))
        if not positive and parsed_rate < 0:
            ranked.append((symbol, parsed_rate))

    ranked.sort(key=lambda item: item[1], reverse=positive)
    return ranked[:limit]


def get_top_negative_funding(limit: int = 10) -> list[FundingEntry]:
    tickers = fetch_all_tickers()
    return [
        FundingEntry(symbol=symbol, bybit_rate=rate, okx_rate=fetch_funding_rate(symbol))
        for symbol, rate in rank_funding_entries(tickers, positive=False, limit=limit)
    ]


def get_top_positive_funding(limit: int = 10) -> list[FundingEntry]:
    tickers = fetch_all_tickers()
    return [
        FundingEntry(symbol=symbol, bybit_rate=rate, okx_rate=fetch_funding_rate(symbol))
        for symbol, rate in rank_funding_entries(tickers, positive=True, limit=limit)
    ]


def find_extreme_funding(threshold: float = -0.015) -> list[FundingEntry]:
    tickers = fetch_all_tickers()
    ranked: list[tuple[str, float]] = []
    for ticker in tickers:
        symbol = ticker.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue

        funding_rate = ticker.get("fundingRate")
        if not funding_rate:
            continue

        try:
            parsed_rate = float(funding_rate)
        except ValueError:
            continue

        if parsed_rate <= threshold:
            ranked.append((symbol, parsed_rate))

    ranked.sort(key=lambda item: item[1])
    return [
        FundingEntry(symbol=symbol, bybit_rate=rate, okx_rate=fetch_funding_rate(symbol))
        for symbol, rate in ranked
    ]
