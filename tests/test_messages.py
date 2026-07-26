from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bot.handlers.messages import handle_message


class TickerMessageTurnoverTests(unittest.IsolatedAsyncioTestCase):
    async def test_chart_uses_hourly_snapshots_of_rolling_24h_turnover(self) -> None:
        status_message = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(
            text="BTC",
            reply_text=AsyncMock(return_value=status_message),
            reply_photo=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(id=123),
            message=message,
        )
        context = SimpleNamespace()
        history = [
            {"timestamp": 1_700_000_000, "turnover": 100_000.0, "volume": 1.0},
            {"timestamp": 1_700_003_600, "turnover": 110_000.0, "volume": 1.1},
        ]

        with (
            patch("bot.handlers.messages.start_scanning_job"),
            patch(
                "bot.handlers.messages.validate_ticker",
                return_value=(True, "linear"),
            ),
            patch(
                "bot.handlers.messages.fetch_market_data",
                return_value=["daily-candle"],
            ) as fetch_market_data,
            patch(
                "bot.handlers.messages.analyze_market_data",
                return_value=object(),
            ),
            patch(
                "bot.handlers.messages.get_symbol_turnover_text",
                return_value="110,000 USDT",
            ),
            patch(
                "bot.handlers.messages.format_volatility_report",
                return_value="volatility-report",
            ),
            patch(
                "bot.handlers.messages.get_hourly_history",
                return_value=history,
            ) as get_history,
            patch(
                "bot.handlers.messages.generate_turnover_chart",
                return_value=b"png",
            ),
        ):
            await handle_message(update, context)

        fetch_market_data.assert_called_once_with("BTCUSDT", "linear", "D")
        get_history.assert_called_once_with("BTCUSDT", 24)
        message.reply_photo.assert_awaited_once()
        caption = message.reply_photo.await_args.kwargs["caption"]
        self.assertIn("Rolling 24H Turnover", caption)
        self.assertIn("last 2 hourly snapshots", caption)
        self.assertIn("Change vs prior snapshot", caption)
        self.assertEqual(message.reply_photo.await_args.kwargs["parse_mode"], "HTML")


if __name__ == "__main__":
    unittest.main()
