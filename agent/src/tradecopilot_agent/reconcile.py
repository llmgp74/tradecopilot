"""Refresh stored journal snapshots against the broker's order state.

Placement records what the broker reports at that moment, often ``pending_new``.
A fill that happens later never reaches the journal unless a new snapshot is
appended, so reads reconcile only the legs that are still open and append one
updated snapshot per changed decision.
"""

from typing import Any

from tradecopilot_agent.store import now_iso

TERMINAL_STATUSES = frozenset(
    {
        "filled",
        "canceled",
        "cancelled",
        "expired",
        "rejected",
        "replaced",
        "stopped",
        "suspended",
        "calculated",
        "done_for_day",
    }
)
FAILED_STATUSES = frozenset(
    {"canceled", "cancelled", "expired", "rejected", "stopped", "suspended"}
)


def client_order_id(ticket_id: str, leg_index: int) -> str:
    """Build the idempotency key used when the leg was placed.

    Args:
        ticket_id: Ticket id stored as the journal decision id.
        leg_index: Position of the leg in the ticket.

    Returns:
        The client order id sent to the broker.
    """
    return f"{ticket_id}-{leg_index}"


def _decision_status(statuses: list[str]) -> str:
    """Map leg statuses to one journal status.

    Args:
        statuses: Broker status per leg.

    Returns:
        ``filled`` when every leg filled, ``failed`` when nothing is open and
        at least one leg failed, otherwise ``submitted``.
    """
    if statuses and all(status == "filled" for status in statuses):
        return "filled"
    if any(status in FAILED_STATUSES for status in statuses) and all(
        status in TERMINAL_STATUSES for status in statuses
    ):
        return "failed"
    return "submitted"


def _needs_refresh(leg: dict[str, Any]) -> bool:
    """Return whether a leg may still change at the broker."""
    return str(leg.get("status") or "") not in TERMINAL_STATUSES


def reconcile(
    rows: list[dict[str, Any]],
    store: Any,
    orders: dict[str, dict[str, Any]],
) -> int:
    """Append an updated snapshot for each decision whose legs changed.

    Args:
        rows: Latest journal snapshots, newest first. Updated in place so the
            caller can render them without reading again.
        store: Store exposing ``append_journal``.
        orders: Broker order states keyed by client order id.

    Returns:
        Number of decisions that received a new snapshot.
    """
    changed_rows = 0
    for row in rows:
        legs = row.get("legs") or []
        if not any(_needs_refresh(leg) for leg in legs):
            continue
        changed = False
        updated: list[dict[str, Any]] = []
        for index, leg in enumerate(legs):
            if not _needs_refresh(leg):
                updated.append(leg)
                continue
            match = orders.get(client_order_id(str(row["id"]), index))
            if match is None:
                updated.append(leg)
                continue
            next_leg = {
                **leg,
                "order_id": match.get("order_id") or leg.get("order_id"),
                "status": match.get("status") or leg.get("status"),
                "fill_price": (
                    match.get("fill_price")
                    if match.get("fill_price") is not None
                    else leg.get("fill_price")
                ),
                "fill_at": match.get("fill_at") or leg.get("fill_at"),
            }
            # Persisting the broker id alone is not worth a snapshot; the
            # client order id already identifies the order.
            if (
                next_leg["status"],
                next_leg["fill_price"],
                next_leg["fill_at"],
            ) != (
                leg.get("status"),
                leg.get("fill_price"),
                leg.get("fill_at"),
            ):
                changed = True
            updated.append(next_leg)
        if not changed:
            continue
        status = _decision_status([str(leg.get("status") or "") for leg in updated])
        row.update({"legs": updated, "status": status, "updated_at": now_iso()})
        store.append_journal(
            {
                "decision_id": row["id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "legs": updated,
                "thesis": row.get("thesis", ""),
                "horizon": row.get("horizon", "weeks"),
                "evidence_ids": row.get("evidence_ids", []),
                "status": status,
                "user_action": row.get("user_action"),
                "rejection_reason": row.get("rejection_reason"),
                "paper": row.get("paper"),
            }
        )
        changed_rows += 1
    return changed_rows
