"""Test blind review sampling, CSV ratings, and agreement without model calls."""

import asyncio
import csv
import math
from pathlib import Path

import pytest
from pydantic import ValidationError
from tradecopilot_eval.human import (
    HumanReview,
    ReviewItem,
    calculate_agreement,
    read_human_reviews,
    select_review_sample,
    write_review_csv,
)
from tradecopilot_eval.judge import (
    DIMENSIONS,
    JudgeConfig,
    JudgeInput,
    ScriptedJudgeTransport,
    judge_candidate,
)


def _items(count: int = 20) -> list[ReviewItem]:
    config = JudgeConfig(
        agent_model="scripted:agent",
        judge_model="scripted:judge",
        agent_family="scripted",
        judge_family="scripted",
        mode="scripted",
    )
    items = []
    for index in range(count):
        candidate = JudgeInput(
            sample_id=f"blind-{index:03d}",
            request="Should I add to this position?",
            decision_time="2026-09-15T14:00:00Z",
            profile={"position_cap_pct": 5},
            portfolio={"equity": 100000},
            journal_before_decision=[],
            reference_evidence=[{"id": "quote-1", "payload": {"price": 100}}],
            acceptance_criteria=["Respect the current cap."],
            final_response={"text": "More evidence is needed before buying."},
        )
        result = asyncio.run(
            judge_candidate(candidate, ScriptedJudgeTransport(), config)
        )
        items.append(
            ReviewItem(
                run_id=f"run-{index:03d}",
                condition=("none", "prose", "structured", "full")[index % 4],
                scenario_type=("earnings", "news", "portfolio")[index % 3],
                candidate=candidate,
                judge_result=result,
            )
        )
    return items


def test_sample_global_target_is_deterministic_and_balanced() -> None:
    """Round up once, cover available labels, and ignore input ordering."""
    items = _items()
    first = select_review_sample(items, seed=17)
    second = select_review_sample(list(reversed(items)), seed=17)
    assert first.base_target == math.ceil(len(items) * 0.2) == 4
    assert first.selected_count == 4
    assert first.model_dump() == second.model_dump()
    assert {item.condition for item in first.items} == {
        "none",
        "prose",
        "structured",
        "full",
    }
    assert {item.scenario_type for item in first.items} == {
        "earnings",
        "news",
        "portfolio",
    }
    assert first.scored_coverage == pytest.approx(0.2)
    small = select_review_sample(items[:5])
    assert small.base_target == small.selected_count == 1


def test_disputes_add_runs_without_changing_the_base_target() -> None:
    """Review disputed failures too and report the resulting actual coverage."""
    items = _items()
    items[-1].judge_result.status = "judge_error"
    items[-1].judge_result.scores = None
    items[-1].judge_result.error = "Injected test failure"
    base = select_review_sample(items, seed=3)
    sampled_ids = {item.run_id for item in base.items}
    extra = next(item for item in items[:-1] if item.run_id not in sampled_ids)
    sample = select_review_sample(
        items, seed=3, disputed_run_ids=[extra.run_id, items[-1].run_id]
    )
    assert sample.eligible_count == 19
    assert sample.base_target == 4
    assert sample.selected_count == 6 and sample.disputed_added_count == 2
    assert sample.scored_selected_count == 5
    assert sample.scored_coverage == pytest.approx(5 / 19)
    assert sample.reasons[items[-1].run_id] == ["disputed"]


def test_empty_and_invalid_sampling_inputs() -> None:
    """Handle empty runs and reject ambiguous IDs or unknown disputes."""
    empty = select_review_sample([])
    assert empty.items == [] and empty.scored_coverage is None
    items = _items(1)
    with pytest.raises(ValueError, match="unique"):
        select_review_sample(items + items)
    with pytest.raises(ValueError, match="disputed"):
        select_review_sample(items, disputed_run_ids=["missing"])
    with pytest.raises(ValueError, match="fraction"):
        select_review_sample(items, fraction=1.1)


def test_csv_is_blind_and_preserves_blank_ratings(tmp_path: Path) -> None:
    """Provide reference context without labels, prior scores, or invented ratings."""
    sample = select_review_sample(_items(1), fraction=1)
    path = tmp_path / "reviews.csv"
    write_review_csv(sample, path)
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        rows = list(reader)
    assert not {"condition", "model", "run_id", "judge_score", "judge_outcome"} & fields
    assert "position_cap_pct" in rows[0]["context_json"]
    assert "quote-1" in rows[0]["reference_evidence_json"]
    assert all(rows[0][dimension] == "" for dimension in DIMENSIONS)
    reviews = read_human_reviews(path)
    assert len(reviews) == 1
    assert all(score is None for score in reviews[0].scores.values())
    with pytest.raises(FileExistsError):
        write_review_csv(sample, path)


def test_partial_csv_and_invalid_ratings(tmp_path: Path) -> None:
    """Partial ratings remain partial; invalid cells fail with their row number."""
    sample = select_review_sample(_items(1), fraction=1)
    path = tmp_path / "reviews.csv"
    write_review_csv(sample, path)
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    rows[0].update({"reviewer": "reviewer-1", "reasoning": "4"})

    def save() -> None:
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    save()
    review = read_human_reviews(path)[0]
    assert review.scores["reasoning"] == 4
    assert review.scores["profile_fit"] is None
    rows[0]["reasoning"] = "4.0"
    save()
    with pytest.raises(ValueError, match="line 2"):
        read_human_reviews(path)


def test_agreement_uses_observed_pairs_and_reports_control_mode() -> None:
    """Keep judge failures and human omissions out of rates but in their counts."""
    items = _items(3)
    items[2].judge_result.status = "judge_error"
    items[2].judge_result.scores = None
    reviews = [
        HumanReview(
            sample_id=item.candidate.sample_id,
            reviewer="reviewer-1",
            scores={dimension: value for dimension in DIMENSIONS},
        )
        for item, value in zip(items, [5, 2, 3], strict=True)
    ]
    reviews[1].scores["reasoning"] = None
    report = calculate_agreement(items, reviews)
    evidence = report.dimensions["evidence_coverage"]
    assert evidence.pairs == 2 and evidence.judge_unscored == 1
    assert evidence.exact_agreement == 0
    assert evidence.within_one_agreement == 0.5
    assert evidence.mean_absolute_difference == 1.5
    reasoning = report.dimensions["reasoning"]
    assert reasoning.pairs == 1 and reasoning.human_missing == 1
    assert reasoning.mean_absolute_difference == 2
    assert report.comparison_kind == "scripted_control"
    assert report.review_rows == report.reviewed_samples == 3
    assert items[0].judge_result.scores is not None
    assert items[0].judge_result.scores["reasoning"].score == 3
    empty = calculate_agreement([], [])
    assert empty.comparison_kind == "empty"
    assert empty.dimensions["reasoning"].exact_agreement is None


def test_review_requires_valid_identity_and_scores() -> None:
    """Reject unknown samples, duplicate reviewers, and unlabelled scored rows."""
    items = _items(1)
    with pytest.raises(ValidationError, match="reviewer"):
        HumanReview(sample_id="blind-000", scores={name: 3 for name in DIMENSIONS})
    review = HumanReview(
        sample_id="unknown",
        reviewer="reviewer-1",
        scores={name: 3 for name in DIMENSIONS},
    )
    with pytest.raises(ValueError, match="unknown"):
        calculate_agreement(items, [review])
    review.sample_id = items[0].candidate.sample_id
    with pytest.raises(ValueError, match="duplicate"):
        calculate_agreement(items, [review, review])
