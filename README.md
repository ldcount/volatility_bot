# Volatility Bot

Telegram bot for three market checks on Bybit:

- volatility assessment for a user-supplied ticker
- funding assessment through commands and background alerts
- turnover assessment through ranking commands

## Entry Point

The runtime entrypoint is `main.py`.

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize the bot and start the background funding scan for the current chat. |
| `/negative` | Show negative funding rates, 10 per page, with OKX comparison. |
| `/positive` | Show positive funding rates, 10 per page, with OKX comparison. |
| `/funding_diff` | Show 10 cost-aware Bybit/OKX funding arbitrage candidates. |
| `/turnover` | Show rolling 24H turnover with inline pagination. |
| `/scan` | Screen the 50 highest-turnover markets by ATR. |
| `/surge BTC 5` | Find the largest historical BTC surge inside a five-day window. |
| `/rate` | Show the current per-chat funding alert threshold. |
| `/rate -1,2` | Set the per-chat funding alert threshold to `-1.2%`. |
| `/frequency [minutes]` | Show or set the background scan interval. |
| `/cooldown [minutes]` | Show or set the material-change alert cooldown. |
| `/stop` | Persistently disable background alerts for the current chat. |
| `/help` | Show help. |
| `<TICKER>` | Run the volatility report for a symbol such as `BTC` or `PEPE`. |

## Structure

The codebase is organized by responsibility:

- `main.py` - application entrypoint
- `bot/app.py` - Telegram app construction and handler registration
- `bot/handlers/` - command handlers and ticker-message handler
- `bot/services/` - volatility, funding, turnover, and job orchestration
- `bot/clients/` - Bybit and OKX API access
- `bot/models.py` - shared dataclasses for candles and computed results
- `bot/reports.py` - Telegram-facing message formatting
- `tests/` - unit tests for refactor-sensitive logic

## Requirements

- Python 3.11+
- Telegram bot token
- Network access to Telegram, Bybit, and OKX

## Installation

```bash
git clone <your-fork-or-repo-url>
cd volatility_bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Create `.env` in the project root:

```env
BOT_ENV=dev
TELEGRAM_TOKEN_PROD=<your-telegram-bot-token>
TELEGRAM_TOKEN_DEV=<your-dev-telegram-bot-token>
FUNDING_THRESHOLD=-0.015
SCAN_INTERVAL=18000
ALERT_COOLDOWN=3600
ALERT_MATERIAL_CHANGE=0.001
FUNDING_NOTIONAL_USDT=1000
BYBIT_TAKER_FEE_RATE=0.00055
OKX_TAKER_FEE_RATE=0.0005
FUNDING_SAFETY_HAIRCUT_RATIO=0.25
FUNDING_HISTORY_SAMPLES=6
FUNDING_PREFILTER_LIMIT=80
DISPLAY_TIMEZONE=Europe/Paris
```

`BOT_ENV=dev` uses `TELEGRAM_TOKEN_DEV`.
`BOT_ENV=prod` uses `TELEGRAM_TOKEN_PROD`.

Turnover chart axes and latest-snapshot captions use `DISPLAY_TIMEZONE`.

`SCAN_INTERVAL=18000` is the five-hour default. Per-chat changes made with
`/rate`, `/frequency`, and `/cooldown`, together with alert subscriptions and
deduplication state, are stored in SQLite and restored when the bot restarts.
An alert is sent when a symbol crosses into an alert condition, or when its
tracked rate changes by at least `ALERT_MATERIAL_CHANGE` after the saved cooldown.

The funding arbitrage screen normalizes both exchanges to an 8-hour horizon,
then estimates a net edge for `FUNDING_NOTIONAL_USDT` after round-trip taker
fees, current order-book spread and slippage. The safety haircut discounts the
gross funding edge for rate movement before settlement. Fee settings are rates,
so `0.00055` means `0.055%` per trade.

To keep interactive scans responsive and within exchange rate limits, the bot
prefilters shared contracts by absolute Bybit funding magnitude before requesting
individual OKX funding rates. The report discloses the screened and total shared
contract counts; increase `FUNDING_PREFILTER_LIMIT` for broader, slower coverage.

Volatility reports retain the existing calculations and add decision context:
downside deviation, historical drawdown, price versus 30-day SMA/VWAP,
liquidity-adjusted ATR, sample coverage, and confidence. The accompanying chart
uses the bot's hourly SQLite snapshots of Bybit's rolling 24-hour turnover, so
each point is a rolling-window value rather than turnover within one hourly candle.

## Run Locally

```bash
python main.py
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## systemd

The sample unit file is `volatility_bot.service`.

The important line is now:

```ini
ExecStart=/opt/bots/volatility_bot/venv/bin/python /opt/bots/volatility_bot/main.py
```

Typical install or refresh flow on the VPS:

```bash
sudo cp /opt/bots/volatility_bot/volatility_bot.service /etc/systemd/system/volatility_bot.service
sudo systemctl daemon-reload
sudo systemctl restart volatility_bot.service
sudo systemctl status volatility_bot.service
```

## GitHub Actions Deployment

The workflow in `.github/workflows/deploy.yml` now:

- installs dependencies
- runs the unit tests before deploy
- pulls latest code on the VPS
- reinstalls requirements in the VPS virtualenv
- copies the updated `volatility_bot.service` into `/etc/systemd/system/`
- reloads systemd
- restarts the bot service

This keeps the VPS unit file aligned with the repository version instead of relying on manual sync.
