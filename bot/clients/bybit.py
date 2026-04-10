from __future__ import annotations

from datetime import datetime

import requests
from pybit.unified_trading import HTTP

from bot.models import Candle


BYBIT_TICKERS_URL = "https://api.bybit.com/v5/market/tickers"
BYBIT_INSTRUMENTS_URL = "https://api.bybit.com/v5/market/instruments-info"


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


def fetch_candles(symbol: str, category: str, interval: str = "D") -> list[Candle] | None:
    session = HTTP(testnet=False)
    try:
        response = session.get_kline(
            category=category,
            symbol=symbol,
            interval=interval,
            limit=1000,
        )
    except Exception as exc:
        print(f"[Bybit] Error fetching candles for {symbol}: {exc}")
        return None

    raw_candles = response.get("result", {}).get("list", [])
    if not raw_candles:
        print(f"[Bybit] No candle data returned for {symbol}")
        return None

    candles: list[Candle] = []
    for candle in reversed(raw_candles):
        timestamp = int(candle[0]) / 1000
        candles.append(
            Candle(
                date=datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d"),
                open=float(candle[1]),
                high=float(candle[2]),
                low=float(candle[3]),
                close=float(candle[4]),
                volume=float(candle[5]),
                turnover=float(candle[6]),
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
