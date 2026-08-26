"""Deterministic nightly scoring, baselines, sensitivity, and orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import pytest

from ai_health_coach.observations import MetricObservation
from ai_health_coach.provider_scores import (
    ProviderScoreComparison,
    ProviderScoreValidationError,
)
from ai_health_coach.sleep_metrics import aggregate_night_values
from ai_health_coach.sleep_scoring import (
    ALGORITHM_VERSIONS,
    PersonalBaseline,
    calculate_nightly_scores,
    calculate_score,
    component_scores,
    compute_baselines,
    next_calculation_index,
    run_nightly_calculation,
    weight_sensitivity_report,
)
from ai_health_coach.storage import (
    DuplicateProviderComparisonConflictError,
    ObservationStore,
)

NIGHT_FIXTURE_PATH = Path("fixtures/synthetic/sleep-night-observations.json")

WINDOW_START = datetime.fromisoformat("2024-03-09T23:00:00-05:00")
WINDOW_END = datetime.fromisoformat("2024-03-10T07:00:00-04:00")
CUTOFF = datetime.fromisoformat("2024-03-10T08:00:00-04:00")
CALCULATED_AT = datetime.fromisoformat("2024-03-10T08:05:00-04:00")
LOCAL_DATE = date(2024, 3, 10)


def nightly_rows() -> list[MetricObservation]:
    return [
        MetricObservation.from_mapping(item)
        for item in json.loads(NIGHT_FIXTURE_PATH.read_text(encoding="utf-8"))
    ]


def populated_store() -> ObservationStore:
    store = ObservationStore()
    store.ingest(nightly_rows())
    return store


def full_night_scores() -> tuple[object, object, object]:
    return calculate_nightly_scores(
        nightly_rows(),
        local_date=LOCAL_DATE,
        timezone="America/New_York",
        sleep_window_start=WINDOW_START,
        sleep_window_end=WINDOW_END,
        input_data_cutoff=CUTOFF,
        calculated_at=CALCULATED_AT,
    )


def test_full_synthetic_dst_night_produces_three_separate_scores() -> None:
    efficiency, recovery, energy = full_night_scores()

    assert [item.score_type for item in (efficiency, recovery, energy)] == [
        "efficiency",
        "recovery",
        "energy",
    ]
    for item in (efficiency, recovery, energy):
        assert 0 <= item.value <= 100
        assert 0 < item.completeness <= 1
        assert 0 < item.confidence <= 1
        assert item.calculated_at == CALCULATED_AT


def test_completeness_and_confidence_reflect_missing_and_estimated_inputs() -> None:
    _, recovery, energy = full_night_scores()

    assert recovery.missing_inputs == ("spo2",)
    assert recovery.completeness == pytest.approx(0.85)
    assert recovery.confidence == pytest.approx(0.835, abs=1e-6)
    assert energy.completeness == pytest.approx(1.0)
    assert energy.confidence == pytest.approx(0.955, abs=1e-6)


def test_missing_inputs_drop_weights_without_imputation() -> None:
    efficiency = calculate_score(
        "efficiency",
        {"sleep_duration": 420},
        {"sleep_duration": [("synthetic-google-health", "duration-id")]},
        PersonalBaseline(),
        local_date=LOCAL_DATE,
        calculated_at=CALCULATED_AT,
    )

    assert efficiency.value == pytest.approx(100.0)
    assert efficiency.inputs[0].name == "sleep_duration"
    assert efficiency.inputs[0].value == 420.0
    assert efficiency.inputs[0].unit == "minutes"
    assert set(efficiency.missing_inputs) == {"time_in_bed", "awakenings"}
    assert efficiency.completeness == pytest.approx(0.40)


def test_baseline_gated_inputs_are_missing_without_prior_history() -> None:
    rows = [
        row
        for row in nightly_rows()
        if row.metric_type not in {"resting_heart_rate", "heart_rate_variability"}
        or row.interval_start >= WINDOW_START
    ]
    scores = calculate_nightly_scores(
        rows,
        local_date=LOCAL_DATE,
        timezone="America/New_York",
        sleep_window_start=WINDOW_START,
        sleep_window_end=WINDOW_END,
        input_data_cutoff=CUTOFF,
        calculated_at=CALCULATED_AT,
    )
    recovery = scores[1]

    assert set(recovery.missing_inputs) >= {
        "resting_heart_rate",
        "heart_rate_variability",
    }


def test_compute_baselines_requires_minimum_samples() -> None:
    rows = nightly_rows()

    assert compute_baselines(rows, before=WINDOW_START).resting_heart_rate_mean == (
        pytest.approx(58.0)
    )
    sparse = [row for row in rows if row.source_observation_id != "hrv-2024-03-08"]
    assert (
        compute_baselines(sparse, before=WINDOW_START).heart_rate_variability_mean
        is None
    )


def test_stage_share_component_is_capped_for_wrist_estimates() -> None:
    values = {"stage_deep_minutes": 200, "sleep_duration": 400}

    assert component_scores("recovery", values, PersonalBaseline())[
        "stage_deep_minutes"
    ] == pytest.approx(100.0)


def test_aggregation_respects_half_open_dst_window() -> None:
    rows = [asdict(row) for row in nightly_rows()]

    values, references = aggregate_night_values(rows, WINDOW_START, WINDOW_END)

    assert values["sleep_duration"] == 380.0
    assert values["awakenings"] == 2.0
    assert references["sleep_duration"][0] == (
        "synthetic-google-health",
        "sleep-duration-2024-03-10",
    )


def test_late_arrival_creates_explicit_new_calculation_not_a_mutation() -> None:
    store = populated_store()
    first = run_nightly_calculation(
        store,
        local_date=LOCAL_DATE,
        timezone="America/New_York",
        sleep_window_start=WINDOW_START,
        sleep_window_end=WINDOW_END,
        input_data_cutoff=CUTOFF,
        calculated_at=CALCULATED_AT,
    )
    late_arrival = MetricObservation.from_mapping(
        {
            "source": "synthetic-google-health",
            "source_observation_id": "spo2-late-2024-03-10",
            "metric_type": "spo2",
            "interval_start": "2024-03-10T06:45:00-04:00",
            "interval_end": "2024-03-10T06:46:00-04:00",
            "value": 96,
            "unit": "percent",
            "timezone": "America/New_York",
            "quality_status": "complete",
        }
    )
    store.ingest([late_arrival])
    second = run_nightly_calculation(
        store,
        local_date=LOCAL_DATE,
        timezone="America/New_York",
        sleep_window_start=WINDOW_START,
        sleep_window_end=WINDOW_END,
        input_data_cutoff=datetime.fromisoformat("2024-03-11T08:00:00-04:00"),
        calculated_at=datetime.fromisoformat("2024-03-11T08:05:00-04:00"),
    )

    assert first["calculation_index"] == 1
    assert second["calculation_index"] == 2
    assert first["scores"][1]["missing_inputs"] == ["spo2"]
    assert second["scores"][1]["missing_inputs"] == []
    first_ids = {row["score_id"] for row in store.all_sleep_scores()}
    assert len(first_ids) == 6
    assert len(store.all_nightly_contexts()) == 2
    assert all(item["score_type"] != "overall" for item in second["scores"])


def test_identical_rerun_is_fully_idempotent() -> None:
    store = populated_store()
    arguments = {
        "local_date": LOCAL_DATE,
        "timezone": "America/New_York",
        "sleep_window_start": WINDOW_START,
        "sleep_window_end": WINDOW_END,
        "input_data_cutoff": CUTOFF,
        "calculated_at": CALCULATED_AT,
    }

    first = run_nightly_calculation(store, **arguments)
    second = run_nightly_calculation(store, **arguments)

    assert first["replayed"] is False
    assert second["replayed"] is True
    assert second["new_score_snapshots"] == 0
    assert len(store.all_sleep_scores()) == 3


@pytest.mark.parametrize(
    ("existing", "expected"),
    [
        ([], 1),
        (
            [
                "efficiency-2024-03-10-efficiency-heuristic-v1-c1",
                "energy-2024-03-10-energy-heuristic-v1-c1",
            ],
            2,
        ),
        (["efficiency-2024-03-09-efficiency-heuristic-v1-c3"], 1),
    ],
)
def test_next_calculation_index_counts_only_matching_nights(
    existing: list[str], expected: int
) -> None:
    assert next_calculation_index(existing, LOCAL_DATE) == expected


def test_sensitivity_report_varies_each_present_weight_symmetrically() -> None:
    efficiency, _, _ = full_night_scores()
    values, _ = aggregate_night_values(nightly_rows(), WINDOW_START, CALCULATED_AT)
    components = component_scores("efficiency", values, PersonalBaseline())

    report = weight_sensitivity_report("efficiency", components)

    assert report["base_value"] == pytest.approx(efficiency.value, abs=1e-5)
    assert len(report["variants"]) == 6
    for variant in report["variants"]:
        assert variant["direction"] in {"minus", "plus"}
        assert abs(variant["delta"]) < 5.0


def test_algorithm_versions_are_independently_versioned() -> None:
    assert len(set(ALGORITHM_VERSIONS.values())) == 3


def test_provider_comparison_storage_is_idempotent_and_immutable() -> None:
    import sqlite3

    store = ObservationStore()
    comparison = ProviderScoreComparison(
        comparison_id="fitbit-sleep-score-2024-03-10",
        provider="google-fitbit-air",
        score_label="Fitbit sleep score",
        value=81,
        unit="points",
        local_date=LOCAL_DATE,
        timezone="America/New_York",
        recorded_at=CALCULATED_AT,
    )

    assert store.store_provider_comparisons([comparison]) == 1
    assert store.store_provider_comparisons([comparison]) == 0

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.connection.execute("UPDATE provider_score_comparison SET value = 99")


def test_conflicting_provider_comparison_replay_is_rejected() -> None:
    store = ObservationStore()
    comparison = ProviderScoreComparison(
        comparison_id="fitbit-sleep-score-2024-03-10",
        provider="google-fitbit-air",
        score_label="Fitbit sleep score",
        value=81,
        unit="points",
        local_date=LOCAL_DATE,
        timezone="America/New_York",
        recorded_at=CALCULATED_AT,
    )
    store.store_provider_comparisons([comparison])

    conflicting = ProviderScoreComparison(
        comparison_id="fitbit-sleep-score-2024-03-10",
        provider="google-fitbit-air",
        score_label="Fitbit sleep score",
        value=82,
        unit="points",
        local_date=LOCAL_DATE,
        timezone="America/New_York",
        recorded_at=CALCULATED_AT,
    )

    with pytest.raises(DuplicateProviderComparisonConflictError, match="conflicting"):
        store.store_provider_comparisons([conflicting])


def test_null_provider_comparison_must_not_carry_a_unit() -> None:
    with pytest.raises(ProviderScoreValidationError, match="unit"):
        ProviderScoreComparison(
            comparison_id="unavailable",
            provider="google-fitbit-air",
            score_label="Fitbit sleep score",
            value=None,
            unit="points",
            local_date=LOCAL_DATE,
            timezone="America/New_York",
            recorded_at=CALCULATED_AT,
        )


def test_populated_store_round_trip_preserves_raw_input_values() -> None:
    store = populated_store()
    run_nightly_calculation(
        store,
        local_date=LOCAL_DATE,
        timezone="America/New_York",
        sleep_window_start=WINDOW_START,
        sleep_window_end=WINDOW_END,
        input_data_cutoff=CUTOFF,
        calculated_at=CALCULATED_AT,
    )
    recovery = next(
        row for row in store.all_sleep_scores() if row["score_type"] == "recovery"
    )
    inputs = json.loads(recovery["inputs_json"])
    by_name = {item["name"]: item for item in inputs}

    assert by_name["sleep_duration"]["value"] == 380.0
    assert by_name["sleep_duration"]["unit"] == "minutes"
    assert by_name["stage_deep_minutes"]["value"] == 85.0
    assert by_name["resting_heart_rate"]["observations"] == [
        {
            "source": "synthetic-google-health",
            "source_observation_id": "resting-heart-rate-night-2024-03-10",
        }
    ]
