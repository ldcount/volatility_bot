from __future__ import annotations

import asyncio
import math

from telegram import LinkPreviewOptions
from telegram.ext import ContextTypes

from bot.config import get_alert_material_change
from bot.reports import (
    format_extreme_funding_alert,
    format_funding_diff_report,
    format_threshold_percent,
)
from bot.clients.bybit import fetch_all_tickers
from bot.services.db import (
    cleanup_old_records,
    get_chat_settings,
    list_subscribed_chat_settings,
    record_alert_notifications,
    save_hourly_snapshots,
    select_alert_changes,
    update_chat_settings,
)
from bot.services.funding import find_extreme_funding
from bot.services.funding_diff import get_top_funding_diff


FUNDING_DIFF_REPORT_LIMIT = 5
FUNDING_DIFF_REPORT_THRESHOLD = 0.003


def get_chat_threshold(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> float:
    return get_chat_settings(chat_id).funding_threshold


def get_chat_interval(chat_id: int) -> int:
    return get_chat_settings(chat_id).scan_interval_seconds


def get_chat_cooldown(chat_id: int) -> int:
    return get_chat_settings(chat_id).alert_cooldown_seconds


def parse_rate_threshold(raw_value: str) -> float:
    normalized = raw_value.strip().replace("%", "").replace(",", ".")
    threshold_percent = float(normalized)

    if not math.isfinite(threshold_percent):
        raise ValueError("Threshold must be finite.")

    if threshold_percent > 0:
        threshold_percent = -threshold_percent

    if threshold_percent >= 0 or threshold_percent <= -100:
        raise ValueError("Threshold must be a negative percentage.")

    return threshold_percent / 100


async def scan_funding_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    loop = asyncio.get_running_loop()
    job = context.job
    if not job or not job.chat_id:
        return

    settings = get_chat_settings(job.chat_id)
    if not settings.alerts_enabled:
        job.schedule_removal()
        return

    threshold = settings.funding_threshold
    extreme_entries, diff_entries = await asyncio.gather(
        loop.run_in_executor(None, find_extreme_funding, threshold),
        loop.run_in_executor(None, get_top_funding_diff, FUNDING_DIFF_REPORT_LIMIT),
    )
    material_change = get_alert_material_change()
    extreme_symbols = select_alert_changes(
        job.chat_id,
        "extreme_funding",
        {entry.symbol: entry.bybit_rate for entry in extreme_entries},
        material_change=material_change,
        cooldown_seconds=settings.alert_cooldown_seconds,
    )
    qualifying_diff_entries = [
        entry
        for entry in diff_entries
        if (
            entry.safety_adjusted_edge is not None
            and entry.safety_adjusted_edge >= FUNDING_DIFF_REPORT_THRESHOLD
        )
    ]
    diff_symbols = select_alert_changes(
        job.chat_id,
        "funding_arbitrage",
        {
            entry.symbol: entry.safety_adjusted_edge
            for entry in qualifying_diff_entries
            if entry.safety_adjusted_edge is not None
        },
        material_change=material_change,
        cooldown_seconds=settings.alert_cooldown_seconds,
        inactive_symbols={
            entry.symbol
            for entry in diff_entries
            if (
                entry.safety_adjusted_edge is None
                or entry.safety_adjusted_edge < FUNDING_DIFF_REPORT_THRESHOLD
            )
        },
    )

    changed_extreme_entries = [
        entry for entry in extreme_entries if entry.symbol in extreme_symbols
    ]
    changed_diff_entries = [
        entry for entry in qualifying_diff_entries if entry.symbol in diff_symbols
    ]
    extreme_report = format_extreme_funding_alert(changed_extreme_entries)
    funding_diff_report = (
        format_funding_diff_report(changed_diff_entries)
        if changed_diff_entries
        else None
    )

    if extreme_report:
        await context.bot.send_message(
            job.chat_id,
            text=extreme_report,
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        record_alert_notifications(
            job.chat_id,
            "extreme_funding",
            {entry.symbol: entry.bybit_rate for entry in changed_extreme_entries},
        )

    if funding_diff_report:
        await context.bot.send_message(
            job.chat_id,
            text=funding_diff_report,
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        record_alert_notifications(
            job.chat_id,
            "funding_arbitrage",
            {
                entry.symbol: entry.safety_adjusted_edge
                for entry in changed_diff_entries
                if entry.safety_adjusted_edge is not None
            },
        )


def start_scanning_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    interval_seconds: int | None = None,
) -> None:
    restart = interval_seconds is not None
    settings = get_chat_settings(chat_id)
    if interval_seconds is None:
        interval_seconds = settings.scan_interval_seconds
    settings = update_chat_settings(
        chat_id,
        scan_interval_seconds=interval_seconds,
        alerts_enabled=True,
    )

    if not context.job_queue:
        print("[Jobs] Warning: JobQueue not available. Background scanning disabled.")
        return

    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    if current_jobs and not restart:
        return

    for job in current_jobs:
        job.schedule_removal()

    context.job_queue.run_repeating(
        scan_funding_job,
        interval=interval_seconds,
        first=10,
        chat_id=chat_id,
        name=str(chat_id),
    )
    print(
        f"[Jobs] Background funding scans for chat {chat_id} set to every "
        f"{interval_seconds}s."
    )


def stop_scanning_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    update_chat_settings(chat_id, alerts_enabled=False)
    if context.job_queue:
        for job in context.job_queue.get_jobs_by_name(str(chat_id)):
            job.schedule_removal()


def restore_scanning_jobs(application) -> None:
    for settings in list_subscribed_chat_settings():
        start_scanning_job(
            application,
            settings.chat_id,
            interval_seconds=settings.scan_interval_seconds,
        )


def get_threshold_message(threshold: float) -> str:
    return f"Current funding alert threshold: {format_threshold_percent(threshold)}"


def get_frequency_message(interval_seconds: int) -> str:
    return f"Current background scan interval: {interval_seconds / 60:g} minutes."


def get_cooldown_message(cooldown_seconds: int) -> str:
    return f"Current alert cooldown: {cooldown_seconds / 60:g} minutes."


async def record_hourly_turnover_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    loop = asyncio.get_running_loop()
    try:
        tickers = await loop.run_in_executor(None, fetch_all_tickers)
        if tickers:
            await loop.run_in_executor(None, save_hourly_snapshots, tickers)
            await loop.run_in_executor(None, cleanup_old_records, 30)
            print("[Jobs] Hourly turnover snapshot successfully recorded and old database records cleaned up.")
        else:
            print("[Jobs] Warning: fetch_all_tickers returned empty, skipping hourly database recording.")
    except Exception as exc:
        print(f"[Jobs] Error in record_hourly_turnover_job: {exc}")


def start_global_jobs(application) -> None:
    """
    Starts system-wide background jobs (like recording hourly turnover).
    These are global and not tied to any specific Telegram chat ID.
    """
    if not application.job_queue:
        print("[Jobs] Warning: JobQueue not available. Global jobs disabled.")
        return

    # Check if job already exists to avoid duplication
    jobs = application.job_queue.get_jobs_by_name("record_hourly_turnover")
    if not jobs:
        application.job_queue.run_repeating(
            record_hourly_turnover_job,
            interval=3600,
            first=10,  # Run first time after 10 seconds, then every 1 hour
            name="record_hourly_turnover",
        )
        print("[Jobs] Registered global hourly turnover recording job.")
