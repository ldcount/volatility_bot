from __future__ import annotations

from datetime import UTC, datetime

import requests

from bot.models import (
    FundingRatePoint,
    FundingSnapshot,
    OkxInstrument,
    OrderBookSnapshot,
)


OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
OKX_INSTRUMENTS_URL = "https://www.okx.com/api/v5/public/instruments"
OKX_ORDERBOOK_URL = "https://www.okx.com/api/v5/market/books"
OKX_FUNDING_HISTORY_URL = "https://www.okx.com/api/v5/public/funding-rate-history"
OKX_OPEN_INTEREST_URL = "https://www.okx.com/api/v5/public/open-interest"


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


def _parse_timestamp_ms(timestamp_ms: object) -> datetime | None:
    if timestamp_ms in (None, "", "0"):
        return None

    try:
        return datetime.fromtimestamp(int(str(timestamp_ms)) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def fetch_usdt_swap_instruments() -> dict[str, OkxInstrument]:
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

    instruments: dict[str, OkxInstrument] = {}
    for item in payload.get("data", []):
        inst_id = item.get("instId", "")
        symbol = okx_inst_id_to_symbol(inst_id)
        if symbol is None or item.get("state") not in (None, "", "live"):
            continue
        contract_value = _parse_float(item.get("ctVal"))
        contract_multiplier = _parse_float(item.get("ctMult"))
        if contract_value is None or contract_multiplier is None:
            continue
        instruments[symbol] = OkxInstrument(
            inst_id=inst_id,
            contract_value=contract_value,
            contract_multiplier=contract_multiplier,
            contract_value_currency=str(item.get("ctValCcy", "")),
        )

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

    funding_at = _parse_timestamp_ms(
        entry.get("fundingTime") or entry.get("fundingTimestamp")
    )
    next_funding_at = _parse_timestamp_ms(entry.get("nextFundingTime"))
    previous_funding_at = _parse_timestamp_ms(entry.get("prevFundingTime"))

    interval_hours = None
    if funding_at is not None and next_funding_at is not None:
        interval_hours = (next_funding_at - funding_at).total_seconds() / 3600
    elif funding_at is not None and previous_funding_at is not None:
        interval_hours = (funding_at - previous_funding_at).total_seconds() / 3600

    details = funding_at.strftime("%Y-%m-%d %H:%M UTC") if funding_at else None
    return FundingSnapshot(
        rate=rate,
        details=details,
        next_funding_at=funding_at,
        interval_hours=interval_hours if interval_hours and interval_hours > 0 else None,
    )


def fetch_funding_rate(bybit_symbol: str) -> float | None:
    snapshot = fetch_funding_snapshot(bybit_to_okx_inst_id(bybit_symbol))
    return None if snapshot is None else snapshot.rate


def fetch_orderbook(
    instrument: OkxInstrument,
    limit: int = 50,
) -> OrderBookSnapshot | None:
    try:
        response = requests.get(
            OKX_ORDERBOOK_URL,
            params={"instId": instrument.inst_id, "sz": limit},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[OKX] Error fetching orderbook for {instrument.inst_id}: {exc}")
        return None

    if payload.get("code") != "0" or not payload.get("data"):
        return None

    data = payload["data"][0]
    try:
        bids = tuple((float(level[0]), float(level[1])) for level in data.get("bids", []))
        asks = tuple((float(level[0]), float(level[1])) for level in data.get("asks", []))
    except (TypeError, ValueError, IndexError):
        return None

    if not bids or not asks:
        return None

    timestamp_ms = data.get("ts")
    return OrderBookSnapshot(
        bids=bids,
        asks=asks,
        timestamp_ms=int(timestamp_ms) if timestamp_ms else None,
        quantity_multiplier=instrument.contract_value * instrument.contract_multiplier,
    )


def fetch_funding_history(
    inst_id: str,
    limit: int = 6,
) -> list[FundingRatePoint]:
    try:
        response = requests.get(
            OKX_FUNDING_HISTORY_URL,
            params={"instId": inst_id, "limit": limit},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[OKX] Error fetching funding history for {inst_id}: {exc}")
        return []

    if payload.get("code") != "0":
        return []

    points: list[FundingRatePoint] = []
    for item in payload.get("data", []):
        funded_at = _parse_timestamp_ms(item.get("fundingTime"))
        rate = _parse_float(item.get("realizedRate") or item.get("fundingRate"))
        if funded_at is not None and rate is not None:
            points.append(FundingRatePoint(rate=rate, funded_at=funded_at))
    return points


def fetch_open_interest_usdt(inst_id: str) -> float | None:
    try:
        response = requests.get(
            OKX_OPEN_INTEREST_URL,
            params={"instType": "SWAP", "instId": inst_id},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[OKX] Error fetching open interest for {inst_id}: {exc}")
        return None

    if payload.get("code") != "0" or not payload.get("data"):
        return None
    return _parse_float(payload["data"][0].get("oiUsd"))
