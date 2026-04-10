import unittest

from bot.models import Candle
from bot.services.funding import rank_funding_entries
from bot.services.turnover import rank_turnover_entries
from bot.services.volatility import analyze_market_data, normalize_symbol


def build_candles() -> list[Candle]:
    candles: list[Candle] = []
    for day in range(1, 31):
        open_price = 100.0 + day
        close_price = open_price + (day % 5) - 2
        high_price = open_price * 1.08
        low_price = open_price * 0.94
        candles.append(
            Candle(
                date=f"2026-01-{day:02d}",
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=1000 + day,
                turnover=5000 + day * 10,
            )
        )
    return candles


class VolatilityServiceTests(unittest.TestCase):
    def test_normalize_symbol_appends_usdt(self) -> None:
        self.assertEqual(normalize_symbol("btc"), "BTCUSDT")
        self.assertEqual(normalize_symbol("ethusdt"), "ETHUSDT")

    def test_analyze_market_data_returns_stats(self) -> None:
        stats = analyze_market_data(build_candles())

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertGreater(stats.vol_day, 0)
        self.assertGreater(stats.atr_14, 0)
        self.assertAlmostEqual(stats.max_pump_val, 0.08)
        self.assertLess(stats.max_dump_val, 0)
        self.assertGreaterEqual(stats.p99_pump, stats.p75_pump)


class FundingServiceTests(unittest.TestCase):
    def test_rank_funding_entries_sorts_by_sign(self) -> None:
        tickers = [
            {"symbol": "AAAUSDT", "fundingRate": "-0.010"},
            {"symbol": "BBBUSDT", "fundingRate": "-0.025"},
            {"symbol": "CCCUSDT", "fundingRate": "0.030"},
            {"symbol": "DDDUSDT", "fundingRate": "0.010"},
            {"symbol": "EEEUSDC", "fundingRate": "-0.500"},
        ]

        negative = rank_funding_entries(tickers, positive=False)
        positive = rank_funding_entries(tickers, positive=True)

        self.assertEqual(negative, [("BBBUSDT", -0.025), ("AAAUSDT", -0.01)])
        self.assertEqual(positive, [("CCCUSDT", 0.03), ("DDDUSDT", 0.01)])


class TurnoverServiceTests(unittest.TestCase):
    def test_rank_turnover_entries_orders_and_offsets_results(self) -> None:
        tickers = [
            {"symbol": "AAAUSDT", "turnover24h": "1200"},
            {"symbol": "BBBUSDT", "turnover24h": "800"},
            {"symbol": "CCCUSDT", "turnover24h": "4500"},
            {"symbol": "DDDUSDC", "turnover24h": "1"},
        ]

        lowest = rank_turnover_entries(tickers, order="min", offset=0, total=2)
        highest = rank_turnover_entries(tickers, order="max", offset=1, total=1)

        self.assertEqual([entry.symbol for entry in lowest], ["BBBUSDT", "AAAUSDT"])
        self.assertEqual([entry.symbol for entry in highest], ["AAAUSDT"])


if __name__ == "__main__":
    unittest.main()
