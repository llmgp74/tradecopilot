"""Trading tools exposed to the agent.

Tools return ``(summary, ToolOutput)`` with the content-and-artifact response
format. Middleware reads the artifact, writes the evidence ledger, and stores
proposals and verdicts in graph state. It also refuses calls whose provider is
not configured, so the tools behave the same inside a subagent.
"""

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from langgraph.types import interrupt
from pydantic import Field

from tradecopilot_agent.claims import match_claims
from tradecopilot_agent.constraints import check_ticket, regular_hours, session_open
from tradecopilot_agent.data import DataSource, MarketClock
from tradecopilot_agent.memory import MemoryStore
from tradecopilot_agent.state import (
    Claim,
    EvidenceRecord,
    OrderLeg,
    OrderTicket,
    ToolOutput,
)
from tradecopilot_agent.store import now_iso
from tradecopilot_agent.web import WebResult, WebSearch, WebSearchUnavailable

PURPOSE_DESCRIPTION = "At most six words explaining why this call is being made."
# The chat row shows this string as the action label. It is optional so
# scripted callers and older stored conversations keep working.
Purpose = Annotated[str, Field(description=PURPOSE_DESCRIPTION)]

GATHER_BUDGET = 12
# Safety bound only: the approval card previews ten rows and opens the full
# table in a dialog, so ordinary baskets stay in one ticket.
MAX_LEGS = 1000

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
    "get_open_orders": "alpaca",
    "get_trade_history": "alpaca",
    "cancel_orders": "order_execution",
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
        "web_search",
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


def _thread_id(runtime: ToolRuntime) -> str:
    """Return the conversation id from the run config.

    The proposal reservation is keyed by this id, so one conversation's open
    ticket never blocks another.

    Args:
        runtime: Injected tool runtime.

    Returns:
        The thread id, or an empty string when the config has none.
    """
    config = runtime.config or {}
    configurable = config.get("configurable") or {}
    value = configurable.get("thread_id")
    return str(value) if value else ""


def web_output(query: str, results: list[WebResult]) -> ToolOutput:
    """Turn web results into a tool result with provenance.

    Args:
        query: Search query the results answer.
        results: Ranked web results.

    Returns:
        The summary for the model and one evidence record per result.
    """
    evidence = [
        EvidenceRecord(
            id=evidence_id(
                "web_search",
                {"query": query, "url": result.url},
                result.source,
                result.published_at,
            ),
            tool="web_search",
            args={"query": query, "url": result.url},
            source=result.source,
            url=result.url,
            published_at=result.published_at,
            fetched_at=now_iso(),
            payload={
                "title": result.title,
                "summary": result.summary,
                "authority": result.authority,
            },
        )
        for result in results
    ]
    summary = json.dumps(
        [
            {
                "title": result.title,
                "url": result.url,
                "published_at": result.published_at,
                "summary": result.summary,
            }
            for result in results
        ],
        default=str,
    )
    return ToolOutput(summary=summary, evidence=evidence)


def _leg_notional(leg: dict[str, Any]) -> float:
    """Return a leg's value, recovering it from quantity and entry price.

    Args:
        leg: Ticket or result leg. Pending ticket legs carry no ``notional``.

    Returns:
        The notional in dollars, or ``0`` when it cannot be derived.
    """
    notional = float(leg.get("notional") or 0)
    if notional > 0:
        return notional
    price = _leg_price(leg)
    if price is not None:
        return float(leg.get("qty", 0)) * price
    return 0.0


def _leg_price(leg: dict[str, Any]) -> float | None:
    """Return the price the model attached to a leg, when it set one.

    A leg price becomes the limit price sent to the broker, and it is the
    price used to size and check the order. Without one, a leg is priced from
    the quote fetched for the ticket.

    Args:
        leg: Leg with an optional ``entry_price``.

    Returns:
        The positive price, or ``None`` when the leg carries no price.
    """
    value = leg.get("entry_price")
    if isinstance(value, int | float) and value > 0:
        return float(value)
    return None


# A proposal older than this needs a fresh quote and a fresh approval.
TICKET_TTL_MINUTES = 30


def _ticket_expired(created_at: Any) -> bool:
    """Report whether a pending ticket is older than its lifetime.

    Args:
        created_at: RFC 3339 timestamp stored on the ticket.

    Returns:
        True when the timestamp is unusable or past the lifetime.
    """
    if not isinstance(created_at, str):
        return True
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if created.tzinfo is None:
        return True
    age = datetime.now(tz=UTC) - created.astimezone(UTC)
    return age > timedelta(minutes=TICKET_TTL_MINUTES)


def _blocked(violations: list[dict[str, Any]]) -> ToolOutput:
    lines = [f"{item['code']}: {item['message']}" for item in violations]
    return ToolOutput(
        summary="Ticket blocked by constraints.\n" + "\n".join(lines),
        error="blocked",
    )


class TradingTools:
    """The tool implementations, independent of graph wiring."""

    def __init__(
        self,
        source: DataSource,
        store: MemoryStore,
        as_of: date | None,
    ) -> None:
        """Bind the tools to a source, store, and cutoff.

        Args:
            source: Provider data or fixtures.
            store: Profile and journal storage.
            as_of: Evaluation cutoff, or ``None`` for live runs.
        """
        self.source = source
        self.store = store
        self.as_of = as_of
        # The single-ticket rule also has to hold when the model proposes in
        # parallel: both calls read the same graph state, so the proposal that
        # is still being built is tracked here instead. The tool instance is
        # shared by every thread, so the reservation is keyed by thread.
        self._propose_lock = asyncio.Lock()
        self._reservations: dict[str, tuple[str, str]] = {}

    def capabilities(self) -> set[str]:
        """Return the source capabilities available to the tools."""
        return set(self.source.capabilities())

    def _guard(self, capability: str) -> ToolOutput | None:
        if not capability or capability in self.capabilities():
            return None
        return _unavailable(capability)

    async def _market_clock(self) -> MarketClock | None:
        """Return the broker session for a live run, None during evaluation."""
        if self.as_of is not None:
            return None
        return await self.source.clock()

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
    ) -> ToolOutput:
        """Match claims against the ledger.

        Args:
            claims: Claims to check.
            evidence: Ledger keyed by evidence id.

        Returns:
            Verdicts in the summary and in ``verification``.
        """
        verdicts = match_claims(claims, evidence, scope="answer")
        return ToolOutput(
            summary=json.dumps(verdicts, default=str), verification=verdicts
        )

    async def _open_ticket(
        self, state: dict[str, Any] | None, thread_id: str
    ) -> ToolOutput | None:
        """Refuse a new ticket while another one is open.

        Only one ticket may be in flight. A proposal waiting for approval and
        a ticket whose orders are working both count. The checks in
        ``check_ticket`` see filled positions only, so without this guard a
        second ticket can stack orders past every limit.

        Args:
            state: Graph state, holding ``pending_tickets``.
            thread_id: Conversation the call belongs to. A reservation in
                another conversation must not block this one.

        Returns:
            The refusal, or ``None`` when no ticket is open.
        """
        reservation = self._reservations.get(thread_id)
        if reservation is not None:
            if not _ticket_expired(reservation[1]):
                return ToolOutput(
                    summary=(
                        "A ticket is already waiting for approval. Execute it "
                        "or let it expire before proposing another."
                    ),
                    error="ticket_pending",
                )
            self._release_reservation(thread_id)
        if (state or {}).get("pending_tickets"):
            return ToolOutput(
                summary=(
                    "A ticket is already waiting for approval. Execute it or "
                    "let it expire before proposing another."
                ),
                error="ticket_pending",
            )
        orders = await self.source.open_orders()
        if orders.error is None:
            try:
                working = json.loads(orders.summary)
            except ValueError:
                working = None
            if isinstance(working, list) and working:
                return ToolOutput(
                    summary=(
                        "A ticket is already working at the broker. Cancel "
                        "those orders or wait for them to fill before "
                        "proposing another."
                    ),
                    error="ticket_working",
                )
        return None

    def _release_reservation(self, thread_id: str) -> None:
        """Free the in-process proposal slot for one conversation."""
        self._reservations.pop(thread_id, None)

    async def propose(
        self,
        legs: list[dict[str, Any]],
        thesis: str,
        horizon: str,
        state: dict[str, Any] | None = None,
        thread_id: str = "",
    ) -> ToolOutput:
        """Propose a ticket, with at most one open ticket per conversation.

        The reservation is taken before the work starts and released when the
        proposal fails. A successful proposal keeps it until ``execute``
        resolves the ticket, or until it expires. This closes the parallel
        case, where two calls in one model step read the same graph state.

        Args:
            legs: Legs with ticker, side, and qty.
            thesis: Rationale in prose.
            horizon: Stated holding horizon.
            state: Graph state, used to refuse a second open ticket.
            thread_id: Conversation the call belongs to.

        Returns:
            The proposal, its evidence, and the portfolio impact.
        """
        async with self._propose_lock:
            refusal = await self._open_ticket(state, thread_id)
            if refusal is not None:
                return refusal
            self._reservations[thread_id] = ("", now_iso())
        try:
            output = await self._build_proposal(legs, thesis, horizon)
        except BaseException:
            self._release_reservation(thread_id)
            raise
        if output.proposal is None:
            self._release_reservation(thread_id)
        else:
            self._reservations[thread_id] = (
                str(output.proposal.get("id") or "open"),
                now_iso(),
            )
        return output

    async def _build_proposal(
        self,
        legs: list[dict[str, Any]],
        thesis: str,
        horizon: str,
    ) -> ToolOutput:
        """Build a ticket, check it, and store the proposal.

        Args:
            legs: Legs with ticker, side, and qty.
            thesis: Rationale in prose.
            horizon: Stated holding horizon.

        Returns:
            The proposal, its evidence, and the portfolio impact.
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
        normalized: list[dict[str, Any]] = []
        for leg in legs:
            price = leg.get("entry_price", leg.get("price", leg.get("limit_price")))
            order_type = leg.get("order_type", leg.get("type"))
            normalized.append(
                {
                    "ticker": str(leg.get("ticker", "")).strip().upper(),
                    "side": str(leg.get("side", "")).lower(),
                    "qty": float(leg.get("qty", 0)),
                    "entry_price": float(price)
                    if isinstance(price, int | float)
                    else None,
                    "order_type": str(order_type).strip().lower()
                    if isinstance(order_type, str) and order_type.strip()
                    else None,
                }
            )
        if any(not leg["ticker"] for leg in normalized):
            return ToolOutput(
                summary="Every leg needs a ticker, for example NVDA.", error="invalid"
            )
        if any(leg["side"] not in {"buy", "sell"} for leg in normalized):
            return ToolOutput(
                summary="Every leg needs side buy or sell.", error="invalid"
            )
        if any(
            leg["order_type"] not in {None, "market", "limit"} for leg in normalized
        ):
            return ToolOutput(
                summary="Every leg order type is market or limit.", error="invalid"
            )
        if any(
            leg["order_type"] == "limit" and leg["entry_price"] is None
            for leg in normalized
        ):
            return ToolOutput(summary="A limit leg needs a price.", error="invalid")
        if any(
            leg["entry_price"] is not None and leg["entry_price"] <= 0
            for leg in normalized
        ):
            return ToolOutput(summary="A leg price must be positive.", error="invalid")

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
        clock = await self._market_clock()
        now = datetime.now(tz=UTC)
        session = (
            None if clock is None else session_open(now, clock.is_open, clock.next_open)
        )
        violations = check_ticket(
            normalized,
            profile,
            account,
            prices,
            sectors,
            now,
            live=self.as_of is None,
            market_open=session,
            next_open=clock.next_open if clock else None,
        )
        if violations:
            return _blocked(violations)

        ordered = [leg for leg in normalized if leg["side"] == "sell"] + [
            leg for leg in normalized if leg["side"] == "buy"
        ]
        # A leg's own price and order type win. Without them, the quote prices
        # the leg and the session picks the type: Alpaca accepts market orders
        # only in the regular session, and a limit elsewhere.
        default_type = "market" if regular_hours(now) else "limit"
        ticket_id = "t_" + uuid4().hex[:12]
        ticket = OrderTicket(
            id=ticket_id,
            legs=[
                OrderLeg(
                    ticker=str(leg["ticker"]),
                    side="buy" if leg["side"] == "buy" else "sell",
                    qty=float(leg["qty"]),
                    entry_price=_leg_price(leg) or prices[leg["ticker"]],
                    order_type=leg["order_type"] or default_type,
                )
                for leg in ordered
            ],
            thesis=thesis,
            horizon=horizon,
            created_at=now_iso(),
        )
        impact = self._impact(account, prices, ordered)

        simulation = self._simulation_record(ticket_id, impact)
        records = [*account_output.evidence, *quote_evidence, simulation]
        evidence_ids = [record.id for record in records]
        pending = {
            **ticket.model_dump(),
            "portfolio_impact": impact,
            "evidence_ids": evidence_ids,
            "paper": account.get("paper"),
        }
        self.store.append_journal(
            {
                "decision_id": ticket_id,
                "created_at": ticket.created_at,
                "legs": [
                    {
                        **leg,
                        "notional": leg["qty"]
                        * (_leg_price(leg) or prices[leg["ticker"]]),
                        "entry_price": _leg_price(leg) or prices[leg["ticker"]],
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
                "paper": account.get("paper"),
            }
        )
        return ToolOutput(
            summary=json.dumps(
                {
                    "ticket_id": ticket_id,
                    "legs": ordered,
                    "portfolio_impact": impact,
                },
                default=str,
            ),
            evidence=records,
            proposal=pending,
            portfolio_impact=impact,
        )

    async def execute(
        self,
        ticket_id: str,
        state: dict[str, Any],
        tool_call_id: str | None = None,
        thread_id: str = "",
    ) -> ToolOutput:
        """Place an approved ticket.

        Args:
            ticket_id: Id from ``propose_ticket``.
            state: Graph state holding the pending ticket.
            tool_call_id: Id of the call that reached the interrupt, used by
                the UI to match the approval to its row.
            thread_id: Conversation the call belongs to, so its proposal
                reservation is released.

        Returns:
            Per-leg results.
        """
        guard = self._guard("order_execution")
        if guard is not None:
            return guard
        entry = (state.get("pending_tickets") or {}).get(ticket_id)
        pending = entry.get("ticket") if isinstance(entry, dict) else None
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
        clock = await self._market_clock()
        now = datetime.now(tz=UTC)
        session = (
            None if clock is None else session_open(now, clock.is_open, clock.next_open)
        )
        violations = check_ticket(
            legs,
            profile,
            account,
            prices,
            sectors,
            now,
            live=self.as_of is None,
            market_open=session,
            next_open=clock.next_open if clock else None,
        )
        if violations:
            # The ticket was approved but cannot be placed as written, so it no
            # longer blocks the next proposal.
            self._release_reservation(thread_id)
            return _blocked(violations).model_copy(update={"ticket_done": True})

        if not profile.get("execution", {}).get("autonomous", False):
            decision = interrupt(
                {
                    "action_requests": [
                        {
                            "name": "execute_ticket",
                            "args": {"ticket_id": ticket_id},
                            "description": "Review the order ticket",
                            "tool_call_id": tool_call_id,
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
                self._release_reservation(thread_id)
                return ToolOutput(
                    summary=f"Ticket rejected: {reason}",
                    error="rejected",
                    ticket_done=True,
                )

        if _ticket_expired(pending.get("created_at")):
            self._release_reservation(thread_id)
            return ToolOutput(
                summary="This ticket has expired. Propose a new one.",
                error="expired",
                ticket_done=True,
            )

        results = await self._place(ticket_id, legs, prices)
        status = self._status(results)
        self._journal_result(pending, results, status, "approve", None)
        self._release_reservation(thread_id)
        return ToolOutput(
            summary=json.dumps(
                {"ticket_id": ticket_id, "status": status, "legs": results}
            ),
            ticket_done=True,
        )

    async def open_orders(self) -> ToolOutput:
        """List the broker's working orders.

        Returns:
            The orders with the ids needed to cancel them.
        """
        guard = self._guard("alpaca")
        if guard is not None:
            return guard
        return await self.source.open_orders()

    async def trade_history(self, days: int) -> ToolOutput:
        """Fetch the account's recent orders and fills.

        Args:
            days: Lookback window in days.

        Returns:
            The broker's orders, including filled and canceled ones.
        """
        guard = self._guard("alpaca")
        if guard is not None:
            return guard
        return await self.source.order_history(max(1, min(days, 90)))

    async def cancel(self, orders: list[dict[str, Any]]) -> ToolOutput:
        """Cancel working orders.

        The user's cancellation request is the approval, so this runs without
        an interrupt. The model is responsible for canceling only orders the
        user asked about.

        Args:
            orders: Orders from ``get_open_orders``, each with an ``order_id``.

        Returns:
            Per-order cancellation results.
        """
        guard = self._guard("order_execution")
        if guard is not None:
            return guard
        cleaned: list[dict[str, Any]] = []
        for order in orders:
            order_id = order.get("order_id") if isinstance(order, dict) else None
            if not isinstance(order_id, str) or not order_id:
                return ToolOutput(
                    summary="Each order needs an order_id from get_open_orders.",
                    error="invalid",
                )
            cleaned.append(
                {
                    "order_id": order_id,
                    "ticker": order.get("ticker"),
                    "side": order.get("side"),
                    "qty": order.get("qty"),
                }
            )
        if not cleaned:
            return ToolOutput(summary="No orders to cancel.", error="invalid")

        results = []
        for order in cleaned:
            output = await self.source.cancel_order(order["order_id"])
            results.append(
                {
                    "order_id": order["order_id"],
                    "ok": output.error is None,
                    "message": output.summary,
                }
            )
        failed = [result for result in results if not result["ok"]]
        status = (
            "cancelled"
            if not failed
            else "partial"
            if len(failed) < len(results)
            else "failed"
        )
        return ToolOutput(summary=json.dumps({"status": status, "orders": results}))

    async def _place(
        self, ticket_id: str, legs: list[dict[str, Any]], prices: dict[str, float]
    ) -> list[dict[str, Any]]:
        account_output = await self.source.portfolio()
        cash = float(self._account(account_output).get("cash", 0))
        results: list[dict[str, Any]] = []
        for index, leg in enumerate(legs):
            quote = prices[leg["ticker"]]
            limit_price = _leg_price(leg)
            # A buy is sized at the higher of its limit and the quote, matching
            # the constraint check; a sell uses its limit.
            if leg["side"] == "buy" and limit_price is not None:
                price = max(limit_price, quote)
            else:
                price = limit_price or quote
            notional = float(leg["qty"]) * price
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
                    "order_id": payload.get("order_id"),
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
        event_at = now_iso()
        decision_at = str(pending.get("created_at") or event_at)
        self.store.append_journal(
            {
                "decision_id": pending.get("id"),
                "created_at": decision_at,
                "updated_at": event_at,
                "legs": [
                    {
                        "ticker": leg.get("ticker"),
                        "side": leg.get("side"),
                        "qty": float(leg.get("qty", 0)),
                        "notional": _leg_notional(leg),
                        "entry_price": leg.get("entry_price"),
                        "order_id": leg.get("order_id"),
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
                "paper": pending.get("paper"),
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
        leg_prices = {
            str(leg["ticker"]): _leg_price(leg)
            for leg in legs
            if _leg_price(leg) is not None
        }
        for leg in legs:
            ticker = str(leg["ticker"])
            quantities[ticker] = quantities.get(ticker, 0.0) + (
                float(leg["qty"]) if leg["side"] == "buy" else -float(leg["qty"])
            )
        for ticker, quantity in quantities.items():
            price = leg_prices.get(ticker) or prices.get(ticker)
            if price is not None:
                after[ticker] = quantity * price / equity * 100
        net = sum(
            float(leg["qty"])
            * (_leg_price(leg) or prices.get(leg["ticker"], 0))
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
    searcher: WebSearch | None = None,
) -> list[BaseTool]:
    """Create the trading tools bound to one source and store.

    Args:
        source: Data source for every provider-backed tool.
        store: Profile and journal store.
        as_of: Evaluation cutoff, or ``None`` for live runs.
        searcher: Web search provider. The web tool is omitted when absent.

    Returns:
        The tool objects passed to the agent.
    """
    impl = TradingTools(source, store, as_of)
    artifact = tool(response_format="content_and_artifact")

    @artifact
    async def get_quote(
        ticker: str, purpose: Purpose = ""
    ) -> tuple[str, dict[str, Any]]:
        """Return the latest quote for a ticker."""
        output = await impl.quote(ticker)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_bars(
        ticker: str,
        period: str = "1d",
        interval: str = "1d",
        purpose: Purpose = "",
    ) -> tuple[str, dict[str, Any]]:
        """Return price bars. Period is 1d, 1w, or 1m."""
        output = await impl.bars(ticker, period, interval)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_portfolio(
        purpose: Purpose = "",
    ) -> tuple[str, dict[str, Any]]:
        """Return the account and its positions."""
        output = await impl.portfolio()
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_positions(
        purpose: Purpose = "",
    ) -> tuple[str, dict[str, Any]]:
        """Return the open positions only."""
        output = await impl.positions()
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_fundamentals(
        ticker: str, purpose: Purpose = ""
    ) -> tuple[str, dict[str, Any]]:
        """Return the profile, sector, and valuation ratios for a ticker."""
        output = await impl.fundamentals(ticker)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_filings(
        ticker: str, limit: int = 10, purpose: Purpose = ""
    ) -> tuple[str, dict[str, Any]]:
        """Return recent SEC filings for a ticker."""
        output = await impl.filings(ticker, limit)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_xbrl_fact(
        ticker: str,
        tag: str,
        period: str,
        unit: str,
        purpose: Purpose = "",
    ) -> tuple[str, dict[str, Any]]:
        """Return one XBRL fact. This is the primary source for numbers."""
        output = await impl.xbrl_fact(ticker, tag, period, unit)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_news(
        ticker: str, limit: int = 10, purpose: Purpose = ""
    ) -> tuple[str, dict[str, Any]]:
        """Return recent company news."""
        output = await impl.news(ticker, limit)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_macro(
        series: str, period: str = "1y", purpose: Purpose = ""
    ) -> tuple[str, dict[str, Any]]:
        """Return one macro series from FRED."""
        output = await impl.macro(series, period)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def verify_claims(
        claims: list[Claim],
        runtime: ToolRuntime,
        purpose: Purpose = "",
    ) -> tuple[str, dict[str, Any]]:
        """Check claims against evidence already gathered in this session."""
        evidence = runtime.state.get("evidence", {}) if runtime.state else {}
        output = impl.verify(claims, evidence)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_open_orders(
        purpose: Purpose = "",
    ) -> tuple[str, dict[str, Any]]:
        """List working orders with the ids needed to cancel them."""
        output = await impl.open_orders()
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def get_trade_history(
        days: int = 7, purpose: Purpose = ""
    ) -> tuple[str, dict[str, Any]]:
        """Return the account's recent orders and fills for the last days."""
        output = await impl.trade_history(days)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def cancel_orders(
        orders: list[dict[str, Any]], purpose: Purpose = ""
    ) -> tuple[str, dict[str, Any]]:
        """Cancel working orders after the user approves the list."""
        output = await impl.cancel(orders)
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def propose_ticket(
        legs: list[dict[str, Any]],
        thesis: str,
        runtime: ToolRuntime,
        horizon: str = "weeks",
        purpose: Purpose = "",
    ) -> tuple[str, dict[str, Any]]:
        """Propose one ticket with one or more legs. No order is placed.

        Only one ticket may be open at a time. This refuses while another
        ticket waits for approval or while any orders are working.

        Each leg takes ticker, side, and qty, plus an optional price and an
        optional order type of market or limit. A leg price becomes the limit
        price sent to the broker; without one, the leg is priced from its
        quote. A limit leg needs a price.
        """
        output = await impl.propose(
            legs,
            thesis,
            horizon,
            (runtime.state or {}) if runtime else {},
            _thread_id(runtime),
        )
        return _text(output), output.model_dump(mode="json")

    @artifact
    async def execute_ticket(
        ticket_id: str, runtime: ToolRuntime, purpose: Purpose = ""
    ) -> tuple[str, dict[str, Any]]:
        """Place a proposed ticket after the user approves it."""
        output = await impl.execute(
            ticket_id,
            runtime.state or {},
            runtime.tool_call_id,
            _thread_id(runtime),
        )
        return _text(output), output.model_dump(mode="json")

    tools: list[BaseTool] = [
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
        get_open_orders,
        get_trade_history,
        cancel_orders,
        propose_ticket,
        execute_ticket,
    ]

    if searcher is not None:

        @artifact
        async def web_search(
            query: str, count: int = 8, purpose: Purpose = ""
        ) -> tuple[str, dict[str, Any]]:
            """Search the public web for current events and general news."""
            cleaned = query.strip()
            if not cleaned:
                output = ToolOutput(
                    summary="A search query is required.", error="invalid"
                )
            else:
                try:
                    results = await searcher.search(
                        cleaned, max(1, min(int(count), 10))
                    )
                except WebSearchUnavailable as exc:
                    output = ToolOutput(summary=str(exc), error="unavailable")
                else:
                    output = web_output(cleaned, results)
            return _text(output), output.model_dump(mode="json")

        tools.append(web_search)

    return tools
