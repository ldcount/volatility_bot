from __future__ import annotations

import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import UTC, datetime

from bot.clients.bybit import (
    fetch_all_tickers,
    fetch_funding_history as fetch_bybit_funding_history,
    fetch_orderbook as fetch_bybit_orderbook,
)
from bot.clients.okx import (
    fetch_funding_history as fetch_okx_funding_history,
    fetch_funding_snapshot,
    fetch_open_interest_usdt,
    fetch_orderbook as fetch_okx_orderbook,
    fetch_usdt_swap_instruments,
)
from bot.config import (
    get_bybit_taker_fee_rate,
    get_funding_history_samples,
    get_funding_notional_usdt,
    get_funding_prefilter_limit,
    get_funding_safety_haircut_ratio,
    get_okx_taker_fee_rate,
)
from bot.models import (
    FundingDiffEntry,
    FundingRatePoint,
    FundingSnapshot,
    LiquidityMetrics,
    OkxInstrument,
    OrderBookSnapshot,
)


FUNDING_HORIZON_HOURS = 8.0
NEAR_MARKET_DEPTH_BAND = 0.005


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
        return datetime.fromtimestamp(int(str(timestamp_ms)) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def build_bybit_funding_index(tickers: list[dict]) -> dict[str, FundingSnapshot]:
    indexed_funding: dict[str, FundingSnapshot] = {}
    for ticker in tickers:
        symbol = _normalize_bybit_symbol(ticker.get("symbol", ""))
        funding_rate = _parse_float(ticker.get("fundingRate"))
        if symbol is None or funding_rate is None:
            continue

        next_funding_at = _parse_timestamp_ms(ticker.get("nextFundingTime"))
        interval_hours = _parse_float(ticker.get("fundingIntervalHour"))
        details = (
            next_funding_at.strftime("%Y-%m-%d %H:%M UTC")
            if next_funding_at is not None
            else None
        )
        indexed_funding[symbol] = FundingSnapshot(
            rate=funding_rate,
            details=details,
            next_funding_at=next_funding_at,
            interval_hours=interval_hours if interval_hours and interval_hours > 0 else None,
            bid_price=_parse_float(ticker.get("bid1Price")),
            ask_price=_parse_float(ticker.get("ask1Price")),
            mark_price=_parse_float(ticker.get("markPrice")),
            open_interest_usdt=_parse_float(ticker.get("openInterestValue")),
        )
    return indexed_funding


def normalize_funding_rate(
    snapshot: FundingSnapshot,
    horizon_hours: float = FUNDING_HORIZON_HOURS,
) -> float:
    interval_hours = snapshot.interval_hours or horizon_hours
    return snapshot.rate * horizon_hours / interval_hours


def analyze_orderbook(
    orderbook: OrderBookSnapshot,
    *,
    side: str,
    notional_usdt: float,
    open_interest_usdt: float | None = None,
) -> LiquidityMetrics | None:
    if not orderbook.bids or not orderbook.asks or notional_usdt <= 0:
        return None

    best_bid = orderbook.bids[0][0]
    best_ask = orderbook.asks[0][0]
    mid_price = (best_bid + best_ask) / 2
    if best_bid <= 0 or best_ask <= 0 or mid_price <= 0 or best_ask < best_bid:
        return None

    spread_rate = (best_ask - best_bid) / mid_price
    levels = orderbook.asks if side == "buy" else orderbook.bids
    best_execution_price = best_ask if side == "buy" else best_bid

    depth_near_market_usdt = 0.0
    remaining_notional = notional_usdt
    executed_base_quantity = 0.0
    executed_quote_value = 0.0

    for price, quantity in levels:
        if price <= 0 or quantity <= 0:
            continue

        if side == "buy":
            is_near_market = price <= mid_price * (1 + NEAR_MARKET_DEPTH_BAND)
        else:
            is_near_market = price >= mid_price * (1 - NEAR_MARKET_DEPTH_BAND)

        available_notional = price * quantity * orderbook.quantity_multiplier
        if is_near_market:
            depth_near_market_usdt += available_notional

        if remaining_notional <= 0:
            continue
        taken_notional = min(available_notional, remaining_notional)
        executed_base_quantity += taken_notional / price
        executed_quote_value += taken_notional
        remaining_notional -= taken_notional

    filled_notional = notional_usdt - max(remaining_notional, 0.0)
    fill_ratio = min(1.0, filled_notional / notional_usdt)
    entry_slippage_rate = None
    if fill_ratio >= 0.999999 and executed_base_quantity > 0:
        vwap = executed_quote_value / executed_base_quantity
        if side == "buy":
            entry_slippage_rate = max(0.0, vwap / best_execution_price - 1)
        else:
            entry_slippage_rate = max(0.0, 1 - vwap / best_execution_price)

    return LiquidityMetrics(
        best_bid=best_bid,
        best_ask=best_ask,
        spread_rate=spread_rate,
        entry_slippage_rate=entry_slippage_rate,
        depth_near_market_usdt=depth_near_market_usdt,
        fill_ratio=fill_ratio,
        open_interest_usdt=open_interest_usdt,
    )


def _historical_persistence(
    bybit_history: list[FundingRatePoint],
    okx_history: list[FundingRatePoint],
    *,
    bybit_interval_hours: float,
    okx_interval_hours: float,
    short_exchange: str,
) -> tuple[float | None, float | None, int]:
    sample_count = min(len(bybit_history), len(okx_history))
    if sample_count == 0:
        return None, None, 0

    directed_edges: list[float] = []
    for bybit_point, okx_point in zip(
        bybit_history[:sample_count],
        okx_history[:sample_count],
    ):
        bybit_rate = bybit_point.rate * FUNDING_HORIZON_HOURS / bybit_interval_hours
        okx_rate = okx_point.rate * FUNDING_HORIZON_HOURS / okx_interval_hours
        if short_exchange == "Bybit":
            directed_edges.append(bybit_rate - okx_rate)
        else:
            directed_edges.append(okx_rate - bybit_rate)

    persistence_ratio = sum(edge > 0 for edge in directed_edges) / sample_count
    return persistence_ratio, statistics.mean(directed_edges), sample_count


def _initial_opportunity(
    symbol: str,
    bybit: FundingSnapshot,
    okx: FundingSnapshot,
    *,
    notional_usdt: float,
    round_trip_fee_rate: float,
    safety_haircut_ratio: float,
    screened_contracts: int,
    shared_contracts: int,
) -> FundingDiffEntry:
    bybit_normalized = normalize_funding_rate(bybit)
    okx_normalized = normalize_funding_rate(okx)
    if bybit_normalized >= okx_normalized:
        short_exchange, long_exchange = "Bybit", "OKX"
    else:
        short_exchange, long_exchange = "OKX", "Bybit"

    warnings: list[str] = []
    if bybit.interval_hours is None:
        warnings.append("Bybit interval unavailable; assumed 8h")
    if okx.interval_hours is None:
        warnings.append("OKX interval unavailable; assumed 8h")

    return FundingDiffEntry(
        symbol=symbol,
        funding_diff=abs(bybit_normalized - okx_normalized),
        bybit=bybit,
        okx=okx,
        long_exchange=long_exchange,
        short_exchange=short_exchange,
        horizon_hours=FUNDING_HORIZON_HOURS,
        notional_usdt=notional_usdt,
        round_trip_fee_rate=round_trip_fee_rate,
        safety_haircut_ratio=safety_haircut_ratio,
        screened_contracts=screened_contracts,
        shared_contracts=shared_contracts,
        warnings=tuple(warnings),
    )


def _enrich_opportunity(
    entry: FundingDiffEntry,
    instrument: OkxInstrument,
    *,
    history_limit: int,
    safety_haircut_ratio: float,
) -> FundingDiffEntry:
    bybit_book = fetch_bybit_orderbook(entry.symbol, "linear", 50)
    okx_book = fetch_okx_orderbook(instrument, 50)
    bybit_history = fetch_bybit_funding_history(entry.symbol, history_limit)
    okx_history = fetch_okx_funding_history(instrument.inst_id, history_limit)
    okx_open_interest = fetch_open_interest_usdt(instrument.inst_id)

    bybit_side = "buy" if entry.long_exchange == "Bybit" else "sell"
    okx_side = "buy" if entry.long_exchange == "OKX" else "sell"
    bybit_liquidity = (
        analyze_orderbook(
            bybit_book,
            side=bybit_side,
            notional_usdt=entry.notional_usdt,
            open_interest_usdt=entry.bybit.open_interest_usdt,
        )
        if bybit_book is not None
        else None
    )
    okx_liquidity = (
        analyze_orderbook(
            okx_book,
            side=okx_side,
            notional_usdt=entry.notional_usdt,
            open_interest_usdt=okx_open_interest,
        )
        if okx_book is not None
        else None
    )

    warnings = list(entry.warnings)
    spread_cost_rate = None
    slippage_cost_rate = None
    net_edge = None
    safety_adjusted_edge = None
    if bybit_liquidity is None or okx_liquidity is None:
        warnings.append("Orderbook unavailable; executable cost not estimated")
    elif (
        bybit_liquidity.entry_slippage_rate is None
        or okx_liquidity.entry_slippage_rate is None
    ):
        warnings.append("Configured notional cannot be filled from sampled books")
    else:
        # A round trip crosses one full spread per venue. Slippage beyond the
        # best quote is doubled as a conservative estimate for entry and exit.
        spread_cost_rate = bybit_liquidity.spread_rate + okx_liquidity.spread_rate
        slippage_cost_rate = 2 * (
            bybit_liquidity.entry_slippage_rate
            + okx_liquidity.entry_slippage_rate
        )
        total_cost_rate = (
            entry.round_trip_fee_rate + spread_cost_rate + slippage_cost_rate
        )
        net_edge = entry.funding_diff - total_cost_rate
        safety_adjusted_edge = (
            entry.funding_diff * (1 - safety_haircut_ratio) - total_cost_rate
        )

    persistence_ratio, historical_avg_edge, sample_count = _historical_persistence(
        bybit_history,
        okx_history,
        bybit_interval_hours=entry.bybit.interval_hours or FUNDING_HORIZON_HOURS,
        okx_interval_hours=entry.okx.interval_hours or FUNDING_HORIZON_HOURS,
        short_exchange=entry.short_exchange,
    )
    if sample_count == 0:
        warnings.append("Funding persistence history unavailable")

    return replace(
        entry,
        spread_cost_rate=spread_cost_rate,
        slippage_cost_rate=slippage_cost_rate,
        net_edge=net_edge,
        safety_adjusted_edge=safety_adjusted_edge,
        persistence_ratio=persistence_ratio,
        historical_avg_edge=historical_avg_edge,
        history_samples=sample_count,
        bybit_liquidity=bybit_liquidity,
        okx_liquidity=okx_liquidity,
        warnings=tuple(warnings),
    )


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

    shared_contracts = len(common_symbols)
    prefilter_limit = max(limit * 2, max(1, get_funding_prefilter_limit()))
    common_symbols.sort(
        key=lambda symbol: (
            -abs(normalize_funding_rate(bybit_funding[symbol])),
            symbol,
        )
    )
    common_symbols = common_symbols[:prefilter_limit]
    screened_contracts = len(common_symbols)

    okx_funding: dict[str, FundingSnapshot] = {}
    max_workers = min(16, len(common_symbols)) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {
            executor.submit(
                fetch_funding_snapshot,
                okx_instruments[symbol].inst_id,
            ): symbol
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

    notional_usdt = max(1.0, get_funding_notional_usdt())
    round_trip_fee_rate = 2 * (
        max(0.0, get_bybit_taker_fee_rate())
        + max(0.0, get_okx_taker_fee_rate())
    )
    safety_haircut_ratio = min(1.0, max(0.0, get_funding_safety_haircut_ratio()))
    history_limit = max(1, get_funding_history_samples())

    opportunities = [
        _initial_opportunity(
            symbol,
            bybit_funding[symbol],
            okx_funding[symbol],
            notional_usdt=notional_usdt,
            round_trip_fee_rate=round_trip_fee_rate,
            safety_haircut_ratio=safety_haircut_ratio,
            screened_contracts=screened_contracts,
            shared_contracts=shared_contracts,
        )
        for symbol in common_symbols
        if symbol in okx_funding
    ]
    opportunities.sort(key=lambda item: (-item.funding_diff, item.symbol))

    # Enrich a wider gross-edge pool, then rerank on safety-adjusted net edge.
    enrichment_pool = opportunities[: min(len(opportunities), max(limit * 2, 10))]
    enriched: list[FundingDiffEntry] = []
    with ThreadPoolExecutor(max_workers=min(8, len(enrichment_pool)) or 1) as executor:
        future_to_entry = {
            executor.submit(
                _enrich_opportunity,
                entry,
                okx_instruments[entry.symbol],
                history_limit=history_limit,
                safety_haircut_ratio=safety_haircut_ratio,
            ): entry
            for entry in enrichment_pool
        }
        for future in as_completed(future_to_entry):
            original = future_to_entry[future]
            try:
                enriched.append(future.result())
            except Exception as exc:
                print(f"[FundingDiff] Error enriching {original.symbol}: {exc}")
                enriched.append(
                    replace(
                        original,
                        warnings=original.warnings + ("Decision enrichment failed",),
                    )
                )

    enriched.sort(
        key=lambda item: (
            -(
                item.safety_adjusted_edge
                if item.safety_adjusted_edge is not None
                else float("-inf")
            ),
            -item.funding_diff,
            item.symbol,
        )
    )
    return enriched[:limit]
