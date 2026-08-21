"""Validated, formula-neutral contracts for deterministic sleep scores."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Literal

SleepScoreType = Literal["efficiency", "recovery", "energy"]


class SleepScoreValidationError(ValueError):
    """Raised when a sleep-score record would lose required meaning."""


def _non_empty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SleepScoreValidationError(f"{field} must be a non-empty string")
    return value


def _unique_strings(values: Iterable[str], field: str) -> tuple[str, ...]:
    result = tuple(values)
    for value in result:
        _non_empty(value, field)
    if len(set(result)) != len(result):
        raise SleepScoreValidationError(f"{field} cannot contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class ObservationReference:
    """The provider-qualified identity of one canonical observation."""

    source: str
    source_observation_id: str

    def __post_init__(self) -> None:
        _non_empty(self.source, "observation source")
        _non_empty(self.source_observation_id, "source observation identifier")


@dataclass(frozen=True, slots=True)
class ScoreInput:
    """One present input and the canonical observations supporting it."""

    name: str
    value: float
    unit: str
    observations: tuple[ObservationReference, ...]

    def __post_init__(self) -> None:
        _non_empty(self.name, "input name")
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise SleepScoreValidationError("input value must be a number")
        if not isfinite(self.value):
            raise SleepScoreValidationError("input value must be finite")
        _non_empty(self.unit, "input unit")
        observations = tuple(self.observations)
        if any(not isinstance(item, ObservationReference) for item in observations):
            raise SleepScoreValidationError(
                "observations must contain ObservationReference records"
            )
        if not observations:
            raise SleepScoreValidationError(
                "a contributing input requires an observation reference"
            )
        if len(set(observations)) != len(observations):
            raise SleepScoreValidationError(
                "observation references cannot contain duplicates"
            )
        object.__setattr__(self, "value", float(self.value))
        object.__setattr__(self, "observations", observations)


@dataclass(frozen=True, slots=True)
class SleepScore:
    """An immutable score snapshot, independent of display and interpretation."""

    score_id: str
    score_type: SleepScoreType
    value: float
    confidence: float
    completeness: float
    inputs: tuple[ScoreInput, ...]
    missing_inputs: tuple[str, ...]
    limitations: tuple[str, ...]
    evidence: tuple[str, ...]
    algorithm_version: str
    calibration_revision: str
    calculated_at: datetime

    def __post_init__(self) -> None:
        _non_empty(self.score_id, "score_id")
        if self.score_type not in {"efficiency", "recovery", "energy"}:
            raise SleepScoreValidationError(
                "score_type must be efficiency, recovery, or energy"
            )
        for field, value, upper in (
            ("value", self.value, 100.0),
            ("confidence", self.confidence, 1.0),
            ("completeness", self.completeness, 1.0),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise SleepScoreValidationError(f"{field} must be a number")
            if not isfinite(value) or not 0 <= value <= upper:
                raise SleepScoreValidationError(
                    f"{field} must be finite and between 0 and {upper:g}"
                )

        inputs = tuple(self.inputs)
        if any(not isinstance(item, ScoreInput) for item in inputs):
            raise SleepScoreValidationError("inputs must contain ScoreInput records")
        input_names = [item.name for item in inputs]
        if len(set(input_names)) != len(input_names):
            raise SleepScoreValidationError("input names cannot contain duplicates")

        missing_inputs = _unique_strings(self.missing_inputs, "missing input")
        if set(input_names) & set(missing_inputs):
            raise SleepScoreValidationError(
                "an input cannot be both contributing and missing"
            )
        limitations = _unique_strings(self.limitations, "limitation")
        evidence = _unique_strings(self.evidence, "evidence")
        _non_empty(self.algorithm_version, "algorithm_version")
        _non_empty(self.calibration_revision, "calibration_revision")
        if self.calculated_at.tzinfo is None or self.calculated_at.utcoffset() is None:
            raise SleepScoreValidationError("calculated_at must include a UTC offset")

        object.__setattr__(self, "value", float(self.value))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "completeness", float(self.completeness))
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(self, "missing_inputs", missing_inputs)
        object.__setattr__(self, "limitations", limitations)
        object.__setattr__(self, "evidence", evidence)

    @property
    def is_energy_prediction(self) -> bool:
        """Identify Energy as a prediction without conflating later feedback."""
        return self.score_type == "energy"
