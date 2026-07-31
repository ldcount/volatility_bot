from datetime import UTC, datetime
import unittest
from unittest.mock import patch

from bot.services.timezones import get_display_timezone


class DisplayTimezoneTests(unittest.TestCase):
    def test_paris_timezone_applies_summer_offset(self) -> None:
        with patch(
            "bot.services.timezones.get_display_timezone_name",
            return_value="Europe/Paris",
        ):
            display_timezone = get_display_timezone()

        timestamp = datetime(2025, 7, 31, 5, 30, tzinfo=UTC).timestamp()
        rendered = datetime.fromtimestamp(timestamp, tz=display_timezone)
        self.assertEqual(rendered.strftime("%H:%M %Z"), "07:30 CEST")

    def test_unknown_timezone_falls_back_to_utc(self) -> None:
        with patch(
            "bot.services.timezones.get_display_timezone_name",
            return_value="Not/A_Timezone",
        ):
            display_timezone = get_display_timezone()

        self.assertEqual(str(display_timezone), "UTC")


if __name__ == "__main__":
    unittest.main()
