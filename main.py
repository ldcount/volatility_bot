from bot.app import build_application, configure_logging
from bot.config import get_required_token, get_runtime_environment, load_environment


def main() -> None:
    load_environment()
    configure_logging()
    print(f"[Startup] Running bot in {get_runtime_environment()} mode.")
    token = get_required_token()
    application = build_application(token)
    application.run_polling()


if __name__ == "__main__":
    main()
