from __future__ import annotations

from datetime import UTC, datetime

import requests

from bot.models import FundingSnapshot


OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
OKX_INSTRUMENTS_URL = "https://www.okx.com/api/v5/public/instruments"


def bybit_to_okx_inst_id(bybit_symbol: str) -> str:
    for quote in ("USDC", "USDT"):
        if bybit_symbol.endswith(quote):
            base = bybit_symbol[: -len(quote)]
            return f"{base}-{quote}-SWAP"
    return f"{bybit_symbol}-USDT-SWAP"


def okx_inst_id_to_symbol(inst_id: str) -> str | None:
    normalized = inst_id.upper()
    if not normalized.endswith("-USDT-SWAP"):
        return None

    parts = normalized.split("-")
    if len(parts) < 3:
        return None

    base = "".join(parts[:-2])
    if not base:
        return None

    return f"{base}USDT"


def _parse_float(value: object) -> float | None:
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_timestamp_ms(timestamp_ms: object) -> str | None:
    if timestamp_ms in (None, "", "0"):
        return None

    try:
        timestamp = int(str(timestamp_ms)) / 1000
        parsed_time = datetime.fromtimestamp(timestamp, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None

    return parsed_time.strftime("%Y-%m-%d %H:%M UTC")


def fetch_usdt_swap_instruments() -> dict[str, str]:
    try:
        response = requests.get(
            OKX_INSTRUMENTS_URL,
            params={"instType": "SWAP"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[OKX] Error fetching swap instruments: {exc}")
        return {}

    if payload.get("code") != "0":
        print(f"[OKX] API error while fetching instruments: {payload.get('msg')}")
        return {}

    instruments: dict[str, str] = {}
    for item in payload.get("data", []):
        inst_id = item.get("instId", "")
        symbol = okx_inst_id_to_symbol(inst_id)
        if symbol is None:
            continue
        instruments[symbol] = inst_id

    return instruments


def fetch_funding_snapshot(inst_id: str) -> FundingSnapshot | None:
    try:
        response = requests.get(
            OKX_FUNDING_URL,
            params={"instId": inst_id},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[OKX] Error fetching funding rate for {inst_id}: {exc}")
        return None

    if payload.get("code") != "0" or not payload.get("data"):
        return None

    entry = payload["data"][0]
    rate = _parse_float(entry.get("fundingRate"))
    if rate is None:
        return None

    details = (
        _format_timestamp_ms(entry.get("fundingTime"))
        or _format_timestamp_ms(entry.get("fundingTimestamp"))
    )
    return FundingSnapshot(rate=rate, details=details)


def fetch_funding_rate(bybit_symbol: str) -> float | None:
    snapshot = fetch_funding_snapshot(bybit_to_okx_inst_id(bybit_symbol))
    return None if snapshot is None else snapshot.rate
