from __future__ import annotations

import os
import sqlite3
import unittest

from bot.services.db import (
    get_chat_settings,
    init_db,
    list_subscribed_chat_settings,
    record_alert_notifications,
    select_alert_changes,
    update_chat_settings,
)


class ChatSettingsPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = "test_settings.db"
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(self.db_path + suffix):
                os.remove(self.db_path + suffix)
        init_db(self.db_path)

    def tearDown(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(self.db_path + suffix):
                os.remove(self.db_path + suffix)

    def test_chat_settings_survive_independent_database_reads(self) -> None:
        defaults = get_chat_settings(123, self.db_path)
        self.assertEqual(defaults.scan_interval_seconds, 18_000)
        self.assertTrue(defaults.alerts_enabled)

        update_chat_settings(
            123,
            funding_threshold=-0.012,
            scan_interval_seconds=1_800,
            alerts_enabled=False,
            alert_cooldown_seconds=900,
            db_path=self.db_path,
        )
        saved = get_chat_settings(123, self.db_path)

        self.assertAlmostEqual(saved.funding_threshold, -0.012)
        self.assertEqual(saved.scan_interval_seconds, 1_800)
        self.assertEqual(saved.alert_cooldown_seconds, 900)
        self.assertFalse(saved.alerts_enabled)
        self.assertEqual(list_subscribed_chat_settings(self.db_path), [])

        update_chat_settings(123, alerts_enabled=True, db_path=self.db_path)
        self.assertEqual(
            [item.chat_id for item in list_subscribed_chat_settings(self.db_path)],
            [123],
        )

    def test_init_migrates_a_legacy_turnover_only_database(self) -> None:
        legacy_path = "test_legacy_settings.db"
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(legacy_path + suffix):
                os.remove(legacy_path + suffix)
        try:
            conn = sqlite3.connect(legacy_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE hourly_turnover (
                        symbol TEXT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        turnover REAL NOT NULL,
                        volume REAL NOT NULL,
                        PRIMARY KEY (symbol, timestamp)
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            init_db(legacy_path)
            settings = get_chat_settings(999, legacy_path)
            self.assertEqual(settings.chat_id, 999)

            conn = sqlite3.connect(legacy_path)
            try:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                conn.close()
            self.assertIn("hourly_turnover", tables)
            self.assertIn("chat_settings", tables)
            self.assertIn("alert_state", tables)
        finally:
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(legacy_path + suffix):
                    os.remove(legacy_path + suffix)

    def test_alerts_fire_on_crossing_or_material_change_after_cooldown(self) -> None:
        first = select_alert_changes(
            123,
            "extreme_funding",
            {"BTCUSDT": -0.02},
            material_change=0.001,
            cooldown_seconds=3_600,
            now=1_000,
            db_path=self.db_path,
        )
        record_alert_notifications(
            123,
            "extreme_funding",
            {"BTCUSDT": -0.02},
            now=1_000,
            db_path=self.db_path,
        )
        duplicate = select_alert_changes(
            123,
            "extreme_funding",
            {"BTCUSDT": -0.02},
            material_change=0.001,
            cooldown_seconds=3_600,
            now=2_000,
            db_path=self.db_path,
        )
        during_cooldown = select_alert_changes(
            123,
            "extreme_funding",
            {"BTCUSDT": -0.023},
            material_change=0.001,
            cooldown_seconds=3_600,
            now=3_000,
            db_path=self.db_path,
        )
        after_cooldown = select_alert_changes(
            123,
            "extreme_funding",
            {"BTCUSDT": -0.023},
            material_change=0.001,
            cooldown_seconds=3_600,
            now=4_601,
            db_path=self.db_path,
        )

        self.assertEqual(first, {"BTCUSDT"})
        self.assertEqual(duplicate, set())
        self.assertEqual(during_cooldown, set())
        self.assertEqual(after_cooldown, {"BTCUSDT"})
        record_alert_notifications(
            123,
            "extreme_funding",
            {"BTCUSDT": -0.023},
            now=4_601,
            db_path=self.db_path,
        )

        select_alert_changes(
            123,
            "extreme_funding",
            {},
            material_change=0.001,
            cooldown_seconds=3_600,
            now=4_700,
            db_path=self.db_path,
        )
        reentry = select_alert_changes(
            123,
            "extreme_funding",
            {"BTCUSDT": -0.023},
            material_change=0.001,
            cooldown_seconds=3_600,
            now=4_800,
            db_path=self.db_path,
        )
        self.assertEqual(reentry, {"BTCUSDT"})

    def test_missing_limited_rank_entry_is_not_treated_as_threshold_exit(self) -> None:
        record_alert_notifications(
            123,
            "funding_arbitrage",
            {"BTCUSDT": 0.004},
            now=1_000,
            db_path=self.db_path,
        )
        hidden_from_top_results = select_alert_changes(
            123,
            "funding_arbitrage",
            {},
            material_change=0.001,
            cooldown_seconds=0,
            inactive_symbols=set(),
            now=2_000,
            db_path=self.db_path,
        )
        unchanged_reappearance = select_alert_changes(
            123,
            "funding_arbitrage",
            {"BTCUSDT": 0.004},
            material_change=0.001,
            cooldown_seconds=0,
            inactive_symbols=set(),
            now=3_000,
            db_path=self.db_path,
        )

        self.assertEqual(hidden_from_top_results, set())
        self.assertEqual(unchanged_reappearance, set())


if __name__ == "__main__":
    unittest.main()
