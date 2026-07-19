from __future__ import annotations

import asyncio

from telegram import LinkPreviewOptions, Update
from telegram.ext import ContextTypes

from datetime import datetime
from bot.reports import (
    format_funding_diff_report,
    format_funding_report,
    format_scan_report,
    format_surge_report,
    format_turnover_reports,
    format_turnover_value,
)
from bot.services.db import get_daily_history, get_hourly_history
from bot.services.charts import generate_turnover_chart
from bot.services.funding_diff import get_top_funding_diff
from bot.services.funding import get_top_negative_funding, get_top_positive_funding
from bot.services.jobs import (
    get_chat_threshold,
    get_threshold_message,
    parse_rate_threshold,
    start_scanning_job,
)
from bot.services.max_surge import calculate_max_surge
from bot.services.turnover import get_ranked_turnover
from bot.ui import build_main_menu
from bot.services.volatility import (
    fetch_market_data,
    normalize_symbol,
    scan_market_volatility,
    validate_ticker,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "I am the Volatility Bot.\n"
        "Send me a ticker such as PEPE to analyze.\n\n"
        "Commands:\n"
        "/negative - top negative funding rates\n"
        "/positive - top positive funding rates\n"
        "/funding_diff - top 30 funding gaps between Bybit and OKX\n"
        "/turnover [offset] - 30 symbols by highest 24H turnover\n"
        "/turnover_hours [hours] <symbol> - chart hourly turnover history\n"
        "/turnover_days [days] <symbol> - chart daily turnover history\n"
        "/scan - market-wide volatility screener\n"
        "/surge <symbol> <days> - calculate max N-day surge\n"
        "/frequency <min> - set background funding scan interval\n"
        "/rate <negative %> - set funding alert threshold\n"
        "/help - list all commands\n\n"
        "The menu buttons below can be used instead of typing commands.",
        reply_markup=build_main_menu(),
    )
    start_scanning_job(context, update.effective_chat.id)


async def negative(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_message = await update.message.reply_text("Fetching negative funding rates...")
    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(None, get_top_negative_funding)
    report = format_funding_report(entries, "*Top 10 negative funding*")
    await status_message.edit_text(
        report,
        parse_mode="Markdown",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def positive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_message = await update.message.reply_text("Fetching positive funding rates...")
    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(None, get_top_positive_funding)
    report = format_funding_report(entries, "*Top 10 positive funding*")
    await status_message.edit_text(
        report,
        parse_mode="Markdown",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def funding_diff(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_message = await update.message.reply_text(
        "Fetching funding-rate differences between Bybit and OKX..."
    )
    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(None, get_top_funding_diff)
    report = format_funding_diff_report(entries)
    await status_message.edit_text(
        report,
        parse_mode="Markdown",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def turnover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    offset = 0

    if context.args:
        first_arg = context.args[0]
        if first_arg.isdigit():
            offset = int(first_arg)

    status_message = await update.effective_message.reply_text(
        f"Fetching highest turnover data (offset: {offset})..."
    )
    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(None, get_ranked_turnover, "max", offset)

    if not entries:
        await status_message.edit_text("No turnover data available.")
        return

    report_1, report_2 = format_turnover_reports(entries, "max", offset)
    await status_message.edit_text(
        report_1,
        parse_mode="Markdown",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    if report_2:
        await update.effective_message.reply_text(
            report_2,
            parse_mode="Markdown",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )


async def frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Usage: /frequency <minutes>\n"
            "Example: /frequency 30 -> scan every 30 minutes"
        )
        return

    minutes = int(context.args[0])
    if minutes < 1:
        await update.message.reply_text("Interval must be at least 1 minute.")
        return

    start_scanning_job(
        context,
        update.effective_chat.id,
        interval_seconds=minutes * 60,
    )
    await update.message.reply_text(
        f"Background funding scan interval updated to every {minutes} minute(s)."
    )


async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            get_threshold_message(get_chat_threshold(context, chat_id))
        )
        return

    try:
        threshold = parse_rate_threshold(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Usage: /rate -1,2\n"
            "Example values: /rate -1,2 or /rate -1.2"
        )
        return

    context.bot_data[f"funding_threshold_{chat_id}"] = threshold
    await update.message.reply_text(
        f"Funding alert threshold updated to {threshold * 100:.2f}%"
    )


async def surge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /surge <symbol> <days>\n"
            "Example: /surge PIPPIN 5"
        )
        return

    symbol_arg = context.args[0]
    days_str = context.args[1]

    if not days_str.isdigit():
        await update.message.reply_text("The number of days must be a whole positive number.")
        return

    days_window = int(days_str)
    if days_window < 1:
        await update.message.reply_text("The number of days must be at least 1.")
        return

    target_symbol = normalize_symbol(symbol_arg)
    status_message = await update.message.reply_text(f"Fetching up to 1000 days of data for {target_symbol}...")

    loop = asyncio.get_running_loop()
    exists, category = await loop.run_in_executor(None, validate_ticker, target_symbol)
    if not exists or not category:
        await status_message.edit_text(f"Symbol {target_symbol} not found on Bybit.")
        return

    candles = await loop.run_in_executor(None, fetch_market_data, target_symbol, category, "D", 1000)
    if not candles:
        await status_message.edit_text("Failed to download data.")
        return

    result = await loop.run_in_executor(None, calculate_max_surge, candles, days_window)
    if not result:
        await status_message.edit_text("Not enough valid data to calculate the surge for that period.")
        return

    max_surge_value, best_date = result
    report = format_surge_report(target_symbol, max_surge_value, best_date)
    await status_message.edit_text(report)


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_message = await update.message.reply_text(
        "Scanning top 50 markets by turnover. This may take a few seconds..."
    )
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, scan_market_volatility, 50)
    report = format_scan_report(results)
    await status_message.edit_text(
        report,
        parse_mode="Markdown",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "*Volatility Bot - Available Commands*\n\n"
        "/start - initialize the bot and start background funding scans\n"
        "/negative - fetch the top 10 most negative funding rates\n"
        "/positive - fetch the top 10 most positive funding rates\n"
        "/funding\_diff - top 30 abs funding gaps between Bybit and OKX\n"
        "/turnover [offset] - show 30 symbols with highest 24H turnover\n"
        "/turnover\_hours [hours] <symbol> - chart hourly turnover history\n"
        "/turnover\_days [days] <symbol> - chart daily turnover history\n"
        "/scan - market-wide volatility screener\n"
        "/surge <symbol> <days> - find max historical surge over N days\n"
        "/rate - show current funding alert threshold\n"
        "/rate <negative %> - change alert threshold, for example `/rate -1,2`\n"
        "/frequency <min> - background funding scan interval\n"
        "/help - show this help message\n\n"
        "*Ticker analysis*\n"
        "Send any coin name such as `BTC` or `PEPE` to receive a volatility report.\n\n"
        "Use the menu buttons below for one-tap commands."
    )
    await update.effective_message.reply_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=build_main_menu(),
    )


async def turnover_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /turnover_hours [hours] <symbol>\nExample: /turnover_hours 14 BTC"
        )
        return

    # Parse arguments
    hours = 24
    symbol_arg = ""
    if len(context.args) == 1:
        arg = context.args[0]
        if arg.isdigit():
            hours = int(arg)
        else:
            symbol_arg = arg
    else:
        arg1, arg2 = context.args[0], context.args[1]
        if arg1.isdigit():
            hours = int(arg1)
            symbol_arg = arg2
        elif arg2.isdigit():
            hours = int(arg2)
            symbol_arg = arg1
        else:
            symbol_arg = arg1

    if not symbol_arg:
        await update.effective_message.reply_text(
            "Please specify a symbol.\nUsage: /turnover_hours [hours] <symbol>"
        )
        return

    target_symbol = normalize_symbol(symbol_arg)
    status_message = await update.effective_message.reply_text(
        f"Fetching {hours} hours of turnover history for {target_symbol}..."
    )

    loop = asyncio.get_running_loop()
    exists, category = await loop.run_in_executor(None, validate_ticker, target_symbol)
    if not exists or not category:
        await status_message.edit_text(f"Symbol {target_symbol} not found on Bybit.")
        return

    data = await loop.run_in_executor(None, get_hourly_history, target_symbol, hours)
    if not data:
        await status_message.edit_text(f"No database history recorded yet for {target_symbol}.")
        return

    if len(data) < 2:
        val = data[0]["turnover"]
        formatted_val = format_turnover_value(val)
        dt = datetime.fromtimestamp(data[0]["timestamp"]).strftime("%m/%d %H:%M")
        await status_message.edit_text(
            f"Only 1 history record exists for {target_symbol} (need at least 2 to chart):\n"
            f"• {dt}: {formatted_val}"
        )
        return

    chart_bytes = await loop.run_in_executor(
        None, generate_turnover_chart, target_symbol, data, "hours"
    )

    display_data = data[-10:]
    lines = []
    for entry in display_data:
        dt = datetime.fromtimestamp(entry["timestamp"]).strftime("%m/%d %H:%M")
        formatted = format_turnover_value(entry["turnover"])
        lines.append(f"`{dt}: {formatted}`")

    caption_text = (
        f"📊 *{target_symbol} Turnover Evolution (Hours)*\n"
        f"Showing last {len(display_data)}/{len(data)} recorded hours:\n\n"
        + "\n".join(lines)
    )

    await update.effective_message.reply_photo(
        photo=chart_bytes,
        caption=caption_text,
        parse_mode="Markdown",
    )
    await status_message.delete()


async def turnover_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /turnover_days [days] <symbol>\nExample: /turnover_days 7 BTC"
        )
        return

    # Parse arguments
    days = 7
    symbol_arg = ""
    if len(context.args) == 1:
        arg = context.args[0]
        if arg.isdigit():
            days = int(arg)
        else:
            symbol_arg = arg
    else:
        arg1, arg2 = context.args[0], context.args[1]
        if arg1.isdigit():
            days = int(arg1)
            symbol_arg = arg2
        elif arg2.isdigit():
            days = int(arg2)
            symbol_arg = arg1
        else:
            symbol_arg = arg1

    if not symbol_arg:
        await update.effective_message.reply_text(
            "Please specify a symbol.\nUsage: /turnover_days [days] <symbol>"
        )
        return

    target_symbol = normalize_symbol(symbol_arg)
    status_message = await update.effective_message.reply_text(
        f"Fetching {days} days of turnover history for {target_symbol}..."
    )

    loop = asyncio.get_running_loop()
    exists, category = await loop.run_in_executor(None, validate_ticker, target_symbol)
    if not exists or not category:
        await status_message.edit_text(f"Symbol {target_symbol} not found on Bybit.")
        return

    data = await loop.run_in_executor(None, get_daily_history, target_symbol, days)
    if not data:
        await status_message.edit_text(f"No database history recorded yet for {target_symbol}.")
        return

    if len(data) < 2:
        val = data[0]["turnover"]
        formatted_val = format_turnover_value(val)
        dt = datetime.fromtimestamp(data[0]["timestamp"]).strftime("%Y-%m-%d")
        await status_message.edit_text(
            f"Only 1 history record exists for {target_symbol} (need at least 2 to chart):\n"
            f"• {dt}: {formatted_val}"
        )
        return

    chart_bytes = await loop.run_in_executor(
        None, generate_turnover_chart, target_symbol, data, "days"
    )

    display_data = data[-10:]
    lines = []
    for entry in display_data:
        dt = datetime.fromtimestamp(entry["timestamp"]).strftime("%Y-%m-%d")
        formatted = format_turnover_value(entry["turnover"])
        lines.append(f"`{dt}: {formatted}`")

    caption_text = (
        f"📊 *{target_symbol} Turnover Evolution (Days)*\n"
        f"Showing last {len(display_data)}/{len(data)} recorded days:\n\n"
        + "\n".join(lines)
    )

    await update.effective_message.reply_photo(
        photo=chart_bytes,
        caption=caption_text,
        parse_mode="Markdown",
    )
    await status_message.delete()
