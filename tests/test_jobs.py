import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.models import ChatSettings
from bot.services.jobs import (
    parse_rate_threshold,
    restore_scanning_jobs,
    scan_funding_job,
)


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
    @staticmethod
    def context(chat_id: int = 12345):
        send_message = AsyncMock()
        return SimpleNamespace(
            job=SimpleNamespace(chat_id=chat_id, schedule_removal=lambda: None),
            bot=SimpleNamespace(send_message=send_message),
        ), send_message

    async def test_scan_funding_job_sends_only_new_extreme_and_diff_alerts(self) -> None:
        extreme = SimpleNamespace(symbol="EXTREMEUSDT", bybit_rate=-0.03)
        diff = SimpleNamespace(symbol="DIFFUSDT", safety_adjusted_edge=0.0031)
        context, send_message = self.context()

        with (
            patch(
                "bot.services.jobs.get_chat_settings",
                return_value=SimpleNamespace(
                    alerts_enabled=True,
                    funding_threshold=-0.02,
                    alert_cooldown_seconds=3600,
                ),
            ),
            patch("bot.services.jobs.find_extreme_funding", return_value=[extreme]) as find,
            patch("bot.services.jobs.get_top_funding_diff", return_value=[diff]) as get_diff,
            patch(
                "bot.services.jobs.select_alert_changes",
                side_effect=[{"EXTREMEUSDT"}, {"DIFFUSDT"}],
            ) as select,
            patch(
                "bot.services.jobs.format_extreme_funding_alert",
                return_value="extreme-report",
            ),
            patch(
                "bot.services.jobs.format_funding_diff_report",
                return_value="diff-report",
            ),
            patch("bot.services.jobs.record_alert_notifications") as record,
        ):
            await scan_funding_job(context)

        find.assert_called_once_with(-0.02)
        get_diff.assert_called_once_with(5)
        self.assertEqual(select.call_count, 2)
        self.assertEqual(send_message.await_count, 2)
        self.assertEqual(send_message.await_args_list[0].kwargs["text"], "extreme-report")
        self.assertEqual(send_message.await_args_list[0].kwargs["parse_mode"], "HTML")
        self.assertEqual(send_message.await_args_list[1].kwargs["text"], "diff-report")
        self.assertEqual(record.call_count, 2)

    async def test_scan_funding_job_suppresses_unchanged_alerts(self) -> None:
        extreme = SimpleNamespace(symbol="EXTREMEUSDT", bybit_rate=-0.03)
        diff = SimpleNamespace(symbol="DIFFUSDT", safety_adjusted_edge=0.004)
        context, send_message = self.context()

        with (
            patch(
                "bot.services.jobs.get_chat_settings",
                return_value=SimpleNamespace(
                    alerts_enabled=True,
                    funding_threshold=-0.02,
                    alert_cooldown_seconds=3600,
                ),
            ),
            patch("bot.services.jobs.find_extreme_funding", return_value=[extreme]),
            patch("bot.services.jobs.get_top_funding_diff", return_value=[diff]),
            patch("bot.services.jobs.select_alert_changes", side_effect=[set(), set()]),
            patch(
                "bot.services.jobs.format_extreme_funding_alert",
                return_value=None,
            ) as extreme_format,
            patch("bot.services.jobs.format_funding_diff_report") as diff_format,
        ):
            await scan_funding_job(context)

        extreme_format.assert_called_once_with([])
        diff_format.assert_not_called()
        send_message.assert_not_awaited()

    async def test_scan_funding_job_ignores_diff_below_safe_threshold(self) -> None:
        diff = SimpleNamespace(symbol="DIFFUSDT", safety_adjusted_edge=0.0029)
        context, send_message = self.context()

        with (
            patch(
                "bot.services.jobs.get_chat_settings",
                return_value=SimpleNamespace(
                    alerts_enabled=True,
                    funding_threshold=-0.015,
                    alert_cooldown_seconds=3600,
                ),
            ),
            patch("bot.services.jobs.find_extreme_funding", return_value=[]),
            patch("bot.services.jobs.get_top_funding_diff", return_value=[diff]),
            patch("bot.services.jobs.select_alert_changes", side_effect=[set(), set()]) as select,
            patch("bot.services.jobs.format_extreme_funding_alert", return_value=None),
            patch("bot.services.jobs.format_funding_diff_report") as diff_format,
        ):
            await scan_funding_job(context)

        self.assertEqual(select.call_args_list[1].args[2], {})
        diff_format.assert_not_called()
        send_message.assert_not_awaited()


class RestoreSubscriptionsTests(unittest.TestCase):
    def test_restore_schedules_each_persisted_subscription(self) -> None:
        application = SimpleNamespace(job_queue=object())
        saved = ChatSettings(
            chat_id=321,
            funding_threshold=-0.012,
            scan_interval_seconds=1_800,
            alerts_enabled=True,
            alert_cooldown_seconds=900,
        )
        with (
            patch(
                "bot.services.jobs.list_subscribed_chat_settings",
                return_value=[saved],
            ),
            patch("bot.services.jobs.start_scanning_job") as start_job,
        ):
            restore_scanning_jobs(application)

        start_job.assert_called_once_with(
            application,
            321,
            interval_seconds=1_800,
        )

if __name__ == "__main__":
    unittest.main()
