import os

from dotenv import load_dotenv


DEFAULT_FUNDING_THRESHOLD = -0.015
DEFAULT_SCAN_INTERVAL = 3600


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
