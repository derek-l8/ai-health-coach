"""Daily feedback validation and prediction-order persistence coverage."""

from __future__ import annotations

import sqlite3
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime

import pytest

from ai_health_coach.sleep_context import NightlyScoringContext
from ai_health_coach.sleep_feedback import (
    DailySleepFeedback,
    SleepFeedbackValidationError,
)
from ai_health_coach.sleep_scores import ObservationReference, ScoreInput, SleepScore
from ai_health_coach.storage import (
    DuplicateSleepFeedbackConflictError,
    MissingEnergyPredictionError,
    ObservationStore,
)


def energy_score(score_id: str = "synthetic-energy-2024-03-10-v1") -> SleepScore:
    return SleepScore(
        score_id=score_id,
        score_type="energy",
        value=72,
        confidence=0.6,
        completeness=0.5,
        inputs=(
            ScoreInput(
                name="sleep_duration",
                value=420,
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
        limitations=("Synthetic contract test; no prediction formula applied.",),
        evidence=("synthetic-sleep-duration",),
        algorithm_version="energy-contract-v1",
        calibration_revision="population-default-v1",
        calculated_at=datetime.fromisoformat("2024-03-10T07:00:00-04:00"),
    )


def feedback(
    feedback_id: str = "synthetic-feedback-2024-03-10-v1",
    energy_score_id: str = "synthetic-energy-2024-03-10-v1",
) -> DailySleepFeedback:
    return DailySleepFeedback(
        feedback_id=feedback_id,
        energy_score_id=energy_score_id,
        local_date=date(2024, 3, 10),
        timezone="America/New_York",
        submitted_at=datetime.fromisoformat("2024-03-10T08:15:00-04:00"),
        perceived_energy=7,
        perceived_recovery=None,
        sleep_quality=8,
        note=None,
    )


def store_scoring_night(store: ObservationStore) -> None:
    energy = energy_score()
    efficiency = replace(
        energy,
        score_id="synthetic-efficiency-2024-03-10-v1",
        score_type="efficiency",
    )
    recovery = replace(
        energy,
        score_id="synthetic-recovery-2024-03-10-v1",
        score_type="recovery",
    )
    store.store_sleep_scores([efficiency, recovery, energy])
    store.store_nightly_contexts(
        [
            NightlyScoringContext(
                context_id="synthetic-night-2024-03-10-v1",
                local_date=date(2024, 3, 10),
                timezone="America/New_York",
                sleep_window_start=datetime.fromisoformat("2024-03-09T23:00:00-05:00"),
                sleep_window_end=datetime.fromisoformat("2024-03-10T06:30:00-04:00"),
                input_data_cutoff=datetime.fromisoformat("2024-03-10T07:00:00-04:00"),
                efficiency_score_id=efficiency.score_id,
                recovery_score_id=recovery.score_id,
                energy_score_id=energy.score_id,
            )
        ]
    )


def test_feedback_is_immutable_and_preserves_skipped_fields_as_none() -> None:
    result = feedback()

    assert result.perceived_energy == 7
    assert result.perceived_recovery is None
    assert result.note is None
    with pytest.raises(FrozenInstanceError):
        result.sleep_quality = 9  # type: ignore[misc]


def test_all_optional_feedback_fields_may_be_skipped() -> None:
    result = replace(feedback(), perceived_energy=None, sleep_quality=None, note=None)

    assert result.perceived_energy is None
    assert result.perceived_recovery is None
    assert result.sleep_quality is None
    assert result.note is None


@pytest.mark.parametrize(
    "field", ["perceived_energy", "perceived_recovery", "sleep_quality"]
)
@pytest.mark.parametrize("value", [0, 11, 1.5, True])
def test_feedback_rejects_values_outside_integer_scale(
    field: str, value: object
) -> None:
    with pytest.raises(SleepFeedbackValidationError, match="1 to 10"):
        replace(feedback(), **{field: value})


def test_feedback_rejects_timestamp_offset_that_contradicts_timezone() -> None:
    with pytest.raises(SleepFeedbackValidationError, match="contradicts"):
        replace(
            feedback(),
            submitted_at=datetime.fromisoformat("2024-03-10T08:15:00-05:00"),
        )


def test_feedback_requires_stored_energy_prediction() -> None:
    store = ObservationStore()

    with pytest.raises(MissingEnergyPredictionError, match="predicted Energy"):
        store.store_sleep_feedback([feedback()])

    assert store.all_sleep_feedback() == []


def test_non_energy_score_cannot_be_feedback_parent() -> None:
    store = ObservationStore()
    store.store_sleep_scores([replace(energy_score(), score_type="recovery")])

    with pytest.raises(MissingEnergyPredictionError, match="predicted Energy"):
        store.store_sleep_feedback([feedback()])


def test_database_gate_also_rejects_feedback_without_energy_prediction() -> None:
    store = ObservationStore()

    with pytest.raises(sqlite3.IntegrityError, match="predicted Energy"):
        store.connection.execute(
            """
            INSERT INTO daily_sleep_feedback (
                feedback_id, energy_score_id, local_date, timezone, submitted_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "synthetic-direct-feedback",
                "missing-energy-score",
                "2024-03-10",
                "America/New_York",
                "2024-03-10T08:15:00-04:00",
            ),
        )


def test_feedback_storage_is_idempotent_and_preserves_nulls() -> None:
    store = ObservationStore()
    prediction = energy_score()
    result = feedback()
    store_scoring_night(store)

    assert store.store_sleep_feedback([result]) == 1
    assert store.store_sleep_feedback([result]) == 0
    row = store.all_sleep_feedback()[0]

    assert row["energy_score_id"] == prediction.score_id
    assert row["local_date"] == "2024-03-10"
    assert row["timezone"] == "America/New_York"
    assert row["perceived_energy"] == 7
    assert row["perceived_recovery"] is None
    assert row["note"] is None


def test_feedback_date_and_timezone_must_match_energy_context() -> None:
    store = ObservationStore()
    store_scoring_night(store)

    with pytest.raises(MissingEnergyPredictionError, match="predicted Energy"):
        store.store_sleep_feedback([replace(feedback(), local_date=date(2024, 3, 11))])


def test_conflicting_feedback_replay_rolls_back_entire_batch() -> None:
    store = ObservationStore()
    store_scoring_night(store)
    original = feedback()
    store.store_sleep_feedback([original])
    second = feedback("synthetic-feedback-second")

    with pytest.raises(DuplicateSleepFeedbackConflictError, match="conflicting"):
        store.store_sleep_feedback([second, replace(original, perceived_energy=6)])

    assert [row["feedback_id"] for row in store.all_sleep_feedback()] == [
        original.feedback_id
    ]


def test_persisted_feedback_cannot_be_updated_in_place() -> None:
    store = ObservationStore()
    store_scoring_night(store)
    store.store_sleep_feedback([feedback()])

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.connection.execute("UPDATE daily_sleep_feedback SET perceived_energy = 6")

    assert store.all_sleep_feedback()[0]["perceived_energy"] == 7
