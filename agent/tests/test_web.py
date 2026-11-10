"""Web search adapters and evidence mapping."""

import asyncio
import json
from unittest.mock import MagicMock

import httpx
import pytest
from tradecopilot_agent.tools import build_tools, web_output
from tradecopilot_agent.web import (
    DeepSeekWebSearch,
    ExaWebSearch,
    WebResult,
    WebSearchUnavailable,
    build_web_search,
)


def _client(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_deepseek_search_maps_results() -> None:
    """DeepSeek results become titles, URLs, summaries, and dates."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Market recap",
                        "url": "https://example.com/recap",
                        "summary": "Stocks rose on earnings.",
                        "snippet": "Stocks rose.",
                        "date": "2026-11-09T00:00:00+00:00",
                        "authority": 3,
                    }
                ]
            },
        )

    search = DeepSeekWebSearch("key", transport=_client(handler))
    results = asyncio.run(search.search("market recap", 5))

    assert captured["path"] == "/v1/tools/search"
    assert captured["body"] == {
        "query": "market recap",
        "count": 5,
        "need_content": False,
    }
    assert results == [
        WebResult(
            title="Market recap",
            url="https://example.com/recap",
            summary="Stocks rose on earnings.",
            published_at="2026-11-09T00:00:00+00:00",
            source="deepseek_search",
            authority=3,
        )
    ]


def test_exa_search_maps_highlights() -> None:
    """Exa results use the first highlight as the summary."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "NVDA jumps",
                        "url": "https://example.com/nvda",
                        "publishedDate": "2026-11-08T00:00:00.000Z",
                        "highlights": ["Nvidia rose after guidance."],
                    }
                ]
            },
        )

    search = ExaWebSearch("key", transport=_client(handler))
    results = asyncio.run(search.search("NVDA", 3))

    assert captured["path"] == "/search"
    assert captured["body"]["numResults"] == 3
    assert results[0].summary == "Nvidia rose after guidance."
    assert results[0].published_at == "2026-11-08T00:00:00.000Z"
    assert results[0].source == "exa_search"


def test_adapter_error_is_wrapped() -> None:
    """A broker error becomes a search error the tool can report."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    search = DeepSeekWebSearch("key", transport=_client(handler))
    with pytest.raises(WebSearchUnavailable):
        asyncio.run(search.search("market", 3))


def test_build_web_search_follows_the_model() -> None:
    """A DeepSeek model uses its own search; others use Exa when keyed."""
    assert isinstance(
        build_web_search("deepseek:deepseek-chat", "ds", "exa"), DeepSeekWebSearch
    )
    assert isinstance(
        build_web_search("anthropic:deepseek-flash", "ds", "exa"), DeepSeekWebSearch
    )
    assert isinstance(build_web_search("openai:gpt-5", "oai", "exa"), ExaWebSearch)
    assert isinstance(build_web_search("deepseek:x", "", "exa"), ExaWebSearch)
    assert build_web_search("openai:gpt-5", "oai", None) is None


def test_deepseek_model_without_a_key_has_no_search() -> None:
    """No key in settings means no search tool."""
    assert build_web_search("anthropic:deepseek-flash", "", None) is None


def test_web_tool_is_registered_only_with_a_searcher() -> None:
    """The model only sees web_search when a provider is configured."""
    without = build_tools(MagicMock(), MagicMock(), None)
    assert "web_search" not in {tool.name for tool in without}

    with_search = build_tools(
        MagicMock(),
        MagicMock(),
        None,
        searcher=DeepSeekWebSearch("key"),
    )
    assert "web_search" in {tool.name for tool in with_search}


def test_web_output_adds_provenance() -> None:
    """Each result becomes an evidence record with its URL and date."""
    output = web_output(
        "market recap",
        [
            WebResult(
                title="Recap",
                url="https://example.com/recap",
                summary="Stocks rose.",
                published_at="2026-11-09T00:00:00+00:00",
                source="deepseek_search",
            )
        ],
    )

    assert len(output.evidence) == 1
    record = output.evidence[0]
    assert record.tool == "web_search"
    assert record.url == "https://example.com/recap"
    assert record.published_at == "2026-11-09T00:00:00+00:00"
    assert record.payload["title"] == "Recap"
    assert "Recap" in output.summary
