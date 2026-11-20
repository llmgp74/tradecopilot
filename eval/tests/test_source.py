"""Frozen data source satisfies the execution signature."""

import asyncio
from datetime import UTC, datetime

from tradecopilot_eval.source import FrozenSource


def test_place_leg_accepts_a_position_intent() -> None:
    """The execution path passes an intent even though fixtures disable orders."""
    source = FrozenSource([], datetime(2026, 11, 5, tzinfo=UTC))
    leg = {"ticker": "NVDA", "side": "sell", "qty": 1}

    output = asyncio.run(source.place_leg(leg, "order-1", "sell_to_open"))

    assert output.error == "execution_disabled"
