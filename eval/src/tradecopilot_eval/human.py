"""Select blind human reviews and compare independent ratings with judge scores."""

import csv
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from tradecopilot_eval.judge import (
    DIMENSIONS,
    RUBRIC_VERSION,
    Dimension,
    JudgeInput,
    JudgeResult,
)


class ReviewItem(BaseModel):
    """Run labels kept outside the blind packet, with its candidate and result."""

    model_config = ConfigDict(extra="forbid")
    run_id: str
    condition: str
    scenario_type: str
    candidate: JudgeInput
    judge_result: JudgeResult

    @model_validator(mode="after")
    def validate_sample_id(self) -> "ReviewItem":
        """Require the candidate and judge result to describe the same sample."""
        if self.candidate.sample_id != self.judge_result.sample_id:
            raise ValueError("Candidate and judge sample IDs differ.")
        return self


class ReviewSelection(BaseModel):
    """Internal sample manifest; CSV export removes labels and judge scores."""

    seed: int
    fraction: float
    eligible_count: int
    base_target: int
    selected_count: int
    scored_selected_count: int
    scored_coverage: float | None
    disputed_added_count: int
    reasons: dict[str, list[str]]
    strata: dict[str, dict[str, int]]
    items: list[ReviewItem]


def _validate_unique(items: list[ReviewItem]) -> None:
    if len({item.run_id for item in items}) != len(items):
        raise ValueError("Review run IDs must be unique.")
    if len({item.candidate.sample_id for item in items}) != len(items):
        raise ValueError("Blind sample IDs must be unique.")


def _stratum(item: ReviewItem) -> tuple[str, str]:
    return item.condition, item.scenario_type


def select_review_sample(
    items: list[ReviewItem],
    *,
    fraction: float = 0.2,
    seed: int = 0,
    disputed_run_ids: list[str] | None = None,
) -> ReviewSelection:
    """Select a fixed-size sample of scored runs, then add disputed runs.

    Args:
        items: All runs, including judge errors that may need disputed review.
        fraction: Global fraction of scored runs, rounded up once.
        seed: Repeatable tie-breaking seed, independent of input order.
        disputed_run_ids: Runs to include regardless of score availability.

    Returns:
        An internal manifest with actual coverage. Selection favors uncovered
        conditions and scenario types, then uncovered combined strata. A small
        target may not cover all strata; it is not enlarged to do so.

    Raises:
        ValueError: IDs are duplicated, a dispute is unknown, or fraction is invalid.
    """
    if not 0 <= fraction <= 1:
        raise ValueError("Review fraction must be between zero and one.")
    _validate_unique(items)
    lookup = {item.run_id: item for item in items}
    disputes = set(disputed_run_ids or [])
    if disputes - lookup.keys():
        raise ValueError("A disputed run ID is missing from the input records.")
    eligible = [
        item
        for item in items
        if item.judge_result.status == "ok" and item.judge_result.scores is not None
    ]
    target = math.ceil(len(eligible) * fraction)
    pool = sorted(eligible, key=lambda item: item.run_id)
    random.Random(seed).shuffle(pool)
    available = Counter(_stratum(item) for item in eligible)
    selected_strata: Counter[tuple[str, str]] = Counter()
    conditions: set[str] = set()
    scenario_types: set[str] = set()
    chosen: list[ReviewItem] = []

    def priority(item: ReviewItem) -> tuple[int, bool, float]:
        stratum = _stratum(item)
        coverage = int(item.condition not in conditions) + int(
            item.scenario_type not in scenario_types
        )
        return (
            coverage,
            selected_strata[stratum] == 0,
            available[stratum] * fraction - selected_strata[stratum],
        )

    while len(chosen) < target:
        next_item = max(pool, key=priority)
        pool.remove(next_item)
        chosen.append(next_item)
        conditions.add(next_item.condition)
        scenario_types.add(next_item.scenario_type)
        selected_strata[_stratum(next_item)] += 1
    sampled_ids = {item.run_id for item in chosen}
    additions = sorted(disputes - sampled_ids)
    chosen.extend(lookup[run_id] for run_id in additions)
    chosen.sort(key=lambda item: item.candidate.sample_id)
    selected_ids = {item.run_id for item in chosen}
    scored_count = sum(item.run_id in selected_ids for item in eligible)
    strata = {
        json.dumps(list(stratum)): {
            "eligible": count,
            "selected": sum(
                _stratum(item) == stratum and item.run_id in selected_ids
                for item in eligible
            ),
        }
        for stratum, count in sorted(available.items())
    }
    reasons = {
        item.run_id: (
            (["sampled"] if item.run_id in sampled_ids else [])
            + (["disputed"] if item.run_id in disputes else [])
        )
        for item in chosen
    }
    return ReviewSelection(
        seed=seed,
        fraction=fraction,
        eligible_count=len(eligible),
        base_target=target,
        selected_count=len(chosen),
        scored_selected_count=scored_count,
        scored_coverage=scored_count / len(eligible) if eligible else None,
        disputed_added_count=len(additions),
        reasons=reasons,
        strata=strata,
        items=chosen,
    )


def _csv_safe(value: str) -> str:
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_review_csv(selection: ReviewSelection, path: Path) -> None:
    """Write a blind rating form without condition labels or judge scores.

    Args:
        selection: Internal selection manifest.
        path: New CSV file. Existing human work is never overwritten.

    Raises:
        FileExistsError: The destination already exists.
        OSError: The file cannot be created.
    """
    fields = [
        "sample_id",
        "rubric_version",
        "reviewer",
        *DIMENSIONS,
        "notes",
        "request",
        "decision_time",
        "context_json",
        "reference_evidence_json",
        "acceptance_criteria_json",
        "final_response_json",
    ]
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in selection.items:
            candidate = item.candidate
            context = {
                "profile": candidate.profile,
                "portfolio": candidate.portfolio,
                "journal_before_decision": candidate.journal_before_decision,
            }
            row: dict[str, str] = {
                "sample_id": candidate.sample_id,
                "rubric_version": RUBRIC_VERSION,
                "reviewer": "",
                "notes": "",
                "request": candidate.request,
                "decision_time": candidate.decision_time,
                "context_json": json.dumps(context, ensure_ascii=True),
                "reference_evidence_json": json.dumps(candidate.reference_evidence),
                "acceptance_criteria_json": json.dumps(candidate.acceptance_criteria),
                "final_response_json": json.dumps(candidate.final_response),
                **{dimension: "" for dimension in DIMENSIONS},
            }
            writer.writerow({key: _csv_safe(value) for key, value in row.items()})


class HumanReview(BaseModel):
    """An independent human rating, including explicitly missing dimension scores."""

    model_config = ConfigDict(extra="forbid")
    sample_id: str = Field(min_length=1)
    reviewer: str = ""
    rubric_version: str = RUBRIC_VERSION
    scores: dict[Dimension, StrictInt | None]
    notes: str = ""

    @model_validator(mode="after")
    def validate_scores(self) -> "HumanReview":
        """Keep blank ratings as null and reject invalid scores or rubric versions."""
        if set(self.scores) != set(DIMENSIONS):
            raise ValueError("Human ratings need all five score columns.")
        if any(
            score is not None and not 1 <= score <= 5 for score in self.scores.values()
        ):
            raise ValueError("Human scores must be integers from 1 to 5 or blank.")
        if (
            any(score is not None for score in self.scores.values())
            and not self.reviewer.strip()
        ):
            raise ValueError("Completed scores need a reviewer name or identifier.")
        if self.rubric_version != RUBRIC_VERSION:
            raise ValueError("The human review uses a different rubric version.")
        return self


def read_human_reviews(path: Path) -> list[HumanReview]:
    """Read completed or partial rating forms without inventing missing scores.

    Args:
        path: CSV exported by write_review_csv and filled in by reviewers.

    Returns:
        One record per row, including untouched rows with null scores.

    Raises:
        ValueError: Required columns, IDs, reviewers, or scores are invalid.
        OSError: The file cannot be read.
    """
    reviews: list[HumanReview] = []
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"sample_id", "rubric_version", "reviewer", *DIMENSIONS, "notes"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError("The human review CSV is missing required columns.")
        for line, row in enumerate(reader, start=2):
            try:
                scores: dict[Dimension, int | None] = {}
                for dimension in DIMENSIONS:
                    value = (row[dimension] or "").strip()
                    if value and value not in {"1", "2", "3", "4", "5"}:
                        raise ValueError(f"Invalid {dimension} score.")
                    scores[dimension] = int(value) if value else None
                review = HumanReview(
                    sample_id=row["sample_id"],
                    reviewer=row["reviewer"].strip(),
                    rubric_version=row["rubric_version"],
                    scores=scores,
                    notes=row["notes"] or "",
                )
                key = review.sample_id, review.reviewer
                if key in seen:
                    raise ValueError("Duplicate sample and reviewer.")
                seen.add(key)
                reviews.append(review)
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError(
                    f"Invalid human review on CSV line {line}: {exc}"
                ) from exc
    return reviews


class DimensionAgreement(BaseModel):
    """Agreement counts and rates for one dimension, with explicit denominators."""

    pairs: int
    human_missing: int
    judge_unscored: int
    exact_agreement: float | None
    within_one_agreement: float | None
    mean_absolute_difference: float | None


class AgreementReport(BaseModel):
    """Human-versus-judge comparison; original ratings remain unchanged."""

    rubric_version: str = RUBRIC_VERSION
    review_rows: int
    reviewed_samples: int
    comparison_kind: Literal["model", "scripted_control", "mixed", "empty"]
    dimensions: dict[Dimension, DimensionAgreement]


def calculate_agreement(
    items: list[ReviewItem], reviews: list[HumanReview]
) -> AgreementReport:
    """Compare each human rating with its judge score, retaining missing counts.

    Args:
        items: Source runs used to identify judge scores and failures.
        reviews: Independent human ratings; multiple named reviewers are allowed.

    Returns:
        Per-dimension exact agreement, agreement within one point, and mean
        absolute difference. Each reviewer contributes one pair per scored item.

    Raises:
        ValueError: An input ID is duplicated or a review has no matching run.
    """
    _validate_unique(items)
    lookup = {item.candidate.sample_id: item for item in items}
    seen: set[tuple[str, str]] = set()
    for review in reviews:
        key = review.sample_id, review.reviewer
        if review.sample_id not in lookup or key in seen:
            raise ValueError(
                "Human review has an unknown sample or duplicate reviewer."
            )
        seen.add(key)
    dimensions: dict[Dimension, DimensionAgreement] = {}
    for dimension in DIMENSIONS:
        differences: list[int] = []
        human_missing = judge_unscored = 0
        for review in reviews:
            human_score = review.scores[dimension]
            result = lookup[review.sample_id].judge_result
            if human_score is None:
                human_missing += 1
            if result.status != "ok" or result.scores is None:
                judge_unscored += 1
            elif human_score is not None:
                differences.append(abs(human_score - result.scores[dimension].score))
        count = len(differences)
        dimensions[dimension] = DimensionAgreement(
            pairs=count,
            human_missing=human_missing,
            judge_unscored=judge_unscored,
            exact_agreement=sum(value == 0 for value in differences) / count
            if count
            else None,
            within_one_agreement=sum(value <= 1 for value in differences) / count
            if count
            else None,
            mean_absolute_difference=sum(differences) / count if count else None,
        )
    modes = {lookup[review.sample_id].judge_result.config.mode for review in reviews}
    kind: Literal["model", "scripted_control", "mixed", "empty"] = "empty"
    if modes == {"scripted"}:
        kind = "scripted_control"
    elif modes == {"model"}:
        kind = "model"
    elif modes:
        kind = "mixed"
    return AgreementReport(
        review_rows=len(reviews),
        reviewed_samples=len({review.sample_id for review in reviews}),
        comparison_kind=kind,
        dimensions=dimensions,
    )
