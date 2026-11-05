"""Replay frozen tool responses without provider clients or order execution."""

import json
from datetime import datetime
from typing import Any

from tradecopilot_agent.data import DataSource
from tradecopilot_agent.state import ToolOutput

from tradecopilot_eval.fixtures import ToolFixture

_CAPABILITIES = frozenset({"alpaca", "edgar", "fmp", "finnhub", "fred"})


def _key(method: str, arguments: dict[str, Any]) -> tuple[str, str]:
    """Index exact arguments without changing their values or filling defaults."""
    try:
        encoded = json.dumps(
            arguments, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Fixture arguments must contain finite JSON values.") from exc
    return method, encoded


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _failure(error: str, summary: str) -> ToolOutput:
    """Return an error without exposing any rejected fixture content."""
    return ToolOutput(summary=summary, error=error)


class FrozenSource(DataSource):
    """Serve exact fixture matches whose content was available at decision time."""

    def __init__(self, fixtures: list[ToolFixture], decision_time: datetime) -> None:
        """Copy fixtures and set the availability cutoff.

        Args:
            fixtures: Responses keyed by method and exact normalized arguments.
                Include default arguments explicitly in fixture keys.
            decision_time: Timezone-aware scenario timestamp.

        Raises:
            ValueError: If the cutoff is naive, arguments are not finite JSON,
                or two fixtures have the same method and arguments.
        """
        if not _aware(decision_time):
            raise ValueError("decision_time must include a timezone.")
        self._decision_time = decision_time
        self._fixtures: dict[tuple[str, str], ToolFixture] = {}
        for fixture in fixtures:
            key = _key(fixture.method, fixture.arguments)
            if key in self._fixtures:
                raise ValueError(
                    f"Duplicate fixture for {fixture.method} and its arguments."
                )
            self._fixtures[key] = fixture.model_copy(deep=True)

    def capabilities(self) -> set[str]:
        """Return the data capabilities supported by fixture replay.

        Returns:
            A fresh set excluding order execution.
        """
        return set(_CAPABILITIES)

    def _response(self, method: str, arguments: dict[str, Any]) -> ToolOutput:
        fixture = self._fixtures.get(_key(method, arguments))
        if fixture is None:
            return _failure(
                "fixture_missing",
                f"No frozen fixture matches {method} and its arguments.",
            )
        if not _aware(fixture.available_at):
            return _failure("fixture_invalid", "Fixture availability has no timezone.")
        if fixture.available_at > self._decision_time:
            return _failure(
                "fixture_after_cutoff", "Fixture is unavailable at decision time."
            )
        for record in fixture.output.evidence:
            if record.published_at is None:
                return _failure(
                    "fixture_invalid", "Fixture evidence has no publication time."
                )
            try:
                published_at = datetime.fromisoformat(record.published_at)
            except ValueError:
                return _failure(
                    "fixture_invalid", "Fixture publication time is invalid."
                )
            if not _aware(published_at):
                return _failure(
                    "fixture_invalid", "Fixture publication time has no timezone."
                )
            if published_at > self._decision_time:
                return _failure(
                    "fixture_after_cutoff",
                    "Fixture evidence is unavailable at decision time.",
                )
        return fixture.output.model_copy(deep=True)

    async def quote(self, ticker: str) -> ToolOutput:
        """Look up a quote.

        Args:
            ticker: Exact normalized ticker.

        Returns:
            A copied fixture response or an explicit fixture error.
        """
        return self._response("quote", {"ticker": ticker})

    async def bars(self, ticker: str, period: str, interval: str) -> ToolOutput:
        """Look up historical bars.

        Args:
            ticker: Exact normalized ticker.
            period: Exact normalized period.
            interval: Exact normalized interval.

        Returns:
            A copied fixture response or an explicit fixture error.
        """
        return self._response(
            "bars", {"ticker": ticker, "period": period, "interval": interval}
        )

    async def portfolio(self) -> ToolOutput:
        """Look up the fixed account and holdings.

        Returns:
            A copied portfolio response or an explicit fixture error.
        """
        return self._response("portfolio", {})

    async def positions(self) -> ToolOutput:
        """Look up the fixed open positions.

        Returns:
            A copied positions response or an explicit fixture error.
        """
        return self._response("positions", {})

    async def fundamentals(self, ticker: str) -> ToolOutput:
        """Look up company fundamentals.

        Args:
            ticker: Exact normalized ticker.

        Returns:
            A copied fixture response or an explicit fixture error.
        """
        return self._response("fundamentals", {"ticker": ticker})

    async def filings(self, ticker: str, limit: int = 10) -> ToolOutput:
        """Look up company filings.

        Args:
            ticker: Exact normalized ticker.
            limit: Exact result limit, including the default in fixture keys.

        Returns:
            A copied fixture response or an explicit fixture error.
        """
        return self._response("filings", {"ticker": ticker, "limit": limit})

    async def xbrl_fact(
        self, ticker: str, tag: str, period: str, unit: str
    ) -> ToolOutput:
        """Look up a tagged financial fact.

        Args:
            ticker: Exact normalized ticker.
            tag: Exact XBRL tag.
            period: Exact reporting period.
            unit: Exact fact unit.

        Returns:
            A copied fixture response or an explicit fixture error.
        """
        return self._response(
            "xbrl_fact", {"ticker": ticker, "tag": tag, "period": period, "unit": unit}
        )

    async def news(self, ticker: str, limit: int = 10) -> ToolOutput:
        """Look up company news.

        Args:
            ticker: Exact normalized ticker.
            limit: Exact result limit, including the default in fixture keys.

        Returns:
            A copied fixture response or an explicit fixture error.
        """
        return self._response("news", {"ticker": ticker, "limit": limit})

    async def macro(self, series: str, period: str) -> ToolOutput:
        """Look up a macroeconomic series.

        Args:
            series: Exact series identifier.
            period: Exact normalized period.

        Returns:
            A copied fixture response or an explicit fixture error.
        """
        return self._response("macro", {"series": series, "period": period})

    async def place_leg(self, leg: dict[str, Any], client_order_id: str) -> ToolOutput:
        """Refuse every order without inspecting or submitting it.

        Args:
            leg: Order details, ignored.
            client_order_id: Order identifier, ignored.

        Returns:
            An execution-disabled error with no order side effect.
        """
        return _failure(
            "execution_disabled", "Order execution is disabled for frozen fixtures."
        )
