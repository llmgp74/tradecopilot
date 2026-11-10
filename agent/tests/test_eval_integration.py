"""Exercise historical memory and the real graph with local model responses."""

import asyncio
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn, cast
from unittest.mock import create_autospec

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatResult
from pydantic import Field
from tradecopilot_agent import agent as agent_module
from tradecopilot_agent.data import DataSource
from tradecopilot_agent.memory import MemoryConfig, MemoryStore
from tradecopilot_agent.middleware import TradingMemoryMiddleware, render_memory
from tradecopilot_agent.state import EvidenceRecord, ToolOutput
from tradecopilot_agent.store import Store

_DECISION = datetime(2020, 9, 15, 14, tzinfo=UTC)


def _forbidden(*args: Any, **kwargs: Any) -> NoReturn:
    raise AssertionError(
        "This test must not construct providers or contact the network."
    )


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent outbound sockets throughout these local tests.

    Args:
        monkeypatch: Scoped pytest patch manager.
    """
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", _forbidden)


def _event(
    decision_id: str, created_at: str, status: str = "proposed"
) -> dict[str, Any]:
    return {
        "decision_id": decision_id,
        "created_at": created_at,
        "status": status,
        "legs": [{"ticker": "SYNAA", "side": "buy", "qty": 1}],
        "thesis": decision_id,
    }


class _LocalModel(FakeMessagesListChatModel):
    """Return scripted messages while retaining the real graph's input prompts."""

    observed: list[list[BaseMessage]] = Field(default_factory=list)

    def bind_tools(
        self, tools: Any, *, tool_choice: Any = None, **kwargs: Any
    ) -> BaseChatModel:
        """Accept graph tools without constructing a provider binding.

        Args:
            tools: Available tools; scripted responses choose the one to call.
            tool_choice: Unused provider option.
            kwargs: Unused provider options.

        Returns:
            This local model.
        """
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.observed.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)


@pytest.mark.parametrize("autonomous", [False, True])
def test_profile_formats_include_the_same_user_facts(autonomous: bool) -> None:
    """Keep permissions and source preferences present in both memory formats.

    Args:
        autonomous: Permission value checked in both renderings.
    """
    profile = {
        "risk_band": "aggressive",
        "position_cap_pct": 7.5,
        "sector_exclusions": ["Energy", "Utilities"],
        "horizon": "months",
        "watchlist": ["SYNAA", "SYNBB"],
        "source_preferences": ["edgar", "fmp"],
        "execution": {"autonomous": autonomous, "max_order_notional": 2500.0},
    }
    prose = render_memory("prose", profile, [])
    structured = render_memory("structured", profile, [])
    for fact in (
        "aggressive",
        "7.5",
        "Energy",
        "Utilities",
        "months",
        "SYNAA",
        "SYNBB",
        "edgar",
        "fmp",
        "2500.0",
    ):
        assert fact in prose
        assert fact in structured
    assert ("enabled" if autonomous else "disabled") in prose
    assert f"autonomous={autonomous}" in structured
    assert render_memory("none", profile, []) == ""


def test_historical_journal_selects_known_revisions_before_limiting(
    tmp_path: Path,
) -> None:
    """Exclude future revisions and preserve the decision state known at cutoff.

    Args:
        tmp_path: Isolated database directory.
    """
    store = Store(tmp_path / "data.db")
    store.append_journal(_event("prior", "2020-09-14T10:00:00Z"))
    store.append_journal(_event("prior", "2020-09-16T10:00:00Z", "filled"))
    store.append_journal(_event("at-cutoff", "2020-09-15T22:00:00+08:00"))
    store.append_journal(
        _event("too-old", (_DECISION - timedelta(days=91)).isoformat())
    )
    store.append_journal(_event("invalid-time", "not-a-time"))
    store.append_journal(_event("naive-time", "2020-09-14T10:00:00"))
    for index in range(15):
        store.append_journal(_event(f"future-{index}", "2020-09-16T11:00:00Z"))
    rows = store.recent_journal(
        ["SYNAA"],
        since=(_DECISION - timedelta(days=90)).isoformat(),
        until=_DECISION.isoformat(),
        limit=2,
    )
    assert [row["id"] for row in rows] == ["at-cutoff", "prior"]
    assert rows[1]["status"] == "proposed"
    assert (
        store.recent_journal(
            ["SYNAA"], since="2020-09-15", until=_DECISION.isoformat(), limit=1
        )[0]["id"]
        == "at-cutoff"
    )
    with pytest.raises(ValueError, match="timezone"):
        store.recent_journal(["SYNAA"], since="2020-09-01", until="2020-09-15")


class _LegacyStore:
    """Provide the original live MemoryStore method signatures."""

    def get_profile(self) -> dict[str, Any]:
        """Return the watchlist used to recognize a request ticker."""
        return {"watchlist": ["SYNAA"]}

    def recent_journal(
        self, tickers: list[str], since: str, limit: int
    ) -> list[dict[str, Any]]:
        """Return an entry without accepting the new historical keyword.

        Args:
            tickers: Requested tickers.
            since: Live lower date bound.
            limit: Maximum entries.

        Returns:
            One entry that identifies this legacy adapter.
        """
        return [{"id": "legacy-live", "thesis": "Legacy store was called."}]

    def append_journal(self, event: dict[str, Any]) -> None:
        """Reject writes because this test only retrieves memory.

        Args:
            event: Unexpected journal event.

        Raises:
            AssertionError: This test must not append journal events.
        """
        raise AssertionError("Unexpected journal write.")


def test_live_memory_does_not_require_the_new_keyword() -> None:
    """Keep existing live adapters usable without an ``until`` parameter."""
    config = MemoryConfig(condition="full", store=cast(MemoryStore, _LegacyStore()))
    middleware = TradingMemoryMiddleware(config)
    request = SimpleNamespace(messages=[HumanMessage(content="Review SYNAA")], state={})
    assert "legacy-live" in middleware._block(request)


@pytest.mark.parametrize("precise_time", [False, True])
def test_local_graph_uses_the_scenario_clock_and_injected_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, precise_time: bool
) -> None:
    """Run the actual graph, quote tool, and memory without APIs.

    Args:
        tmp_path: Isolated database directory.
        monkeypatch: Scoped provider-construction guard.
        precise_time: Use a timestamp or the backward-compatible as_of date.
    """
    monkeypatch.setattr(agent_module, "build_chat_model", _forbidden)
    monkeypatch.setattr(agent_module, "get_settings", _forbidden)
    store = Store(tmp_path / "data.db")
    store.patch_profile({"watchlist": ["SYNAA"]})
    store.append_journal(_event("known-history", "2020-09-14T10:00:00Z"))
    store.append_journal(_event("later-today", "2020-09-15T20:00:00Z"))
    store.append_journal(_event("future-history", "2020-09-16T10:00:00Z"))
    store.append_journal(_event("expired-history", "2020-01-01T10:00:00Z"))
    source = create_autospec(DataSource, instance=True)
    source.capabilities.return_value = {"alpaca"}
    source.quote.return_value = ToolOutput(
        summary="SYNAA quote is 100.",
        evidence=[
            EvidenceRecord(
                id="quote-1",
                tool="get_quote",
                source="synthetic",
                published_at="2020-09-15T12:00:00Z",
                fetched_at="2020-09-15T13:00:00Z",
                payload={"kind": "quote", "ticker": "SYNAA", "price": 100.0},
            )
        ],
    )
    model = _LocalModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_quote",
                        "args": {"ticker": "SYNAA"},
                        "id": "quote-call",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="The quote is 100."),
        ]
    )
    graph = agent_module.build_agent(
        MemoryConfig(condition="full", store=store),
        source,
        _DECISION.date(),
        model=model,
        decision_time=_DECISION if precise_time else None,
    )
    result = asyncio.run(
        graph.ainvoke({"messages": [HumanMessage(content="Review SYNAA")]})
    )
    assert result["messages"][-1].content == "The quote is 100."
    source.quote.assert_awaited_once_with("SYNAA")
    assert result["evidence"]["quote-1"]["payload"]["price"] == 100.0
    assert "verification" not in result or result["verification"] == []
    assert any(
        isinstance(message, ToolMessage) and message.tool_call_id == "quote-call"
        for message in result["messages"]
    )
    prompt = str(model.observed[0][0].content)
    assert "known-history" in prompt
    assert "future-history" not in prompt
    assert "expired-history" not in prompt
    assert ("later-today" in prompt) is (not precise_time)


def test_builder_rejects_a_naive_scenario_clock() -> None:
    """Reject ambiguous historical timestamps before constructing a provider."""
    with pytest.raises(ValueError, match="timezone"):
        agent_module.build_agent(
            MemoryConfig(condition="none", store=cast(MemoryStore, _LegacyStore())),
            create_autospec(DataSource, instance=True),
            decision_time=_DECISION.replace(tzinfo=None),
        )
