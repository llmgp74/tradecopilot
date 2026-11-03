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

Settings come from environment variables:

| Variable | Default | Notes |
| --- | --- | --- |
| `AGENT_MODEL` | none | `provider:model` string; required to build a graph |
| `JUDGE_MODEL` | none | `provider:model` string for the eval judge |
| `DB_PATH` | `~/.tradecopilot/data.db` | SQLite file |
| `UI_DIST` | `ui/dist` | built frontend directory |
| `HOST` | `127.0.0.1` | |
| `PORT` | `8000` | |
