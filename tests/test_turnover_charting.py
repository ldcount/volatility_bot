from __future__ import annotations

import os
import time
import unittest
from datetime import datetime, timedelta, timezone

from bot.services.charts import (
    generate_turnover_chart,
    get_turnover_annotation_indices,
)
from bot.services.db import (
    cleanup_old_records,
    get_connection,
    get_daily_history,
    get_hourly_history,
    init_db,
    save_hourly_snapshots,
)


class TurnoverDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = "test_bot.db"
        # Ensure clean state
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        init_db(self.db_path)

    def tearDown(self) -> None:
        # Clean up database files
        for suffix in ["", "-wal", "-shm"]:
            path = self.db_path + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_database_initialization(self) -> None:
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            # Verify table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hourly_turnover'")
            table = cursor.fetchone()
            self.assertIsNotNone(table)

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_settings'")
            self.assertIsNotNone(cursor.fetchone())
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alert_state'")
            self.assertIsNotNone(cursor.fetchone())

            # Verify index exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_symbol_timestamp'")
            index = cursor.fetchone()
            self.assertIsNotNone(index)
        finally:
            conn.close()

    def test_save_and_retrieve_hourly_snapshots(self) -> None:
        tickers = [
            {"symbol": "BTCUSDT", "turnover24h": "1000000.0", "volume24h": "10.0"},
            {"symbol": "ETHUSDT", "turnover24h": "500000.0", "volume24h": "5.0"},
            {"symbol": "INVALID", "turnover24h": None, "volume24h": "0.0"},
        ]

        timestamp = int(time.time())
        save_hourly_snapshots(tickers, timestamp=timestamp, db_path=self.db_path)

        # Retrieve BTCUSDT history
        btc_history = get_hourly_history("BTCUSDT", hours=10, db_path=self.db_path)
        self.assertEqual(len(btc_history), 1)
        self.assertEqual(btc_history[0]["timestamp"], timestamp)
        self.assertAlmostEqual(btc_history[0]["turnover"], 1000000.0)
        self.assertAlmostEqual(btc_history[0]["volume"], 10.0)

        # Retrieve ETHUSDT history
        eth_history = get_hourly_history("ETHUSDT", hours=10, db_path=self.db_path)
        self.assertEqual(len(eth_history), 1)

        # Check invalid symbol was skipped
        invalid_history = get_hourly_history("INVALID", hours=10, db_path=self.db_path)
        self.assertEqual(len(invalid_history), 0)

    def test_hourly_history_sorting_and_limit(self) -> None:
        symbol = "BTCUSDT"
        tickers = [{"symbol": symbol, "turnover24h": "100.0", "volume24h": "1.0"}]

        base_time = int(time.time() - 3600 * 10)
        for i in range(5):
            ts = base_time + 3600 * i
            save_hourly_snapshots(tickers, timestamp=ts, db_path=self.db_path)

        # Get last 3 hours, check chronological sorting (ascending)
        history = get_hourly_history(symbol, hours=3, db_path=self.db_path)
        self.assertEqual(len(history), 3)
        self.assertTrue(history[0]["timestamp"] < history[1]["timestamp"])
        self.assertTrue(history[1]["timestamp"] < history[2]["timestamp"])

    def test_daily_history_max_snapshot_selection(self) -> None:
        symbol = "BTCUSDT"
        # We simulate multiple hourly snapshots across 2 days
        now_dt = datetime.now(timezone.utc)
        day1 = now_dt - timedelta(days=1)
        day2 = now_dt

        # Snapshots for Day 1
        ts_day1_10am = int(datetime(day1.year, day1.month, day1.day, 10, 0).timestamp())
        ts_day1_11pm = int(datetime(day1.year, day1.month, day1.day, 23, 0).timestamp())

        # Snapshots for Day 2
        ts_day2_9am = int(datetime(day2.year, day2.month, day2.day, 9, 0).timestamp())
        ts_day2_6pm = int(datetime(day2.year, day2.month, day2.day, 18, 0).timestamp())

        save_hourly_snapshots([{"symbol": symbol, "turnover24h": "10.0", "volume24h": "1.0"}], timestamp=ts_day1_10am, db_path=self.db_path)
        save_hourly_snapshots([{"symbol": symbol, "turnover24h": "15.0", "volume24h": "1.5"}], timestamp=ts_day1_11pm, db_path=self.db_path)
        save_hourly_snapshots([{"symbol": symbol, "turnover24h": "20.0", "volume24h": "2.0"}], timestamp=ts_day2_9am, db_path=self.db_path)
        save_hourly_snapshots([{"symbol": symbol, "turnover24h": "25.0", "volume24h": "2.5"}], timestamp=ts_day2_6pm, db_path=self.db_path)

        daily = get_daily_history(symbol, days=5, db_path=self.db_path)
        # Should return exactly 2 rows (one for Day 1 and one for Day 2)
        self.assertEqual(len(daily), 2)
        # Verify it fetched the MAX timestamp of each day (the last snapshot of the day)
        self.assertEqual(daily[0]["timestamp"], ts_day1_11pm)
        self.assertAlmostEqual(daily[0]["turnover"], 15.0)

        self.assertEqual(daily[1]["timestamp"], ts_day2_6pm)
        self.assertAlmostEqual(daily[1]["turnover"], 25.0)

    def test_database_cleanup_prunes_old_records(self) -> None:
        symbol = "BTCUSDT"
        now = time.time()
        old_ts = int(now - 31 * 24 * 3600)  # 31 days ago
        recent_ts = int(now - 10 * 24 * 3600)  # 10 days ago

        save_hourly_snapshots([{"symbol": symbol, "turnover24h": "10.0", "volume24h": "1.0"}], timestamp=old_ts, db_path=self.db_path)
        save_hourly_snapshots([{"symbol": symbol, "turnover24h": "20.0", "volume24h": "2.0"}], timestamp=recent_ts, db_path=self.db_path)

        cleanup_old_records(days=30, db_path=self.db_path)

        # The old entry should be gone, the recent one remains
        history = get_hourly_history(symbol, hours=10, db_path=self.db_path)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["timestamp"], recent_ts)


class TurnoverChartingTests(unittest.TestCase):
    def test_annotations_include_only_first_min_max_and_last(self) -> None:
        turnovers = [5.0, 1.0, 10.0, 4.0, 6.0]

        self.assertEqual(
            get_turnover_annotation_indices(turnovers),
            [0, 1, 2, 4],
        )

    def test_annotation_roles_are_deduplicated(self) -> None:
        # The first point is also the minimum and the last is also the maximum.
        self.assertEqual(
            get_turnover_annotation_indices([1.0, 2.0, 3.0]),
            [0, 2],
        )

    def test_generate_turnover_chart_produces_png_bytes(self) -> None:
        dummy_data = [
            {"timestamp": int(time.time() - 3600 * 3), "turnover": 100000.0, "volume": 1.0},
            {"timestamp": int(time.time() - 3600 * 2), "turnover": 150000.0, "volume": 1.5},
            {"timestamp": int(time.time() - 3600 * 1), "turnover": 120000.0, "volume": 1.2},
        ]

        chart_bytes = generate_turnover_chart("BTCUSDT", dummy_data, "hours")
        self.assertIsInstance(chart_bytes, bytes)
        self.assertTrue(len(chart_bytes) > 0)
        # Check PNG header signature bytes
        self.assertEqual(chart_bytes[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
