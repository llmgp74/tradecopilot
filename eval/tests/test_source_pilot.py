"""Check source-pilot data internally without access to private source archives."""

import hashlib
import json
import math
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tradecopilot_agent.state import EvidenceRecord

_APPLE = (
    Path(__file__).resolve().parents[1] / "scenarios" / "source_pilot" / "apple_2024_q4"
)
_NEWS = _APPLE.parent / "google_wiz_2025_03"


def _document(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((_APPLE / name).read_text(encoding="utf-8"))
    return document


def _records() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for fixture in _document("inputs.json")["tool_fixtures"]:
        for record in fixture["output"]["evidence"]:
            assert record["id"] not in records
            records[record["id"]] = record
    return records


def test_apple_case_has_no_fabricated_quote_or_trading_label() -> None:
    """Keep real company facts separate from assumed portfolio context."""
    inputs = _document("inputs.json")
    reference = _document("reference.json")
    provenance = _document("provenance.json")
    assert inputs["scenario_id"] == reference["scenario_id"] == "REAL-EARN-01"
    assert provenance["scenario_id"] == inputs["scenario_id"]
    assert inputs["split"] == reference["split"] == "development"
    assert inputs["synthetic"] is False
    assert reference["provenance_status"] == "primary_source_pending_review"
    assert provenance["status"] == reference["provenance_status"]
    assert inputs["journal_before_decision"] == []
    assert inputs["profile"]["position_cap_pct"] == 5
    assert inputs["profile"]["watchlist"] == ["AAPL"]
    assert inputs["profile"]["execution"]["autonomous"] is False
    fixtures = {item["method"]: item for item in inputs["tool_fixtures"]}
    assert set(fixtures) == {"quote", "portfolio", "positions", "filings"}
    assert fixtures["quote"]["output"]["error"] == "not_collected"
    assert fixtures["quote"]["output"]["evidence"] == []
    account = fixtures["portfolio"]["output"]["evidence"][0]
    positions = fixtures["positions"]["output"]["evidence"][0]
    assert account["payload"] == positions["payload"]
    assert account["payload"]["scenario_assumption"] is True
    assert account["payload"]["positions"] == []
    assert account["payload"]["equity"] == account["payload"]["cash"] == 100000
    assert account["payload"]["buying_power"] == account["payload"]["cash"]
    assert reference["candidates"] == reference["claim_probes"] == []
    assert set(reference["acceptable_outcomes"]) == {"no_trade", "needs_information"}
    for record in _records().values():
        assert record["payload"]["kind"] not in {"quote", "xbrl"}
    assert "growth_pct" not in fixtures["filings"]["output"]["summary"]
    assert "response_criteria" not in fixtures["filings"]["output"]["summary"]


def test_apple_provenance_covers_records_and_keeps_retrieval_time() -> None:
    """Check manifest bindings and hashes, without claiming raw-source verification."""
    inputs = _document("inputs.json")
    reference = _document("reference.json")
    provenance = _document("provenance.json")
    records = _records()
    assert {item["id"]: item for item in reference["reference_evidence"]} == records
    bindings = {item["evidence_id"]: item for item in provenance["evidence"]}
    assert set(bindings) == set(records)
    sources = {item["id"]: item for item in provenance["sources"]}
    assert len(sources) == 2
    cutoff = datetime.fromisoformat(inputs["decision_time"])
    for source in sources.values():
        assert source["published_date"] == "2024-10-31"
        assert source["available_at"] == "2024-11-01T07:00:00Z"
        assert datetime.fromisoformat(source["available_at"]) < cutoff
        assert datetime.fromisoformat(source["retrieved_at"]) > cutoff
        assert "proxy" in source["availability_basis"]
        assert urlparse(source["url"]).hostname == "www.apple.com"
        assert Path(source["snapshot_path"]).name == source["snapshot_path"]
        assert len(bytes.fromhex(source["sha256"])) == 32
    for identifier, record in records.items():
        binding = bindings[identifier]
        canonical = EvidenceRecord.model_validate(record).model_dump()
        digest = hashlib.sha256(
            json.dumps(
                canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode()
        ).hexdigest()
        assert binding["evidence_sha256"] == digest
        assert binding["locator"] and binding["note"]
        assert datetime.fromisoformat(record["published_at"]) <= cutoff
        if binding["origin"] == "primary_source":
            source = sources[binding["source_id"]]
            assert record["source"] == source["id"]
            assert record["url"] == source["url"]
            assert record["published_at"] == source["available_at"]
            assert record["fetched_at"] == source["retrieved_at"]
        else:
            assert binding["origin"] == "scenario_assumption"
            assert binding["source_id"] is None
            assert record["source"].startswith("assumed_")
            assert record["url"] is None
    release = records["REAL-EARN-01-RELEASE"]["payload"]
    assert (
        release["financial_statements_url"]
        == sources["apple_fy2024_q4_financials"]["url"]
    )


def test_apple_calculations_use_quarterly_gaap_values_and_separate_adjustment() -> None:
    """Recompute changes and margins, and reconcile the separate non-GAAP table."""
    records = _records()
    quarterly = records["REAL-EARN-01-QUARTERLY-GAAP"]["payload"]
    adjustment = records["REAL-EARN-01-TAX-RECONCILIATION"]["payload"]
    assert quarterly["source_page"] == 1
    assert adjustment["source_page"] == 4
    for payload in (quarterly, adjustment):
        assert payload["extraction_method"] == "manual_table_transcription"
        assert payload["duration"] == "three_months"
        assert payload["unit"] == "USD_millions"
    assert quarterly["accounting_basis"] == "GAAP"
    current, previous = quarterly["periods"]
    assert current["period_end"] == adjustment["period_end"] == "2024-09-28"
    assert previous["period_end"] == "2023-09-30"
    assert current["net_income"] == adjustment["reported_gaap_net_income"]
    assert (
        current["provision_for_income_taxes"]
        == adjustment["reported_gaap_income_taxes"]
    )
    calculations = _document("reference.json")["calculation"]
    for metric, label in (
        ("total_net_sales", "revenue_growth_pct"),
        ("net_income", "net_income_change_pct"),
        ("operating_income", "operating_income_change_pct"),
    ):
        expected = (Decimal(current[metric]) / Decimal(previous[metric]) - 1) * 100
        assert math.isclose(calculations[label], float(expected), abs_tol=1e-12)
    margins = []
    for period, label in (
        (previous, "prior_net_margin_pct"),
        (current, "current_net_margin_pct"),
    ):
        margin = Decimal(period["net_income"]) / Decimal(period["total_net_sales"])
        margins.append(margin * 100)
        assert math.isclose(calculations[label], float(margin * 100), abs_tol=1e-12)
    assert math.isclose(
        calculations["net_margin_change_percentage_points"],
        float(margins[1] - margins[0]),
        abs_tol=1e-12,
    )
    adjusted_income = (
        adjustment["reported_gaap_net_income"] + adjustment["net_income_adjustment"]
    )
    assert adjusted_income == adjustment["adjusted_non_gaap_net_income"]
    assert (
        adjusted_income == calculations["reconciled_non_gaap_net_income_usd_millions"]
    )
    assert (
        adjustment["reported_gaap_income_taxes"] + adjustment["income_tax_adjustment"]
        == adjustment["adjusted_non_gaap_income_taxes"]
    )
    assert adjustment["income_tax_adjustment"] == -adjustment["net_income_adjustment"]


def test_news_case_keeps_announcement_status_and_assumed_portfolio_separate() -> None:
    """Retain the historical announcement and price gap without a made-up order."""
    inputs = json.loads((_NEWS / "inputs.json").read_text())
    reference = json.loads((_NEWS / "reference.json").read_text())
    provenance = json.loads((_NEWS / "provenance.json").read_text())
    fixtures = {item["method"]: item for item in inputs["tool_fixtures"]}
    records = {
        record["id"]: record
        for fixture in fixtures.values()
        for record in fixture["output"]["evidence"]
    }
    assert {item["id"]: item for item in reference["reference_evidence"]} == records
    announcement = records["REALNEWS01-ANNOUNCEMENT"]
    news = announcement["payload"]
    assert news["consideration_usd"] == 32_000_000_000
    assert news["payment_form"] == "cash"
    assert news["consideration_subject_to_closing_adjustments"] is True
    assert news["transaction_status"] == "agreement_signed_pending_closing"
    assert "regulatory_approvals" in news["closing_conditions"]
    assert news["date"] == "2025-03-18"
    assert news["extraction_method"] == "manual_announcement_summary"
    assert fixtures["quote"]["output"]["error"] == "not_collected"
    assert fixtures["quote"]["output"]["evidence"] == []
    assert reference["candidates"] == reference["claim_probes"] == []
    assert set(reference["acceptable_outcomes"]) == {"no_trade", "needs_information"}
    source = provenance["sources"][0]
    assert announcement["fetched_at"] == source["retrieved_at"]
    assert announcement["published_at"] == source["available_at"]
    assert source["published_date"] == news["date"]
    assert datetime.fromisoformat(source["available_at"]) < datetime.fromisoformat(
        inputs["decision_time"]
    )
    assert datetime.fromisoformat(source["retrieved_at"]) > datetime.fromisoformat(
        inputs["decision_time"]
    )
    assert {item["evidence_id"] for item in provenance["evidence"]} == set(records)
    for binding in provenance["evidence"]:
        record = records[binding["evidence_id"]]
        canonical = EvidenceRecord.model_validate(record).model_dump(mode="json")
        digest = hashlib.sha256(
            json.dumps(
                canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode()
        ).hexdigest()
        assert binding["evidence_sha256"] == digest
        if binding["origin"] == "scenario_assumption":
            assert record["source"].startswith("assumed_")
            assert record["payload"]["data_origin"] == "scenario_assumption"
            assert record["url"] is None
        else:
            assert record["source"] == source["id"]
            assert record["url"] == source["url"]


def test_source_smoke_cases_do_not_replace_the_memory_comparison() -> None:
    """Keep two development cases outside the fixed ten-case comparison suite."""
    suites = _APPLE.parents[2] / "suites"
    source = json.loads((suites / "source-pilot.json").read_text())
    pilot = json.loads((suites / "pilot.json").read_text())
    assert len(source["scenario_paths"]) == 2 and source["ablation_scenarios"] == []
    assert source["repetitions"] == 1 and source["full_condition"] == "full"
    assert len(pilot["scenario_paths"]) == 10
    assert len(pilot["ablation_scenarios"]) == 3 and pilot["repetitions"] == 3
    assert not set(source["scenario_paths"]) & set(pilot["scenario_paths"])
    for relative in source["scenario_paths"]:
        case = json.loads((suites / relative / "inputs.json").read_text())
        assert case["split"] == "development" and case["synthetic"] is False
