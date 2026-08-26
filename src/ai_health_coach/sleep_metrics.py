"""Supported sleep metrics, trust classes, and deterministic nightly selection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TrustClass = Literal["direct", "derived", "estimated"]

TRUST_FACTORS: dict[TrustClass, float] = {
    "direct": 1.0,
    "derived": 0.9,
    "estimated": 0.7,
}

AGGREGATION_SUM = "sum"
AGGREGATION_MEAN = "mean"


@dataclass(frozen=True, slots=True)
class SleepMetricDefinition:
    """One supported metric with its unit, aggregation, and provenance trust."""

    metric_type: str
    unit: str
    aggregation: str
    trust_class: TrustClass


SUPPORTED_SLEEP_METRICS: dict[str, SleepMetricDefinition] = {
    definition.metric_type: definition
    for definition in (
        SleepMetricDefinition("sleep_duration", "minutes", AGGREGATION_SUM, "direct"),
        SleepMetricDefinition("time_in_bed", "minutes", AGGREGATION_SUM, "direct"),
        SleepMetricDefinition("awakenings", "count", AGGREGATION_SUM, "direct"),
        SleepMetricDefinition(
            "stage_light_minutes", "minutes", AGGREGATION_SUM, "estimated"
        ),
        SleepMetricDefinition(
            "stage_deep_minutes", "minutes", AGGREGATION_SUM, "estimated"
        ),
        SleepMetricDefinition(
            "stage_rem_minutes", "minutes", AGGREGATION_SUM, "estimated"
        ),
        SleepMetricDefinition(
            "stage_awake_minutes", "minutes", AGGREGATION_SUM, "estimated"
        ),
        SleepMetricDefinition(
            "resting_heart_rate", "beats/minute", AGGREGATION_MEAN, "direct"
        ),
        SleepMetricDefinition(
            "heart_rate_variability", "milliseconds", AGGREGATION_MEAN, "direct"
        ),
        SleepMetricDefinition(
            "breathing_rate", "breaths/minute", AGGREGATION_MEAN, "direct"
        ),
        SleepMetricDefinition("spo2", "percent", AGGREGATION_MEAN, "direct"),
    )
}


def _row_field(row: Mapping[str, object] | object, key: str) -> object:
    if isinstance(row, Mapping):
        return row[key]
    if hasattr(row, key):
        return getattr(row, key)
    return row[key]  # type: ignore[index]


def aggregate_night_values(
    observations: Iterable[Mapping[str, object] | object],
    window_start: datetime,
    window_end: datetime,
) -> tuple[dict[str, float], dict[str, list[tuple[str, str]]]]:
    """Aggregate observations overlapping the night into one value per metric.

    An observation belongs to the night when its interval overlaps the half-open
    ``[window_start, window_end)`` interval. Missing-quality observations never
    contribute a value. Returns per-metric aggregated values and the
    provider-qualified provenance references backing each metric.
    """
    values: dict[str, list[float]] = {}
    references: dict[str, list[tuple[str, str]]] = {}
    for row in observations:
        quality_status = _row_field(row, "quality_status")
        raw_value = _row_field(row, "value")
        if quality_status == "missing" or raw_value is None:
            continue
        start = datetime.fromisoformat(str(_row_field(row, "interval_start")))
        end = datetime.fromisoformat(str(_row_field(row, "interval_end")))
        if end <= window_start or start >= window_end:
            continue
        metric_type = str(_row_field(row, "metric_type"))
        if metric_type not in SUPPORTED_SLEEP_METRICS:
            continue
        values.setdefault(metric_type, []).append(float(raw_value))
        references.setdefault(metric_type, []).append(
            (
                str(_row_field(row, "source")),
                str(_row_field(row, "source_observation_id")),
            )
        )

    aggregated: dict[str, float] = {}
    for metric_type, samples in values.items():
        definition = SUPPORTED_SLEEP_METRICS[metric_type]
        aggregated[metric_type] = (
            sum(samples)
            if definition.aggregation == AGGREGATION_SUM
            else sum(samples) / len(samples)
        )
    return aggregated, references
