"""Profile suggestions derived from repeated rejection reasons."""

from datetime import UTC, datetime
from typing import Any

from tradecopilot_agent.promotion import derive_suggestions

NOW = datetime(2026, 11, 17, 12, tzinfo=UTC)


def _rejection(
    decision_id: str,
    reason: str,
    *,
    updated: str = "2026-11-10T10:00:00+00:00",
) -> dict[str, Any]:
    return {
        "id": decision_id,
        "status": "rejected",
        "user_action": "reject",
        "rejection_reason": reason,
        "updated_at": updated,
        "legs": [],
    }


def _profile(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "position_cap_pct": 10.0,
        "horizon": "weeks",
        "sector_exclusions": [],
        "updated_at": "2026-10-01T10:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def test_two_size_rejections_suggest_a_lower_cap() -> None:
    """Two size rejections propose a two point reduction."""
    suggestions = derive_suggestions(
        [
            _rejection("a", "Too large for my account"),
            _rejection("b", "Position size is too big"),
        ],
        _profile(),
        set(),
        NOW,
    )

    assert [(item["key"], item["kind"], item["patch"]) for item in suggestions] == [
        ("cap_8", "cap", {"position_cap_pct": 8.0})
    ]


def test_one_rejection_is_not_enough() -> None:
    """A single rejection does not form a pattern."""
    assert (
        derive_suggestions([_rejection("a", "Too large")], _profile(), set(), NOW) == []
    )


def test_a_later_profile_change_suppresses_the_rule() -> None:
    """A profile edit after the latest rejection mutes the rule."""
    profile = _profile(updated_at="2026-11-15T10:00:00+00:00")

    assert (
        derive_suggestions(
            [_rejection("a", "Too large"), _rejection("b", "Too big")],
            profile,
            set(),
            NOW,
        )
        == []
    )


def test_a_same_second_profile_change_suppresses_the_rule() -> None:
    """Timestamps have second precision, so an equal time counts as after."""
    profile = _profile(updated_at="2026-11-10T10:00:00+00:00")

    assert (
        derive_suggestions(
            [_rejection("a", "Too large"), _rejection("b", "Too big")],
            profile,
            set(),
            NOW,
        )
        == []
    )


def test_a_dismissed_key_is_suppressed() -> None:
    """A dismissed suggestion stays dismissed."""
    assert (
        derive_suggestions(
            [_rejection("a", "Too large"), _rejection("b", "Too big")],
            _profile(),
            {"cap_8"},
            NOW,
        )
        == []
    )


def test_a_satisfied_cap_is_suppressed() -> None:
    """A cap already at the floor needs no suggestion."""
    assert (
        derive_suggestions(
            [_rejection("a", "Too large"), _rejection("b", "Too big")],
            _profile(position_cap_pct=1.0),
            set(),
            NOW,
        )
        == []
    )


def test_a_gics_alias_maps_to_the_provider_value() -> None:
    """A GICS name is stored as the value the constraint check compares."""
    suggestions = derive_suggestions(
        [
            _rejection("a", "No health care exposure"),
            _rejection("b", "Avoid health care"),
        ],
        _profile(),
        set(),
        NOW,
    )

    assert suggestions[0]["key"] == "sector_healthcare"
    assert suggestions[0]["patch"] == {"sector_exclusions": ["Healthcare"]}


def test_the_horizon_ladder_stops_at_months() -> None:
    """The longest horizon has no step above it."""
    assert (
        derive_suggestions(
            [_rejection("a", "Too short-term"), _rejection("b", "Too short")],
            _profile(horizon="months"),
            set(),
            NOW,
        )
        == []
    )
