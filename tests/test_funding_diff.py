import unittest
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch

from bot.clients.okx import okx_inst_id_to_symbol
from bot.models import (
    FundingDiffEntry,
    FundingEntry,
    FundingSnapshot,
    LiquidityMetrics,
    OkxInstrument,
    OrderBookSnapshot,
)
from bot.reports import format_funding_diff_report, format_funding_report
from bot.services.funding_diff import analyze_orderbook, get_top_funding_diff


def instrument(symbol: str) -> OkxInstrument:
    return OkxInstrument(
        inst_id=symbol,
        contract_value=1.0,
        contract_multiplier=1.0,
        contract_value_currency=symbol.split("-")[0],
    )


class FundingDiffClientTests(unittest.TestCase):
    def test_okx_inst_id_to_symbol_normalizes_usdt_swap(self) -> None:
        self.assertEqual(okx_inst_id_to_symbol("RAVE-USDT-SWAP"), "RAVEUSDT")
        self.assertIsNone(okx_inst_id_to_symbol("RAVE-USDC-SWAP"))


class FundingDiffServiceTests(unittest.TestCase):
    @patch("bot.services.funding_diff._enrich_opportunity")
    @patch("bot.services.funding_diff.fetch_funding_snapshot")
    @patch("bot.services.funding_diff.fetch_usdt_swap_instruments")
    @patch("bot.services.funding_diff.fetch_all_tickers")
    def test_get_top_funding_diff_normalizes_intervals_and_ranks_safe_edge(
        self,
        mock_fetch_all_tickers,
        mock_fetch_usdt_swap_instruments,
        mock_fetch_funding_snapshot,
        mock_enrich,
    ) -> None:
        mock_fetch_all_tickers.return_value = [
            {"symbol": "ZZZUSDT", "fundingRate": "0.0100", "fundingIntervalHour": "8"},
            {"symbol": "AAAUSDT", "fundingRate": "0.0100", "fundingIntervalHour": "8"},
            {"symbol": "MIDUSDT", "fundingRate": "-0.0400", "fundingIntervalHour": "8"},
            {"symbol": "MISSUSDT", "fundingRate": "0.0200", "fundingIntervalHour": "8"},
            {"symbol": "OTHERUSDC", "fundingRate": "-0.5000", "fundingIntervalHour": "8"},
        ]
        mock_fetch_usdt_swap_instruments.return_value = {
            "AAAUSDT": instrument("AAA-USDT-SWAP"),
            "MIDUSDT": instrument("MID-USDT-SWAP"),
            "MISSUSDT": instrument("MISS-USDT-SWAP"),
            "ZZZUSDT": instrument("ZZZ-USDT-SWAP"),
        }
        mock_fetch_funding_snapshot.side_effect = lambda inst_id: {
            "AAA-USDT-SWAP": FundingSnapshot(rate=0.0050, interval_hours=1),
            "MID-USDT-SWAP": FundingSnapshot(rate=0.0100, interval_hours=4),
            "MISS-USDT-SWAP": None,
            "ZZZ-USDT-SWAP": FundingSnapshot(rate=0.0050, interval_hours=8),
        }[inst_id]
        mock_enrich.side_effect = lambda entry, _instrument, **_kwargs: replace(
            entry,
            net_edge=entry.funding_diff - 0.001,
            safety_adjusted_edge=entry.funding_diff - 0.002,
        )

        entries = get_top_funding_diff(limit=10)

        self.assertEqual(
            [entry.symbol for entry in entries],
            ["MIDUSDT", "AAAUSDT", "ZZZUSDT"],
        )
        # MID: -4% on Bybit versus +1% per 4h (= +2% per 8h).
        self.assertAlmostEqual(entries[0].funding_diff, 0.06)
        # AAA: +0.5% hourly becomes +4% on the common 8h horizon.
        self.assertAlmostEqual(entries[1].funding_diff, 0.03)
        self.assertEqual(entries[1].short_exchange, "OKX")
        self.assertEqual(entries[1].long_exchange, "Bybit")

    def test_analyze_orderbook_estimates_spread_slippage_and_depth(self) -> None:
        orderbook = OrderBookSnapshot(
            bids=((99.9, 20.0), (99.5, 20.0)),
            asks=((100.1, 5.0), (100.4, 10.0)),
        )

        metrics = analyze_orderbook(
            orderbook,
            side="buy",
            notional_usdt=1_000,
            open_interest_usdt=5_000_000,
        )

        self.assertIsNotNone(metrics)
        assert metrics is not None
        self.assertAlmostEqual(metrics.spread_rate, 0.002)
        self.assertEqual(metrics.fill_ratio, 1.0)
        self.assertGreater(metrics.entry_slippage_rate or 0.0, 0.0)
        self.assertGreater(metrics.depth_near_market_usdt, 1_000)
        self.assertEqual(metrics.open_interest_usdt, 5_000_000)


class FundingDiffReportTests(unittest.TestCase):
    def test_funding_report_escapes_unexpected_symbol_text(self) -> None:
        report = format_funding_report(
            [FundingEntry(symbol="BAD<&USDT", bybit_rate=-0.01, okx_rate=None)],
            "Negative <funding>",
        )

        self.assertIn("Negative &lt;funding&gt;", report)
        self.assertIn("BAD&lt;&amp;USDT", report)
        self.assertNotIn("BAD<&USDT", report)

    def test_format_funding_diff_report_includes_decision_inputs(self) -> None:
        settlement = datetime(2026, 7, 26, 16, tzinfo=UTC)
        liquidity = LiquidityMetrics(
            best_bid=99.9,
            best_ask=100.1,
            spread_rate=0.002,
            entry_slippage_rate=0.0001,
            depth_near_market_usdt=2_000_000,
            fill_ratio=1.0,
            open_interest_usdt=50_000_000,
        )
        report = format_funding_diff_report(
            [
                FundingDiffEntry(
                    symbol="BTCUSDT",
                    funding_diff=0.004,
                    bybit=FundingSnapshot(
                        rate=0.004,
                        interval_hours=8,
                        next_funding_at=settlement,
                    ),
                    okx=FundingSnapshot(
                        rate=0.0,
                        interval_hours=4,
                        next_funding_at=settlement,
                    ),
                    long_exchange="OKX",
                    short_exchange="Bybit",
                    notional_usdt=1_000,
                    round_trip_fee_rate=0.0021,
                    safety_haircut_ratio=0.25,
                    spread_cost_rate=0.0002,
                    slippage_cost_rate=0.0001,
                    net_edge=0.0016,
                    safety_adjusted_edge=0.0006,
                    persistence_ratio=2 / 3,
                    historical_avg_edge=0.001,
                    history_samples=6,
                    bybit_liquidity=liquidity,
                    okx_liquidity=liquidity,
                )
            ]
        )

        self.assertIn("Funding arbitrage decision screen", report)
        self.assertIn("ACTIONABLE CANDIDATE", report)
        self.assertIn("short Bybit / long OKX", report)
        self.assertIn(
            "Rates B/O: <code>0.400%/8h</code> / <code>0.000%/8h</code>",
            report,
        )
        self.assertIn("safe <code>0.060% ($0.60)</code>", report)
        self.assertIn("26 Jul 16:00 UTC (8h)", report)
        self.assertIn("Persistence: 67%/6", report)
        self.assertIn("OI B/O", report)


if __name__ == "__main__":
    unittest.main()
