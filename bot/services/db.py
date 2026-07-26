from __future__ import annotations

import os
import sqlite3
import time

from bot.config import (
    get_default_alert_cooldown,
    get_default_funding_threshold,
    get_default_scan_interval,
)
from bot.models import ChatSettings

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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_settings (
                    chat_id INTEGER PRIMARY KEY,
                    funding_threshold REAL NOT NULL,
                    scan_interval_seconds INTEGER NOT NULL,
                    alerts_enabled INTEGER NOT NULL DEFAULT 1,
                    alert_cooldown_seconds INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_state (
                    chat_id INTEGER NOT NULL,
                    alert_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    last_notified_value REAL NOT NULL,
                    active INTEGER NOT NULL,
                    last_sent_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (chat_id, alert_type, symbol)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_alert_state_chat_type
                ON alert_state (chat_id, alert_type)
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


def get_chat_settings(
    chat_id: int,
    db_path: str | None = None,
) -> ChatSettings:
    init_db(db_path)
    now = int(time.time())
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO chat_settings (
                    chat_id,
                    funding_threshold,
                    scan_interval_seconds,
                    alerts_enabled,
                    alert_cooldown_seconds,
                    updated_at
                ) VALUES (?, ?, ?, 1, ?, ?)
                """,
                (
                    chat_id,
                    get_default_funding_threshold(),
                    get_default_scan_interval(),
                    get_default_alert_cooldown(),
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT funding_threshold, scan_interval_seconds,
                       alerts_enabled, alert_cooldown_seconds
                FROM chat_settings
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise RuntimeError(f"Could not load settings for chat {chat_id}.")
    return ChatSettings(
        chat_id=chat_id,
        funding_threshold=float(row[0]),
        scan_interval_seconds=int(row[1]),
        alerts_enabled=bool(row[2]),
        alert_cooldown_seconds=int(row[3]),
    )


def update_chat_settings(
    chat_id: int,
    *,
    funding_threshold: float | None = None,
    scan_interval_seconds: int | None = None,
    alerts_enabled: bool | None = None,
    alert_cooldown_seconds: int | None = None,
    db_path: str | None = None,
) -> ChatSettings:
    get_chat_settings(chat_id, db_path)
    updates: list[str] = []
    values: list[object] = []
    for column, value in (
        ("funding_threshold", funding_threshold),
        ("scan_interval_seconds", scan_interval_seconds),
        ("alerts_enabled", int(alerts_enabled) if alerts_enabled is not None else None),
        ("alert_cooldown_seconds", alert_cooldown_seconds),
    ):
        if value is not None:
            updates.append(f"{column} = ?")
            values.append(value)

    if updates:
        updates.append("updated_at = ?")
        values.extend((int(time.time()), chat_id))
        conn = get_connection(db_path)
        try:
            with conn:
                conn.execute(
                    f"UPDATE chat_settings SET {', '.join(updates)} WHERE chat_id = ?",
                    values,
                )
        finally:
            conn.close()
    return get_chat_settings(chat_id, db_path)


def list_subscribed_chat_settings(
    db_path: str | None = None,
) -> list[ChatSettings]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT chat_id, funding_threshold, scan_interval_seconds,
                   alerts_enabled, alert_cooldown_seconds
            FROM chat_settings
            WHERE alerts_enabled = 1
            ORDER BY chat_id
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        ChatSettings(
            chat_id=int(row[0]),
            funding_threshold=float(row[1]),
            scan_interval_seconds=int(row[2]),
            alerts_enabled=bool(row[3]),
            alert_cooldown_seconds=int(row[4]),
        )
        for row in rows
    ]


def select_alert_changes(
    chat_id: int,
    alert_type: str,
    current_values: dict[str, float],
    *,
    material_change: float,
    cooldown_seconds: int,
    inactive_symbols: set[str] | None = None,
    now: int | None = None,
    db_path: str | None = None,
) -> set[str]:
    """Return symbols that newly crossed or materially changed since notification."""
    if now is None:
        now = int(time.time())
    material_change = max(0.0, material_change)
    cooldown_seconds = max(0, cooldown_seconds)

    conn = get_connection(db_path)
    selected: set[str] = set()
    try:
        with conn:
            rows = conn.execute(
                """
                SELECT symbol, last_notified_value, active, last_sent_at
                FROM alert_state
                WHERE chat_id = ? AND alert_type = ?
                """,
                (chat_id, alert_type),
            ).fetchall()
            previous = {
                str(row[0]): (float(row[1]), bool(row[2]), int(row[3]))
                for row in rows
            }

            symbols_to_deactivate = (
                set(previous).difference(current_values)
                if inactive_symbols is None
                else set(previous).intersection(inactive_symbols)
            )
            for symbol in symbols_to_deactivate:
                conn.execute(
                    """
                    UPDATE alert_state
                    SET active = 0, updated_at = ?
                    WHERE chat_id = ? AND alert_type = ? AND symbol = ?
                    """,
                    (now, chat_id, alert_type, symbol),
                )

            for symbol, value in current_values.items():
                prior = previous.get(symbol)
                crossed = prior is None or not prior[1]
                changed = prior is not None and abs(value - prior[0]) >= material_change
                cooldown_elapsed = prior is None or now - prior[2] >= cooldown_seconds
                should_notify = crossed or (changed and cooldown_elapsed)

                if should_notify:
                    selected.add(symbol)
                elif prior is not None:
                    conn.execute(
                        """
                        UPDATE alert_state
                        SET active = 1, updated_at = ?
                        WHERE chat_id = ? AND alert_type = ? AND symbol = ?
                        """,
                        (now, chat_id, alert_type, symbol),
                    )
    finally:
        conn.close()
    return selected


def record_alert_notifications(
    chat_id: int,
    alert_type: str,
    notified_values: dict[str, float],
    *,
    now: int | None = None,
    db_path: str | None = None,
) -> None:
    """Persist alert state only after the Telegram message was sent successfully."""
    if not notified_values:
        return
    if now is None:
        now = int(time.time())
    conn = get_connection(db_path)
    try:
        with conn:
            conn.executemany(
                """
                INSERT INTO alert_state (
                    chat_id, alert_type, symbol, last_notified_value,
                    active, last_sent_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(chat_id, alert_type, symbol) DO UPDATE SET
                    last_notified_value = excluded.last_notified_value,
                    active = 1,
                    last_sent_at = excluded.last_sent_at,
                    updated_at = excluded.updated_at
                """,
                [
                    (chat_id, alert_type, symbol, value, now, now)
                    for symbol, value in notified_values.items()
                ],
            )
    finally:
        conn.close()
