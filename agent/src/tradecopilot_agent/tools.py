"""Trading tools exposed to the agent.

Tools return ``(summary, ToolOutput)`` with the content-and-artifact response
format. Middleware reads the artifact, writes the evidence ledger, and stores
proposals and verdicts in graph state. It also refuses calls whose provider is
not configured, so the tools behave the same inside a subagent.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import uuid4

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from langgraph.types import interrupt

from tradecopilot_agent.claims import match_claims
from tradecopilot_agent.constraints import check_ticket
from tradecopilot_agent.data import DataSource
from tradecopilot_agent.memory import MemoryStore
from tradecopilot_agent.state import (
    Claim,
    EvidenceRecord,
    OrderLeg,
    OrderTicket,
    ToolOutput,
)
from tradecopilot_agent.store import now_iso

MAX_LEGS = 10
GATHER_BUDGET = 12

TOOL_CAPABILITIES: dict[str, str] = {
    "get_quote": "alpaca",
    "get_bars": "alpaca",
    "get_portfolio": "alpaca",
    "get_positions": "alpaca",
    "get_fundamentals": "fmp",
    "get_filings": "edgar",
    "get_xbrl_fact": "edgar",
    "get_news": "finnhub",
    "get_macro": "fred",
    "propose_ticket": "alpaca",
    "execute_ticket": "order_execution",
    "verify_claims": "",
}
TRADING_TOOL_NAMES = frozenset(TOOL_CAPABILITIES)
EVIDENCE_TOOL_NAMES = frozenset(
    {
        "get_quote",
        "get_bars",
        "get_portfolio",
        "get_positions",
        "get_fundamentals",
        "get_filings",
        "get_xbrl_fact",
        "get_news",
        "get_macro",
    }
)

_CAPABILITY_LABELS = {
    "alpaca": "Alpaca",
    "order_execution": "Alpaca order execution",
    "edgar": "SEC EDGAR",
    "fmp": "FMP",
    "finnhub": "Finnhub",
    "fred": "FRED",
}


def evidence_id(
    tool_name: str, args: dict[str, Any], source: str, published_at: str | None
) -> str:
    """Return a stable evidence id.

    Args:
        tool_name: Tool that produced the record.
        args: Normalized arguments.
        source: Provider name.
        published_at: Source timestamp.

    Returns:
        ``ev_`` followed by 12 hex characters.
    """
    canonical = json.dumps(
        {"tool": tool_name, "args": args, "source": source, "at": published_at},
        sort_keys=True,
        default=str,
    )
    return "ev_" + hashlib.sha256(canonical.encode()).hexdigest()[:12]


def _unavailable(capability: str) -> ToolOutput:
    label = _CAPABILITY_LABELS.get(capability, capability)
    return ToolOutput(summary=f"{label} is not configured.", error="unavailable")


def _text(output: ToolOutput) -> str:
    if output.error:
        return output.summary
    ids = [record.id for record in output.evidence]
    return output.summary + (f"\nEvidence: {', '.join(ids)}" if ids else "")


def _blocked(violations: list[dict[str, Any]]) -> ToolOutput:
    lines = [f"{item['code']}: {item['message']}" for item in violations]
    return ToolOutput(
        summary="Ticket blocked by constraints. Adjust and try again.\n"
        + "\n".join(lines),
        error="blocked",
    )


class TradingTools:
    """The tool implementations, independent of graph wiring."""

    def __init__(
        self,
        source: DataSource,
        store: MemoryStore,
        as_of: date | None,
        extract_claims: Callable[[str], list[Claim]],
    ) -> None:
        """Bind the tools to a source, store, and cutoff.

        Args:
            source: Provider data or fixtures.
            store: Profile and journal storage.
            as_of: Evaluation cutoff, or ``None`` for live runs.
            extract_claims: Claim extractor used for proposals.
        """
        self.source = source
        self.store = store
        self.as_of = as_of
        self.extract_claims = extract_claims

    def capabilities(self) -> set[str]:
        """Return the source capabilities available to the tools."""
        return set(self.source.capabilities())

    def _guard(self, capability: str) -> ToolOutput | None:
        if not capability or capability in self.capabilities():
            return None
        return _unavailable(capability)

    async def quote(self, ticker: str) -> ToolOutput:
        """Fetch a quote."""
        return self._guard("alpaca") or await self.source.quote(ticker.upper())

    async def bars(self, ticker: str, period: str, interval: str) -> ToolOutput:
        """Fetch bars."""
        return self._guard("alpaca") or await self.source.bars(
            ticker.upper(), period.lower(), interval.lower()
        )

    async def portfolio(self) -> ToolOutput:
        """Fetch the account."""
        return self._guard("alpaca") or await self.source.portfolio()

    async def positions(self) -> ToolOutput:
        """Fetch the positions."""
        return self._guard("alpaca") or await self.source.positions()

    async def fundamentals(self, ticker: str) -> ToolOutput:
        """Fetch fundamentals."""
        return self._guard("fmp") or await self.source.fundamentals(ticker.upper())

    async def filings(self, ticker: str, limit: int = 10) -> ToolOutput:
        """Fetch filings."""
        return self._guard("edgar") or await self.source.filings(
            ticker.upper(), max(1, min(int(limit), 50))
        )

    async def xbrl_fact(
        self, ticker: str, tag: str, period: str, unit: str
    ) -> ToolOutput:
        """Fetch one XBRL fact."""
        return self._guard("edgar") or await self.source.xbrl_fact(
            ticker.upper(), tag.strip(), period.strip().upper(), unit.strip()
        )

    async def news(self, ticker: str, limit: int = 10) -> ToolOutput:
        """Fetch news."""
        return self._guard("finnhub") or await self.source.news(
            ticker.upper(), max(1, min(int(limit), 50))
        )

    async def macro(self, series: str, period: str) -> ToolOutput:
        """Fetch a macro series."""
        return self._guard("fred") or await self.source.macro(
            series.strip().upper(), period.strip()
        )

    def verify(
        self,
        claims: list[Claim],
        evidence: dict[str, Any],
        scope: Literal["draft", "answer"],
    ) -> ToolOutput:
        """Match claims against the ledger.

        Args:
            claims: Claims to check.
            evidence: Ledger keyed by evidence id.
            scope: ``draft`` or ``answer``.

        Returns:
            Verdicts in the summary and in ``verification``.
        """
        verdicts = match_claims(claims, evidence, scope=scope)
        return ToolOutput(
            summary=json.dumps(verdicts, default=str), verification=verdicts
        )

    async def propose(
        self,
        legs: list[dict[str, Any]],
        thesis: str,
        horizon: str,
        evidence: dict[str, Any],
    ) -> ToolOutput:
        """Build a ticket, check it, and store the proposal.

        Args:
            legs: Legs with ticker, side, and qty.
            thesis: Rationale in prose.
            horizon: Stated holding horizon.
            evidence: Ledger already gathered this session.

        Returns:
            The proposal, impact, verdicts, and evidence.
        """
        guard = self._guard("alpaca")
        if guard is not None:
            return guard
        if not legs:
            return ToolOutput(
                summary="A ticket needs at least one leg.", error="invalid"
            )
        if len(legs) > MAX_LEGS:
            return ToolOutput(
                summary=f"A ticket takes at most {MAX_LEGS} legs.", error="invalid"
            )
        normalized: list[dict[str, Any]] = [
            {
                "ticker": str(leg.get("ticker", "")).strip().upper(),
                "side": str(leg.get("side", "")).lower(),
                "qty": float(leg.get("qty", 0)),
            }
            for leg in legs
        ]
        if any(leg["side"] not in {"buy", "sell"} for leg in normalized):
            return ToolOutput(
                summary="Every leg needs side buy or sell.", error="invalid"
            )

        account_output = await self.source.portfolio()
        if account_output.error:
            return account_output
        account = self._account(account_output)
        prices, quote_evidence, quote_error = await self._prices(
            [leg["ticker"] for leg in normalized]
        )
        if quote_error is not None:
            return ToolOutput(summary=quote_error, error="missing_price")

        profile = self.store.get_profile()
        sectors = await self._sectors(
            [leg["ticker"] for leg in normalized],
            profile.get("sector_exclusions", []),
        )
        violations = check_ticket(
            normalized,
            profile,
            account,
            prices,
            sectors,
            datetime.now(tz=UTC),
            live=self.as_of is None,
        )
        if violations:
            return _blocked(violations)

        ordered = [leg for leg in normalized if leg["side"] == "sell"] + [
            leg for leg in normalized if leg["side"] == "buy"
        ]
        ticket_id = "t_" + uuid4().hex[:12]
        ticket = OrderTicket(
            id=ticket_id,
            legs=[
                OrderLeg(
                    ticker=str(leg["ticker"]),
                    side="buy" if leg["side"] == "buy" else "sell",
                    qty=float(leg["qty"]),
                )
                for leg in ordered
            ],
            thesis=thesis,
            horizon=horizon,
            created_at=now_iso(),
        )
        impact = self._impact(account, prices, ordered)
        try:
            claims = self.extract_claims(thesis)
            verdicts = match_claims(claims, evidence, scope="draft")
        except Exception:
            verdicts = [{"scope": "draft", "status": "unavailable"}]

        simulation = self._simulation_record(ticket_id, impact)
        records = [*account_output.evidence, *quote_evidence, simulation]
        evidence_ids = [record.id for record in records]
        pending = {
            **ticket.model_dump(),
            "portfolio_impact": impact,
            "verification": verdicts,
            "evidence_ids": evidence_ids,
        }
        self.store.append_journal(
            {
                "decision_id": ticket_id,
                "created_at": ticket.created_at,
                "legs": [
                    {
                        **leg,
                        "notional": leg["qty"] * prices[leg["ticker"]],
                        "fill_price": None,
                        "fill_at": None,
                        "status": "proposed",
                    }
                    for leg in ordered
                ],
                "thesis": thesis,
                "horizon": horizon,
                "evidence_ids": evidence_ids,
                "status": "proposed",
                "user_action": None,
                "rejection_reason": None,
            }
        )
        return ToolOutput(
            summary=json.dumps(
                {
                    "ticket_id": ticket_id,
                    "legs": ordered,
                    "portfolio_impact": impact,
                    "verdicts": verdicts,
                },
                default=str,
            ),
            evidence=records,
            proposal=pending,
            portfolio_impact=impact,
            verification=verdicts,
        )

    async def execute(self, ticket_id: str, state: dict[str, Any]) -> ToolOutput:
        """Place an approved ticket.

        Args:
            ticket_id: Id from ``propose_ticket``.
            state: Graph state holding the pending ticket.

        Returns:
            Per-leg results.
        """
        guard = self._guard("order_execution")
        if guard is not None:
            return guard
        pending = state.get("pending_ticket")
        if not isinstance(pending, dict) or pending.get("id") != ticket_id:
            return ToolOutput(summary="No matching pending ticket.", error="invalid")
        legs = [dict(leg) for leg in pending.get("legs", [])]
        if not legs:
            return ToolOutput(summary="The ticket has no legs.", error="invalid")

        account_output = await self.source.portfolio()
        if account_output.error:
            return account_output
        account = self._account(account_output)
        prices, _, quote_error = await self._prices([leg["ticker"] for leg in legs])
        if quote_error is not None:
            return ToolOutput(summary=quote_error, error="missing_price")
        profile = self.store.get_profile()
        sectors = await self._sectors(
            [leg["ticker"] for leg in legs], profile.get("sector_exclusions", [])
        )
        violations = check_ticket(
            legs,
            profile,
            account,
            prices,
            sectors,
            datetime.now(tz=UTC),
            live=self.as_of is None,
        )
        if violations:
            return _blocked(violations)

        if not profile.get("execution", {}).get("autonomous", False):
            decision = interrupt(
                {
                    "action_requests": [
                        {
                            "name": "execute_ticket",
                            "args": {"ticket_id": ticket_id},
                            "description": "Review the order ticket",
                        }
                    ],
                    "review_configs": [
                        {
                            "action_name": "execute_ticket",
                            "allowed_decisions": ["approve", "reject"],
                        }
                    ],
                }
            )
            if not self._approved(decision):
                reason = self._rejection_reason(decision)
                self._journal_result(pending, legs, "rejected", "reject", reason)
                return ToolOutput(
                    summary=f"Ticket rejected: {reason}", error="rejected"
                )

        results = await self._place(ticket_id, legs, prices)
        status = self._status(results)
        self._journal_result(pending, results, status, "approve", None)
        return ToolOutput(
            summary=json.dumps(
                {"ticket_id": ticket_id, "status": status, "legs": results}
            ),
            ticket_done=True,
        )

    async def _place(
        self, ticket_id: str, legs: list[dict[str, Any]], prices: dict[str, float]
    ) -> list[dict[str, Any]]:
        account_output = await self.source.portfolio()
        cash = float(self._account(account_output).get("cash", 0))
        results: list[dict[str, Any]] = []
        for index, leg in enumerate(legs):
            notional = float(leg["qty"]) * prices[leg["ticker"]]
            if leg["side"] == "buy" and notional > cash:
                results.append(
                    {
                        **leg,
                        "notional": notional,
                        "status": "skipped_unfunded",
                        "fill_price": None,
                        "fill_at": None,
                    }
                )
                continue
            placed = await self.source.place_leg(leg, f"{ticket_id}-{index}")
            if placed.error:
                results.append(
                    {
                        **leg,
                        "notional": notional,
                        "status": "failed",
                        "fill_price": None,
                        "fill_at": None,
                    }
                )
                continue
            payload = placed.evidence[0].payload if placed.evidence else {}
            status = str(payload.get("status", "submitted"))
            if status == "filled":
                cash -= notional if leg["side"] == "buy" else -notional
            results.append(
                {
                    **leg,
                    "notional": notional,
                    "status": status,
                    "fill_price": payload.get("fill_price"),
                    "fill_at": payload.get("fill_at"),
                }
            )
        return results

    def _journal_result(
        self,
        pending: dict[str, Any],
        legs: list[dict[str, Any]],
        status: str,
        user_action: str | None,
        reason: str | None,
    ) -> None:
        self.store.append_journal(
            {
                "decision_id": pending.get("id"),
                "created_at": now_iso(),
                "legs": [
                    {
                        "ticker": leg.get("ticker"),
                        "side": leg.get("side"),
                        "qty": float(leg.get("qty", 0)),
                        "notional": float(leg.get("notional", 0)),
                        "fill_price": leg.get("fill_price"),
                        "fill_at": leg.get("fill_at"),
                        "status": leg.get("status", status),
                    }
                    for leg in legs
                ],
                "thesis": pending.get("thesis", ""),
                "horizon": pending.get("horizon", "weeks"),
                "evidence_ids": pending.get("evidence_ids", []),
                "status": status,
                "user_action": user_action,
                "rejection_reason": reason,
            }
        )

    @staticmethod
    def _approved(decision: Any) -> bool:
        if not isinstance(decision, dict):
            return False
        decisions = decision.get("decisions")
        if not isinstance(decisions, list) or not decisions:
            return False
        first = decisions[0]
        return isinstance(first, dict) and first.get("type") == "approve"

    @staticmethod
    def _rejection_reason(decision: Any) -> str:
        if isinstance(decision, dict):
            decisions = decision.get("decisions")
            if isinstance(decisions, list) and decisions:
                first = decisions[0]
                if isinstance(first, dict):
                    message = first.get("message")
                    if isinstance(message, str):
                        return message
        return "Rejected"

    @staticmethod
    def _status(results: list[dict[str, Any]]) -> str:
        statuses = {str(result.get("status")) for result in results}
        if statuses == {"filled"}:
            return "filled"
        if statuses <= {"failed", "skipped_unfunded"}:
            return "failed"
        return "submitted"

    @staticmethod
    def _account(output: ToolOutput) -> dict[str, Any]:
        payload = output.evidence[0].payload if output.evidence else {}
        return payload if isinstance(payload, dict) else {}

    async def _prices(
        self, tickers: list[str]
    ) -> tuple[dict[str, float], list[EvidenceRecord], str | None]:
        prices: dict[str, float] = {}
        evidence: list[EvidenceRecord] = []
        for ticker in dict.fromkeys(tickers):
            output = await self.source.quote(ticker)
            if output.error or not output.evidence:
                return {}, [], f"No quote for {ticker}."
            payload = output.evidence[0].payload
            price = payload.get("price") if isinstance(payload, dict) else None
            if not isinstance(price, int | float):
                return {}, [], f"No price for {ticker}."
            prices[ticker] = float(price)
            evidence.extend(output.evidence)
        return prices, evidence, None

    async def _sectors(
        self, tickers: list[str], exclusions: list[str]
    ) -> dict[str, str | None]:
        if not exclusions:
            return {}
        sectors: dict[str, str | None] = {}
        for ticker in dict.fromkeys(tickers):
            if "fmp" not in self.capabilities():
                sectors[ticker] = None
                continue
            output = await self.source.fundamentals(ticker)
            payload = output.evidence[0].payload if output.evidence else {}
            sectors[ticker] = (
                payload.get("sector") if isinstance(payload, dict) else None
            )
        return sectors

    @staticmethod
    def _impact(
        account: dict[str, Any],
        prices: dict[str, float],
        legs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        equity = float(account.get("equity", 0)) or 1.0
        before: dict[str, float] = {}
        quantities: dict[str, float] = {}
        for position in account.get("positions", []):
            ticker = str(position.get("ticker", "")).upper()
            quantities[ticker] = float(position.get("qty", 0))
            before[ticker] = float(position.get("market_value", 0)) / equity * 100
        after = dict(before)
        for leg in legs:
            ticker = str(leg["ticker"])
            quantities[ticker] = quantities.get(ticker, 0.0) + (
                float(leg["qty"]) if leg["side"] == "buy" else -float(leg["qty"])
            )
        for ticker, quantity in quantities.items():
            price = prices.get(ticker)
            if price is not None:
                after[ticker] = quantity * price / equity * 100
        net = sum(
            float(leg["qty"])
            * prices.get(leg["ticker"], 0)
            * (1 if leg["side"] == "buy" else -1)
            for leg in legs
        )
        return {
            "before_pct": before,
            "after_pct": after,
            "net_notional": net,
            "equity": equity,
        }

    @staticmethod
    def _simulation_record(ticket_id: str, impact: dict[str, Any]) -> EvidenceRecord:
        args = {"ticket_id": ticket_id}
        return EvidenceRecord(
            id=evidence_id("portfolio_simulation", args, "portfolio_simulation", None),
            tool="portfolio_simulation",
            args=args,
            source="portfolio_simulation",
            fetched_at=now_iso(),
            payload={"kind": "simulation", **args, **impact},
        )


def build_tools(
    source: DataSource,
    store: MemoryStore,
    as_of: date | None,
    extract_claims: Callable[[str], list[Claim]],
) -> list[BaseTool]:
    """Create the trading tools bound to one source and store.

    Args:
        source: Data source for every provider-backed tool.
        store: Profile and journal store.
        as_of: Evaluation cutoff, or ``None`` for live runs.
        extract_claims: Callable that extracts claims from prose.

    Returns:
        The tool objects passed to the agent.
    """
    impl = TradingTools(source, store, as_of, extract_claims)
    artifact = tool(response_format="content_and_artifact")

    @artifact
    async def get_quote(ticker: str) -> tuple[str, dict[str, Any]]:
        """Return the latest quote for a ticker."""
        output = await impl.quote(ticker)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_bars(
        ticker: str, period: str = "1d", interval: str = "1d"
    ) -> tuple[str, dict[str, Any]]:
        """Return price bars. Period is 1d, 1w, or 1m."""
        output = await impl.bars(ticker, period, interval)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_portfolio() -> tuple[str, dict[str, Any]]:
        """Return the account and its positions."""
        output = await impl.portfolio()
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_positions() -> tuple[str, dict[str, Any]]:
        """Return the open positions only."""
        output = await impl.positions()
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_fundamentals(ticker: str) -> tuple[str, dict[str, Any]]:
        """Return the profile, sector, and valuation ratios for a ticker."""
        output = await impl.fundamentals(ticker)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_filings(ticker: str, limit: int = 10) -> tuple[str, dict[str, Any]]:
        """Return recent SEC filings for a ticker."""
        output = await impl.filings(ticker, limit)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_xbrl_fact(
        ticker: str, tag: str, period: str, unit: str
    ) -> tuple[str, dict[str, Any]]:
        """Return one XBRL fact. This is the primary source for numbers."""
        output = await impl.xbrl_fact(ticker, tag, period, unit)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_news(ticker: str, limit: int = 10) -> tuple[str, dict[str, Any]]:
        """Return recent company news."""
        output = await impl.news(ticker, limit)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_macro(series: str, period: str = "1y") -> tuple[str, dict[str, Any]]:
        """Return one macro series from FRED."""
        output = await impl.macro(series, period)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def verify_claims(
        claims: list[Claim],
        runtime: ToolRuntime,
        scope: Literal["draft", "answer"] = "answer",
    ) -> tuple[str, dict[str, Any]]:
        """Check claims against evidence already gathered in this session."""
        evidence = runtime.state.get("evidence", {}) if runtime.state else {}
        output = impl.verify(claims, evidence, scope)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def propose_ticket(
        legs: list[dict[str, Any]],
        thesis: str,
        runtime: ToolRuntime,
        horizon: str = "weeks",
    ) -> tuple[str, dict[str, Any]]:
        """Propose one ticket with one or more legs. No order is placed."""
        evidence = runtime.state.get("evidence", {}) if runtime.state else {}
        output = await impl.propose(legs, thesis, horizon, evidence)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def execute_ticket(
        ticket_id: str, runtime: ToolRuntime
    ) -> tuple[str, dict[str, Any]]:
        """Place a proposed ticket after the user approves it."""
        output = await impl.execute(ticket_id, runtime.state or {})
        return _text(output), output.model_dump(mode="json")

    return [
        get_quote,
        get_bars,
        get_portfolio,
        get_positions,
        get_fundamentals,
        get_filings,
        get_xbrl_fact,
        get_news,
        get_macro,
        verify_claims,
        propose_ticket,
        execute_ticket,
    ]
