from __future__ import annotations

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import Application


def build_bot_commands() -> list[BotCommand]:
    return [
        BotCommand("start", "Start the bot and show the menu"),
        BotCommand("negative", "Top negative funding rates"),
        BotCommand("positive", "Top positive funding rates"),
        BotCommand("funding_diff", "Funding arbitrage decision screen"),
        BotCommand("turnover", "24H turnover ranking"),
        BotCommand("scan", "Market-wide volatility scan"),

        BotCommand("surge", "Max N-day historical surge"),
        BotCommand("rate", "Show or change the funding alert threshold"),
        BotCommand("frequency", "Change the background scan interval"),
        BotCommand("cooldown", "Show or change the alert cooldown"),
        BotCommand("stop", "Stop background alerts"),
        BotCommand("help", "Show the list of commands"),
    ]


def build_main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("/negative"), KeyboardButton("/positive")],
        [KeyboardButton("/funding_diff"), KeyboardButton("/turnover")],
        [KeyboardButton("/scan"), KeyboardButton("/surge")],
        [KeyboardButton("/rate"), KeyboardButton("/frequency")],
        [KeyboardButton("/cooldown"), KeyboardButton("/stop")],
        [KeyboardButton("/help")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose a command or type a ticker",
    )


def build_pagination_keyboard(
    ranking: str,
    page: int,
    *,
    has_next: bool,
) -> InlineKeyboardMarkup | None:
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton(
                "◀ Previous",
                callback_data=f"page:{ranking}:{page - 1}",
            )
        )
    if has_next:
        buttons.append(
            InlineKeyboardButton(
                "Next ▶",
                callback_data=f"page:{ranking}:{page + 1}",
            )
        )
    return InlineKeyboardMarkup([buttons]) if buttons else None


async def configure_bot_ui(application: Application) -> None:
    await application.bot.set_my_commands(build_bot_commands())
