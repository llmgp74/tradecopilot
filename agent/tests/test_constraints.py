"""The deterministic order ticket check."""

from datetime import UTC, datetime

from tradecopilot_agent.constraints import check_ticket

NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)


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
