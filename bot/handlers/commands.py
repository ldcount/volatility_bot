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
from bot.services.db import update_chat_settings
from bot.services.funding import get_top_negative_funding, get_top_positive_funding
from bot.services.funding_diff import get_top_funding_diff
from bot.services.jobs import (
    get_chat_cooldown,
    get_chat_interval,
    get_chat_threshold,
    get_cooldown_message,
    get_frequency_message,
    get_threshold_message,
    parse_rate_threshold,
    start_scanning_job,
    stop_scanning_job,
)
from bot.services.max_surge import calculate_max_surge
from bot.services.turnover import get_ranked_turnover
from bot.services.volatility import (
    fetch_market_data,
    normalize_symbol,
    scan_market_volatility,
    validate_ticker,
)
from bot.ui import build_main_menu, build_pagination_keyboard


PAGE_SIZE = 10
MAX_PAGE = 100
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_scanning_job(context, update.effective_chat.id)
    await update.effective_message.reply_text(
        "👋 <b>Volatility Bot is ready</b>\n\n"
        "Send a ticker such as <code>BTC</code> or <code>PEPE</code> for the full "
        "volatility report. Background funding alerts are enabled using your saved "
        "threshold, frequency, and cooldown.\n\n"
        "Use /help for examples and an explanation of every command.",
        parse_mode="HTML",
        reply_markup=build_main_menu(),
    )


async def _funding_ranking_page(
    *,
    positive: bool,
    page: int,
) -> tuple[str, object]:
    offset = page * PAGE_SIZE
    fetcher = get_top_positive_funding if positive else get_top_negative_funding
    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(None, fetcher, PAGE_SIZE + 1, offset)
    has_next = len(entries) > PAGE_SIZE
    visible_entries = entries[:PAGE_SIZE]
    title = "Positive funding ranking" if positive else "Negative funding ranking"
    report = format_funding_report(visible_entries, title, offset)
    ranking = "positive" if positive else "negative"
    keyboard = build_pagination_keyboard(ranking, page, has_next=has_next)
    return report, keyboard


async def negative(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_message = await update.effective_message.reply_text(
        "Fetching negative funding rates..."
    )
    report, keyboard = await _funding_ranking_page(positive=False, page=0)
    await status_message.edit_text(
        report,
        parse_mode="HTML",
        link_preview_options=NO_PREVIEW,
        reply_markup=keyboard,
    )


async def positive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_message = await update.effective_message.reply_text(
        "Fetching positive funding rates..."
    )
    report, keyboard = await _funding_ranking_page(positive=True, page=0)
    await status_message.edit_text(
        report,
        parse_mode="HTML",
        link_preview_options=NO_PREVIEW,
        reply_markup=keyboard,
    )


async def funding_diff(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_message = await update.effective_message.reply_text(
        "Building the 10-symbol funding arbitrage decision screen..."
    )
    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(None, get_top_funding_diff, 10)
    report = format_funding_diff_report(entries)
    await status_message.edit_text(
        report,
        parse_mode="HTML",
        link_preview_options=NO_PREVIEW,
    )


async def _turnover_page(page: int) -> tuple[str, object]:
    offset = page * PAGE_SIZE
    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(
        None,
        get_ranked_turnover,
        "max",
        offset,
        PAGE_SIZE + 1,
    )
    has_next = len(entries) > PAGE_SIZE
    report, _ = format_turnover_reports(entries[:PAGE_SIZE], "max", offset)
    keyboard = build_pagination_keyboard("turnover", page, has_next=has_next)
    return report, keyboard


async def turnover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    page = 0
    if context.args and context.args[0].isdigit():
        page = min(MAX_PAGE, int(context.args[0]) // PAGE_SIZE)

    status_message = await update.effective_message.reply_text(
        "Fetching rolling 24-hour turnover ranking..."
    )
    report, keyboard = await _turnover_page(page)
    await status_message.edit_text(
        report,
        parse_mode="HTML",
        link_preview_options=NO_PREVIEW,
        reply_markup=keyboard,
    )


async def pagination_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer("Refreshing market data...")

    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "page" or not parts[2].isdigit():
        return
    ranking = parts[1]
    page = min(MAX_PAGE, int(parts[2]))

    if ranking == "negative":
        report, keyboard = await _funding_ranking_page(positive=False, page=page)
    elif ranking == "positive":
        report, keyboard = await _funding_ranking_page(positive=True, page=page)
    elif ranking == "turnover":
        report, keyboard = await _turnover_page(page)
    else:
        return

    await query.edit_message_text(
        report,
        parse_mode="HTML",
        link_preview_options=NO_PREVIEW,
        reply_markup=keyboard,
    )


async def frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.args:
        await update.effective_message.reply_text(
            get_frequency_message(get_chat_interval(chat_id))
        )
        return
    if not context.args[0].isdigit():
        await update.effective_message.reply_text(
            "Usage: /frequency &lt;minutes&gt;\nExample: /frequency 30",
            parse_mode="HTML",
        )
        return

    minutes = int(context.args[0])
    if minutes < 1:
        await update.effective_message.reply_text("Interval must be at least 1 minute.")
        return

    start_scanning_job(context, chat_id, interval_seconds=minutes * 60)
    await update.effective_message.reply_text(
        f"Background funding scan interval saved as every {minutes} minute(s)."
    )


async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.args:
        await update.effective_message.reply_text(
            get_threshold_message(get_chat_threshold(context, chat_id))
        )
        return

    try:
        threshold = parse_rate_threshold(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(
            "Usage: /rate -1,2\nExamples: /rate -1,2 or /rate -1.2"
        )
        return

    update_chat_settings(chat_id, funding_threshold=threshold)
    await update.effective_message.reply_text(
        f"Funding alert threshold saved as {threshold * 100:.2f}%."
    )


async def cooldown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.args:
        await update.effective_message.reply_text(
            get_cooldown_message(get_chat_cooldown(chat_id))
        )
        return
    if not context.args[0].isdigit():
        await update.effective_message.reply_text(
            "Usage: /cooldown &lt;minutes&gt;\nExample: /cooldown 60",
            parse_mode="HTML",
        )
        return

    minutes = int(context.args[0])
    if minutes < 0:
        await update.effective_message.reply_text("Cooldown cannot be negative.")
        return
    update_chat_settings(chat_id, alert_cooldown_seconds=minutes * 60)
    await update.effective_message.reply_text(
        f"Alert cooldown saved as {minutes} minute(s)."
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stop_scanning_job(context, update.effective_chat.id)
    await update.effective_message.reply_text(
        "Background alerts are disabled and the subscription was saved. "
        "Use /start to enable them again."
    )


async def surge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: /surge &lt;symbol&gt; &lt;days&gt;\nExample: /surge PIPPIN 5",
            parse_mode="HTML",
        )
        return

    symbol_arg, days_str = context.args[:2]
    if not days_str.isdigit():
        await update.effective_message.reply_text(
            "The number of days must be a whole positive number."
        )
        return

    days_window = int(days_str)
    if days_window < 1:
        await update.effective_message.reply_text(
            "The number of days must be at least 1."
        )
        return

    target_symbol = normalize_symbol(symbol_arg)
    status_message = await update.effective_message.reply_text(
        f"Fetching up to 1000 completed daily candles for {target_symbol}..."
    )
    loop = asyncio.get_running_loop()
    exists, category = await loop.run_in_executor(None, validate_ticker, target_symbol)
    if not exists or not category:
        await status_message.edit_text(f"Symbol {target_symbol} not found on Bybit.")
        return

    candles = await loop.run_in_executor(
        None,
        fetch_market_data,
        target_symbol,
        category,
        "D",
        1000,
    )
    if not candles:
        await status_message.edit_text("Failed to download data.")
        return

    result = await loop.run_in_executor(
        None,
        calculate_max_surge,
        candles,
        days_window,
    )
    if not result:
        await status_message.edit_text(
            "Not enough valid data to calculate the surge for that period."
        )
        return

    max_surge_value, best_date = result
    await status_message.edit_text(
        format_surge_report(target_symbol, max_surge_value, best_date),
        parse_mode="HTML",
    )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_message = await update.effective_message.reply_text(
        "Scanning top 50 markets by turnover. This may take a few seconds..."
    )
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, scan_market_volatility, 50)
    await status_message.edit_text(
        format_scan_report(results),
        parse_mode="HTML",
        link_preview_options=NO_PREVIEW,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "🤖 <b>Volatility Bot — command guide</b>\n\n"
        "<b>Analyze one market</b>\n"
        "Send <code>BTC</code>, <code>ETHUSDT</code>, or another ticker to receive "
        "the complete volatility, ATR, DCA, drawdown, price-context, and turnover report.\n\n"
        "<b>Funding and arbitrage</b>\n"
        "<code>/negative</code> — negative Bybit funding rates, with OKX comparison, "
        "shown 10 per page. Use the inline arrows for more results.\n"
        "<code>/positive</code> — positive rates, also shown 10 per page.\n"
        "<code>/funding_diff</code> — ten cost-aware Bybit/OKX arbitrage candidates. "
        "It shows direction, normalized rates, next settlements, execution costs, "
        "liquidity, persistence, and safety-adjusted edge.\n\n"
        "<b>Market screens</b>\n"
        "<code>/turnover</code> — rolling 24-hour turnover ranking; navigate with inline arrows.\n"
        "<code>/scan</code> — ATR volatility scan across the 50 highest-turnover markets.\n"
        "<code>/surge BTC 5</code> — largest historical low-to-high surge inside a "
        "five-day window. Replace the ticker and window as needed.\n\n"
        "<b>Background alerts</b>\n"
        "<code>/rate</code> — show the saved funding threshold.\n"
        "<code>/rate -1.2</code> — alert when funding crosses -1.2% or lower. "
        "A comma is also accepted: <code>-1,2</code>.\n"
        "<code>/frequency</code> — show the saved scan interval.\n"
        "<code>/frequency 30</code> — scan every 30 minutes. The default is five hours.\n"
        "<code>/cooldown</code> — show the saved duplicate-alert cooldown.\n"
        "<code>/cooldown 60</code> — require 60 minutes between material-change updates.\n"
        "<code>/stop</code> — disable background alerts and persist that choice.\n"
        "<code>/start</code> — enable alerts again using all previously saved settings.\n\n"
        "Alerts are sent when a symbol first crosses the threshold or when its value "
        "changes materially after the cooldown. Settings and alert state survive restarts."
    )
    await update.effective_message.reply_text(
        help_text,
        parse_mode="HTML",
        reply_markup=build_main_menu(),
    )
