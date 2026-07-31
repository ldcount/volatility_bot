from __future__ import annotations

from datetime import UTC, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.config import get_display_timezone_name


def get_display_timezone() -> tzinfo:
    """Return the configured reporting timezone, falling back safely to UTC."""
    timezone_name = get_display_timezone_name()
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        print(
            f"[Timezone] Unknown DISPLAY_TIMEZONE '{timezone_name}'; using UTC."
        )
        return UTC
