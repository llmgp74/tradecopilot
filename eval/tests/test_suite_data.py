"""Check the fixed pilot data and independent labels without running a model."""

import asyncio
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tradecopilot_agent.claims import match_claims
from tradecopilot_agent.constraints import check_ticket
from tradecopilot_eval.reference import Case, load_case, load_suite
from tradecopilot_eval.source import FrozenSource

_EVAL = Path(__file__).resolve().parents[1]
_SUITE = _EVAL / "suites" / "pilot.json"
_DIRECTORIES = sorted((_EVAL / "scenarios" / "evaluation").glob("*/inputs.json")) + [
    _EVAL / "scenarios" / "dev_02_false_growth" / "inputs.json"
]


def _number(value: Any) -> Decimal:
    return Decimal(str(value))


def _account(case: Case) -> dict[str, Any]:
    fixture = next(
        item for item in case.scenario.tool_fixtures if item.method == "portfolio"
    )
    payload: dict[str, Any] = fixture.output.evidence[0].payload
    return payload


def _facts(case: Case) -> dict[tuple[str, str], Decimal]:
    return {
        (record.payload["tag"], record.payload["period"]): _number(
            record.payload["value"]
        )
        for record in case.reference.reference_evidence
        if record.payload.get("kind") == "xbrl"
    }


def test_plan_matches_proposal_categories_and_presets() -> None:
    """Keep ten candidate cases and a preselected repeated memory comparison."""
    suite, cases = load_suite(_SUITE)
    assert len(cases) == 10
    assert Counter(case.reference.category for case in cases) == {
        "earnings": 2,
        "news": 2,
        "portfolio": 2,
        "false_claim": 2,
        "constraint": 1,
        "tool_failure": 1,
    }
    assert suite.ablation_scenarios == ["PORT-01", "NEWS-01", "PORT-02"]
    assert suite.repetitions == 3
    assert suite.conditions == ["none", "prose", "structured", "full"]
    assert len(cases) + len(suite.ablation_scenarios) * 4 * suite.repetitions == 46
    assert suite.provenance_status == "synthetic_pending_review"
    assert all(case.scenario.split == "evaluation" for case in cases)
    assert all(case.scenario.synthetic for case in cases)
    assert all(
        case.reference.provenance_status == "synthetic_pending_review" for case in cases
    )


@pytest.mark.parametrize("input_path", _DIRECTORIES, ids=lambda path: path.parent.name)
def test_case_records_balance_and_replay_before_cutoff(input_path: Path) -> None:
    """Validate fixed assets, record dates, and every recorded data-source call.

    Args:
        input_path: One pilot case's input file.
    """
    case = load_case(input_path.parent)
    scenario = case.scenario
    account = _account(case)
    equity = _number(account["equity"])
    held = sum(
        (_number(position["market_value"]) for position in account["positions"]),
        Decimal(0),
    )
    assert _number(account["cash"]) + held == equity
    assert _number(account["buying_power"]) == _number(account["cash"])
    assert all(
        _number(position["market_value"]) / equity * 100
        <= _number(scenario.profile.position_cap_pct)
        for position in account["positions"]
    )
    source = FrozenSource(scenario.tool_fixtures, scenario.decision_time)
    for fixture in scenario.tool_fixtures:
        output = asyncio.run(getattr(source, fixture.method)(**fixture.arguments))
        assert output.model_dump() == fixture.output.model_dump()
        assert "expected" not in output.model_dump_json()
    for record in case.reference.reference_evidence:
        assert record.source.startswith("synthetic_")
        assert record.url is None
        assert record.published_at is not None
        assert datetime.fromisoformat(record.published_at) <= scenario.decision_time
    assert "order_execution" not in source.capabilities()


@pytest.mark.parametrize("input_path", _DIRECTORIES, ids=lambda path: path.parent.name)
def test_candidate_labels_match_arithmetic_and_agent_rules(input_path: Path) -> None:
    """Compare fixed expected labels with arithmetic and the shared rule checker.

    Args:
        input_path: One pilot case's input file.
    """
    case = load_case(input_path.parent)
    account = _account(case)
    records = case.reference.reference_evidence
    prices = {
        record.payload["ticker"]: float(record.payload["price"])
        for record in records
        if record.payload.get("kind") == "quote"
    }
    sectors = {
        record.payload["ticker"]: record.payload["sector"]
        for record in records
        if record.payload.get("kind") == "fundamentals"
    }
    profile = case.scenario.profile.model_dump()
    for candidate in case.reference.candidates:
        legs = candidate.tool_arguments["legs"]
        leg = legs[0]
        assert len(legs) == 1 and leg["side"] == "buy"
        held = next(
            (
                _number(position["qty"])
                for position in account["positions"]
                if position["ticker"] == leg["ticker"]
            ),
            Decimal(0),
        )
        value = (held + _number(leg["qty"])) * _number(prices[leg["ticker"]])
        weight = value / _number(account["equity"]) * 100
        expected = candidate.expected
        assert value == _number(expected.resulting_position_value_usd)
        assert weight == _number(expected.resulting_weight_pct)
        codes = []
        if weight > _number(profile["position_cap_pct"]):
            codes.append("position_cap")
        if sectors[leg["ticker"]] in profile["sector_exclusions"]:
            codes.append("sector_exclusion")
        assert sorted(codes) == sorted(expected.violation_codes)
        assert expected.eligible == (not codes)
        actual = check_ticket(
            legs,
            profile,
            account,
            prices,
            sectors,
            case.scenario.decision_time,
            live=False,
        )
        assert sorted(item["code"] for item in actual) == sorted(codes)


@pytest.mark.parametrize("input_path", _DIRECTORIES, ids=lambda path: path.parent.name)
def test_claim_labels_match_reference_values(input_path: Path) -> None:
    """Check planted facts and true controls before testing the agent matcher.

    Args:
        input_path: One pilot case's input file.
    """
    case = load_case(input_path.parent)
    evidence = {
        record.id: record.model_dump() for record in case.reference.reference_evidence
    }
    for probe in case.reference.claim_probes:
        records = [evidence[record_id] for record_id in probe.evidence_ids]
        values = [_number(record["payload"]["value"]) for record in records]
        if probe.expected_verdict == "supported":
            assert all(value == _number(probe.claim.value) for value in values)
        elif probe.expected_verdict == "contradicted":
            assert all(value != _number(probe.claim.value) for value in values)
        verdicts = match_claims([probe.claim], evidence, scope="answer")
        assert verdicts[0]["verdict"] == probe.expected_verdict
    if case.reference.category == "false_claim":
        assert {probe.expected_verdict for probe in case.reference.claim_probes} >= {
            "supported",
            "contradicted",
        }


def test_independent_derived_calculations() -> None:
    """Recompute growth, margins, and remaining capacity from frozen facts."""
    _, cases = load_suite(_SUITE)
    dev = load_case(_EVAL / "scenarios" / "dev_02_false_growth")
    for case in [*cases, dev]:
        facts = _facts(case)
        calculation = case.reference.calculation
        if "revenue_growth_pct" in calculation:
            previous = facts["Revenues", "FY2024"]
            current = facts["Revenues", "FY2025"]
            assert (current / previous - 1) * 100 == _number(
                calculation["revenue_growth_pct"]
            )
        if "net_income_change_pct" in calculation:
            previous = facts["NetIncomeLoss", "FY2024"]
            current = facts["NetIncomeLoss", "FY2025"]
            assert (current / previous - 1) * 100 == _number(
                calculation["net_income_change_pct"]
            )
        for key, period in (
            ("prior_net_margin_pct", "FY2024"),
            ("current_net_margin_pct", "FY2025"),
        ):
            if key in calculation:
                assert facts["NetIncomeLoss", period] / facts[
                    "Revenues", period
                ] * 100 == (_number(calculation[key]))
        if "current_operating_margin_pct" in calculation:
            margin = (
                facts["OperatingIncomeLoss", "FY2025"] / facts["Revenues", "FY2025"]
            )
            assert margin * 100 == _number(calculation["current_operating_margin_pct"])
        if "remaining_capacity_usd" in calculation:
            account = _account(case)
            maximum = (
                _number(account["equity"])
                * _number(case.scenario.profile.position_cap_pct)
                / 100
            )
            held_value = _number(account["positions"][0]["market_value"])
            assert maximum == _number(calculation["max_position_value_usd"])
            assert maximum - held_value == _number(
                calculation["remaining_capacity_usd"]
            )


def test_quote_outage_has_no_hidden_price_reference() -> None:
    """Keep missing price evidence unavailable to both the agent and the scorer."""
    case = load_case(_EVAL / "scenarios" / "evaluation" / "adv_04")
    source = FrozenSource(case.scenario.tool_fixtures, case.scenario.decision_time)
    output = asyncio.run(source.quote("SYNCJ"))
    assert output.error == "planned_outage"
    assert output.evidence == []
    assert all(
        record.payload.get("kind") != "quote"
        for record in case.reference.reference_evidence
    )
    assert case.reference.candidates == []
    assert "recommendation" not in case.reference.acceptable_outcomes
