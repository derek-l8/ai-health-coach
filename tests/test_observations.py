"""Synthetic-only schema and SQLite storage coverage."""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from ai_health_coach.observations import MetricObservation, ObservationValidationError
from ai_health_coach.storage import DuplicateObservationConflictError, ObservationStore

FIXTURE_PATH = Path("fixtures/synthetic/metric-observations.json")


def fixture_observations() -> list[MetricObservation]:
    return [
        MetricObservation.from_mapping(item)
        for item in json.loads(FIXTURE_PATH.read_text())
    ]


def test_schema_preserves_missing_partial_timezone_and_dst_data() -> None:
    complete, partial, missing = fixture_observations()

    assert complete.value == 58.0
    assert partial.quality_status == "partial"
    assert (
        partial.interval_end.utcoffset() - partial.interval_start.utcoffset()
        == timedelta(hours=1)
    )
    assert missing.value is None
    assert missing.unit is None
    assert missing.quality_status == "missing"
    assert missing.timezone == "America/New_York"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("interval_start", "2024-03-10T08:00:00", "UTC offset"),
        ("timezone", "Not/AZone", "IANA"),
        ("value", 0, "missing observations"),
    ],
)
def test_schema_rejects_invalid_boundary_values(
    field: str, value: object, message: str
) -> None:
    data = json.loads(FIXTURE_PATH.read_text())[2]
    data[field] = value

    with pytest.raises(ObservationValidationError, match=message):
        MetricObservation.from_mapping(data)


def test_ingestion_is_idempotent_and_preserves_nulls(tmp_path: Path) -> None:
    store = ObservationStore(tmp_path / "health-coach.sqlite3")
    observations = fixture_observations()

    assert store.ingest(observations) == 3
    assert store.ingest(observations) == 0
    rows = store.all_observations()

    assert len(rows) == 3
    assert rows[1]["interval_start"] == "2024-03-10T01:30:00-05:00"
    assert rows[1]["interval_end"] == "2024-03-10T03:30:00-04:00"
    assert rows[2]["value"] is None
    assert rows[2]["unit"] is None


def test_existing_database_adds_nullable_source_metadata_columns(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE metric_observation (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            source_observation_id TEXT NOT NULL,
            metric_type TEXT NOT NULL,
            interval_start TEXT NOT NULL,
            interval_end TEXT NOT NULL,
            value REAL,
            unit TEXT,
            timezone TEXT NOT NULL,
            quality_status TEXT NOT NULL,
            UNIQUE(source, source_observation_id)
        )
        """
    )
    connection.close()

    store = ObservationStore(database)

    columns = {
        row[1]
        for row in store.connection.execute("PRAGMA table_info(metric_observation)")
    }
    assert {
        "source_platform",
        "recording_method",
        "device_manufacturer",
        "device_display_name",
    } <= columns
    assert store.ingest([fixture_observations()[0]]) == 1
    row = store.all_observations()[0]
    assert row["source_platform"] is None
    assert row["recording_method"] is None
    assert row["device_manufacturer"] is None
    assert row["device_display_name"] is None


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf")])
def test_schema_rejects_non_finite_values_before_storage(invalid_value: float) -> None:
    data = json.loads(FIXTURE_PATH.read_text())[0]
    data["value"] = invalid_value

    with pytest.raises(ObservationValidationError, match="finite"):
        MetricObservation.from_mapping(data)


def test_schema_rejects_offset_that_contradicts_iana_zone() -> None:
    data = json.loads(FIXTURE_PATH.read_text())[1]
    data["interval_end"] = "2024-03-10T03:30:00-05:00"

    with pytest.raises(ObservationValidationError, match="contradicts"):
        MetricObservation.from_mapping(data)


def test_true_zero_is_distinct_from_missingness() -> None:
    data = json.loads(FIXTURE_PATH.read_text())[0]
    data["value"] = 0
    zero = MetricObservation.from_mapping(data)
    missing = fixture_observations()[2]

    assert zero.value == 0.0
    assert missing.value is None


def test_conflicting_delayed_observation_rolls_back_and_corrected_retry_succeeds() -> (
    None
):
    store = ObservationStore()
    first, second, _ = fixture_observations()
    conflicting_second_data = json.loads(FIXTURE_PATH.read_text())[1]
    conflicting_second_data["value"] = 61
    conflicting_second = MetricObservation.from_mapping(conflicting_second_data)

    assert store.ingest([first, second]) == 2
    with pytest.raises(DuplicateObservationConflictError, match="conflicting"):
        store.ingest([first, conflicting_second])

    assert len(store.all_observations()) == 2
    assert store.ingest([first, second]) == 0


def test_multi_step_insert_rolls_back_on_database_failure() -> None:
    store = ObservationStore()
    first, second, _ = fixture_observations()
    store.connection.execute(
        """
        CREATE TRIGGER reject_second_insert BEFORE INSERT ON metric_observation
        WHEN NEW.source_observation_id = 'sleep-duration-dst-2024-03-10'
        BEGIN SELECT RAISE(ABORT, 'synthetic write failure'); END;
        """
    )

    with pytest.raises(sqlite3.IntegrityError, match="synthetic write failure"):
        store.ingest([first, second])

    assert store.all_observations() == []
