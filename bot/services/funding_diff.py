from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta

from bot.clients.bybit import fetch_all_tickers
from bot.clients.okx import fetch_funding_snapshot, fetch_usdt_swap_instruments
from bot.models import FundingDiffEntry, FundingSnapshot


def _parse_float(value: object) -> float | None:
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_bybit_symbol(symbol: str) -> str | None:
    normalized = symbol.upper()
    if not normalized.endswith("USDT"):
        return None
    return normalized


def _parse_timestamp_ms(timestamp_ms: object) -> datetime | None:
    if timestamp_ms in (None, "", "0"):
        return None

    try:
        timestamp = int(str(timestamp_ms)) / 1000
    except (TypeError, ValueError):
        return None

    try:
        return datetime.fromtimestamp(timestamp, tz=UTC)
    except OSError:
        return None


def _format_timestamp_ms(timestamp_ms: object) -> str | None:
    parsed_timestamp = _parse_timestamp_ms(timestamp_ms)
    if parsed_timestamp is None:
        return None
    return parsed_timestamp.strftime("%Y-%m-%d %H:%M UTC")


def _format_interval_hours(interval_hours: object) -> str | None:
    parsed_hours = _parse_float(interval_hours)
    if parsed_hours is None:
        return None

    if parsed_hours.is_integer():
        return f"{int(parsed_hours)}h"
    return f"{parsed_hours:g}h"


def _build_bybit_details(ticker: dict) -> str | None:
    direct_timestamp = (
        _format_timestamp_ms(ticker.get("fundingTime"))
        or _format_timestamp_ms(ticker.get("fundingTimestamp"))
    )
    if direct_timestamp:
        return direct_timestamp

    next_funding_time = _parse_timestamp_ms(ticker.get("nextFundingTime"))
    interval_hours = _parse_float(ticker.get("fundingIntervalHour"))
    if next_funding_time is not None and interval_hours is not None:
        # Bybit exposes the next settlement time in ticker data, so we step
        # back one interval to approximate the timestamp of the current rate.
        inferred_timestamp = next_funding_time - timedelta(hours=interval_hours)
        return inferred_timestamp.strftime("%Y-%m-%d %H:%M UTC")

    return _format_interval_hours(ticker.get("fundingIntervalHour"))


def build_bybit_funding_index(tickers: list[dict]) -> dict[str, FundingSnapshot]:
    indexed_funding: dict[str, FundingSnapshot] = {}
    for ticker in tickers:
        symbol = _normalize_bybit_symbol(ticker.get("symbol", ""))
        if symbol is None:
            continue

        funding_rate = _parse_float(ticker.get("fundingRate"))
        if funding_rate is None:
            continue

        indexed_funding[symbol] = FundingSnapshot(
            rate=funding_rate,
            details=_build_bybit_details(ticker),
        )

    return indexed_funding


def get_top_funding_diff(limit: int = 10) -> list[FundingDiffEntry]:
    bybit_funding = build_bybit_funding_index(fetch_all_tickers("linear"))
    if not bybit_funding:
        return []

    okx_instruments = fetch_usdt_swap_instruments()
    if not okx_instruments:
        return []

    common_symbols = sorted(set(bybit_funding).intersection(okx_instruments))
    if not common_symbols:
        return []

    okx_funding: dict[str, FundingSnapshot] = {}
    max_workers = min(16, len(common_symbols)) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {
            executor.submit(fetch_funding_snapshot, okx_instruments[symbol]): symbol
            for symbol in common_symbols
        }
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                snapshot = future.result()
            except Exception as exc:
                print(f"[FundingDiff] Error fetching OKX funding for {symbol}: {exc}")
                continue

            if snapshot is not None:
                okx_funding[symbol] = snapshot

    ranked_entries: list[FundingDiffEntry] = []
    for symbol in common_symbols:
        okx_snapshot = okx_funding.get(symbol)
        if okx_snapshot is None:
            continue

        bybit_snapshot = bybit_funding[symbol]
        funding_diff = abs(abs(bybit_snapshot.rate) - abs(okx_snapshot.rate))
        ranked_entries.append(
            FundingDiffEntry(
                symbol=symbol,
                funding_diff=funding_diff,
                bybit=bybit_snapshot,
                okx=okx_snapshot,
            )
        )

    ranked_entries.sort(key=lambda entry: (-entry.funding_diff, entry.symbol))
    return ranked_entries[:limit]
