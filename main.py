import logging

from telegram.error import NetworkError

from bot.app import build_application, configure_logging
from bot.config import get_required_token, get_runtime_environment, load_environment


def main() -> None:
    load_environment()
    configure_logging()
    print(f"[Startup] Running bot in {get_runtime_environment()} mode.")
    token = get_required_token()
    application = build_application(token)
    try:
        application.run_polling()
    except NetworkError as exc:
        logging.critical(
            "[Main] Failed to connect to Telegram API (NetworkError). "
            "Check your internet connection or proxy settings. Error: %s",
            exc,
        )
    except Exception as exc:
        logging.critical("[Main] Unexpected error caused the bot to stop: %s", exc, exc_info=True)


if __name__ == "__main__":
    main()
