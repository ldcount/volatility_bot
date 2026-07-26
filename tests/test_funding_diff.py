import unittest
from unittest.mock import patch

from bot.clients.okx import okx_inst_id_to_symbol
from bot.models import FundingDiffEntry, FundingSnapshot
from bot.reports import format_funding_diff_report
from bot.services.funding_diff import get_top_funding_diff


class FundingDiffClientTests(unittest.TestCase):
    def test_okx_inst_id_to_symbol_normalizes_usdt_swap(self) -> None:
        self.assertEqual(okx_inst_id_to_symbol("RAVE-USDT-SWAP"), "RAVEUSDT")
        self.assertIsNone(okx_inst_id_to_symbol("RAVE-USDC-SWAP"))


class FundingDiffServiceTests(unittest.TestCase):
    @patch("bot.services.funding_diff.fetch_funding_snapshot")
    @patch("bot.services.funding_diff.fetch_usdt_swap_instruments")
    @patch("bot.services.funding_diff.fetch_all_tickers")
    def test_get_top_funding_diff_sorts_by_signed_rate_spread_and_symbol(
        self,
        mock_fetch_all_tickers,
        mock_fetch_usdt_swap_instruments,
        mock_fetch_funding_snapshot,
    ) -> None:
        mock_fetch_all_tickers.return_value = [
            {"symbol": "ZZZUSDT", "fundingRate": "0.0100", "fundingIntervalHour": "8"},
            {"symbol": "AAAUSDT", "fundingRate": "0.0100", "fundingIntervalHour": "8"},
            {"symbol": "MIDUSDT", "fundingRate": "-0.0400", "fundingIntervalHour": "8"},
            {"symbol": "MISSUSDT", "fundingRate": "0.0200", "fundingIntervalHour": "8"},
            {"symbol": "OTHERUSDC", "fundingRate": "-0.5000", "fundingIntervalHour": "8"},
        ]
        mock_fetch_usdt_swap_instruments.return_value = {
            "AAAUSDT": "AAA-USDT-SWAP",
            "MIDUSDT": "MID-USDT-SWAP",
            "MISSUSDT": "MISS-USDT-SWAP",
            "ZZZUSDT": "ZZZ-USDT-SWAP",
        }
        mock_fetch_funding_snapshot.side_effect = lambda inst_id: {
            "AAA-USDT-SWAP": FundingSnapshot(rate=0.0050, details="1h"),
            "MID-USDT-SWAP": FundingSnapshot(rate=0.0100, details="4h"),
            "MISS-USDT-SWAP": None,
            "ZZZ-USDT-SWAP": FundingSnapshot(rate=0.0050, details="8h"),
        }[inst_id]

        entries = get_top_funding_diff(limit=10)

        self.assertEqual([entry.symbol for entry in entries], ["MIDUSDT", "AAAUSDT", "ZZZUSDT"])
        # Opposite-sign rates compound the delta-neutral funding edge:
        # short OKX receives 1%, while long Bybit receives 4%.
        self.assertAlmostEqual(entries[0].funding_diff, 0.05)
        self.assertEqual(entries[1].okx.details, "1h")


class FundingDiffReportTests(unittest.TestCase):
    def test_format_funding_diff_report_includes_details(self) -> None:
        report = format_funding_diff_report(
            [
                FundingDiffEntry(
                    symbol="BTCUSDT",
                    funding_diff=0.00175,
                    bybit=FundingSnapshot(rate=0.0010, details="8h"),
                    okx=FundingSnapshot(rate=-0.00075, details="4h"),
                )
            ]
        )

        self.assertIn("💱*Funding arbitrage: Bybit - OKX*", report)
        self.assertIn("*BTCUSDT*", report)
        self.assertIn(
            "Diff: `0.18%` | `0.10%` | `-0.07%`",
            report,
        )
        self.assertIn("Direction: `Short Bybit / Long OKX`", report)


if __name__ == "__main__":
    unittest.main()
