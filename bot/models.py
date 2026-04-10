from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float


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


@dataclass(frozen=True)
class FundingEntry:
    symbol: str
    bybit_rate: float
    okx_rate: float | None


@dataclass(frozen=True)
class TurnoverEntry:
    symbol: str
    turnover_24h: float
