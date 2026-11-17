"""The deterministic order ticket check."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from tradecopilot_agent.constraints import check_ticket, session_open

NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)
_NEW_YORK = ZoneInfo("America/New_York")


def _profile(**overrides: object) -> dict:
    profile: dict = {
        "position_cap_pct": 10.0,
        "sector_exclusions": [],
        "execution": {"autonomous": False, "max_order_notional": 1000.0},
    }
    profile.update(overrides)
    return profile


def _account(**overrides: object) -> dict:
    account: dict = {
        "equity": 100_000.0,
        "cash": 100_000.0,
        "buying_power": 100_000.0,
        "positions": [],
    }
    account.update(overrides)
    return account


def _codes(violations: list[dict]) -> set[str]:
    return {violation["code"] for violation in violations}


@pytest.mark.parametrize(
    ("day", "hour", "minute", "expected_open"),
    [
        (5, 3, 59, False),
        (5, 4, 0, True),
        (5, 9, 30, True),
        (5, 16, 0, True),
        (5, 19, 59, True),
        (5, 20, 0, False),
        (7, 12, 0, False),
    ],
)
def test_market_hours_cover_the_extended_session(
    day: int, hour: int, minute: int, expected_open: bool
) -> None:
    """Pre-market and after-hours are open; the weekend stays closed."""
    now = datetime(2026, 11, day, hour, minute, tzinfo=_NEW_YORK)

    violations = check_ticket(
        [{"ticker": "AAPL", "side": "buy", "qty": 1}],
        _profile(),
        _account(),
        prices={"AAPL": 100.0},
        sectors={"AAPL": "Technology"},
        now=now,
        live=True,
    )

    assert ("market_closed" in _codes(violations)) is not expected_open


@pytest.mark.parametrize(
    ("day", "hour", "minute", "is_open", "next_open", "expected"),
    [
        (17, 8, 0, False, "2026-11-17T09:30:00-05:00", True),
        (17, 8, 0, False, "2026-11-18T09:30:00-05:00", False),
        (17, 3, 0, False, "2026-11-17T09:30:00-05:00", False),
        (17, 10, 0, True, None, True),
        (17, 17, 0, False, "2026-11-18T09:30:00-05:00", True),
        (17, 20, 30, False, "2026-11-18T09:30:00-05:00", False),
        (21, 10, 0, False, "2026-11-23T09:30:00-05:00", False),
        (17, 8, 0, False, None, False),
        (17, 8, 0, False, "not-a-time", False),
    ],
)
def test_session_open_combines_clock_and_extended_window(
    day: int,
    hour: int,
    minute: int,
    is_open: bool,
    next_open: str | None,
    expected: bool,
) -> None:
    """The regular clock leaves pre-market and after-hours open."""
    now = datetime(2026, 11, day, hour, minute, tzinfo=_NEW_YORK)

    assert session_open(now, is_open, next_open) is expected


def test_the_broker_clock_overrides_the_local_window() -> None:
    """A closed local window still passes when the broker says it is open."""
    now = datetime(2026, 11, 5, 3, 0, tzinfo=_NEW_YORK)

    violations = check_ticket(
        [{"ticker": "AAPL", "side": "buy", "qty": 1}],
        _profile(),
        _account(),
        prices={"AAPL": 100.0},
        sectors={"AAPL": "Technology"},
        now=now,
        live=True,
        market_open=True,
    )

    assert "market_closed" not in _codes(violations)


def test_a_closed_market_reports_the_next_open() -> None:
    """The broker's next_open is quoted in the violation message."""
    next_open = "2026-11-17T09:30:00-05:00"

    violations = check_ticket(
        [{"ticker": "AAPL", "side": "buy", "qty": 1}],
        _profile(),
        _account(),
        prices={"AAPL": 100.0},
        sectors={"AAPL": "Technology"},
        now=datetime(2026, 11, 7, 12, 0, tzinfo=_NEW_YORK),
        live=True,
        market_open=False,
        next_open=next_open,
    )

    closed = [v for v in violations if v["code"] == "market_closed"]
    assert closed[0]["message"] == f"The market is closed. It opens at {next_open}."


def test_a_buy_funded_by_a_sell_passes() -> None:
    """Sell proceeds count before the buy is checked."""
    legs = [
        {"ticker": "NVDA", "side": "sell", "qty": 100},
        {"ticker": "AAPL", "side": "buy", "qty": 5},
    ]
    account = _account(
        cash=0.0,
        buying_power=0.0,
        positions=[{"ticker": "NVDA", "qty": 100, "market_value": 100_000.0}],
    )

    violations = check_ticket(
        legs,
        _profile(),
        account,
        prices={"NVDA": 1000.0, "AAPL": 1000.0},
        sectors={"NVDA": "Technology", "AAPL": "Technology"},
        now=NOW,
    )

    assert violations == []


def test_the_same_buy_alone_fails_buying_power() -> None:
    """Without the sell there is no cash for the buy."""
    violations = check_ticket(
        [{"ticker": "AAPL", "side": "buy", "qty": 50}],
        _profile(),
        _account(cash=0.0, buying_power=0.0),
        prices={"AAPL": 1000.0},
        sectors={"AAPL": "Technology"},
        now=NOW,
    )

    assert "insufficient_buying_power" in _codes(violations)


def test_position_cap_applies_to_the_resulting_position() -> None:
    """A buy that pushes a position above the cap is rejected."""
    violations = check_ticket(
        [{"ticker": "AAPL", "side": "buy", "qty": 20}],
        _profile(position_cap_pct=10.0),
        _account(),
        prices={"AAPL": 1000.0},
        sectors={"AAPL": "Technology"},
        now=NOW,
    )

    assert "position_cap" in _codes(violations)


def test_a_sell_is_never_blocked_by_the_cap() -> None:
    """Reducing exposure cannot break the cap."""
    account = _account(
        positions=[{"ticker": "NVDA", "qty": 100, "market_value": 100_000.0}],
        cash=0.0,
    )

    violations = check_ticket(
        [{"ticker": "NVDA", "side": "sell", "qty": 10}],
        _profile(position_cap_pct=10.0),
        account,
        prices={"NVDA": 1000.0},
        sectors={"NVDA": "Technology"},
        now=NOW,
    )

    assert violations == []


def test_sector_exclusion_blocks_a_buy_and_allows_a_sell() -> None:
    """Exclusions apply to risk-increasing legs only."""
    profile = _profile(sector_exclusions=["Technology"])
    buy = check_ticket(
        [{"ticker": "NVDA", "side": "buy", "qty": 1}],
        profile,
        _account(),
        prices={"NVDA": 100.0},
        sectors={"NVDA": "Technology"},
        now=NOW,
    )
    account = _account(
        positions=[{"ticker": "NVDA", "qty": 10, "market_value": 1000.0}]
    )
    sell = check_ticket(
        [{"ticker": "NVDA", "side": "sell", "qty": 1}],
        profile,
        account,
        prices={"NVDA": 100.0},
        sectors={"NVDA": "Technology"},
        now=NOW,
    )

    assert "sector_exclusion" in _codes(buy)
    assert sell == []


def test_unknown_sector_fails_closed_for_a_buy() -> None:
    """With exclusions configured, an unknown sector cannot be cleared."""
    violations = check_ticket(
        [{"ticker": "ZZZZ", "side": "buy", "qty": 1}],
        _profile(sector_exclusions=["Technology"]),
        _account(),
        prices={"ZZZZ": 10.0},
        sectors={"ZZZZ": None},
        now=NOW,
    )

    assert "sector_exclusion" in _codes(violations)


def test_no_exclusions_means_no_sector_lookup() -> None:
    """An empty exclusion list never needs fundamentals."""
    violations = check_ticket(
        [{"ticker": "ZZZZ", "side": "buy", "qty": 1}],
        _profile(sector_exclusions=[]),
        _account(),
        prices={"ZZZZ": 10.0},
        sectors={},
        now=NOW,
    )

    assert violations == []


def test_oversell_is_rejected() -> None:
    """Selling more than is held is out of scope."""
    account = _account(
        positions=[{"ticker": "NVDA", "qty": 10, "market_value": 1000.0}]
    )

    violations = check_ticket(
        [{"ticker": "NVDA", "side": "sell", "qty": 11}],
        _profile(),
        account,
        prices={"NVDA": 100.0},
        sectors={"NVDA": "Technology"},
        now=NOW,
    )

    assert "oversell" in _codes(violations)


def test_autonomous_notional_cap() -> None:
    """Autonomous mode enforces the maximum order notional."""
    violations = check_ticket(
        [{"ticker": "AAPL", "side": "buy", "qty": 5}],
        _profile(execution={"autonomous": True, "max_order_notional": 1000.0}),
        _account(),
        prices={"AAPL": 1000.0},
        sectors={"AAPL": "Technology"},
        now=NOW,
    )

    assert "notional_cap" in _codes(violations)


def test_fractional_quantity_requires_permission() -> None:
    """Fractional shares are rejected when the account does not allow them."""
    violations = check_ticket(
        [{"ticker": "AAPL", "side": "buy", "qty": 0.5}],
        _profile(),
        _account(),
        prices={"AAPL": 100.0},
        sectors={"AAPL": "Technology"},
        now=NOW,
    )

    assert "fractional_qty" in _codes(violations)
