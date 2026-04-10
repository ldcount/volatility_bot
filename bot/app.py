import logging

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from bot.handlers.commands import (
    frequency,
    help_command,
    negative,
    positive,
    rate,
    start,
    turnover,
)
from bot.handlers.messages import handle_message


def configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def log_error(update, context) -> None:
    logging.exception("Unhandled exception while processing update.", exc_info=context.error)


def build_application(token: str):
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("negative", negative))
    application.add_handler(CommandHandler("positive", positive))
    application.add_handler(CommandHandler("turnover", turnover))
    application.add_handler(CommandHandler("rate", rate))
    application.add_handler(CommandHandler("frequency", frequency))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    )
    application.add_error_handler(log_error)
    return application
