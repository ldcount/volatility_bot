from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.reports import format_turnover_value, format_volatility_report
from bot.services.charts import generate_turnover_chart
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
    # Update status message with volatility report
    await status_message.edit_text(report, parse_mode="Markdown")

    # Exchange klines provide completed hourly turnover without depending on
    # how long this bot process has been recording ticker snapshots.
    hourly_candles = await loop.run_in_executor(
        None,
        fetch_market_data,
        target_symbol,
        category,
        "60",
        25,
    )
    data = [
        {"timestamp": candle.timestamp, "turnover": candle.turnover}
        for candle in (hourly_candles or [])[-24:]
        if candle.timestamp is not None
    ]
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
            hourly_change = (
                latest_turnover / prior_turnover - 1
                if prior_turnover > 0
                else None
            )
            latest_dt = datetime.fromtimestamp(
                data[-1]["timestamp"],
                tz=UTC,
            ).strftime("%m/%d %H:%M UTC")
            change_text = (
                "N/A" if hourly_change is None else f"{hourly_change * 100:+.1f}%"
            )

            caption_text = (
                f"📊 *{target_symbol} Hourly Turnover*\n"
                f"Period: last {len(data)} completed 1H candles\n\n"
                f"• *Latest*: `{format_turnover_value(latest_turnover)}` ({latest_dt})\n"
                f"• *Change vs prior hour*: `{change_text}`\n"
                f"• *Average*: `{format_turnover_value(avg_turnover)}`\n"
                f"• *Maximum*: `{format_turnover_value(max_turnover)}`\n"
                f"• *Minimum*: `{format_turnover_value(min_turnover)}`"
            )

            await update.message.reply_photo(
                photo=chart_bytes,
                caption=caption_text,
                parse_mode="Markdown",
            )
        except Exception as exc:
            print(f"[Messages] Error generating/sending turnover chart for {target_symbol}: {exc}")

    print(
        f"[Messages] Request #{REQUEST_COUNT}: sent report with {len(candles)} candles."
    )

