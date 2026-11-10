"""Portfolio history request parameters."""

import pytest
from tradecopilot_agent.portfolio import history_params


@pytest.mark.parametrize(
    ("range_", "period", "timeframe"),
    [
        ("1D", "1D", "5Min"),
        ("1W", "1W", "15Min"),
        ("1M", "1M", "1D"),
        ("3M", "3M", "1D"),
        ("1Y", "1A", "1D"),
        ("ALL", "all", "1D"),
    ],
)
def test_history_params_use_supported_values(
    range_: str, period: str, timeframe: str
) -> None:
    """Every range maps to a period and timeframe Alpaca accepts."""
    assert history_params(range_) == {"period": period, "timeframe": timeframe}


def test_history_params_fall_back_to_one_month() -> None:
    """An unknown range uses the one-month window."""
    assert history_params("unknown") == {"period": "1M", "timeframe": "1D"}
