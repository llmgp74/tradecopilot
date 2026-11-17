"""Outcome computation from locally recorded prices."""

from datetime import date
from typing import Any

import pytest
from tradecopilot_agent.outcomes import compute_outcome

TODAY = date(2026, 11, 17)


def _decision(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "d1",
        "created_at": "2026-10-01T10:00:00+00:00",
        "horizon": "weeks",
        "status": "filled",
        "legs": [
            {
                "ticker": "NVDA",
                "side": "buy",
                "qty": 10.0,
                "notional": 1000.0,
                "entry_price": 100.0,
                "fill_price": 100.0,
                "fill_at": "2026-10-01T15:00:00+00:00",
                "status": "filled",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_a_filled_buy_reports_return_and_alpha() -> None:
    """A filled buy earns the price move and the spread over SPY."""
    observations = {
        "NVDA": [("2026-10-01", 100.0), ("2026-10-28", 110.0)],
        "SPY": [("2026-10-01", 500.0), ("2026-10-28", 505.0)],
    }

    outcome = compute_outcome(_decision(), observations, TODAY)

    assert outcome is not None
    assert outcome["return_pct"] == 10.0
    assert round(outcome["alpha_pct"], 2) == 9.0
    assert outcome["counterfactual"] is False
    assert outcome["partial"] is False
    assert outcome["observed_at"] == "2026-10-28"


def test_a_rejected_decision_is_a_counterfactual() -> None:
    """A decision without a fill is measured as if it had been taken."""
    legs = [
        {
            **_decision()["legs"][0],
            "fill_price": None,
            "fill_at": None,
            "status": "rejected",
        }
    ]

    outcome = compute_outcome(
        _decision(status="rejected", legs=legs),
        {"NVDA": [("2026-10-01", 100.0), ("2026-10-28", 110.0)]},
        TODAY,
    )

    assert outcome is not None
    assert outcome["counterfactual"] is True
    assert outcome["alpha_pct"] is None
    assert outcome["entry_at"] == "2026-10-01T10:00:00+00:00"


def test_a_sell_gains_when_the_price_falls() -> None:
    """A sell return is the inverse of the price move."""
    legs = [{**_decision()["legs"][0], "side": "sell"}]

    outcome = compute_outcome(
        _decision(legs=legs),
        {"NVDA": [("2026-10-01", 100.0), ("2026-10-28", 90.0)]},
        TODAY,
    )

    assert outcome is not None
    assert outcome["return_pct"] == 10.0


def test_a_price_more_than_five_days_from_the_end_is_not_used() -> None:
    """A price far from the horizon end cannot stand in for it."""
    observations = {"NVDA": [("2026-10-01", 100.0), ("2026-10-20", 120.0)]}

    assert compute_outcome(_decision(), observations, TODAY) is None


def test_a_price_before_entry_is_not_used() -> None:
    """An observation before the entry date is outside the exit window."""
    observations = {"NVDA": [("2026-09-28", 90.0), ("2026-10-28", 110.0)]}

    outcome = compute_outcome(_decision(), observations, TODAY)

    assert outcome is not None
    assert outcome["observed_at"] == "2026-10-28"


def test_a_future_horizon_is_pending() -> None:
    """A decision whose horizon has not ended has no outcome."""
    observations = {"NVDA": [("2026-11-01", 100.0), ("2026-11-17", 105.0)]}
    future = _decision(created_at="2026-11-10T10:00:00+00:00")

    assert compute_outcome(future, observations, TODAY) is None


def test_a_multi_leg_outcome_is_notional_weighted() -> None:
    """Aggregate return uses absolute notional, not a simple average."""
    legs = [
        {**_decision()["legs"][0], "notional": 1000.0},
        {
            **_decision()["legs"][0],
            "ticker": "AAPL",
            "notional": 3000.0,
            "entry_price": 200.0,
            "fill_price": 200.0,
        },
    ]
    observations = {
        "NVDA": [("2026-10-01", 100.0), ("2026-10-28", 110.0)],
        "AAPL": [("2026-10-01", 200.0), ("2026-10-28", 190.0)],
    }

    outcome = compute_outcome(_decision(legs=legs), observations, TODAY)

    assert outcome is not None
    assert outcome["return_pct"] == pytest.approx(-1.25)


def test_a_partial_multi_leg_outcome_is_flagged() -> None:
    """A leg without an exit price is omitted and the outcome is partial."""
    legs = [
        _decision()["legs"][0],
        {**_decision()["legs"][0], "ticker": "AAPL", "notional": 500.0},
    ]

    outcome = compute_outcome(
        _decision(legs=legs),
        {"NVDA": [("2026-10-01", 100.0), ("2026-10-28", 110.0)]},
        TODAY,
    )

    assert outcome is not None
    assert outcome["partial"] is True
    assert [leg["ticker"] for leg in outcome["legs"]] == ["NVDA"]


def test_malformed_dates_are_skipped_without_raising() -> None:
    """An unusable decision produces no outcome instead of an exception."""
    assert (
        compute_outcome({"id": "x", "created_at": "not-a-date", "legs": []}, {}, TODAY)
        is None
    )
