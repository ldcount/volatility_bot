from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    timestamp: int | None = None


@dataclass(frozen=True)
class VolatilityStats:
    vol_day: float
    vol_week: float
    max_daily_surge: float
    max_daily_crash: float
    max_pump_val: float
    max_pump_date: str
    avg_pump: float
    std_pump: float
    max_dump_val: float
    max_dump_date: str
    avg_dump: float
    std_dump: float
    atr_14: float
    atr_28: float
    atr_relative: float
    p75_pump: float
    p80_pump: float
    p85_pump: float
    p90_pump: float
    p95_pump: float
    p99_pump: float
    avg_price_10: float | None
    avg_price_30: float | None
    avg_price_60: float | None
    avg_price_90: float | None
    downside_deviation: float
    max_drawdown: float
    current_close: float
    sma_30: float | None
    vwap_30: float | None
    distance_to_sma_30: float | None
    distance_to_vwap_30: float | None
    avg_turnover_30: float | None
    liquidity_adjusted_atr: float
    sample_start: str
    sample_end: str
    data_confidence: str



@dataclass(frozen=True)
class FundingEntry:
    symbol: str
    bybit_rate: float
    okx_rate: float | None


@dataclass(frozen=True)
class FundingSnapshot:
    rate: float
    details: str | None = None
    next_funding_at: datetime | None = None
    interval_hours: float | None = None
    bid_price: float | None = None
    ask_price: float | None = None
    mark_price: float | None = None
    open_interest_usdt: float | None = None


@dataclass(frozen=True)
class FundingRatePoint:
    rate: float
    funded_at: datetime


@dataclass(frozen=True)
class OrderBookSnapshot:
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]
    timestamp_ms: int | None = None
    quantity_multiplier: float = 1.0


@dataclass(frozen=True)
class OkxInstrument:
    inst_id: str
    contract_value: float
    contract_multiplier: float
    contract_value_currency: str


@dataclass(frozen=True)
class LiquidityMetrics:
    best_bid: float
    best_ask: float
    spread_rate: float
    entry_slippage_rate: float | None
    depth_near_market_usdt: float
    fill_ratio: float
    open_interest_usdt: float | None = None


@dataclass(frozen=True)
class FundingDiffEntry:
    symbol: str
    funding_diff: float
    bybit: FundingSnapshot
    okx: FundingSnapshot
    long_exchange: str = ""
    short_exchange: str = ""
    horizon_hours: float = 8.0
    notional_usdt: float = 0.0
    round_trip_fee_rate: float = 0.0
    safety_haircut_ratio: float = 0.0
    screened_contracts: int = 0
    shared_contracts: int = 0
    spread_cost_rate: float | None = None
    slippage_cost_rate: float | None = None
    net_edge: float | None = None
    safety_adjusted_edge: float | None = None
    persistence_ratio: float | None = None
    historical_avg_edge: float | None = None
    history_samples: int = 0
    bybit_liquidity: LiquidityMetrics | None = None
    okx_liquidity: LiquidityMetrics | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TurnoverEntry:
    symbol: str
    turnover_24h: float


@dataclass(frozen=True)
class ChatSettings:
    chat_id: int
    funding_threshold: float
    scan_interval_seconds: int
    alerts_enabled: bool
    alert_cooldown_seconds: int
