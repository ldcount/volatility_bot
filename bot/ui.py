from __future__ import annotations

from telegram import BotCommand, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application


def build_bot_commands() -> list[BotCommand]:
    return [
        BotCommand("start", "Start the bot and show the menu"),
        BotCommand("negative", "Top negative funding rates"),
        BotCommand("positive", "Top positive funding rates"),
        BotCommand("funding_diff", "Top funding gaps: Bybit vs OKX"),
        BotCommand("turnover", "24H turnover ranking"),
        BotCommand("scan", "Market-wide volatility scan"),
        BotCommand("surge", "Max N-day historical surge"),
        BotCommand("rate", "Show or change the funding alert threshold"),
        BotCommand("frequency", "Change the background scan interval"),
        BotCommand("help", "Show the list of commands"),
    ]


def build_main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("/negative"), KeyboardButton("/positive")],
        [KeyboardButton("/funding_diff"), KeyboardButton("/turnover")],
        [KeyboardButton("/scan"), KeyboardButton("/rate")],
        [KeyboardButton("/frequency"), KeyboardButton("/help")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose a command or type a ticker",
    )


async def configure_bot_ui(application: Application) -> None:
    await application.bot.set_my_commands(build_bot_commands())
