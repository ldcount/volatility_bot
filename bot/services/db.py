from __future__ import annotations

import os
import sqlite3
import time

DB_PATH = "bot.db"


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = DB_PATH
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: str | None = None) -> None:
    if db_path is None:
        db_path = DB_PATH
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hourly_turnover (
                    symbol TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    turnover REAL NOT NULL,
                    volume REAL NOT NULL,
                    PRIMARY KEY (symbol, timestamp)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_timestamp 
                ON hourly_turnover (symbol, timestamp DESC)
            """)
    finally:
        conn.close()


def save_hourly_snapshots(tickers: list[dict], timestamp: int | None = None, db_path: str | None = None) -> None:
    """
    Saves a list of tickers (from Bybit fetch_all_tickers) into the database.
    Each ticker dict is expected to contain:
    - symbol: e.g. 'BTCUSDT'
    - turnover24h: e.g. '123456.78'
    - volume24h: e.g. '12.34'
    """
    if timestamp is None:
        # Round current time to the start of the hour
        now = time.time()
        timestamp = int(now - (now % 3600))

    conn = get_connection(db_path)
    try:
        with conn:
            records = []
            for t in tickers:
                symbol = t.get("symbol", "")
                if not symbol:
                    continue

                turnover_val = t.get("turnover24h")
                volume_val = t.get("volume24h")
                if turnover_val is None or volume_val is None:
                    continue

                try:
                    turnover = float(turnover_val)
                    volume = float(volume_val)
                    records.append((symbol, timestamp, turnover, volume))
                except (ValueError, TypeError):
                    continue

            if records:
                conn.executemany("""
                    INSERT OR REPLACE INTO hourly_turnover (symbol, timestamp, turnover, volume)
                    VALUES (?, ?, ?, ?)
                """, records)
    finally:
        conn.close()


def get_hourly_history(symbol: str, hours: int, db_path: str | None = None) -> list[dict]:
    """
    Retrieves the last `hours` records for the given symbol sorted chronologically (ascending).
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, turnover, volume 
            FROM hourly_turnover 
            WHERE symbol = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (symbol, hours))
        rows = cursor.fetchall()
        # Convert to chronological order (ascending)
        results = [
            {"timestamp": r[0], "turnover": r[1], "volume": r[2]}
            for r in reversed(rows)
        ]
        return results
    finally:
        conn.close()


def get_daily_history(symbol: str, days: int, db_path: str | None = None) -> list[dict]:
    """
    Retrieves the daily snapshots for the given symbol (using the latest snapshot of each calendar day)
    sorted chronologically (ascending).
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.timestamp, t.turnover, t.volume
            FROM hourly_turnover t
            INNER JOIN (
                SELECT MAX(timestamp) as max_ts
                FROM hourly_turnover
                WHERE symbol = ?
                GROUP BY date(timestamp, 'unixepoch')
            ) m ON t.timestamp = m.max_ts
            WHERE t.symbol = ?
            ORDER BY t.timestamp DESC
            LIMIT ?
        """, (symbol, symbol, days))
        rows = cursor.fetchall()
        # Convert to chronological order (ascending)
        results = [
            {"timestamp": r[0], "turnover": r[1], "volume": r[2]}
            for r in reversed(rows)
        ]
        return results
    finally:
        conn.close()


def cleanup_old_records(days: int = 30, db_path: str | None = None) -> None:
    """
    Deletes records that are older than `days` relative to current time.
    """
    cutoff_timestamp = int(time.time() - (days * 24 * 3600))
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM hourly_turnover WHERE timestamp < ?", (cutoff_timestamp,))
    finally:
        conn.close()
