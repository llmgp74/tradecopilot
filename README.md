# TradeCopilot

Single-user, local trading co-pilot.

## Requirements

For development:

- Python 3.12 or later and [uv](https://docs.astral.sh/uv/)
- Node.js 22 or later and npm, for the frontend and the desktop build
- Rust, for the Tauri shell

The desktop app ships with its own Python runtime. End users need none of the
above.

## Setup

From the repository root:

```bash
uv sync
```

## Configuration

Credentials are entered in the app's Settings screen and stored encrypted in
SQLite. The process environment supplies deployment settings only; it is never
read for an API key or a model.

| Variable | Notes |
| --- | --- |
| `DB_PATH` | Defaults to `~/.tradecopilot/data.db` |
| `UI_DIST` | Built frontend directory; defaults to `ui/dist` |
| `HOST`, `PORT` | Default to `127.0.0.1:8000` |

Provider keys, the broker keys, and the data and search keys live in `data.db`.
The Fernet key is `settings.key` next to it, mode 0600.

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

## Build the desktop app

After cloning, install the frontend dependencies once with `npm --prefix ui ci`.
Then, from the repository root:

```bash
make macos          # macOS
make windows-arm64  # Windows on ARM64, native build
make windows-x64    # Windows x64, cross-built on an ARM64 host
```

Each target stages the agent source and exported requirements into the Tauri
resources, builds the frontend, compiles the shell, then installs and opens the
app. Windows needs GNU make, from Git Bash or MSYS2. Use `windows-x64` on any
Windows host for builds that ship to x64 PCs. On an ARM64 host it cross-builds
and runs the app through Windows 11 x64 emulation.

The first launch downloads uv, CPython 3.13 and the locked dependencies into
`~/.tradecopilot/runtime`, so it needs network access. Later launches start the
managed runtime and the agent directly.
