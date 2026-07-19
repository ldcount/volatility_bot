from __future__ import annotations

import asyncio

from telegram import LinkPreviewOptions
from telegram.ext import ContextTypes

from bot.config import get_default_funding_threshold, get_default_scan_interval
from bot.reports import (
    format_extreme_funding_alert,
    format_funding_diff_report,
    format_threshold_percent,
)
from bot.clients.bybit import fetch_all_tickers
from bot.services.db import cleanup_old_records, save_hourly_snapshots
from bot.services.funding import find_extreme_funding
from bot.services.funding_diff import get_top_funding_diff


FUNDING_DIFF_REPORT_LIMIT = 5
FUNDING_DIFF_REPORT_THRESHOLD = 0.003


def get_chat_threshold(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> float:
    return context.bot_data.get(
        f"funding_threshold_{chat_id}",
        get_default_funding_threshold(),
    )


def parse_rate_threshold(raw_value: str) -> float:
    normalized = raw_value.strip().replace("%", "").replace(",", ".")
    threshold = float(normalized)

    if threshold > 0:
        threshold = -threshold

    if abs(threshold) >= 1:
        threshold /= 100

    if threshold >= 0 or threshold <= -1:
        raise ValueError("Threshold must be a negative percentage.")

    return threshold


async def scan_funding_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    loop = asyncio.get_running_loop()
    job = context.job
    if not job or not job.chat_id:
        return

    threshold = get_chat_threshold(context, job.chat_id)
    extreme_entries, diff_entries = await asyncio.gather(
        loop.run_in_executor(None, find_extreme_funding, threshold),
        loop.run_in_executor(None, get_top_funding_diff, FUNDING_DIFF_REPORT_LIMIT),
    )
    extreme_report = format_extreme_funding_alert(extreme_entries)
    funding_diff_report = None
    if any(entry.funding_diff >= FUNDING_DIFF_REPORT_THRESHOLD for entry in diff_entries):
        funding_diff_report = format_funding_diff_report(diff_entries)

    if extreme_report:
        await context.bot.send_message(
            job.chat_id,
            text=extreme_report,
            parse_mode="Markdown",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    if funding_diff_report:
        await context.bot.send_message(
            job.chat_id,
            text=funding_diff_report,
            parse_mode="Markdown",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )


def start_scanning_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    interval_seconds: int | None = None,
) -> None:
    restart = interval_seconds is not None
    if interval_seconds is None:
        interval_seconds = context.bot_data.get(
            f"scan_interval_{chat_id}",
            get_default_scan_interval(),
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
    context.bot_data[f"scan_interval_{chat_id}"] = interval_seconds
    print(
        f"[Jobs] Background funding scans for chat {chat_id} set to every "
        f"{interval_seconds}s."
    )


def get_threshold_message(threshold: float) -> str:
    return f"Current funding alert threshold: {format_threshold_percent(threshold)}"


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
