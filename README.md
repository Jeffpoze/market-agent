# Market Agent

Paper-trading signals, backtests and a memecoin radar, running on your home server.
**Nothing here moves real money.** It's a lab for finding out which ideas actually work.

## What it does

| Part | What it does | When |
|---|---|---|
| Backtests | Tests each strategy on 10 years of history vs. buy-and-hold, after trading costs | On first start, then Sundays 7 pm |
| Signals + paper portfolio | Decides HOLD or CASH for each symbol/strategy, trades $1,000 of pretend money | Daily 5:30 pm (after the TSX close) |
| Memecoin radar | Places pretend $5 bets on newly promoted tokens under 4 rules, tracks rugs, pumps and dumps | Every hour |
| Coinbase (optional) | Shows your real balances, read-only | On page load |
| Home Assistant (optional) | Sends a webhook when a signal flips | When it happens |

Strategies: `trend_200` (above 200-day average), `golden_cross` (50-day above 200-day),
`rsi_dip` (buy oversold dips in uptrends). Data: Yahoo Finance and DexScreener, no keys needed.

## Install on ZimaOS (easiest)

1. App Store → **Custom Install** → Import → paste the whole `zimaos-compose.yml`.
2. Install. First start takes a few minutes while it installs Python packages.
3. Open `http://<zima-ip>:8088`.

Settings: `/DATA/AppData/market-agent/config.yaml` (watchlist, starting cash, fees, radar rules).
Edit, then restart the app.

## Install anywhere with Docker

```
docker compose up -d --build
```

## Coinbase, read-only

Create a key at portal.cdp.coinbase.com with **View permission only** — never Trade or Transfer.
Put it in `COINBASE_API_KEY` / `COINBASE_API_SECRET` (in the compose file or `.env`).
Wealthsimple and Crypto.com's app don't offer a personal API, so they're not connected.

## Home Assistant alerts

Create an automation with a **Webhook** trigger, then set `home_assistant.webhook_url` in the config,
e.g. `http://<ha-ip>:8123/api/webhook/market_agent`. The payload has `title` and `message`.
`/api/summary` returns JSON you can use in a REST sensor.

## How to read the results

- A strategy is only interesting if it beats buy-and-hold **after costs**, with a smaller worst drop.
- Give paper trading 2–3 months before trusting anything.
- The radar's point is to measure honestly how memecoins turn out. Expect most rules to lose.
