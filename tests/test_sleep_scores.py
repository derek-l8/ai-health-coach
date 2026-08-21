"""Formula-neutral sleep-score contract and persistence coverage."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import FrozenInstanceError, replace
from datetime import datetime

import pytest

from ai_health_coach.sleep_scores import (
    ObservationReference,
    ScoreInput,
    SleepScore,
    SleepScoreValidationError,
)
from ai_health_coach.storage import (
    DuplicateSleepScoreConflictError,
    ObservationStore,
)


def score(
    score_id: str = "synthetic-efficiency-2024-03-10-v1",
    score_type: str = "efficiency",
) -> SleepScore:
    return SleepScore(
        score_id=score_id,
        score_type=score_type,  # type: ignore[arg-type]
        value=84,
        confidence=0.75,
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
        missing_inputs=("awakenings",),
        limitations=("Synthetic contract test; no scoring formula applied.",),
        evidence=("synthetic-sleep-duration",),
        algorithm_version="efficiency-contract-v1",
        calibration_revision="population-default-v1",
        calculated_at=datetime.fromisoformat("2024-03-10T08:00:00+00:00"),
    )


def test_score_is_immutable_and_preserves_missingness_and_provenance() -> None:
    result = score()

    assert result.value == 84.0
    assert result.inputs[0].value == 420.0
    assert result.inputs[0].observations == (
        ObservationReference(
            source="synthetic-google-health",
            source_observation_id="synthetic-sleep-duration",
        ),
    )
    assert result.missing_inputs == ("awakenings",)
    with pytest.raises(FrozenInstanceError):
        result.value = 90  # type: ignore[misc]


@pytest.mark.parametrize("score_type", ["efficiency", "recovery", "energy"])
def test_only_three_separate_score_types_are_supported(score_type: str) -> None:
    result = score(score_id=f"synthetic-{score_type}", score_type=score_type)

    assert result.score_type == score_type
    assert result.is_energy_prediction is (score_type == "energy")


def test_overall_composite_score_is_rejected() -> None:
    with pytest.raises(SleepScoreValidationError, match="score_type"):
        score(score_type="overall")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"value": -0.01}, "value"),
        ({"value": 100.01}, "value"),
        ({"confidence": float("nan")}, "confidence"),
        ({"completeness": 1.01}, "completeness"),
        ({"calculated_at": datetime(2024, 3, 10)}, "UTC offset"),
        ({"missing_inputs": ("sleep_duration",)}, "both contributing and missing"),
    ],
)
def test_score_rejects_invalid_boundaries(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(SleepScoreValidationError, match=message):
        replace(score(), **changes)


def test_zero_is_a_present_input_and_not_missing() -> None:
    zero = ScoreInput(
        name="awakenings",
        value=0,
        unit="count",
        observations=(
            ObservationReference(
                source="synthetic-google-health",
                source_observation_id="synthetic-awakenings",
            ),
        ),
    )
    result = replace(score(), inputs=(zero,), missing_inputs=("sleep_duration",))

    assert result.inputs[0].value == 0.0
    assert result.missing_inputs == ("sleep_duration",)


def test_sleep_score_storage_is_idempotent_and_preserves_snapshot() -> None:
    store = ObservationStore()
    result = score()

    assert store.store_sleep_scores([result]) == 1
    assert store.store_sleep_scores([result]) == 0
    row = store.all_sleep_scores()[0]

    assert row["score_type"] == "efficiency"
    assert row["calculated_at"] == "2024-03-10T08:00:00+00:00"
    assert json.loads(row["inputs_json"]) == [
        {
            "name": "sleep_duration",
            "value": 420.0,
            "unit": "min",
            "observations": [
                {
                    "source": "synthetic-google-health",
                    "source_observation_id": "synthetic-sleep-duration",
                }
            ],
        }
    ]
    assert json.loads(row["missing_inputs_json"]) == ["awakenings"]


def test_conflicting_score_replay_rolls_back_entire_batch() -> None:
    store = ObservationStore()
    original = score()
    second = score("synthetic-recovery", "recovery")
    store.store_sleep_scores([original])

    with pytest.raises(DuplicateSleepScoreConflictError, match="conflicting"):
        store.store_sleep_scores([second, replace(original, value=85)])

    assert [row["score_id"] for row in store.all_sleep_scores()] == [original.score_id]


def test_persisted_score_snapshot_cannot_be_updated_in_place() -> None:
    store = ObservationStore()
    store.store_sleep_scores([score()])

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.connection.execute("UPDATE sleep_score SET value = 85")

    assert store.all_sleep_scores()[0]["value"] == 84.0
