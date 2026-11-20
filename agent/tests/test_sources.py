"""Provider adapters, exercised with recorded responses and no network."""

import asyncio
import json
from datetime import UTC, datetime

import httpx
from tradecopilot_agent.models import AppSettings
from tradecopilot_agent.sources.alpaca import AlpacaSource
from tradecopilot_agent.sources.edgar import EdgarSource
from tradecopilot_agent.sources.feeds import FmpSource


def _settings(**overrides: object) -> AppSettings:
    values: dict = {
        "alpaca_api_key": "key",
        "alpaca_api_secret": "secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "fmp_api_key": "fmp",
        "finnhub_api_key": "",
        "fred_api_key": "",
        "edgar_user_agent": "TradeCopilot you@example.com",
        "updated_at": "2026-11-05T00:00:00Z",
    }
    values.update(overrides)
    return AppSettings(**values)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_capabilities_follow_the_configured_keys() -> None:
    """A missing key removes its provider."""
    settings = _settings(fmp_api_key="", fred_api_key="")
    source = FmpSource(lambda: settings)

    assert source.capabilities() == set()
    assert AlpacaSource(lambda: _settings()).capabilities() == {
        "alpaca",
        "order_execution",
    }


def test_alpaca_quote_is_marked_stale_when_old() -> None:
    """Free-tier quotes older than 15 minutes are stale."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"latestTrade": {"p": 123.5, "t": "2020-01-01T00:00:00Z"}}
        )

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    output = asyncio.run(source.quote("NVDA"))

    assert output.error is None
    assert output.evidence[0].payload["price"] == 123.5
    assert output.evidence[0].stale is True


def test_fmp_fundamentals_are_cached_for_the_day() -> None:
    """Two calls in one day make one request."""
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        assert request.url.params["symbol"] == "NVDA"
        return httpx.Response(
            200, json=[{"sector": "Technology", "industry": "Semiconductors"}]
        )

    source = FmpSource(lambda: _settings(), client=_client(handler))
    first = asyncio.run(source.fundamentals("NVDA"))
    second = asyncio.run(source.fundamentals("NVDA"))

    assert calls["count"] == 1
    assert first.evidence[0].payload["sector"] == "Technology"
    assert second.summary == first.summary


def test_edgar_picks_the_requested_period() -> None:
    """The XBRL fact carries the requested period and fiscal label."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(
                200, json={"0": {"ticker": "NVDA", "cik_str": 1045810}}
            )
        return httpx.Response(
            200,
            json={
                "units": {
                    "USD": [
                        {
                            "end": "2025-07-27",
                            "val": 30_000_000_000,
                            "fy": 2025,
                            "fp": "Q2",
                            "form": "10-Q",
                            "filed": "2025-08-20",
                        },
                        {
                            "end": "2025-10-26",
                            "val": 35_082_000_000,
                            "fy": 2025,
                            "fp": "Q3",
                            "form": "10-Q",
                            "filed": "2025-11-20",
                        },
                    ]
                }
            },
        )

    source = EdgarSource(lambda: _settings(), client=_client(handler))
    output = asyncio.run(source.xbrl_fact("NVDA", "Revenues", "FY2025Q3", "USD"))

    assert output.error is None
    payload = output.evidence[0].payload
    assert payload["value"] == 35_082_000_000
    assert payload["period"] == "2025-10-26"
    assert output.evidence[0].published_at == "2025-11-20"


def test_edgar_requires_a_contact_user_agent() -> None:
    """Without the contact header the provider is unavailable."""
    source = EdgarSource(lambda: _settings(edgar_user_agent=""))

    assert source.capabilities() == set()


def test_evidence_ids_are_stable() -> None:
    """Replaying the same source produces the same evidence id."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"latestTrade": {"p": 1.0, "t": "2026-11-05T14:00:00Z"}}
        )

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    first = asyncio.run(source.quote("NVDA"))
    second = asyncio.run(source.quote("NVDA"))

    assert first.evidence[0].id == second.evidence[0].id


def test_alpaca_clock_reports_the_session() -> None:
    """The clock call reads is_open and next_open from the trading host."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/clock"
        return httpx.Response(
            200, json={"is_open": False, "next_open": "2026-11-18T09:30:00-05:00"}
        )

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    clock = asyncio.run(source.clock())

    assert clock is not None
    assert clock.is_open is False
    assert clock.next_open == "2026-11-18T09:30:00-05:00"


def test_alpaca_clock_is_none_when_rejected() -> None:
    """An unauthenticated clock call falls back to the local window."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "unauthorized."})

    source = AlpacaSource(lambda: _settings(), client=_client(handler))

    assert asyncio.run(source.clock()) is None


def test_alpaca_places_a_limit_order_in_extended_hours() -> None:
    """Outside the regular session the order is a limit flagged for extended hours."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "accepted"})

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    leg = {"ticker": "SPY", "side": "buy", "qty": 1, "entry_price": 612.34}
    output = asyncio.run(
        source.place_leg(leg, "order-1", now=datetime(2026, 11, 17, 12, 0, tzinfo=UTC))
    )

    assert output.error is None
    assert seen["type"] == "limit"
    assert seen["limit_price"] == "612.34"
    assert seen["extended_hours"] is True


def test_alpaca_places_a_market_order_in_regular_hours() -> None:
    """The regular session keeps market orders."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "accepted"})

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    leg = {"ticker": "SPY", "side": "buy", "qty": 1, "entry_price": 612.34}
    asyncio.run(
        source.place_leg(leg, "order-2", now=datetime(2026, 11, 17, 15, 0, tzinfo=UTC))
    )

    assert seen["type"] == "market"
    assert "extended_hours" not in seen


def test_alpaca_places_a_limit_order_in_regular_hours() -> None:
    """A limit leg keeps its type and price inside the regular session."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "accepted"})

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    leg = {
        "ticker": "SPY",
        "side": "sell",
        "qty": 1,
        "entry_price": 612.34,
        "order_type": "limit",
    }
    asyncio.run(
        source.place_leg(leg, "order-3", now=datetime(2026, 11, 17, 15, 0, tzinfo=UTC))
    )

    assert seen["type"] == "limit"
    assert seen["limit_price"] == "612.34"
    assert "extended_hours" not in seen


def test_alpaca_turns_a_market_leg_into_a_limit_outside_regular_hours() -> None:
    """A market order cannot be sent in extended hours, so the price is a limit."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "accepted"})

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    leg = {
        "ticker": "SPY",
        "side": "sell",
        "qty": 1,
        "entry_price": 612.34,
        "order_type": "market",
    }
    asyncio.run(
        source.place_leg(leg, "order-4", now=datetime(2026, 11, 17, 12, 0, tzinfo=UTC))
    )

    assert seen["type"] == "limit"
    assert seen["limit_price"] == "612.34"
    assert seen["extended_hours"] is True


def test_alpaca_lists_open_orders() -> None:
    """Open orders are normalized to the fields the agent needs."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(
            200,
            json=[
                {
                    "id": "o1",
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": "1",
                    "filled_qty": "0",
                    "type": "market",
                    "limit_price": None,
                    "status": "accepted",
                    "submitted_at": "2026-11-19T13:00:00Z",
                }
            ],
        )

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    output = asyncio.run(source.open_orders())

    assert seen["status"] == "open"
    assert output.error is None
    assert json.loads(output.summary)[0]["order_id"] == "o1"
    assert json.loads(output.summary)[0]["ticker"] == "AAPL"


def test_alpaca_cancels_one_order() -> None:
    """Cancelling deletes the order by id."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/v2/orders/o1"
        return httpx.Response(204)

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    output = asyncio.run(source.cancel_order("o1"))

    assert output.error is None
    assert "o1" in output.summary


def test_alpaca_bars_requests_a_date_range() -> None:
    """Alpaca needs an explicit window to return bars."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={"bars": [{"t": "2026-11-04T00:00:00Z", "c": 1.5}]},
        )

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    output = asyncio.run(source.bars("SPY", "1d", "1d"))

    assert "start" in seen and "end" in seen
    assert output.summary == "1 bars for SPY"


def test_account_summary_states_the_environment(monkeypatch) -> None:
    """A live account is named in the tool summary the model reads."""
    from tradecopilot_agent.models import Account, DayPnl, Portfolio, Position

    snapshot = Portfolio(
        as_of="2026-11-17T00:00:00Z",
        paper=False,
        account=Account(
            currency="USD",
            equity=10.0,
            cash=10.0,
            buying_power=20.0,
            long_market_value=311.0,
        ),
        day=DayPnl(pnl=0.0, pnl_pct=0.0),
        positions=[
            Position(
                ticker="NVDA",
                side="long",
                sector="Technology",
                qty=1.0,
                avg_entry_price=300.0,
                current_price=311.0,
                market_value=311.0,
                unrealized_pl=11.0,
                unrealized_pl_pct=3.67,
                weight_pct=5.0,
            )
        ],
        equity_curve=[],
    )

    async def fake_fetch(_settings, _range):
        return snapshot

    monkeypatch.setattr("tradecopilot_agent.sources.alpaca.fetch_portfolio", fake_fetch)
    source = AlpacaSource(lambda: _settings())

    output = asyncio.run(source.portfolio())

    assert output.summary.startswith("Live account.")
    assert "Positions: NVDA 1.0 shares worth 311.0." in output.summary
    assert output.evidence[0].payload["paper"] is False


def test_account_payload_reports_capability_and_signs_shorts(monkeypatch) -> None:
    """The tool payload carries the flag and a negative short quantity."""
    from tradecopilot_agent import portfolio as portfolio_module
    from tradecopilot_agent import sources

    snapshot = portfolio_module._portfolio(
        _settings(),
        {
            "currency": "USD",
            "equity": "100000",
            "last_equity": "99000",
            "cash": "50000",
            "buying_power": "100000",
            "long_market_value": "50000",
            "shorting_enabled": True,
        },
        [
            {
                "symbol": "AMD",
                "side": "short",
                "qty": "5",
                "market_value": "-500",
                "avg_entry_price": "120",
                "current_price": "100",
                "unrealized_pl": "-100",
                "unrealized_plpc": "-0.1667",
            }
        ],
        {},
    )

    async def fake_fetch(settings: object, range_: str) -> object:
        return snapshot

    monkeypatch.setattr(sources.alpaca, "fetch_portfolio", fake_fetch)
    source = AlpacaSource(lambda: _settings())

    output = asyncio.run(source.portfolio())

    payload = output.evidence[0].payload
    assert payload["shorting_enabled"] is True
    assert payload["positions"][0]["qty"] == -5.0


def test_alpaca_sends_the_position_intent() -> None:
    """An explicit intent reaches the order body."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "accepted"})

    source = AlpacaSource(lambda: _settings(), client=_client(handler))
    leg = {"ticker": "SPY", "side": "sell", "qty": 5}
    asyncio.run(
        source.place_leg(
            leg,
            "order-1",
            "sell_to_open",
            now=datetime(2026, 11, 17, 15, 0, tzinfo=UTC),
        )
    )

    assert seen["position_intent"] == "sell_to_open"
