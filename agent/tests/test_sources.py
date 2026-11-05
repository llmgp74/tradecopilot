"""Provider adapters, exercised with recorded responses and no network."""

import asyncio

import httpx
from tradecopilot_agent.models import AppSettings
from tradecopilot_agent.sources.alpaca import AlpacaSource
from tradecopilot_agent.sources.edgar import EdgarSource
from tradecopilot_agent.sources.feeds import FmpSource


def _settings(**overrides: object) -> AppSettings:
    values: dict = {
        "agent_model": "",
        "model_api_key": "",
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
