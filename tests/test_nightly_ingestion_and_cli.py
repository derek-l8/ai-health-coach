"""Coverage for sleep-metric raw-response points and the nightly scoring command."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from ai_health_coach.provider_ingestion import (
    RawResponseValidationError,
    SyntheticProviderIngestor,
)
from ai_health_coach.storage import ObservationStore


def data_source() -> dict[str, object]:
    return {
        "recordingMethod": "PASSIVELY_MEASURED",
        "platform": "FITBIT",
    }


def interval(start: str, end: str) -> dict[str, object]:
    return {
        "startTime": start,
        "startUtcOffset": "0s",
        "endTime": end,
        "endUtcOffset": "0s",
        "civilStartTime": {"date": {"year": 2024, "month": 3, "day": 10}, "time": {}},
        "civilEndTime": {
            "date": {"year": 2024, "month": 3, "day": 10},
            "time": {"hours": 7},
        },
    }


def sleep_metric_response() -> dict[str, object]:
    return {
        "dataPoints": [
            {
                "dataSource": data_source(),
                "metricType": "sleep_duration",
                "interval": interval(
                    "2024-03-10T00:00:00+00:00", "2024-03-10T07:00:00+00:00"
                ),
                "value": 380,
                "unit": "minutes",
            }
        ]
    }


def test_ingestion_accepts_supported_sleep_metric_points() -> None:
    store = ObservationStore()
    ingestor = SyntheticProviderIngestor(store)

    assert ingestor.ingest_raw_response(sleep_metric_response()) == 1
    row = store.all_observations()[0]

    assert row["metric_type"] == "sleep_duration"
    assert row["value"] == 380.0
    assert row["unit"] == "minutes"
    assert row["quality_status"] == "complete"
    assert row["source_observation_id"].startswith("generated-sleep_duration-")


def test_sleep_metric_ingestion_is_idempotent() -> None:
    store = ObservationStore()
    ingestor = SyntheticProviderIngestor(store)

    assert ingestor.ingest_raw_response(sleep_metric_response()) == 1
    assert ingestor.ingest_raw_response(sleep_metric_response()) == 0


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r["dataPoints"][0].__setitem__("unit", "seconds"), "unit must be"),
        (
            lambda r: r["dataPoints"][0].__setitem__("metricType", "mood"),
            "not a supported sleep metric",
        ),
        (
            lambda r: r["dataPoints"][0].__setitem__("value", "high"),
            "must be a number",
        ),
        (
            lambda r: (
                r["dataPoints"][0].__setitem__("value", None),
                r["dataPoints"][0].__setitem__("unit", "minutes"),
            ),
            "cannot accompany a missing value",
        ),
    ],
)
def test_sleep_metric_points_are_rejected_before_writes(
    mutate: object, message: str
) -> None:
    store = ObservationStore()
    response = sleep_metric_response()
    mutate(response)  # type: ignore[operator]

    with pytest.raises(RawResponseValidationError, match=message):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


def test_missing_sleep_metric_value_maps_to_explicit_missingness() -> None:
    store = ObservationStore()
    response = sleep_metric_response()
    point = response["dataPoints"][0]
    assert isinstance(point, dict)
    point["value"] = None
    del point["unit"]

    SyntheticProviderIngestor(store).ingest_raw_response(response)

    row = store.all_observations()[0]
    assert row["value"] is None
    assert row["unit"] is None
    assert row["quality_status"] == "missing"


def test_synthetic_score_night_command_runs_end_to_end() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ai_health_coach", "--synthetic-score-night"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["mode"] == "synthetic-score-night"
    assert summary["private_data_accessed"] is False
    assert summary["calculation_index"] == 1
    assert [item["score_type"] for item in summary["scores"]] == [
        "efficiency",
        "recovery",
        "energy",
    ]
    recovery = next(
        item for item in summary["scores"] if item["score_type"] == "recovery"
    )
    assert recovery["missing_inputs"] == ["spo2"]
    assert 0 <= recovery["value"] <= 100
