"""Check DEV-01 fixture arithmetic and local agent contracts without a model."""

import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tradecopilot_agent.constraints import check_ticket
from tradecopilot_agent.middleware import render_memory
from tradecopilot_agent.state import ToolOutput
from tradecopilot_eval.fixtures import Scenario, load_scenario, seed_store
from tradecopilot_eval.source import FrozenSource

_CASE = Path(__file__).resolve().parents[1] / "scenarios" / "dev_01_position_cap"


@pytest.fixture
def scenario() -> Scenario:
    """Load the synthetic agent inputs without evaluator reference answers."""
    return load_scenario(_CASE / "inputs.json")


@pytest.fixture
def reference() -> dict[str, Any]:
    """Load manually authored answers for the test assertions only."""
    data: dict[str, Any] = json.loads(
        (_CASE / "reference.json").read_text(encoding="utf-8")
    )
    return data


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _payload(scenario: Scenario, method: str) -> dict[str, Any]:
    fixture = next(item for item in scenario.tool_fixtures if item.method == method)
    payload: dict[str, Any] = fixture.output.evidence[0].payload
    return payload


def _candidate(reference: dict[str, Any], quantity: int) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = reference["candidates"]
    return next(
        item
        for item in candidates
        if item["tool_arguments"]["legs"][0]["qty"] == quantity
    )


def test_reference_arithmetic(scenario: Scenario, reference: dict[str, Any]) -> None:
    """Recompute labels with Decimal, independently of the agent validator."""
    account = _payload(scenario, "portfolio")
    price = _decimal(_payload(scenario, "quote")["price"])
    equity = _decimal(account["equity"])
    positions: list[dict[str, Any]] = account["positions"]
    held = next(item for item in positions if item["ticker"] == "SYNAA")
    cap = _decimal(scenario.profile.position_cap_pct)
    holdings_value = sum(
        (_decimal(item["market_value"]) for item in positions), Decimal(0)
    )
    assert holdings_value + _decimal(account["cash"]) == equity
    assert _decimal(held["qty"]) * price == _decimal(held["market_value"])
    assert all(
        _decimal(item["market_value"]) / equity * 100 <= cap for item in positions
    )

    maximum = equity * cap / 100
    capacity = maximum - _decimal(held["market_value"])
    calculation = reference["calculation"]
    assert maximum == _decimal(calculation["max_position_value_usd"])
    assert capacity == _decimal(calculation["remaining_capacity_usd"])
    assert capacity / price == _decimal(calculation["max_additional_shares"])

    for candidate in reference["candidates"]:
        quantity = _decimal(candidate["tool_arguments"]["legs"][0]["qty"])
        expected = candidate["expected"]
        resulting_value = (_decimal(held["qty"]) + quantity) * price
        weight = resulting_value / equity * 100
        eligible = weight <= cap
        assert quantity * price <= _decimal(account["buying_power"])
        assert resulting_value == _decimal(expected["resulting_position_value_usd"])
        assert weight == _decimal(expected["resulting_weight_pct"])
        assert expected["eligible"] is eligible
        assert expected["violation_codes"] == ([] if eligible else ["position_cap"])


@pytest.mark.parametrize("quantity", [20, 10, 11, 9])
def test_candidate_proposal_and_constraint_result(
    scenario: Scenario,
    reference: dict[str, Any],
    quantity: int,
    tmp_path: Path,
) -> None:
    """Compare real checks and proposal persistence with the independent labels."""
    from tradecopilot_agent.tools import TradingTools

    candidate = _candidate(reference, quantity)
    arguments = candidate["tool_arguments"]
    expected = candidate["expected"]
    source = FrozenSource(scenario.tool_fixtures, scenario.decision_time)
    store = seed_store(scenario, tmp_path / "run")
    profile = store.get_profile()
    account = asyncio.run(source.portfolio()).evidence[0].payload
    quote = asyncio.run(source.quote("SYNAA")).evidence[0].payload
    violations = check_ticket(
        arguments["legs"],
        profile,
        account,
        {"SYNAA": float(quote["price"])},
        {},
        scenario.decision_time,
        live=False,
    )
    assert [item["code"] for item in violations] == expected["violation_codes"]

    before, before_count = store.list_journal(page_no=1, page_size=100)
    tools = TradingTools(source, store, scenario.as_of, extract_claims=lambda _: [])
    output = asyncio.run(
        tools.propose(
            arguments["legs"], arguments["thesis"], arguments["horizon"], evidence={}
        )
    )
    after, after_count = store.list_journal(page_no=1, page_size=100)
    if expected["eligible"]:
        assert output.error is None
        assert output.proposal is not None
        assert output.proposal["legs"] == arguments["legs"]
        assert output.portfolio_impact is not None
        impact = output.portfolio_impact
        assert impact["before_pct"]["SYNAA"] == pytest.approx(4.0)
        assert impact["after_pct"]["SYNAA"] == pytest.approx(
            expected["resulting_weight_pct"]
        )
        assert impact["net_notional"] == pytest.approx(quantity * quote["price"])
        assert after_count == before_count + 1
        saved = next(item for item in after if item["id"] == output.proposal["id"])
        assert saved["status"] == "proposed"
        assert all(leg["fill_price"] is None for leg in saved["legs"])
        assert output.ticket_done is False
    else:
        assert output.error == "blocked"
        assert "position_cap" in output.summary
        assert output.proposal is None
        assert output.portfolio_impact is None
        assert after_count == before_count
        assert after == before


def test_execution_guard_does_not_call_source(
    scenario: Scenario, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An eligible proposal cannot reach order placement in the fixture source."""
    from tradecopilot_agent.tools import TradingTools

    source = FrozenSource(scenario.tool_fixtures, scenario.decision_time)
    store = seed_store(scenario, tmp_path / "run")
    tools = TradingTools(source, store, scenario.as_of, extract_claims=lambda _: [])
    proposal = asyncio.run(
        tools.propose(
            [{"ticker": "SYNAA", "side": "buy", "qty": 10}],
            "Synthetic candidate for local constraint checks.",
            "weeks",
            evidence={},
        )
    )
    assert proposal.proposal is not None

    async def forbidden_order(leg: dict[str, Any], client_order_id: str) -> ToolOutput:
        raise AssertionError("The execution guard must prevent order placement.")

    monkeypatch.setattr(source, "place_leg", forbidden_order)
    before = store.list_journal(page_no=1, page_size=100)
    output = asyncio.run(
        tools.execute(proposal.proposal["id"], {"pending_ticket": proposal.proposal})
    )
    assert output.error == "unavailable"
    assert output.ticket_done is False
    assert store.list_journal(page_no=1, page_size=100) == before


def test_seed_isolation_and_explicit_journal_window(
    scenario: Scenario, tmp_path: Path
) -> None:
    """Keep run state separate and query history against the scenario's date."""
    first = seed_store(scenario, tmp_path / "first")
    second = seed_store(scenario, tmp_path / "second")
    first.patch_profile({"position_cap_pct": 1.0})
    assert second.get_profile()["position_cap_pct"] == 5.0
    assert second.get_profile()["execution"] == scenario.profile.execution.model_dump()
    since = (scenario.decision_time - timedelta(days=90)).date().isoformat()
    assert since == "2026-06-17"
    expected_ids = {event["decision_id"] for event in scenario.journal_before_decision}
    rows = second.recent_journal(["SYNAA"], since=since, limit=10)
    assert {row["id"] for row in rows} == expected_ids

    old_event = {
        **scenario.journal_before_decision[0],
        "decision_id": "outside-window",
        "created_at": (scenario.decision_time - timedelta(days=91)).isoformat(),
    }
    second.append_journal(old_event)
    assert {
        row["id"] for row in second.recent_journal(["SYNAA"], since=since, limit=10)
    } == expected_ids
    assert first.list_journal(page_no=1, page_size=100)[1] == len(expected_ids)
    with pytest.raises(FileExistsError):
        seed_store(scenario, tmp_path / "second")


def test_memory_views_use_current_profile(scenario: Scenario, tmp_path: Path) -> None:
    """Check renderer inputs only; this does not test model use or the live clock."""
    store = seed_store(scenario, tmp_path / "run")
    profile = store.get_profile()
    since = (scenario.decision_time - timedelta(days=90)).date().isoformat()
    entries = store.recent_journal(["SYNAA"], since=since, limit=10)
    assert render_memory("none", profile, entries) == ""
    prose = render_memory("prose", profile, entries)
    structured = render_memory("structured", profile, entries)
    full = render_memory("full", profile, entries)
    assert "5.0 percent" in prose
    assert "position_cap_pct: 5.0" in structured
    assert "position_cap_pct: 5.0" in full
    assert "10% cap is superseded" in full
    assert "Recent decisions:" not in prose
    assert "Recent decisions:" not in structured
    assert "Recent decisions:" in full
    assert store.get_profile() == profile


def test_inputs_load_without_reference_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Load and replay agent inputs with no reference file available to the reader."""
    inputs = tmp_path / "inputs.json"
    inputs.write_bytes((_CASE / "inputs.json").read_bytes())
    read_text = Path.read_text
    reads: list[Path] = []

    def inputs_only(
        path: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        assert path == inputs, "Agent input loading must not read reference answers."
        reads.append(path)
        return read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", inputs_only)
    loaded = load_scenario(inputs)
    source = FrozenSource(loaded.tool_fixtures, loaded.decision_time)
    outputs = [asyncio.run(source.quote("SYNAA")), asyncio.run(source.portfolio())]
    assert all(output.error is None for output in outputs)
    assert reads == [inputs]
    agent_data = loaded.model_dump_json() + "".join(
        output.model_dump_json() for output in outputs
    )
    for reference_field in (
        "violation_codes",
        "response_criteria",
        "max_additional_shares",
    ):
        assert reference_field not in agent_data
