"""Nightly scoring identity, timing, and score-linkage coverage."""

from __future__ import annotations

import sqlite3
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime

import pytest

from ai_health_coach.sleep_context import (
    NightlyScoringContext,
    SleepContextValidationError,
)
from ai_health_coach.sleep_scores import ObservationReference, ScoreInput, SleepScore
from ai_health_coach.storage import (
    DuplicateSleepContextConflictError,
    InvalidSleepContextScoresError,
    ObservationStore,
)


def score(score_type: str) -> SleepScore:
    return SleepScore(
        score_id=f"synthetic-{score_type}-2024-03-10-v1",
        score_type=score_type,  # type: ignore[arg-type]
        value=70,
        confidence=0.6,
        completeness=0.5,
        inputs=(
            ScoreInput(
                name="sleep_duration",
                value=390,
                unit="min",
                observations=(
                    ObservationReference(
                        source="synthetic-google-health",
                        source_observation_id="synthetic-sleep-duration",
                    ),
                ),
            ),
        ),
        missing_inputs=("sleep_regularity",),
        limitations=("Synthetic contract test; no scoring formula applied.",),
        evidence=("synthetic-sleep-duration",),
        algorithm_version=f"{score_type}-contract-v1",
        calibration_revision="population-default-v1",
        calculated_at=datetime.fromisoformat("2024-03-10T07:00:00-04:00"),
    )


def context() -> NightlyScoringContext:
    return NightlyScoringContext(
        context_id="synthetic-night-2024-03-10-v1",
        local_date=date(2024, 3, 10),
        timezone="America/New_York",
        sleep_window_start=datetime.fromisoformat("2024-03-09T23:00:00-05:00"),
        sleep_window_end=datetime.fromisoformat("2024-03-10T06:30:00-04:00"),
        input_data_cutoff=datetime.fromisoformat("2024-03-10T07:00:00-04:00"),
        efficiency_score_id="synthetic-efficiency-2024-03-10-v1",
        recovery_score_id="synthetic-recovery-2024-03-10-v1",
        energy_score_id="synthetic-energy-2024-03-10-v1",
    )


def three_scores() -> list[SleepScore]:
    return [score("efficiency"), score("recovery"), score("energy")]


def test_context_is_immutable_and_preserves_dst_sleep_window() -> None:
    result = context()

    assert result.sleep_window_start.utcoffset() != result.sleep_window_end.utcoffset()
    assert result.local_date == date(2024, 3, 10)
    with pytest.raises(FrozenInstanceError):
        result.local_date = date(2024, 3, 11)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"sleep_window_end": datetime.fromisoformat("2024-03-10T06:30:00-05:00")},
            "contradicts",
        ),
        (
            {"input_data_cutoff": datetime.fromisoformat("2024-03-10T06:00:00-04:00")},
            "cannot precede",
        ),
        ({"local_date": date(2024, 3, 11)}, "sleep window end date"),
        (
            {"energy_score_id": "synthetic-recovery-2024-03-10-v1"},
            "distinct",
        ),
    ],
)
def test_context_rejects_invalid_timing_or_identity(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(SleepContextValidationError, match=message):
        replace(context(), **changes)


def test_context_storage_requires_all_three_correct_score_types() -> None:
    store = ObservationStore()
    scores = three_scores()
    store.store_sleep_scores([scores[0], scores[2]])

    with pytest.raises(InvalidSleepContextScoresError, match="correctly typed"):
        store.store_nightly_contexts([context()])

    assert store.all_nightly_contexts() == []


def test_database_gate_rejects_context_with_wrong_score_types() -> None:
    store = ObservationStore()
    scores = three_scores()
    store.store_sleep_scores(scores)

    with pytest.raises(sqlite3.IntegrityError, match="expected score types"):
        store.connection.execute(
            """
            INSERT INTO nightly_scoring_context (
                context_id, local_date, timezone, sleep_window_start,
                sleep_window_end, input_data_cutoff, efficiency_score_id,
                recovery_score_id, energy_score_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "synthetic-invalid-context",
                "2024-03-10",
                "America/New_York",
                "2024-03-09T23:00:00-05:00",
                "2024-03-10T06:30:00-04:00",
                "2024-03-10T07:00:00-04:00",
                scores[2].score_id,
                scores[1].score_id,
                scores[0].score_id,
            ),
        )


def test_context_rejects_score_calculated_before_input_cutoff() -> None:
    store = ObservationStore()
    scores = three_scores()
    scores[2] = replace(
        scores[2], calculated_at=datetime.fromisoformat("2024-03-10T06:59:00-04:00")
    )
    store.store_sleep_scores(scores)

    with pytest.raises(InvalidSleepContextScoresError, match="input data cutoff"):
        store.store_nightly_contexts([context()])


def test_context_storage_is_idempotent_and_preserves_separate_scores() -> None:
    store = ObservationStore()
    store.store_sleep_scores(three_scores())
    result = context()

    assert store.store_nightly_contexts([result]) == 1
    assert store.store_nightly_contexts([result]) == 0
    row = store.all_nightly_contexts()[0]

    assert row["efficiency_score_id"] != row["recovery_score_id"]
    assert row["recovery_score_id"] != row["energy_score_id"]
    assert row["sleep_window_start"] == "2024-03-09T23:00:00-05:00"
    assert row["sleep_window_end"] == "2024-03-10T06:30:00-04:00"


def test_reusing_one_score_in_another_context_is_a_conflict() -> None:
    store = ObservationStore()
    store.store_sleep_scores(three_scores())
    store.store_nightly_contexts([context()])

    with pytest.raises(DuplicateSleepContextConflictError, match="conflicting"):
        store.store_nightly_contexts(
            [replace(context(), context_id="synthetic-night-replay")]
        )


def test_persisted_context_cannot_be_updated_in_place() -> None:
    store = ObservationStore()
    store.store_sleep_scores(three_scores())
    store.store_nightly_contexts([context()])

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.connection.execute(
            "UPDATE nightly_scoring_context SET local_date = '2024-03-11'"
        )

    assert store.all_nightly_contexts()[0]["local_date"] == "2024-03-10"
