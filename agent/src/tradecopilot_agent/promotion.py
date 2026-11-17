"""Profile suggestions derived from repeated rejection reasons.

Promotion is deterministic and read-only. It never writes the profile. The
interface shows the suggestions and the user accepts or dismisses each one,
so a wrong inference costs a dismissal rather than a silent constraint change.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

HORIZONS = ["intraday", "days", "weeks", "months"]
SIZE_TERMS = (
    "too big",
    "too large",
    "oversize",
    "position size",
    "allocation",
    "cap",
)
SHORT_TERMS = ("too short", "short-term", "intraday", "not enough time")
PROVIDER_SECTORS = (
    "Technology",
    "Healthcare",
    "Consumer Cyclical",
    "Financial Services",
    "Basic Materials",
    "Consumer Defensive",
    "Industrials",
    "Communication Services",
    "Energy",
    "Utilities",
    "Real Estate",
)
SECTOR_ALIASES = {
    "information technology": "Technology",
    "health care": "Healthcare",
    "consumer discretionary": "Consumer Cyclical",
    "financials": "Financial Services",
    "materials": "Basic Materials",
    "consumer staples": "Consumer Defensive",
}
WINDOW_DAYS = 90
MIN_MATCHES = 2
CAP_STEP = 2.0


@dataclass(frozen=True)
class _Rejection:
    """One rejected decision inside the promotion window."""

    decision: dict[str, Any]
    reason: str
    event: datetime


def _parse_time(value: Any) -> datetime | None:
    """Read an ISO timestamp as an aware datetime without raising.

    Args:
        value: Timestamp string or unusable value.

    Returns:
        The timestamp, or ``None`` when it cannot be read.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _event_time(decision: dict[str, Any]) -> datetime | None:
    """Return a decision's event time, falling back to its creation time."""
    return _parse_time(decision.get("updated_at")) or _parse_time(
        decision.get("created_at")
    )


def _mentions(text: str, term: str) -> bool:
    """Return whether a whole word or phrase appears in the lowercase text."""
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def _sectors_in(text: str) -> list[str]:
    """Return the provider sectors named by a rejection reason."""
    named = {
        provider for provider in PROVIDER_SECTORS if _mentions(text, provider.lower())
    }
    named.update(
        provider for alias, provider in SECTOR_ALIASES.items() if _mentions(text, alias)
    )
    return sorted(named)


def _rule_is_stale(profile_updated: datetime | None, matches: list[_Rejection]) -> bool:
    """Return whether the profile changed after the latest matching rejection."""
    if profile_updated is None or not matches:
        return False
    latest = max(match.event for match in matches)
    # Journal and profile timestamps have second precision. An edit in the
    # same second as the latest rejection cannot be ordered, so treat it as
    # later: the user has already acted on the pattern.
    return profile_updated >= latest


def _suggestion(
    key: str,
    kind: str,
    title: str,
    matches: list[_Rejection],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Build one suggestion payload."""
    ordered = sorted(matches, key=lambda match: match.event, reverse=True)
    return {
        "key": key,
        "kind": kind,
        "title": title,
        "rationale": (
            f'{len(matches)} recent rejections. Latest: "{ordered[0].reason[:120]}"'
        ),
        "patch": patch,
        "decision_ids": [str(match.decision.get("id")) for match in ordered],
    }


def derive_suggestions(
    decisions: list[dict[str, Any]],
    profile: dict[str, Any],
    dismissed: set[str],
    now: datetime,
) -> list[dict[str, Any]]:
    """Derive profile suggestions from rejection patterns.

    Args:
        decisions: Latest journal snapshot per decision.
        profile: Ground-truth profile.
        dismissed: Suggestion keys the user has dismissed.
        now: Current aware timestamp.

    Returns:
        Suggestions ordered cap, horizon, then sectors by name.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=UTC)
    window_start = now - timedelta(days=WINDOW_DAYS)
    profile_updated = _parse_time(profile.get("updated_at"))

    rejected: list[_Rejection] = []
    for decision in decisions:
        if decision.get("status") != "rejected":
            continue
        reason = str(decision.get("rejection_reason") or "").strip()
        event = _event_time(decision)
        if not reason or event is None:
            continue
        if event < window_start or event > now:
            continue
        rejected.append(_Rejection(decision=decision, reason=reason, event=event))

    suggestions: list[dict[str, Any]] = []

    size_matches = [
        match
        for match in rejected
        if any(_mentions(match.reason.lower(), term) for term in SIZE_TERMS)
    ]
    if len(size_matches) >= MIN_MATCHES and not _rule_is_stale(
        profile_updated, size_matches
    ):
        current = float(profile.get("position_cap_pct", 10.0))
        target = max(1.0, round(current - CAP_STEP, 2))
        key = f"cap_{target:g}"
        if current > target and key not in dismissed:
            suggestions.append(
                _suggestion(
                    key,
                    "cap",
                    f"Lower the position cap to {target:g}%",
                    size_matches,
                    {"position_cap_pct": target},
                )
            )

    short_matches = [
        match
        for match in rejected
        if any(_mentions(match.reason.lower(), term) for term in SHORT_TERMS)
    ]
    if len(short_matches) >= MIN_MATCHES and not _rule_is_stale(
        profile_updated, short_matches
    ):
        current_horizon = str(profile.get("horizon", "weeks"))
        index = (
            HORIZONS.index(current_horizon)
            if current_horizon in HORIZONS
            else HORIZONS.index("weeks")
        )
        if index + 1 < len(HORIZONS):
            horizon_target = HORIZONS[index + 1]
            key = f"horizon_{horizon_target}"
            if key not in dismissed:
                suggestions.append(
                    _suggestion(
                        key,
                        "horizon",
                        f"Lengthen the horizon to {horizon_target}",
                        short_matches,
                        {"horizon": horizon_target},
                    )
                )

    exclusions = {
        str(sector).strip().lower() for sector in profile.get("sector_exclusions", [])
    }
    by_sector: dict[str, list[_Rejection]] = {}
    for match in rejected:
        for sector in _sectors_in(match.reason.lower()):
            by_sector.setdefault(sector, []).append(match)
    for sector in sorted(by_sector):
        matches = by_sector[sector]
        key = "sector_" + sector.lower().replace(" ", "_")
        if (
            len(matches) < MIN_MATCHES
            or sector.lower() in exclusions
            or key in dismissed
            or _rule_is_stale(profile_updated, matches)
        ):
            continue
        suggestions.append(
            _suggestion(
                key,
                "sector",
                f"Exclude the {sector} sector",
                matches,
                {
                    "sector_exclusions": [
                        *profile.get("sector_exclusions", []),
                        sector,
                    ]
                },
            )
        )

    return suggestions
