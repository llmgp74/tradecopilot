"""Request and response models for the HTTP API.

The models are the source of the OpenAPI document served at ``/docs``.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

RiskBand = Literal["conservative", "moderate", "aggressive"]
Horizon = Literal["intraday", "days", "weeks", "months"]
PortfolioRange = Literal["1D", "1W", "1M", "3M", "1Y", "ALL"]
JournalStatus = Literal[
    "proposed", "approved", "edited", "rejected", "deferred", "filled", "failed"
]
Side = Literal["buy", "sell"]
UserAction = Literal["approve", "edit", "reject", "defer"]


class Health(BaseModel):
    """Readiness payload."""

    status: str
    agent_model: str


class ExecutionSettings(BaseModel):
    """Order execution permissions."""

    autonomous: bool = False
    max_order_notional: float = Field(default=1000.0, ge=0)


class Profile(BaseModel):
    """Durable user profile."""

    risk_band: RiskBand = "moderate"
    position_cap_pct: float = Field(default=10.0, ge=0, le=100)
    sector_exclusions: list[str] = Field(default_factory=list)
    horizon: Horizon = "weeks"
    watchlist: list[str] = Field(default_factory=list)
    source_preferences: list[str] = Field(default_factory=list)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    updated_at: str


class ProfilePatch(BaseModel):
    """Partial profile update."""

    risk_band: RiskBand | None = None
    position_cap_pct: float | None = Field(default=None, ge=0, le=100)
    sector_exclusions: list[str] | None = None
    horizon: Horizon | None = None
    watchlist: list[str] | None = None
    source_preferences: list[str] | None = None
    execution: ExecutionSettings | None = None


class AppSettings(BaseModel):
    """User-editable application settings."""

    agent_model: str = ""
    model_api_key: str = ""
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = ""
    updated_at: str


class AppSettingsPatch(BaseModel):
    """Partial settings update."""

    agent_model: str | None = None
    model_api_key: str | None = None
    alpaca_api_key: str | None = None
    alpaca_api_secret: str | None = None
    alpaca_base_url: str | None = None


class ThreadSummary(BaseModel):
    """Thread metadata."""

    thread_id: str
    title: str
    created_at: str
    updated_at: str


class ThreadList(BaseModel):
    """One page of threads."""

    items: list[ThreadSummary]
    page_no: int
    page_size: int
    total: int


class ThreadDetail(ThreadSummary):
    """Thread metadata plus its rehydrated messages."""

    messages: list[dict[str, Any]]


class Account(BaseModel):
    """Broker account snapshot."""

    currency: str
    equity: float
    cash: float
    buying_power: float
    long_market_value: float


class DayPnl(BaseModel):
    """Change in equity since the previous close."""

    pnl: float
    pnl_pct: float


class Position(BaseModel):
    """One open position."""

    ticker: str
    side: Literal["long", "short"]
    sector: str | None
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float
    weight_pct: float


class EquityPoint(BaseModel):
    """One point on the equity curve."""

    t: str
    equity: float


class Portfolio(BaseModel):
    """Account, positions, and equity history."""

    as_of: str
    paper: bool
    account: Account
    day: DayPnl
    positions: list[Position]
    equity_curve: list[EquityPoint]


class JournalOutcome(BaseModel):
    """Lazily computed decision outcome."""

    counterfactual: bool
    entry_price: float
    entry_at: str
    horizon: Horizon
    return_pct: float
    benchmark: str
    benchmark_return_pct: float
    alpha_pct: float
    computed_at: str


class JournalEntry(BaseModel):
    """One decision journal row."""

    id: str
    created_at: str
    tickers: list[str]
    side: Side
    qty: float
    size_pct: float
    thesis: str
    evidence_ids: list[str]
    status: JournalStatus
    user_action: UserAction | None
    rejection_reason: str | None
    fill_price: float | None
    fill_at: str | None
    outcome: JournalOutcome | None


class JournalList(BaseModel):
    """One page of journal rows."""

    items: list[JournalEntry]
    page_no: int
    page_size: int
    total: int
