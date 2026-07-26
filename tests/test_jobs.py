import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services.jobs import parse_rate_threshold, scan_funding_job


class ParseRateThresholdTests(unittest.TestCase):
    def test_accepts_negative_percent_with_comma(self) -> None:
        self.assertAlmostEqual(parse_rate_threshold("-1,2"), -0.012)

    def test_converts_positive_input_to_negative_threshold(self) -> None:
        self.assertAlmostEqual(parse_rate_threshold("1.5"), -0.015)

    def test_treats_sub_one_values_as_percentage_points(self) -> None:
        self.assertAlmostEqual(parse_rate_threshold("-0.5"), -0.005)
        self.assertAlmostEqual(parse_rate_threshold("-0.5%"), -0.005)

    def test_rejects_zero_or_invalid_range(self) -> None:
        with self.assertRaises(ValueError):
            parse_rate_threshold("0")

        with self.assertRaises(ValueError):
            parse_rate_threshold("-120")


class BackgroundFundingJobTests(unittest.IsolatedAsyncioTestCase):
    @patch("bot.services.jobs.format_funding_diff_report")
    @patch("bot.services.jobs.format_extreme_funding_alert")
    @patch("bot.services.jobs.get_top_funding_diff")
    @patch("bot.services.jobs.find_extreme_funding")
    async def test_scan_funding_job_sends_extreme_and_diff_reports(
        self,
        mock_find_extreme_funding,
        mock_get_top_funding_diff,
        mock_format_extreme_funding_alert,
        mock_format_funding_diff_report,
    ) -> None:
        mock_find_extreme_funding.return_value = ["extreme-entry"]
        mock_get_top_funding_diff.return_value = [SimpleNamespace(funding_diff=0.0031)]
        mock_format_extreme_funding_alert.return_value = "extreme-report"
        mock_format_funding_diff_report.return_value = "diff-report"

        send_message = AsyncMock()
        context = SimpleNamespace(
            job=SimpleNamespace(chat_id=12345),
            bot=SimpleNamespace(send_message=send_message),
            bot_data={"funding_threshold_12345": -0.02},
        )

        await scan_funding_job(context)

        mock_find_extreme_funding.assert_called_once_with(-0.02)
        mock_get_top_funding_diff.assert_called_once_with(5)
        self.assertEqual(send_message.await_count, 2)
        self.assertEqual(send_message.await_args_list[0].kwargs["text"], "extreme-report")
        self.assertEqual(send_message.await_args_list[1].kwargs["text"], "diff-report")

    @patch("bot.services.jobs.format_funding_diff_report")
    @patch("bot.services.jobs.format_extreme_funding_alert")
    @patch("bot.services.jobs.get_top_funding_diff")
    @patch("bot.services.jobs.find_extreme_funding")
    async def test_scan_funding_job_sends_diff_report_above_threshold_even_without_extreme_alert(
        self,
        mock_find_extreme_funding,
        mock_get_top_funding_diff,
        mock_format_extreme_funding_alert,
        mock_format_funding_diff_report,
    ) -> None:
        mock_find_extreme_funding.return_value = []
        mock_get_top_funding_diff.return_value = [SimpleNamespace(funding_diff=0.004)]
        mock_format_extreme_funding_alert.return_value = None
        mock_format_funding_diff_report.return_value = "diff-report"

        send_message = AsyncMock()
        context = SimpleNamespace(
            job=SimpleNamespace(chat_id=999),
            bot=SimpleNamespace(send_message=send_message),
            bot_data={},
        )

        await scan_funding_job(context)

        mock_find_extreme_funding.assert_called_once()
        mock_get_top_funding_diff.assert_called_once_with(5)
        self.assertEqual(send_message.await_count, 1)
        self.assertEqual(send_message.await_args.kwargs["text"], "diff-report")

    @patch("bot.services.jobs.format_funding_diff_report")
    @patch("bot.services.jobs.format_extreme_funding_alert")
    @patch("bot.services.jobs.get_top_funding_diff")
    @patch("bot.services.jobs.find_extreme_funding")
    async def test_scan_funding_job_skips_diff_report_at_or_below_threshold(
        self,
        mock_find_extreme_funding,
        mock_get_top_funding_diff,
        mock_format_extreme_funding_alert,
        mock_format_funding_diff_report,
    ) -> None:
        mock_find_extreme_funding.return_value = []
        mock_get_top_funding_diff.return_value = [
            SimpleNamespace(funding_diff=0.0029),
            SimpleNamespace(funding_diff=0.0025),
        ]
        mock_format_extreme_funding_alert.return_value = None

        send_message = AsyncMock()
        context = SimpleNamespace(
            job=SimpleNamespace(chat_id=999),
            bot=SimpleNamespace(send_message=send_message),
            bot_data={},
        )

        await scan_funding_job(context)

        mock_get_top_funding_diff.assert_called_once_with(5)
        mock_format_funding_diff_report.assert_not_called()
        send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
