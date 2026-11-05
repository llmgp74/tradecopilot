# TradeCopilot Agent

Agent library and API server for TradeCopilot.

## Setup

Run from the repository root:

```bash
uv sync
```

## Commands

From `agent/`:

```bash
uv run tradecopilot serve      # start the server on 127.0.0.1:8000
uv run pytest                  # run the contract checks
```

From the repository root:

```bash
uv run --package tradecopilot-agent tradecopilot serve
```

## Configuration

Settings come from environment variables and the repository `.env` file. The
process environment wins over `.env`. Values saved from the frontend settings
screen are stored in SQLite and win over both.

| Variable | Default | Notes |
| --- | --- | --- |
| `AGENT_MODEL` | none | `provider:model` string; required to build a graph |
| `MODEL_API_KEY` | none | Provider key fallback |
| `JUDGE_MODEL` | none | `provider:model` string for the eval judge |
| `ALPACA_API_KEY` | none | Broker key |
| `ALPACA_API_SECRET` | none | Broker secret |
| `ALPACA_BASE_URL` | paper host | Trading API base URL |
| `FMP_API_KEY` | none | Fundamentals; free plan is 250 calls a day |
| `FINNHUB_API_KEY` | none | Company news; free plan covers North America |
| `FRED_API_KEY` | none | Macro series; free |
| `EDGAR_USER_AGENT` | none | Name and contact email, required by SEC |
| `DB_PATH` | `~/.tradecopilot/data.db` | SQLite file |
| `UI_DIST` | `ui/dist` | built frontend directory |
| `HOST` | `127.0.0.1` | |
| `PORT` | `8000` | |
