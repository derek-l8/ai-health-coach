"""Rolling-origin utilities, metrics, model arms, and leakage rejection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import timedelta

import pytest

from ai_health_coach.evaluation import (
    EvaluationError,
    FeatureValue,
    GoogleOnlyArm,
    HistoricalMedianArm,
    HybridArm,
    PersonalOnlyArm,
    RollingAverageArm,
    TemporalLeakageError,
    calibration_bins,
    mean_absolute_error,
    metric_report,
    rank_correlation,
    rolling_origin_predictions,
    rolling_origin_splits,
    within_one_point_accuracy,
)
from ai_health_coach.study_protocol import Target
from ai_health_coach.synthetic_study import generate_labeled_examples


@dataclass(frozen=True)
class _MeanPredictor:
    value: float

    def predict(self, features: Mapping[str, float]) -> float:
        assert features
        return self.value


@dataclass(frozen=True)
class _MeanTrainer:
    seen_columns: tuple[str, ...] = ()

    def fit(
        self,
        rows: Sequence[Mapping[str, float]],
        outcomes: Sequence[float],
    ) -> _MeanPredictor:
        assert rows
        assert len(rows) == len(outcomes)
        return _MeanPredictor(sum(outcomes) / len(outcomes))


def test_historical_baselines_and_google_arm_run_prospectively() -> None:
    examples = generate_labeled_examples()
    arms = (HistoricalMedianArm(), RollingAverageArm(window=7), GoogleOnlyArm())

    results = {
        arm.name: rolling_origin_predictions(
            examples,
            arm,
            minimum_training_rows=20,
        )
        for arm in arms
    }

    assert all(len(predictions) == 40 for predictions in results.values())
    assert results["historical_median"][0].example_id.endswith(
        Target.MORNING_READINESS.value
    )
    assert all(
        1 <= item.predicted <= 10 for items in results.values() for item in items
    )


def test_personal_and_hybrid_interfaces_fit_only_eligible_rows() -> None:
    examples = generate_labeled_examples()
    features = ("sleep_minutes", "sleep_efficiency", "academic_stress")
    personal = PersonalOnlyArm(
        trainer=_MeanTrainer(),
        feature_names=features,
        minimum_training_rows=20,
    )
    hybrid = HybridArm(
        trainer=_MeanTrainer(),
        feature_names=features,
        minimum_training_rows=20,
    )

    personal_predictions = rolling_origin_predictions(
        examples, personal, minimum_training_rows=20
    )
    hybrid_predictions = rolling_origin_predictions(
        examples, hybrid, minimum_training_rows=20
    )

    assert len(personal_predictions) == 40
    assert len(hybrid_predictions) == 40
    assert personal_predictions[0].predicted == hybrid_predictions[0].predicted


def test_late_feature_is_rejected_as_temporal_leakage() -> None:
    examples = list(generate_labeled_examples(count=25))
    original = examples[-1]
    leaked_feature = FeatureValue(
        name=original.features[0].name,
        value=original.features[0].value,
        available_at=original.prediction_cutoff + timedelta(minutes=1),
    )
    examples[-1] = replace(
        original,
        features=(leaked_feature, *original.features[1:]),
    )

    with pytest.raises(TemporalLeakageError, match="unavailable"):
        rolling_origin_splits(examples, minimum_training_rows=20)


def test_late_historical_label_is_not_in_training_window() -> None:
    examples = list(generate_labeled_examples(count=22))
    first = examples[0]
    examples[0] = replace(
        first,
        label_available_at=examples[-1].prediction_cutoff + timedelta(minutes=1),
    )

    splits = rolling_origin_splits(examples, minimum_training_rows=20)

    assert len(splits) == 1
    assert all(item.example_id != first.example_id for item in splits[0].training)


def test_metrics_handle_ties_coverage_and_calibration() -> None:
    predicted = [2.0, 4.0, 4.0, 8.0]
    observed = [1.0, 5.0, 4.0, 9.0]

    assert mean_absolute_error(predicted, observed) == pytest.approx(0.75)
    assert within_one_point_accuracy(predicted, observed) == 1.0
    assert rank_correlation(predicted, observed) == pytest.approx(0.9486832981)
    bins = calibration_bins(predicted, observed, bin_count=3)
    assert sum(item.count for item in bins) == 4


def test_metric_report_includes_eligible_coverage() -> None:
    examples = generate_labeled_examples()
    predictions = rolling_origin_predictions(
        examples,
        GoogleOnlyArm(),
        minimum_training_rows=20,
    )

    report = metric_report(predictions, eligible_count=40)

    assert report.count == 40
    assert report.coverage == 1.0
    assert report.mean_absolute_error >= 0
    assert report.calibration


def test_metric_inputs_reject_empty_or_mismatched_sequences() -> None:
    with pytest.raises(EvaluationError):
        mean_absolute_error([], [])
    with pytest.raises(EvaluationError):
        within_one_point_accuracy([1.0], [1.0, 2.0])
