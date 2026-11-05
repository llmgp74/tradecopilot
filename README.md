# TradeCopilot

Single-user, local trading co-pilot.

## Requirements

- Python 3.12 or later and [uv](https://docs.astral.sh/uv/)
<!-- - Node.js 20 or later and npm, for the frontend -->

## Setup

From the repository root:

```bash
uv sync
```

## Configuration

Runtime settings resolve in this order, highest first:

1. Settings saved from the frontend, stored in SQLite
2. Process environment variables
3. `.env` at the repository root
4. Defaults

Copy the example for local development:

```bash
cp .env.example .env
```

| Variable | Notes |
| --- | --- |
| `AGENT_MODEL` | `provider:model`; required to run the agent |
| `MODEL_API_KEY` | Provider key |
| `ALPACA_API_KEY` | Portfolio panel |
| `ALPACA_API_SECRET` | Portfolio panel |
| `ALPACA_BASE_URL` | Defaults to the paper host |
| `FMP_API_KEY` | Fundamentals; free plan is 250 calls a day |
| `FINNHUB_API_KEY` | Company news; free plan covers North America |
| `FRED_API_KEY` | Macro series; free |
| `EDGAR_USER_AGENT` | SEC requires a name and contact email |
| `DB_PATH` | Defaults to `~/.tradecopilot/data.db` |
| `HOST`, `PORT` | Default to `127.0.0.1:8000` |

Keys saved from the frontend win over the environment. They are stored
encrypted in `data.db`; the Fernet key is `settings.key` next to it, mode 0600.

## Run the agent

From the repository root:

```bash
uv run --package tradecopilot-agent tradecopilot serve
```

Or from `agent/`:

```bash
uv run tradecopilot serve
```

The server listens on `http://127.0.0.1:8000`. API documentation is at `/docs`,
`/redoc`, and `/openapi.json`. When `ui/dist` exists, the same process serves the
built frontend at `/`.
