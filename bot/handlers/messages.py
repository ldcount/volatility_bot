from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from bot.reports import format_volatility_report
from bot.services.jobs import start_scanning_job
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
    await update.message.reply_text(report, parse_mode="Markdown")
    print(
        f"[Messages] Request #{REQUEST_COUNT}: sent report with {len(candles)} candles."
    )
