"""Helpers shared by the provider adapters."""

from typing import Any

from tradecopilot_agent.state import EvidenceRecord
from tradecopilot_agent.store import now_iso
from tradecopilot_agent.tools import evidence_id


def record(
    tool: str,
    args: dict[str, Any],
    source: str,
    payload: dict[str, Any],
    *,
    url: str | None = None,
    published_at: str | None = None,
    stale: bool = False,
) -> EvidenceRecord:
    """Build one evidence record.

    Args:
        tool: Tool name the record serves.
        args: Normalized arguments.
        source: Provider name.
        payload: Trimmed fact.
        url: Human-readable source.
        published_at: Source timestamp.
        stale: Whether the record is too old.

    Returns:
        The record with a stable id.
    """
    return EvidenceRecord(
        id=evidence_id(tool, args, source, published_at),
        tool=tool,
        args=args,
        source=source,
        url=url,
        published_at=published_at,
        fetched_at=now_iso(),
        stale=stale,
        payload=payload,
    )
