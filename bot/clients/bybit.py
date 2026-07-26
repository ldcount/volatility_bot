from __future__ import annotations

import time
from datetime import UTC, datetime

import requests
from pybit.unified_trading import HTTP

from bot.models import Candle, FundingRatePoint, OrderBookSnapshot


BYBIT_TICKERS_URL = "https://api.bybit.com/v5/market/tickers"
BYBIT_INSTRUMENTS_URL = "https://api.bybit.com/v5/market/instruments-info"
BYBIT_ORDERBOOK_URL = "https://api.bybit.com/v5/market/orderbook"
BYBIT_FUNDING_HISTORY_URL = "https://api.bybit.com/v5/market/funding/history"
MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000


def _interval_duration_ms(interval: str) -> int | None:
    if interval.isdigit():
        return int(interval) * 60 * 1000
    if interval == "D":
        return MILLISECONDS_PER_DAY
    if interval == "W":
        return 7 * MILLISECONDS_PER_DAY
    return None


def fetch_all_tickers(category: str = "linear") -> list[dict]:
    try:
        response = requests.get(
            BYBIT_TICKERS_URL,
            params={"category": category, "limit": 1000},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[Bybit] Error fetching tickers: {exc}")
        return []

    if payload.get("retCode") != 0:
        print(f"[Bybit] API error while fetching tickers: {payload.get('retMsg')}")
        return []

    return payload.get("result", {}).get("list", [])


def instrument_exists(symbol: str) -> tuple[bool, str | None]:
    for category in ("linear", "inverse", "spot"):
        cursor = ""
        try:
            while True:
                params = {"category": category, "limit": 1000}
                if cursor:
                    params["cursor"] = cursor

                response = requests.get(BYBIT_INSTRUMENTS_URL, params=params, timeout=10)
                response.raise_for_status()
                payload = response.json()

                instruments = payload.get("result", {}).get("list", [])
                for item in instruments:
                    if item.get("symbol") == symbol:
                        return True, category

                cursor = payload.get("result", {}).get("nextPageCursor", "")
                if not cursor:
                    break
        except Exception as exc:
            print(f"[Bybit] Error checking category '{category}': {exc}")

    print(f"[Bybit] Symbol not found: {symbol}")
    return False, None


def fetch_candles(symbol: str, category: str, interval: str = "D", limit: int = 1000) -> list[Candle] | None:
    session = HTTP(testnet=False, recv_window=10000)
    try:
        response = session.get_kline(
            category=category,
            symbol=symbol,
            interval=interval,
            limit=limit,
        )
    except Exception as exc:
        print(f"[Bybit] Error fetching candles for {symbol}: {exc}")
        return None

    raw_candles = response.get("result", {}).get("list", [])
    if not raw_candles:
        print(f"[Bybit] No candle data returned for {symbol}")
        return None

    candles: list[Candle] = []
    current_time_ms = int(time.time() * 1000)
    interval_duration_ms = _interval_duration_ms(interval)
    for candle in reversed(raw_candles):
        start_time_ms = int(candle[0])
        if (
            interval_duration_ms is not None
            and start_time_ms + interval_duration_ms > current_time_ms
        ):
            continue

        timestamp = start_time_ms / 1000
        date_format = "%Y-%m-%d" if interval in {"D", "W", "M"} else "%Y-%m-%d %H:%M"
        candles.append(
            Candle(
                date=datetime.fromtimestamp(timestamp, tz=UTC).strftime(date_format),
                open=float(candle[1]),
                high=float(candle[2]),
                low=float(candle[3]),
                close=float(candle[4]),
                volume=float(candle[5]),
                turnover=float(candle[6]),
                timestamp=int(timestamp),
            )
        )

    return candles


def fetch_symbol_turnover(symbol: str, category: str = "linear") -> float | None:
    try:
        response = requests.get(
            BYBIT_TICKERS_URL,
            params={"category": category, "symbol": symbol},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[Bybit] Error fetching turnover for {symbol}: {exc}")
        return None

    if payload.get("retCode") != 0:
        return None

    tickers = payload.get("result", {}).get("list", [])
    if not tickers:
        return None

    turnover = tickers[0].get("turnover24h")
    return float(turnover) if turnover else None


def fetch_orderbook(
    symbol: str,
    category: str = "linear",
    limit: int = 50,
) -> OrderBookSnapshot | None:
    try:
        response = requests.get(
            BYBIT_ORDERBOOK_URL,
            params={"category": category, "symbol": symbol, "limit": limit},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[Bybit] Error fetching orderbook for {symbol}: {exc}")
        return None

    if payload.get("retCode") != 0:
        return None

    result = payload.get("result", {})
    try:
        bids = tuple((float(level[0]), float(level[1])) for level in result.get("b", []))
        asks = tuple((float(level[0]), float(level[1])) for level in result.get("a", []))
    except (TypeError, ValueError, IndexError):
        return None

    if not bids or not asks:
        return None

    timestamp_ms = result.get("ts")
    return OrderBookSnapshot(
        bids=bids,
        asks=asks,
        timestamp_ms=int(timestamp_ms) if timestamp_ms else None,
    )


def fetch_funding_history(
    symbol: str,
    limit: int = 6,
) -> list[FundingRatePoint]:
    try:
        response = requests.get(
            BYBIT_FUNDING_HISTORY_URL,
            params={"category": "linear", "symbol": symbol, "limit": limit},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[Bybit] Error fetching funding history for {symbol}: {exc}")
        return []

    if payload.get("retCode") != 0:
        return []

    points: list[FundingRatePoint] = []
    for item in payload.get("result", {}).get("list", []):
        try:
            funded_at = datetime.fromtimestamp(
                int(item["fundingRateTimestamp"]) / 1000,
                tz=UTC,
            )
            points.append(FundingRatePoint(rate=float(item["fundingRate"]), funded_at=funded_at))
        except (KeyError, TypeError, ValueError, OSError):
            continue
    return points
