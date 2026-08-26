"""Deterministic heuristic scoring for the three separate nightly sleep scores."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from ai_health_coach.storage import ObservationStore

from ai_health_coach.sleep_metrics import (
    SUPPORTED_SLEEP_METRICS,
    TRUST_FACTORS,
    _row_field,
    aggregate_night_values,
)
from ai_health_coach.sleep_scores import (
    ObservationReference,
    ScoreInput,
    SleepScore,
    SleepScoreValidationError,
)

HEURISTIC_LIMITATION = (
    "Coefficient magnitudes are labeled heuristics pending fitting or validation."
)
ESTIMATED_STAGE_LIMITATION = (
    "Wrist-estimated sleep-stage inputs reduce confidence because they are "
    "model estimates rather than direct measurements."
)

BASELINE_LOOKBACK_DAYS = 14
MINIMUM_BASELINE_SAMPLES = 3

ALGORITHM_VERSIONS: dict[str, str] = {
    "efficiency": "efficiency-heuristic-v1",
    "recovery": "recovery-heuristic-v1",
    "energy": "energy-heuristic-v1",
}

CALIBRATION_REVISION = "population-default-v1"

WEIGHTS: dict[str, dict[str, float]] = {
    "efficiency": {
        "sleep_duration": 0.40,
        "time_in_bed": 0.35,
        "awakenings": 0.25,
    },
    "recovery": {
        "sleep_duration": 0.30,
        "resting_heart_rate": 0.25,
        "heart_rate_variability": 0.20,
        "spo2": 0.15,
        "breathing_rate": 0.05,
        "stage_deep_minutes": 0.05,
    },
    "energy": {
        "sleep_duration": 0.35,
        "heart_rate_variability": 0.25,
        "resting_heart_rate": 0.15,
        "awakenings": 0.10,
        "stage_rem_minutes": 0.15,
    },
}

BASELINE_INPUT_REQUIREMENTS: dict[str, str] = {
    "resting_heart_rate": "resting_heart_rate",
    "heart_rate_variability": "heart_rate_variability",
}


class NightlyScoringError(ValueError):
    """Raised when a nightly calculation cannot produce meaningful scores."""


@dataclass(frozen=True, slots=True)
class PersonalBaseline:
    """Rolling personal means used instead of population constants."""

    resting_heart_rate_mean: float | None = None
    heart_rate_variability_mean: float | None = None


def _clip(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return min(max(value, lower), upper)


def compute_baselines(
    observations: Sequence[Mapping[str, object] | object],
    before: datetime,
    lookback_days: int = BASELINE_LOOKBACK_DAYS,
    minimum_samples: int = MINIMUM_BASELINE_SAMPLES,
) -> PersonalBaseline:
    """Average prior physiological samples strictly before the sleep window."""
    earliest = before - timedelta(days=lookback_days)
    samples: dict[str, list[float]] = {}
    for row in observations:
        metric_type = str(_row_field(row, "metric_type"))
        if metric_type not in BASELINE_INPUT_REQUIREMENTS.values():
            continue
        if _row_field(row, "quality_status") == "missing" or (
            _row_field(row, "value") is None
        ):
            continue
        interval_end = datetime.fromisoformat(str(_row_field(row, "interval_end")))
        if interval_end > before or interval_end <= earliest:
            continue
        samples.setdefault(metric_type, []).append(float(_row_field(row, "value")))

    def mean(metric_type: str) -> float | None:
        values = samples.get(metric_type, [])
        if len(values) < minimum_samples:
            return None
        return sum(values) / len(values)

    return PersonalBaseline(
        resting_heart_rate_mean=mean("resting_heart_rate"),
        heart_rate_variability_mean=mean("heart_rate_variability"),
    )


def _duration_adequacy(values: Mapping[str, float]) -> float | None:
    if "sleep_duration" not in values:
        return None
    return _clip(100.0 * min(values["sleep_duration"] / 420.0, 1.0))


def _consolidation(values: Mapping[str, float]) -> float | None:
    if "awakenings" not in values:
        return None
    return _clip(100.0 - 5.0 * values["awakenings"])


def _bed_rest_ratio(values: Mapping[str, float]) -> float | None:
    if "time_in_bed" not in values or "sleep_duration" not in values:
        return None
    if values["time_in_bed"] <= 0:
        return None
    return _clip(100.0 * values["sleep_duration"] / values["time_in_bed"])


def _baseline_deviation(
    values: Mapping[str, float],
    baseline_value: float | None,
    metric: str,
    slope_per_unit: float,
    neutral: float,
) -> float | None:
    if metric not in values or baseline_value is None:
        return None
    deviation = values[metric] - baseline_value
    return _clip(neutral + slope_per_unit * deviation)


def _capped_share(
    values: Mapping[str, float], stage_metric: str, reference_share: float
) -> float | None:
    if stage_metric not in values or "sleep_duration" not in values:
        return None
    if values["sleep_duration"] <= 0:
        return None
    share = values[stage_metric] / values["sleep_duration"]
    return _clip(100.0 * min(share, reference_share) / reference_share)


def component_scores(
    score_type: str,
    values: Mapping[str, float],
    baselines: PersonalBaseline,
) -> dict[str, float]:
    """Map nightly metric values to 0-100 sub-scores keyed by input name."""
    if score_type not in WEIGHTS:
        raise NightlyScoringError(f"unsupported score type {score_type}")
    components: dict[str, float] = {}
    for name in WEIGHTS[score_type]:
        component: float | None
        if name == "sleep_duration":
            component = _duration_adequacy(values)
        elif name == "awakenings":
            component = _consolidation(values)
        elif name == "time_in_bed":
            component = _bed_rest_ratio(values)
        elif name == "resting_heart_rate":
            component = _baseline_deviation(
                values, baselines.resting_heart_rate_mean, name, -2.5, 100.0
            )
        elif name == "heart_rate_variability":
            component = _baseline_deviation(
                values, baselines.heart_rate_variability_mean, name, 2.0, 50.0
            )
        elif name == "spo2":
            component = (
                None
                if "spo2" not in values
                else _clip(100.0 - 10.0 * max(95.0 - values["spo2"], 0.0))
            )
        elif name == "breathing_rate":
            component = (
                None
                if "breathing_rate" not in values
                else _clip(100.0 - 8.0 * max(values["breathing_rate"] - 16.0, 0.0))
            )
        elif name == "stage_deep_minutes":
            component = _capped_share(values, name, 0.22)
        elif name == "stage_rem_minutes":
            component = _capped_share(values, name, 0.25)
        else:  # pragma: no cover - guarded by WEIGHTS structure
            raise NightlyScoringError(f"unsupported scoring input {name}")
        if component is not None:
            components[name] = component
    return components


def _weighted_value(
    weights: Mapping[str, float], components: Mapping[str, float]
) -> float:
    total_weight = sum(weights[name] for name in components)
    if total_weight <= 0:
        raise NightlyScoringError("no contributing scoring inputs")
    return sum(weights[name] * components[name] for name in components) / total_weight


def completeness_and_confidence(
    score_type: str,
    components: Mapping[str, float],
) -> tuple[float, float]:
    """Completeness is retained weight mass; confidence discounts low trust."""
    weights = WEIGHTS[score_type]
    total_weight = sum(weights.values())
    present_weight = sum(weights[name] for name in components)
    completeness = present_weight / total_weight
    trust_mass = sum(
        weights[name]
        * TRUST_FACTORS[
            SUPPORTED_SLEEP_METRICS[
                BASELINE_INPUT_REQUIREMENTS.get(name, name)
            ].trust_class
        ]
        for name in components
    )
    confidence = completeness * (trust_mass / present_weight)
    return round(completeness, 6), round(confidence, 6)


def _missing_input_names(
    score_type: str,
    values: Mapping[str, float],
    baselines: PersonalBaseline,
) -> tuple[str, ...]:
    missing = []
    for name in WEIGHTS[score_type]:
        if name in ("sleep_duration", "time_in_bed", "awakenings"):
            if name not in values:
                missing.append(name)
        elif name in BASELINE_INPUT_REQUIREMENTS:
            if name not in values:
                missing.append(name)
            elif (
                baselines.resting_heart_rate_mean is None
                and name == "resting_heart_rate"
            ) or (
                baselines.heart_rate_variability_mean is None
                and name == "heart_rate_variability"
            ):
                missing.append(name)
        elif name not in values:
            missing.append(name)
    return tuple(missing)


def calculate_score(
    score_type: str,
    values: Mapping[str, float],
    references: Mapping[str, Sequence[tuple[str, str]]],
    baselines: PersonalBaseline,
    *,
    local_date: date,
    calculated_at: datetime,
    calculation_index: int = 1,
) -> SleepScore:
    """Compute one immutable score snapshot for one night and type."""
    algorithm_version = ALGORITHM_VERSIONS[score_type]
    components = component_scores(score_type, values, baselines)
    if not components:
        raise NightlyScoringError(
            f"{score_type} has no contributing inputs for {local_date}"
        )

    inputs = tuple(
        ScoreInput(
            name=name,
            value=values[name],
            unit=SUPPORTED_SLEEP_METRICS[name].unit,
            observations=tuple(
                ObservationReference(source=source, source_observation_id=identity)
                for source, identity in sorted(references.get(name, []))
            ),
        )
        for name in sorted(components)
    )
    for score_input in inputs:
        if not score_input.observations:
            raise SleepScoreValidationError(
                f"contributing input {score_input.name} lacks observation provenance"
            )

    completeness, confidence = completeness_and_confidence(score_type, components)
    limitations = [HEURISTIC_LIMITATION]
    if any(
        SUPPORTED_SLEEP_METRICS[BASELINE_INPUT_REQUIREMENTS.get(name, name)].trust_class
        == "estimated"
        for name in components
    ):
        limitations.append(ESTIMATED_STAGE_LIMITATION)
    evidence = [
        f"{name}={values[name]:g} {SUPPORTED_SLEEP_METRICS[name].unit}"
        for name in sorted(values)
    ]

    return SleepScore(
        score_id=(
            f"{score_type}-{local_date.isoformat()}-"
            f"{algorithm_version}-c{calculation_index}"
        ),
        score_type=score_type,  # type: ignore[arg-type]
        value=round(_weighted_value(WEIGHTS[score_type], components), 6),
        confidence=confidence,
        completeness=completeness,
        inputs=inputs,
        missing_inputs=_missing_input_names(score_type, values, baselines),
        limitations=tuple(limitations),
        evidence=tuple(evidence),
        algorithm_version=algorithm_version,
        calibration_revision=CALIBRATION_REVISION,
        calculated_at=calculated_at,
    )


def calculate_nightly_scores(
    observations: Sequence[Mapping[str, object]],
    *,
    local_date: date,
    timezone: str,
    sleep_window_start: datetime,
    sleep_window_end: datetime,
    input_data_cutoff: datetime,
    calculated_at: datetime,
    calculation_index: int = 1,
    baselines: PersonalBaseline | None = None,
) -> tuple[SleepScore, SleepScore, SleepScore]:
    """Produce Efficiency, Recovery, and predicted Energy for one night."""
    zone = ZoneInfo(timezone)
    values, references = aggregate_night_values(
        observations, sleep_window_start, input_data_cutoff
    )
    if baselines is None:
        baselines = compute_baselines(observations, sleep_window_start.astimezone(zone))
    return tuple(  # type: ignore[return-value]
        calculate_score(
            score_type,
            values,
            references,
            baselines,
            local_date=local_date,
            calculated_at=calculated_at,
            calculation_index=calculation_index,
        )
        for score_type in ("efficiency", "recovery", "energy")
    )


def next_calculation_index(existing_score_ids: Sequence[str], local_date: date) -> int:
    """Return the next explicit recalculation counter for a local date.

    Historical results are never silently recalculated; late arrivals create an
    explicitly numbered later calculation.
    """
    marker = f"-{local_date.isoformat()}-"
    highest = 0
    for score_id in existing_score_ids:
        if marker not in score_id:
            continue
        suffix = score_id.rsplit("-c", 1)[-1]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest + 1


def weight_sensitivity_report(
    score_type: str,
    components: Mapping[str, float],
    relative_delta: float = 0.3,
) -> dict[str, object]:
    """Report each present weight shifted ±relative_delta with renormalization."""
    if score_type not in WEIGHTS:
        raise NightlyScoringError(f"unsupported score type {score_type}")
    weights = WEIGHTS[score_type]
    base = round(_weighted_value(weights, components), 6)
    variants: list[dict[str, object]] = []
    for name in sorted(components):
        for direction in ("minus", "plus"):
            scaled = {
                other: weights[other]
                * (
                    1.0 - relative_delta
                    if other == name and direction == "minus"
                    else 1.0 + relative_delta
                    if other == name
                    else 1.0
                )
                for other in components
            }
            value = round(_weighted_value(scaled, components), 6)
            variants.append(
                {
                    "input": name,
                    "direction": direction,
                    "value": value,
                    "delta": round(value - base, 6),
                }
            )
    return {
        "score_type": score_type,
        "algorithm_version": ALGORITHM_VERSIONS[score_type],
        "base_value": base,
        "relative_delta": relative_delta,
        "variants": variants,
    }


def _score_ids_for(local_date: date, calculation_index: int) -> dict[str, str]:
    return {
        score_type: (
            f"{score_type}-{local_date.isoformat()}-"
            f"{ALGORITHM_VERSIONS[score_type]}-c{calculation_index}"
        )
        for score_type in ALGORITHM_VERSIONS
    }


def _resolve_calculation_index(
    store: ObservationStore,
    local_date: date,
    scores_by_index: dict[int, tuple[SleepScore, ...]],
) -> int:
    """Pick the first index that is either free or an exact stored replay."""
    from ai_health_coach.storage import ObservationStore

    candidate = 1
    while True:
        identifiers = list(_score_ids_for(local_date, candidate).values())
        rows = store.connection.execute(
            """
            SELECT score_id, score_type, value, confidence, completeness,
                   inputs_json, missing_inputs_json, limitations_json,
                   evidence_json, algorithm_version, calibration_revision,
                   calculated_at
            FROM sleep_score
            WHERE score_id IN (?, ?, ?)
            """,
            tuple(identifiers),
        ).fetchall()
        if len(rows) == 0:
            return candidate
        if len(rows) != 3:
            raise NightlyScoringError(
                f"partial nightly calculation state for {local_date} "
                f"calculation {candidate}"
            )
        computed = scores_by_index[candidate]
        stored = {row["score_id"]: row for row in rows}
        if all(
            all(
                stored[score.score_id][key] == value
                for key, value in ObservationStore._sleep_score_payload(score).items()
            )
            for score in computed
        ):
            return candidate
        candidate += 1


def run_nightly_calculation(
    store: ObservationStore,
    *,
    local_date: date,
    timezone: str,
    sleep_window_start: datetime,
    sleep_window_end: datetime,
    input_data_cutoff: datetime,
    calculated_at: datetime,
) -> dict[str, object]:
    """Calculate and transactionally store one explicit nightly calculation.

    Identical reruns replay idempotently under the same calculation counter.
    Late-arriving data never mutates history: the next counter produces
    distinct immutable snapshots and a new context.
    """
    from ai_health_coach.sleep_context import NightlyScoringContext

    base_arguments = {
        "local_date": local_date,
        "timezone": timezone,
        "sleep_window_start": sleep_window_start,
        "sleep_window_end": sleep_window_end,
        "input_data_cutoff": input_data_cutoff,
        "calculated_at": calculated_at,
    }
    observations = store.all_observations()
    highest_existing = (
        next_calculation_index(
            [row["score_id"] for row in store.all_sleep_scores()], local_date
        )
        - 1
    )
    scores_by_index = {
        index: calculate_nightly_scores(
            observations, **base_arguments, calculation_index=index
        )
        for index in range(1, max(highest_existing, 0) + 2)
    }
    calculation_index = _resolve_calculation_index(store, local_date, scores_by_index)
    scores = scores_by_index[calculation_index]
    context = NightlyScoringContext(
        context_id=f"night-{local_date.isoformat()}-c{calculation_index}",
        sleep_window_start=sleep_window_start,
        sleep_window_end=sleep_window_end,
        input_data_cutoff=input_data_cutoff,
        efficiency_score_id=scores[0].score_id,
        recovery_score_id=scores[1].score_id,
        energy_score_id=scores[2].score_id,
        **{
            key: value
            for key, value in base_arguments.items()
            if key in ("local_date", "timezone")
        },
    )
    stored_scores = store.store_sleep_scores(scores)
    stored_contexts = store.store_nightly_contexts([context])
    return {
        "context_id": context.context_id,
        "calculation_index": calculation_index,
        "new_score_snapshots": stored_scores,
        "replayed": stored_scores == 0 and stored_contexts == 0,
        "scores": [
            {
                "score_id": score.score_id,
                "score_type": score.score_type,
                "value": score.value,
                "confidence": score.confidence,
                "completeness": score.completeness,
                "missing_inputs": list(score.missing_inputs),
            }
            for score in scores
        ],
    }
