import unittest

from bot.models import Candle
from bot.services.max_surge import calculate_max_surge


def candle(date: str, *, low: float, high: float) -> Candle:
    return Candle(
        date=date,
        open=100.0,
        high=high,
        low=low,
        close=100.0,
        volume=0.0,
        turnover=0.0,
    )


class MaxSurgeTests(unittest.TestCase):
    def test_finds_drawup_inside_window_not_only_at_endpoints(self) -> None:
        candles = [
            candle("2026-01-01", low=100.0, high=101.0),
            candle("2026-01-02", low=100.0, high=200.0),
            candle("2026-01-03", low=100.0, high=101.0),
        ]

        self.assertEqual(calculate_max_surge(candles, 3), (1.0, "2026-01-01"))

    def test_rejects_window_larger_than_history(self) -> None:
        candles = [candle("2026-01-01", low=100.0, high=101.0)]

        self.assertIsNone(calculate_max_surge(candles, 2))


if __name__ == "__main__":
    unittest.main()
