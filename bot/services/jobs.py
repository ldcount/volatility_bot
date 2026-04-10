from __future__ import annotations

import asyncio

from telegram import LinkPreviewOptions
from telegram.ext import ContextTypes

from bot.config import get_default_funding_threshold, get_default_scan_interval
from bot.reports import format_extreme_funding_alert, format_threshold_percent
from bot.services.funding import find_extreme_funding


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
    threshold = (
        get_chat_threshold(context, job.chat_id)
        if job and job.chat_id
        else get_default_funding_threshold()
    )
    entries = await loop.run_in_executor(None, find_extreme_funding, threshold)
    report = format_extreme_funding_alert(entries)

    if report and job and job.chat_id:
        await context.bot.send_message(
            job.chat_id,
            text=report,
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
        f"[Jobs] Background funding scan for chat {chat_id} set to every "
        f"{interval_seconds}s."
    )


def get_threshold_message(threshold: float) -> str:
    return f"Current funding alert threshold: {format_threshold_percent(threshold)}"
