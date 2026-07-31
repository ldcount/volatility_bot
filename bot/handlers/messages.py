from __future__ import annotations

import asyncio
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.reports import format_turnover_value, format_volatility_report
from bot.services.charts import generate_turnover_chart
from bot.services.db import get_hourly_history
from bot.services.jobs import start_scanning_job
from bot.services.timezones import get_display_timezone
from bot.services.turnover import get_symbol_turnover_text
from bot.services.volatility import (
    analyze_market_data,
    fetch_market_data,
    normalize_symbol,
    validate_ticker,
)

REQUEST_COUNT = 0


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global REQUEST_COUNT
    REQUEST_COUNT += 1

    chat_id = update.effective_chat.id
    start_scanning_job(context, chat_id)

    user_text = update.message.text or ""
    target_symbol = normalize_symbol(user_text)
    status_message = await update.message.reply_text(f"Checking {target_symbol}...")

    loop = asyncio.get_running_loop()
    exists, category = await loop.run_in_executor(None, validate_ticker, target_symbol)
    if not exists or not category:
        await status_message.edit_text(f"Symbol {target_symbol} not found on Bybit.")
        return

    await status_message.edit_text(f"Found in {category}. Downloading data...")
    candles = await loop.run_in_executor(
        None,
        fetch_market_data,
        target_symbol,
        category,
        "D",
    )
    if not candles:
        await status_message.edit_text("Failed to download data.")
        return

    stats = analyze_market_data(candles)
    if not stats:
        await status_message.edit_text(
            "Error: Could not calculate stats. Not enough data?"
        )
        return

    turnover_text = await loop.run_in_executor(
        None,
        get_symbol_turnover_text,
        target_symbol,
        category,
    )
    report = format_volatility_report(
        target_symbol,
        len(candles),
        stats,
        turnover_text,
    )
    # Update status message with volatility report
    await status_message.edit_text(report, parse_mode="HTML")

    # Each stored point is Bybit's rolling 24H turnover, sampled once per hour.
    data = await loop.run_in_executor(None, get_hourly_history, target_symbol, 24)
    if data and len(data) >= 2:
        try:
            chart_bytes = await loop.run_in_executor(
                None, generate_turnover_chart, target_symbol, data, "hours"
            )

            turnovers = [entry["turnover"] for entry in data]
            avg_turnover = sum(turnovers) / len(turnovers)
            max_turnover = max(turnovers)
            min_turnover = min(turnovers)
            latest_turnover = turnovers[-1]
            prior_turnover = turnovers[-2]
            snapshot_change = (
                latest_turnover / prior_turnover - 1
                if prior_turnover > 0
                else None
            )
            latest_dt = datetime.fromtimestamp(
                data[-1]["timestamp"],
                tz=get_display_timezone(),
            ).strftime("%m/%d %H:%M %Z")
            change_text = (
                "N/A" if snapshot_change is None else f"{snapshot_change * 100:+.1f}%"
            )

            caption_text = (
                f"📊 <b>{target_symbol} Rolling 24H Turnover</b>\n"
                f"Period: last {len(data)} hourly snapshots\n\n"
                f"• <b>Latest</b>: <code>{format_turnover_value(latest_turnover)}</code> ({latest_dt})\n"
                f"• <b>Change vs prior snapshot</b>: <code>{change_text}</code>\n"
                f"• <b>Average</b>: <code>{format_turnover_value(avg_turnover)}</code>\n"
                f"• <b>Maximum</b>: <code>{format_turnover_value(max_turnover)}</code>\n"
                f"• <b>Minimum</b>: <code>{format_turnover_value(min_turnover)}</code>"
            )

            await update.message.reply_photo(
                photo=chart_bytes,
                caption=caption_text,
                parse_mode="HTML",
            )
        except Exception as exc:
            print(f"[Messages] Error generating/sending turnover chart for {target_symbol}: {exc}")

    print(
        f"[Messages] Request #{REQUEST_COUNT}: sent report with {len(candles)} candles."
    )

