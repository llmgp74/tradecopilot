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

Credentials are entered in the app's Settings screen and stored encrypted in
SQLite. The process environment supplies deployment settings only.

| Variable | Default | Notes |
| --- | --- | --- |
| `DB_PATH` | `~/.tradecopilot/data.db` | SQLite file |
| `UI_DIST` | `ui/dist` | Built frontend directory |
| `HOST` | `127.0.0.1` | |
| `PORT` | `8000` | |

Provider, broker, data, and search keys are never read from the environment.
