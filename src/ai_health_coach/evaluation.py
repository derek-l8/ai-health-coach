"""Prospective experiment arms, leakage guards, and evaluation metrics."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from ai_health_coach.study_protocol import Target


class EvaluationError(ValueError):
    """Raised when an evaluation would be invalid or misleading."""


class TemporalLeakageError(EvaluationError):
    """Raised when a feature or label was unavailable at prediction time."""


@dataclass(frozen=True, slots=True)
class FeatureValue:
    """A numeric feature paired with the first instant it was usable."""

    name: str
    value: float
    available_at: datetime

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise EvaluationError("feature name must be non-empty")
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise EvaluationError("feature value must be numeric")
        if not math.isfinite(float(self.value)):
            raise EvaluationError("feature value must be finite")
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise EvaluationError("feature available_at must be offset-aware")
        object.__setattr__(self, "value", float(self.value))


@dataclass(frozen=True, slots=True)
class LabeledExample:
    """One prospectively evaluable target and its cutoff-safe inputs."""

    example_id: str
    target: Target
    target_time: datetime
    label_available_at: datetime
    prediction_cutoff: datetime
    outcome: float
    features: tuple[FeatureValue, ...]
    google_prediction: float | None = None
    google_available_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.example_id.strip():
            raise EvaluationError("example_id must be non-empty")
        for field in ("target_time", "label_available_at", "prediction_cutoff"):
            value = getattr(self, field)
            if value.tzinfo is None or value.utcoffset() is None:
                raise EvaluationError(f"{field} must be offset-aware")
        if self.prediction_cutoff > self.target_time:
            raise EvaluationError("prediction_cutoff cannot follow target_time")
        if self.label_available_at < self.target_time:
            raise EvaluationError("label cannot be available before its target time")
        if isinstance(self.outcome, bool) or not isinstance(self.outcome, int | float):
            raise EvaluationError("outcome must be numeric")
        if not 1 <= float(self.outcome) <= 10:
            raise EvaluationError("outcome must be from 1 to 10")
        object.__setattr__(self, "outcome", float(self.outcome))

        names = [feature.name for feature in self.features]
        if len(names) != len(set(names)):
            raise EvaluationError("feature names must be unique")

        if self.google_prediction is None:
            if self.google_available_at is not None:
                raise EvaluationError(
                    "google_available_at requires a Google prediction"
                )
        else:
            if isinstance(self.google_prediction, bool) or not isinstance(
                self.google_prediction, int | float
            ):
                raise EvaluationError("google_prediction must be numeric")
            if not 1 <= float(self.google_prediction) <= 10:
                raise EvaluationError("google_prediction must be from 1 to 10")
            if self.google_available_at is None:
                raise EvaluationError("Google predictions require google_available_at")
            if (
                self.google_available_at.tzinfo is None
                or self.google_available_at.utcoffset() is None
            ):
                raise EvaluationError("google_available_at must be offset-aware")
            object.__setattr__(self, "google_prediction", float(self.google_prediction))


@dataclass(frozen=True, slots=True)
class Prediction:
    """One immutable arm prediction paired with its later outcome."""

    example_id: str
    target: Target
    arm_name: str
    predicted: float
    observed: float
    prediction_cutoff: datetime


@runtime_checkable
class ExperimentArm(Protocol):
    """A comparison arm that can be evaluated under rolling origin."""

    name: str

    def predict(
        self,
        training_examples: Sequence[LabeledExample],
        example: LabeledExample,
    ) -> float | None:
        """Predict one example using only the supplied historical records."""


def _clip_rating(value: float) -> float:
    if not math.isfinite(value):
        raise EvaluationError("prediction must be finite")
    return min(10.0, max(1.0, float(value)))


@dataclass(frozen=True, slots=True)
class HistoricalMedianArm:
    """Rolling historical median baseline."""

    name: str = "historical_median"

    def predict(
        self,
        training_examples: Sequence[LabeledExample],
        example: LabeledExample,
    ) -> float | None:
        outcomes = [
            item.outcome for item in training_examples if item.target is example.target
        ]
        if not outcomes:
            return None
        return float(statistics.median(outcomes))


@dataclass(frozen=True, slots=True)
class RollingAverageArm:
    """Mean of the most recent target-matched outcomes."""

    window: int = 7
    name: str = "rolling_average"

    def __post_init__(self) -> None:
        if self.window < 1:
            raise EvaluationError("rolling average window must be positive")

    def predict(
        self,
        training_examples: Sequence[LabeledExample],
        example: LabeledExample,
    ) -> float | None:
        outcomes = [
            item.outcome for item in training_examples if item.target is example.target
        ]
        if not outcomes:
            return None
        return float(statistics.fmean(outcomes[-self.window :]))


@dataclass(frozen=True, slots=True)
class GoogleOnlyArm:
    """Provider output used only when it was available by the cutoff."""

    name: str = "google_only"

    def predict(
        self,
        training_examples: Sequence[LabeledExample],
        example: LabeledExample,
    ) -> float | None:
        del training_examples
        if (
            example.google_prediction is None
            or example.google_available_at is None
            or example.google_available_at > example.prediction_cutoff
        ):
            return None
        return example.google_prediction


@runtime_checkable
class FittedPredictor(Protocol):
    """A fitted numeric predictor independent of a specific ML library."""

    def predict(self, features: Mapping[str, float]) -> float:
        """Return one numeric prediction."""


@runtime_checkable
class PredictorTrainer(Protocol):
    """A replaceable training interface for personal model arms."""

    def fit(
        self,
        rows: Sequence[Mapping[str, float]],
        outcomes: Sequence[float],
    ) -> FittedPredictor:
        """Fit only on the provided historical rows and outcomes."""


def _eligible_feature_map(
    example: LabeledExample, feature_names: tuple[str, ...]
) -> dict[str, float] | None:
    values = {
        feature.name: feature.value
        for feature in example.features
        if feature.available_at <= example.prediction_cutoff
    }
    if not all(name in values for name in feature_names):
        return None
    return {name: values[name] for name in feature_names}


@dataclass(frozen=True, slots=True)
class PersonalOnlyArm:
    """ML-library-neutral interface for a personal raw-feature model."""

    trainer: PredictorTrainer
    feature_names: tuple[str, ...]
    minimum_training_rows: int = 20
    name: str = "personal_only"

    def __post_init__(self) -> None:
        if not self.feature_names or len(self.feature_names) != len(
            set(self.feature_names)
        ):
            raise EvaluationError("personal feature names must be unique and non-empty")
        if self.minimum_training_rows < 1:
            raise EvaluationError("minimum_training_rows must be positive")

    def predict(
        self,
        training_examples: Sequence[LabeledExample],
        example: LabeledExample,
    ) -> float | None:
        test_row = _eligible_feature_map(example, self.feature_names)
        if test_row is None:
            return None

        rows: list[Mapping[str, float]] = []
        outcomes: list[float] = []
        for item in training_examples:
            if item.target is not example.target:
                continue
            row = _eligible_feature_map(item, self.feature_names)
            if row is not None:
                rows.append(row)
                outcomes.append(item.outcome)
        if len(rows) < self.minimum_training_rows:
            return None
        fitted = self.trainer.fit(rows, outcomes)
        return _clip_rating(fitted.predict(test_row))


@dataclass(frozen=True, slots=True)
class HybridArm:
    """Personal feature model with cutoff-eligible Google output added."""

    trainer: PredictorTrainer
    feature_names: tuple[str, ...]
    minimum_training_rows: int = 20
    name: str = "hybrid"

    def __post_init__(self) -> None:
        if not self.feature_names or len(self.feature_names) != len(
            set(self.feature_names)
        ):
            raise EvaluationError("hybrid feature names must be unique and non-empty")
        if self.minimum_training_rows < 1:
            raise EvaluationError("minimum_training_rows must be positive")

    def _row(self, example: LabeledExample) -> dict[str, float] | None:
        row = _eligible_feature_map(example, self.feature_names)
        if (
            row is None
            or example.google_prediction is None
            or example.google_available_at is None
            or example.google_available_at > example.prediction_cutoff
        ):
            return None
        return {**row, "google_prediction": example.google_prediction}

    def predict(
        self,
        training_examples: Sequence[LabeledExample],
        example: LabeledExample,
    ) -> float | None:
        test_row = self._row(example)
        if test_row is None:
            return None

        rows: list[Mapping[str, float]] = []
        outcomes: list[float] = []
        for item in training_examples:
            if item.target is not example.target:
                continue
            row = self._row(item)
            if row is not None:
                rows.append(row)
                outcomes.append(item.outcome)
        if len(rows) < self.minimum_training_rows:
            return None
        fitted = self.trainer.fit(rows, outcomes)
        return _clip_rating(fitted.predict(test_row))


def assert_no_feature_leakage(example: LabeledExample) -> None:
    """Reject any feature that became available after its prediction cutoff."""

    late = sorted(
        feature.name
        for feature in example.features
        if feature.available_at > example.prediction_cutoff
    )
    if late:
        raise TemporalLeakageError(f"features unavailable at prediction cutoff: {late}")


@dataclass(frozen=True, slots=True)
class RollingOriginSplit:
    """One prediction instant and its eligible historical training records."""

    training: tuple[LabeledExample, ...]
    test: LabeledExample


def rolling_origin_splits(
    examples: Sequence[LabeledExample],
    *,
    minimum_training_rows: int,
) -> tuple[RollingOriginSplit, ...]:
    """Create one-step expanding-window splits with label-availability checks."""

    if minimum_training_rows < 1:
        raise EvaluationError("minimum_training_rows must be positive")
    ordered = sorted(examples, key=lambda item: (item.target_time, item.example_id))
    splits: list[RollingOriginSplit] = []
    for index, test in enumerate(ordered):
        assert_no_feature_leakage(test)
        prior = ordered[:index]
        eligible = tuple(
            item
            for item in prior
            if item.target is test.target
            and item.label_available_at <= test.prediction_cutoff
        )
        if len(eligible) >= minimum_training_rows:
            splits.append(RollingOriginSplit(eligible, test))
    return tuple(splits)


def rolling_origin_predictions(
    examples: Sequence[LabeledExample],
    arm: ExperimentArm,
    *,
    minimum_training_rows: int,
) -> tuple[Prediction, ...]:
    """Evaluate an arm prospectively without random train/test mixing."""

    predictions: list[Prediction] = []
    for split in rolling_origin_splits(
        examples, minimum_training_rows=minimum_training_rows
    ):
        value = arm.predict(split.training, split.test)
        if value is None:
            continue
        predictions.append(
            Prediction(
                example_id=split.test.example_id,
                target=split.test.target,
                arm_name=arm.name,
                predicted=_clip_rating(value),
                observed=split.test.outcome,
                prediction_cutoff=split.test.prediction_cutoff,
            )
        )
    return tuple(predictions)


def mean_absolute_error(
    predictions: Sequence[float], observed: Sequence[float]
) -> float:
    """Return paired mean absolute error."""

    _validate_metric_inputs(predictions, observed)
    return statistics.fmean(
        abs(float(predicted) - float(actual))
        for predicted, actual in zip(predictions, observed, strict=True)
    )


def within_one_point_accuracy(
    predictions: Sequence[float], observed: Sequence[float]
) -> float:
    """Return the share of predictions within one rating point."""

    _validate_metric_inputs(predictions, observed)
    hits = sum(
        abs(float(predicted) - float(actual)) <= 1.0
        for predicted, actual in zip(predictions, observed, strict=True)
    )
    return hits / len(predictions)


def _average_ranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        average = ((start + 1) + end) / 2
        for position in range(start, end):
            ranks[ordered[position][0]] = average
        start = end
    return ranks


def rank_correlation(
    predictions: Sequence[float], observed: Sequence[float]
) -> float | None:
    """Return Spearman correlation with average ranks, or None if undefined."""

    _validate_metric_inputs(predictions, observed)
    predicted_ranks = _average_ranks([float(value) for value in predictions])
    observed_ranks = _average_ranks([float(value) for value in observed])
    predicted_mean = statistics.fmean(predicted_ranks)
    observed_mean = statistics.fmean(observed_ranks)
    numerator = sum(
        (left - predicted_mean) * (right - observed_mean)
        for left, right in zip(predicted_ranks, observed_ranks, strict=True)
    )
    left_scale = math.sqrt(
        sum((value - predicted_mean) ** 2 for value in predicted_ranks)
    )
    right_scale = math.sqrt(
        sum((value - observed_mean) ** 2 for value in observed_ranks)
    )
    if left_scale == 0 or right_scale == 0:
        return None
    return numerator / (left_scale * right_scale)


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    """Observed and predicted averages for one fixed-width prediction bin."""

    lower: float
    upper: float
    count: int
    mean_predicted: float
    mean_observed: float


def calibration_bins(
    predictions: Sequence[float],
    observed: Sequence[float],
    *,
    bin_count: int = 3,
    lower: float = 1.0,
    upper: float = 10.0,
) -> tuple[CalibrationBin, ...]:
    """Return non-empty fixed-width calibration bins on the rating scale."""

    _validate_metric_inputs(predictions, observed)
    if bin_count < 1 or upper <= lower:
        raise EvaluationError("calibration range and bin count are invalid")
    width = (upper - lower) / bin_count
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bin_count)]
    for predicted, actual in zip(predictions, observed, strict=True):
        predicted_value = float(predicted)
        if not lower <= predicted_value <= upper:
            raise EvaluationError("prediction is outside the calibration range")
        index = min(bin_count - 1, int((predicted_value - lower) / width))
        buckets[index].append((predicted_value, float(actual)))

    result: list[CalibrationBin] = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        result.append(
            CalibrationBin(
                lower=lower + index * width,
                upper=lower + (index + 1) * width,
                count=len(bucket),
                mean_predicted=statistics.fmean(item[0] for item in bucket),
                mean_observed=statistics.fmean(item[1] for item in bucket),
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class MetricReport:
    """Core metrics plus coverage for one comparison arm."""

    count: int
    coverage: float
    mean_absolute_error: float
    within_one_point_accuracy: float
    rank_correlation: float | None
    calibration: tuple[CalibrationBin, ...]


def metric_report(
    predictions: Sequence[Prediction], *, eligible_count: int
) -> MetricReport:
    """Summarize one arm without hiding its prediction coverage."""

    if eligible_count < 1 or len(predictions) > eligible_count:
        raise EvaluationError("eligible_count is invalid")
    if not predictions:
        raise EvaluationError("at least one prediction is required")
    predicted = [item.predicted for item in predictions]
    observed = [item.observed for item in predictions]
    return MetricReport(
        count=len(predictions),
        coverage=len(predictions) / eligible_count,
        mean_absolute_error=mean_absolute_error(predicted, observed),
        within_one_point_accuracy=within_one_point_accuracy(predicted, observed),
        rank_correlation=rank_correlation(predicted, observed),
        calibration=calibration_bins(predicted, observed),
    )


def _validate_metric_inputs(
    predictions: Sequence[float], observed: Sequence[float]
) -> None:
    if not predictions or len(predictions) != len(observed):
        raise EvaluationError("metric inputs must be non-empty paired sequences")
    for value in (*predictions, *observed):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise EvaluationError("metric inputs must be numeric")
        if not math.isfinite(float(value)):
            raise EvaluationError("metric inputs must be finite")
