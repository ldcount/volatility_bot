from __future__ import annotations

import asyncio

from telegram import LinkPreviewOptions, Update
from telegram.ext import ContextTypes

from bot.reports import (
    format_funding_diff_report,
    format_funding_report,
    format_scan_report,
    format_surge_report,
    format_turnover_reports,
)
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
        "/turnover [min|max] [offset] - 30 symbols by 24H turnover\n"
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
    order = "min"
    offset = 0

    if context.args:
        first_arg = context.args[0].lower()
        if first_arg in {"min", "max"}:
            order = first_arg
            if len(context.args) >= 2 and context.args[1].isdigit():
                offset = int(context.args[1])
        elif context.args[0].isdigit():
            offset = int(context.args[0])

    status_message = await update.message.reply_text(
        f"Fetching {order} turnover data (offset: {offset})..."
    )
    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(None, get_ranked_turnover, order, offset)

    if not entries:
        await status_message.edit_text("No turnover data available.")
        return

    report_1, report_2 = format_turnover_reports(entries, order, offset)
    await status_message.edit_text(
        report_1,
        parse_mode="Markdown",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    if report_2:
        await update.message.reply_text(
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
        "/funding_diff - show the top 30 absolute funding gaps between Bybit and OKX\n"
        "/turnover [min|max] [offset] - show 30 symbols with lowest/highest 24H turnover\n"
        "/scan - market-wide volatility screener\n"
        "/surge <symbol> <days> - find max historical percentage surge over N days\n"
        "/rate - show current funding alert threshold\n"
        "/rate <negative %> - change alert threshold, for example `/rate -1,2`\n"
        "/frequency <min> - change how often the background funding scans run\n"
        "/help - show this help message\n\n"
        "*Ticker analysis*\n"
        "Send any coin name such as `BTC` or `PEPE` to receive a volatility report.\n\n"
        "Use the menu buttons below for one-tap commands."
    )
    await update.message.reply_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=build_main_menu(),
    )
