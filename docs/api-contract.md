# API Contract

The contract between the React frontend and the FastAPI backend. Both sides are
implemented against this document.

## 1. Conventions

| Item | Rule |
| --- | --- |
| Base URL | `http://127.0.0.1:<port>`, served by the same process as the UI |
| Auth | none; the server binds to loopback only |
| Request body | JSON, UTF-8 |
| Response body | JSON, UTF-8; `POST /api/chat` returns SSE |
| Field naming | snake_case |
| Timestamps | RFC 3339 in UTC, `2026-11-05T03:00:12Z` |
| Dates | `YYYY-MM-DD` |
| Money | JSON number in USD, no currency symbol |
| Percent | `*_pct` fields are percentage points; `10.0` means 10 percent |
| IDs | Opaque strings |
| Pagination | `page_no` is 1-based, `page_size` is capped at 200 |
| Idempotency | None. Repeating `POST /api/chat` starts another turn on the thread |
| Caching | No response is cacheable |

### Hosted documentation

The server publishes the schema. URLs use the default port; they follow
`port` from the settings, `8000` by default.

| URL | Content |
| --- | --- |
| `http://127.0.0.1:8000/docs` | Swagger UI |
| `http://127.0.0.1:8000/redoc` | ReDoc |
| `http://127.0.0.1:8000/openapi.json` | OpenAPI JSON |

The YAML export is [openapi.yaml](openapi.yaml), regenerated with
`uv run tradecopilot openapi`.

## 2. Shared types

### 2.1 UIMessage

The AI SDK message shape, used in chat requests and thread detail. Only these fields
are defined; extra fields are preserved by the client and ignored by the server.

```json
{
  "id": "u1",
  "role": "user",
  "parts": [{"type": "text", "text": "Should I add NVDA?"}]
}
```

`role` is `user`, `assistant`, or `system`.

Parts:

| Part type | Fields | Roles |
| --- | --- | --- |
| `text` | `text` | user, assistant |
| `reasoning` | `text` | assistant |
| `tool-<toolName>` | `toolCallId`, `state`, `input`, `output`, `errorText`, `approval` | assistant |
| `data-<name>` | `data` | assistant |
| `step-start` | - | assistant |

Tool part states:

| State | Meaning |
| --- | --- |
| `input-streaming` | Tool arguments are still streaming |
| `input-available` | Arguments complete, tool still running |
| `output-available` | Result in `output` |
| `output-error` | Failure text in `errorText` |
| `approval-requested` | Waiting for the user; `approval` carries the descriptor |
| `approval-responded` | The user answered; `approval` carries `approved` and `reason` |

### 2.2 Approval descriptor

Attached to a `propose_order` tool part while `state` is `approval-requested`.

```json
{
  "ticket": {
    "ticker": "NVDA",
    "side": "buy",
    "qty": 10.0,
    "order_type": "market",
    "limit_price": null,
    "estimated_notional": 1950.0
  },
  "rationale": "Earnings beat and guidance raised.",
  "portfolio_impact": {
    "position_weight_after_pct": 11.2,
    "cap_pct": 10.0,
    "violates_cap": true
  }
}
```

`ticket.side` is `buy` or `sell`. `order_type` is `market` or `limit`; `limit_price` is
null for market orders. `rationale` and `portfolio_impact` may be null when they were
not produced for the turn.

### 2.3 Profile

```json
{
  "risk_band": "moderate",
  "position_cap_pct": 10.0,
  "sector_exclusions": ["Energy"],
  "horizon": "weeks",
  "watchlist": ["NVDA", "MSFT"],
  "source_preferences": ["sec_edgar", "finnhub"],
  "execution": {"autonomous": false, "max_order_notional": 2000.0},
  "updated_at": "2026-11-05T02:00:00Z"
}
```

| Field | Type | Constraint |
| --- | --- | --- |
| `risk_band` | enum | `conservative`, `moderate`, `aggressive` |
| `position_cap_pct` | number | 0 to 100, percent of account equity |
| `sector_exclusions` | string[] | GICS sector names |
| `horizon` | enum | `intraday`, `days`, `weeks`, `months` |
| `watchlist` | string[] | uppercase tickers |
| `source_preferences` | string[] | ordered source ids; may be empty |
| `execution.autonomous` | boolean | allows orders without approval when true |
| `execution.max_order_notional` | number | 0 or greater, USD |
| `updated_at` | timestamp | server-managed |

`updated_at` is read-only and ignored on write.

### 2.4 Settings

Application settings owned by the user. API keys are returned in plaintext: the
server is loopback-only and has no authentication.

```json
{
  "agent_model": "deepseek:deepseek-flash",
  "model_api_key": "sk-...",
  "alpaca_api_key": "PK...",
  "alpaca_api_secret": "...",
  "alpaca_base_url": "https://paper-api.alpaca.markets",
  "fmp_api_key": "",
  "finnhub_api_key": "",
  "fred_api_key": "",
  "edgar_user_agent": "TradeCopilot you@example.com",
  "exa_api_key": "",
  "updated_at": "2026-11-05T03:00:12Z"
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `agent_model` | string | `provider:model`; empty means unset |
| `model_api_key` | string | Key for the selected provider; empty means unset |
| `alpaca_api_key` | string | Empty means unset |
| `alpaca_api_secret` | string | Empty means unset |
| `alpaca_base_url` | string | Trading host; defaults to the paper host |
| `fmp_api_key` | string | Fundamentals; its tools are hidden when empty |
| `finnhub_api_key` | string | Company news; its tools are hidden when empty |
| `fred_api_key` | string | Macro series; its tools are hidden when empty |
| `edgar_user_agent` | string | Name and contact email required by SEC EDGAR |
| `exa_api_key` | string | Web search for non-DeepSeek models; its tools are hidden when empty |
| `updated_at` | timestamp | Server-managed |

Resolution order for every field: stored setting, then process environment, then
the repository `.env` file, then the default. Cleared fields fall back to the
environment.

## 3. Endpoints

### 3.1 GET /api/health

Readiness probe and frontend setup signal.

Response 200:

```json
{"status": "ok", "agent_model": "anthropic:claude-sonnet-5"}
```

| Field | Type | Notes |
| --- | --- | --- |
| `status` | string | Always `ok` while the process is serving |
| `agent_model` | string | The effective `provider:model` string; empty when neither settings nor environment provide one |

The endpoint never calls an upstream provider. A server with an empty `agent_model`
still answers 200; chat and thread detail then return 503.

### 3.2 POST /api/chat

Runs one agent turn and streams it as an AI SDK UI message stream.

#### Request

```json
{
  "thread_id": "9f2c8e1a0b7d4c3e9a1f2b3c4d5e6f70",
  "trigger": "submit-message",
  "messageId": "Kq3Zx9mN2pLr",
  "messages": [
    {"id": "u1", "role": "user", "parts": [{"type": "text", "text": "Should I add NVDA?"}]}
  ]
}
```

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `thread_id` | string | no | Omitted creates a new thread |
| `messages` | UIMessage[] | yes | Full client history from `useChat` |
| `trigger` | enum | no | `submit-message` or `regenerate-message`; accepted, not used by the server |
| `messageId` | string | no | Client-generated id of the assistant message being regenerated; ignored by the server |

The server reads only the last element of `messages`:

- A `user` message starts a new turn. Earlier messages are ignored because the
  checkpointer already holds the conversation.
- An `assistant` message whose tool part has `state: "approval-responded"` resumes a
  pending interrupt with the approve or reject decision.

#### Response 200

`Content-Type: text/event-stream`

| Header | Value |
| --- | --- |
| `Cache-Control` | `no-cache` |
| `x-vercel-ai-ui-message-stream` | `v1` |

Framing: one JSON object per frame, `data: <json>\n\n`, then `data: [DONE]\n\n` after
the `finish` part. Frames are not batched.

#### Stream parts

| Part type | Fields |
| --- | --- |
| `start` | `messageId` |
| `start-step` | - |
| `finish-step` | - |
| `text-start` | `id` |
| `text-delta` | `id`, `delta` |
| `text-end` | `id` |
| `reasoning-start` | `id` |
| `reasoning-delta` | `id`, `delta` |
| `reasoning-end` | `id` |
| `tool-input-start` | `toolCallId`, `toolName`, `dynamic` |
| `tool-input-delta` | `toolCallId`, `inputTextDelta` |
| `tool-input-available` | `toolCallId`, `toolName`, `input`, `dynamic` |
| `tool-output-available` | `toolCallId`, `output` |
| `tool-output-error` | `toolCallId`, `errorText` |
| `tool-approval-request` | `approvalId`, `toolCallId`, `reason`, `approvalDescriptor` |
| `data-thread` | `data`, `transient` |
| `data-todos` | `data` |
| `error` | `errorText` |
| `finish` | - |

`messageId` in `start` is generated by the server: `msg-` followed by 32 lowercase hex
characters. The client must render the assistant message under this id. The
request `messageId` is never echoed.

`tool-approval-request.approvalId` equals `toolCallId`. The client replies by sending
the descriptor id back as `approval.id`.

`data-thread`:

```json
{"type": "data-thread", "data": {"thread_id": "9f2c..."}, "transient": true}
```

It is transient, so the client must capture it in `onData` and persist it; it is not
added to `useChat` state. It is emitted even when the turn fails before the graph runs.

`data-todos`:

```json
{
  "type": "data-todos",
  "data": {
    "type": "todos",
    "todos": [{"content": "Pull latest filings", "status": "completed"}]
  }
}
```

`todos[].status` is `pending`, `in_progress`, or `completed`.

#### Approval response

The client answers in the next `POST /api/chat` by sending the same thread and an
assistant message whose tool part is in `approval-responded` state:

```json
{
  "thread_id": "9f2c...",
  "messages": [
    {
      "id": "msg-4f2a...",
      "role": "assistant",
      "parts": [
        {
          "type": "tool-propose_order",
          "toolCallId": "c1",
          "state": "approval-responded",
          "approval": {"id": "c1", "approved": false, "reason": "Position too large"}
        }
      ]
    }
  ]
}
```

There is no separate approval endpoint. The ticket id is the idempotency key inside
the graph; the server rejects a response that does not match a pending interrupt.

#### Errors

| Status | When | Body |
| --- | --- | --- |
| 422 | Invalid request body | FastAPI validation shape |
| 503 | `agent_model` is empty | `{"detail": "..."}` |

Failures inside the stream do not change the HTTP status. The server emits an `error`
part, then `finish`, then `[DONE]`.

### 3.3 GET /api/threads

Lists conversation threads, newest first.

#### Query

| Parameter | Type | Default | Constraint |
| --- | --- | --- | --- |
| `page_no` | integer | 1 | 1 or greater |
| `page_size` | integer | 50 | 1 to 200 |

#### Response 200

```json
{
  "items": [
    {
      "thread_id": "9f2c8e1a0b7d4c3e9a1f2b3c4d5e6f70",
      "title": "NVDA earnings call",
      "created_at": "2026-11-04T03:00:12Z",
      "updated_at": "2026-11-04T03:05:41Z"
    }
  ],
  "page_no": 1,
  "page_size": 50,
  "total": 12
}
```

| Field | Notes |
| --- | --- |
| `items` | Sorted by `updated_at` descending |
| `total` | Number of thread rows that match, across all pages |
| `title` | First user message, trimmed to about 60 characters; set when the thread is created |

A page past the end returns 200 with `items: []`. `total` counts records, not pages.
The endpoint reads SQLite only and works while `agent_model` is empty.

### 3.4 GET /api/threads/{thread_id}

Returns one thread with its conversation, ready to seed `useChat({initialMessages})`.

#### Response 200

```json
{
  "thread_id": "9f2c8e1a0b7d4c3e9a1f2b3c4d5e6f70",
  "title": "NVDA earnings call",
  "created_at": "2026-11-04T03:00:12Z",
  "updated_at": "2026-11-04T03:05:41Z",
  "messages": [
    {"id": "u1", "role": "user", "parts": [{"type": "text", "text": "Should I add NVDA?"}]},
    {
      "id": "a1",
      "role": "assistant",
      "parts": [
        {"type": "text", "text": "The position cap would be exceeded."},
        {
          "type": "tool-propose_order",
          "toolCallId": "c1",
          "state": "approval-requested",
          "input": {"ticker": "NVDA", "side": "buy", "qty": 10},
          "approval": {"id": "c1", "ticket": {}, "rationale": "...", "portfolio_impact": {}}
        }
      ]
    }
  ]
}
```

Messages are rehydrated from the checkpoint:

- Human and assistant messages become `user` and `assistant` messages.
- Tool results are attached to their `tool-<name>` part; completed calls have
  `state: "output-available"`.
- A pending interrupt produces `state: "approval-requested"` with the same descriptor
  the live stream would send, so an interrupted thread resumes after a restart.
- The `todos` channel becomes a `data-todos` part on the last assistant message,
  because it is transient on the live stream.
- `data-thread` is not included; the thread id is the resource key.

#### Errors

| Status | When |
| --- | --- |
| 404 | No thread row or no checkpoint for the id |
| 503 | `agent_model` is empty, because the detail reads graph state |

### 3.5 GET /api/portfolio

Current account, positions, and equity history.

#### Query

| Parameter | Type | Default | Values |
| --- | --- | --- | --- |
| `range` | enum | `1M` | `1D`, `1W`, `1M`, `3M`, `1Y`, `ALL` |

`range` affects `equity_curve` only; the account and positions are always current.

#### Response 200

```json
{
  "as_of": "2026-11-05T03:00:12Z",
  "paper": true,
  "account": {
    "currency": "USD",
    "equity": 100000.0,
    "cash": 25000.0,
    "buying_power": 50000.0,
    "long_market_value": 75000.0
  },
  "day": {"pnl": 250.0, "pnl_pct": 0.25},
  "positions": [
    {
      "ticker": "NVDA",
      "side": "long",
      "sector": "Information Technology",
      "qty": 10.0,
      "avg_entry_price": 180.0,
      "current_price": 195.0,
      "market_value": 1950.0,
      "unrealized_pl": 150.0,
      "unrealized_pl_pct": 8.33,
      "weight_pct": 1.95
    }
  ],
  "equity_curve": [{"t": "2026-10-05T00:00:00Z", "equity": 99000.0}]
}
```

| Field | Notes |
| --- | --- |
| `as_of` | Server time when the snapshot was assembled |
| `paper` | True when trading against a paper account |
| `day.pnl` | `equity - last_equity`, from the account |
| `day.pnl_pct` | `(equity - last_equity) / last_equity * 100`; 0 when `last_equity` is 0 |
| `positions[].side` | `long` or `short` |
| `positions[].sector` | GICS sector; null when unavailable |
| `positions[].unrealized_pl_pct` | Percentage points |
| `positions[].weight_pct` | `market_value / equity * 100` |
| `equity_curve` | `1D` yields intraday points; other ranges yield daily closes |

A flat account returns `positions: []` and still returns the account. `equity_curve` may
be empty for `1D` outside trading hours.

#### Errors

| Status | When |
| --- | --- |
| 503 | Broker is unconfigured or unreachable |

### 3.6 GET /api/profile

Returns the Profile object defined in section 2.3.

Response 200: Profile. No other status is expected.

### 3.7 PATCH /api/profile

Partially updates the profile.

#### Request

Any subset of the writable Profile fields. Omitted fields are untouched. An explicit
empty list clears a list. When `execution` is present it replaces the whole object;
there is no nested merge.

```json
{
  "position_cap_pct": 8.0,
  "execution": {"autonomous": false, "max_order_notional": 1500.0}
}
```

`updated_at` is ignored if sent.

#### Response 200

The full updated Profile.

#### Validation

Invalid enum values, wrong types, and out-of-range numbers return 422 with FastAPI's
validation shape. The endpoint does not require a confirmation token: the local user
is the authority when editing directly. The client warns before sending changes that
affect hard constraints or execution; that warning is a UI concern, not a server check.

### 3.8 GET /api/journal

Lists decision journal entries, newest first.

#### Query

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `page_no` | integer | 1 | 1 or greater |
| `page_size` | integer | 50 | 1 to 200 |
| `status` | enum | none | `proposed`, `approved`, `edited`, `rejected`, `deferred`, `submitted`, `filled`, `failed`, `skipped_unfunded` |
| `ticker` | string | none | Matches any leg, case-insensitive |
| `from` | date | none | Inclusive lower bound on `created_at` |
| `to` | date | none | Inclusive upper bound on `created_at` |

#### Response 200

```json
{
  "items": [
    {
      "id": "t_7f3a...",
      "created_at": "2026-11-04T14:02:11Z",
      "legs": [
        {
          "ticker": "NVDA",
          "side": "sell",
          "qty": 10.0,
          "notional": 1950.0,
          "fill_price": 195.0,
          "fill_at": "2026-11-04T14:02:40Z",
          "status": "filled"
        },
        {
          "ticker": "AAPL",
          "side": "buy",
          "qty": 5.0,
          "notional": 1200.0,
          "fill_price": 240.0,
          "fill_at": "2026-11-04T14:02:41Z",
          "status": "filled"
        }
      ],
      "thesis": "Earnings beat and guidance raised.",
      "horizon": "weeks",
      "evidence_ids": ["ev1"],
      "status": "filled",
      "user_action": "approve",
      "rejection_reason": null,
      "outcome": {
        "counterfactual": false,
        "entry_price": 195.0,
        "entry_at": "2026-11-04T14:02:40Z",
        "horizon": "weeks",
        "return_pct": 3.2,
        "benchmark": "SPY",
        "benchmark_return_pct": 1.1,
        "alpha_pct": 2.1,
        "computed_at": "2026-11-05T03:00:12Z"
      }
    }
  ],
  "page_no": 1,
  "page_size": 50,
  "total": 3
}
```

| Field | Notes |
| --- | --- |
| `id` | Decision id shared by every event of one ticket |
| `legs` | One entry per order, with its own fill data and status |
| `status` | Decision status derived from the legs |
| `user_action` | `approve`, `edit`, `reject`, `defer`, or null while pending |
| `outcome` | Null until computable; see below |

The newest event per decision is returned. `total` counts decisions, not event rows.

Outcome rules:

- Computed lazily on read from daily bars up to now.
- `entry_price` is the fill price, or the decision-time quote when not executed.
- `horizon` is the horizon stated in the recommendation.
- Returns are compared with `benchmark` (SPY) over the same window.
- Rejected proposals get a counterfactual outcome with `counterfactual: true`.
- `outcome` is null when the horizon has not elapsed or bars are missing.

#### Errors

422 for invalid query values.

### 3.9 GET /api/settings

Returns the effective settings defined in section 2.4.

Response 200: Settings. Always 200. The response carries `Cache-Control: no-store`.

### 3.10 PATCH /api/settings

Partially updates the stored settings.

#### Request

Any subset of the fields. Omitted fields are untouched. An empty string clears a
stored value, which makes the environment fallback apply again.

```json
{
  "agent_model": "deepseek:deepseek-flash",
  "model_api_key": "sk-..."
}
```

`updated_at` is ignored if sent.

#### Response 200

The full effective Settings, with secrets in plaintext and `Cache-Control: no-store`.

#### Behaviour

Changing `agent_model` or `model_api_key` discards the cached agent graph. The next
chat turn builds a new graph with the new model.

#### Errors

422 for wrong field types.

## 4. Error format

All non-streaming errors use `{"detail": ...}`.

| Status | Body |
| --- | --- |
| 404 | `{"detail": "thread not found"}` |
| 422 | `{"detail": [{"loc": ["body", "position_cap_pct"], "msg": "...", "type": "..."}]}` |
| 503 | `{"detail": "AGENT_MODEL is not set. ..."}` |

5xx other than 503 is unexpected and indicates a server bug.

## 5. Non-goals

- Authentication, multi-user scoping, CORS.
- Thread rename, delete, and search.
- Journal entry detail, mutation, or export.
- Manual order placement outside the chat approval flow.
