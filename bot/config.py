import os

from dotenv import load_dotenv


DEFAULT_FUNDING_THRESHOLD = -0.015
DEFAULT_SCAN_INTERVAL = 18000
DEFAULT_FUNDING_NOTIONAL_USDT = 1000.0
DEFAULT_BYBIT_TAKER_FEE_RATE = 0.00055
DEFAULT_OKX_TAKER_FEE_RATE = 0.0005
DEFAULT_FUNDING_SAFETY_HAIRCUT_RATIO = 0.25
DEFAULT_FUNDING_HISTORY_SAMPLES = 6
DEFAULT_FUNDING_PREFILTER_LIMIT = 80
DEFAULT_ALERT_COOLDOWN = 3600
DEFAULT_ALERT_MATERIAL_CHANGE = 0.001


def load_environment() -> None:
    load_dotenv()


def get_runtime_environment() -> str:
    env_name = os.getenv("BOT_ENV", "dev").strip().lower()
    if env_name not in {"dev", "prod"}:
        raise RuntimeError("BOT_ENV must be either 'dev' or 'prod'.")
    return env_name


def get_required_token() -> str:
    env_name = get_runtime_environment()
    token_var = "TELEGRAM_TOKEN_PROD" if env_name == "prod" else "TELEGRAM_TOKEN_DEV"
    token = os.getenv(token_var, "")
    if not token:
        raise RuntimeError(f"{token_var} not found in .env file.")
    return token


def get_default_funding_threshold() -> float:
    return float(os.getenv("FUNDING_THRESHOLD", DEFAULT_FUNDING_THRESHOLD))


def get_default_scan_interval() -> int:
    return int(os.getenv("SCAN_INTERVAL", DEFAULT_SCAN_INTERVAL))


def get_funding_notional_usdt() -> float:
    return float(os.getenv("FUNDING_NOTIONAL_USDT", DEFAULT_FUNDING_NOTIONAL_USDT))


def get_bybit_taker_fee_rate() -> float:
    return float(os.getenv("BYBIT_TAKER_FEE_RATE", DEFAULT_BYBIT_TAKER_FEE_RATE))


def get_okx_taker_fee_rate() -> float:
    return float(os.getenv("OKX_TAKER_FEE_RATE", DEFAULT_OKX_TAKER_FEE_RATE))


def get_funding_safety_haircut_ratio() -> float:
    return float(
        os.getenv(
            "FUNDING_SAFETY_HAIRCUT_RATIO",
            DEFAULT_FUNDING_SAFETY_HAIRCUT_RATIO,
        )
    )


def get_funding_history_samples() -> int:
    return int(os.getenv("FUNDING_HISTORY_SAMPLES", DEFAULT_FUNDING_HISTORY_SAMPLES))


def get_funding_prefilter_limit() -> int:
    return int(os.getenv("FUNDING_PREFILTER_LIMIT", DEFAULT_FUNDING_PREFILTER_LIMIT))


def get_default_alert_cooldown() -> int:
    return int(os.getenv("ALERT_COOLDOWN", DEFAULT_ALERT_COOLDOWN))


def get_alert_material_change() -> float:
    return float(os.getenv("ALERT_MATERIAL_CHANGE", DEFAULT_ALERT_MATERIAL_CHANGE))
