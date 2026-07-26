import unittest
from unittest.mock import patch

from bot.clients.bybit import fetch_candles


class BybitCandleTests(unittest.TestCase):
    @patch("bot.clients.bybit.time.time", return_value=1767355200.0)
    @patch("bot.clients.bybit.HTTP")
    def test_fetch_candles_excludes_active_daily_candle(
        self,
        mock_http,
        _mock_time,
    ) -> None:
        # 2026-01-02 12:00 UTC: the Jan 2 daily candle is still active.
        mock_http.return_value.get_kline.return_value = {
            "result": {
                "list": [
                    ["1767312000000", "110", "120", "105", "115", "10", "1100"],
                    ["1767225600000", "100", "112", "95", "110", "9", "900"],
                ]
            }
        }

        candles = fetch_candles("BTCUSDT", "linear", "D")

        self.assertIsNotNone(candles)
        assert candles is not None
        self.assertEqual([item.date for item in candles], ["2026-01-01"])


if __name__ == "__main__":
    unittest.main()
