import logging

from telegram.error import NetworkError
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from bot.handlers.commands import (
    frequency,
    funding_diff,
    help_command,
    negative,
    positive,
    rate,
    scan,
    start,
    surge,
    turnover,
)
from bot.handlers.messages import handle_message
from bot.ui import configure_bot_ui


def configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def log_error(update, context) -> None:
    if isinstance(context.error, NetworkError):
        logging.warning(
            "[ErrorHandler] NetworkError (transient connectivity issue): %s",
            context.error,
        )
        return
    logging.error(
        "[ErrorHandler] Unhandled exception while processing update.",
        exc_info=context.error,
    )


async def on_startup(application) -> None:
    from bot.services.db import init_db
    from bot.services.jobs import start_global_jobs

    # 1. Initialize SQLite Database
    init_db()

    # 2. Configure Telegram UI commands
    await configure_bot_ui(application)

    # 3. Start system-wide background jobs (e.g. hourly turnover logger)
    start_global_jobs(application)


def build_application(token: str):
    application = ApplicationBuilder().token(token).post_init(on_startup).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("negative", negative))
    application.add_handler(CommandHandler("positive", positive))
    application.add_handler(CommandHandler("funding_diff", funding_diff))
    application.add_handler(CommandHandler("turnover", turnover))
    application.add_handler(CommandHandler("scan", scan))
    application.add_handler(CommandHandler("surge", surge))
    application.add_handler(CommandHandler("rate", rate))
    application.add_handler(CommandHandler("frequency", frequency))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    )
    application.add_error_handler(log_error)
    return application
