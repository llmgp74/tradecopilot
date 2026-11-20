"""Journal reconciliation against the broker's order state."""

from typing import Any

from tradecopilot_agent.reconcile import reconcile


class RecordingStore:
    """Collects appended journal snapshots."""

    def __init__(self) -> None:
        self.appended: list[dict[str, Any]] = []

    def append_journal(self, event: dict[str, Any]) -> None:
        """Record one snapshot."""
        self.appended.append(event)


def _row(status: str = "submitted") -> dict[str, Any]:
    return {
        "id": "ticket-1",
        "created_at": "2026-11-19T10:00:00Z",
        "updated_at": "2026-11-19T10:00:00Z",
        "legs": [
            {
                "ticker": "NVDA",
                "side": "buy",
                "qty": 5.0,
                "notional": 500.0,
                "fill_price": None,
                "fill_at": None,
                "status": status,
            }
        ],
        "thesis": "test",
        "horizon": "weeks",
        "evidence_ids": [],
        "status": status,
        "user_action": "approve",
        "rejection_reason": None,
    }


def test_a_later_fill_appends_a_new_snapshot() -> None:
    """A pending order that filled at the broker updates the journal row."""
    rows = [_row("pending_new")]
    store = RecordingStore()
    orders = {
        "ticket-1-0": {
            "order_id": "abc",
            "status": "filled",
            "fill_price": "101.25",
            "fill_at": "2026-11-19T14:31:00Z",
        }
    }

    changed = reconcile(rows, store, orders)

    assert changed == 1
    assert rows[0]["status"] == "filled"
    assert rows[0]["legs"][0]["status"] == "filled"
    assert rows[0]["legs"][0]["fill_price"] == "101.25"
    assert store.appended[0]["decision_id"] == "ticket-1"
    assert store.appended[0]["status"] == "filled"


def test_an_unchanged_leg_appends_nothing() -> None:
    """An order still pending leaves the stored snapshot alone."""
    rows = [_row("pending_new")]
    store = RecordingStore()
    orders = {
        "ticket-1-0": {
            "order_id": "abc",
            "status": "pending_new",
            "fill_price": None,
            "fill_at": None,
        }
    }

    changed = reconcile(rows, store, orders)

    assert changed == 0
    assert store.appended == []


def test_a_terminal_leg_is_not_queried_again() -> None:
    """A filled leg does not produce another snapshot on later reads."""
    rows = [_row("filled")]
    store = RecordingStore()

    changed = reconcile(rows, store, {})

    assert changed == 0
