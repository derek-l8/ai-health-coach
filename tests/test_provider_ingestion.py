"""Synthetic-only coverage for the strict Google Health raw-response boundary."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from ai_health_coach.provider_ingestion import (
    RawResponseValidationError,
    SyntheticProviderIngestor,
    half_open_local_day_window,
)
from ai_health_coach.storage import DuplicateObservationConflictError, ObservationStore

FIXTURE_PATH = Path("fixtures/synthetic/google-health-raw-response.json")
DST_FIXTURE_PATH = Path("fixtures/synthetic/google-health-steps-dst-response.json")


def raw_response() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_ingestion_accepts_documented_nested_steps_list_response() -> None:
    store = ObservationStore()

    assert SyntheticProviderIngestor(store).ingest_raw_response(raw_response()) == 2
    rows = store.all_observations()

    assert rows[0]["metric_type"] == "steps"
    assert rows[0]["value"] == 40.0
    assert rows[0]["timezone"] == "UTC"
    assert rows[0]["source_platform"] == "FITBIT"
    assert rows[0]["recording_method"] == "PASSIVELY_MEASURED"
    assert rows[0]["source_observation_id"].startswith("generated-steps-")
    assert rows[1]["value"] == 0.0


def test_ingestion_is_idempotent_for_a_replayed_documented_page() -> None:
    store = ObservationStore()
    ingestor = SyntheticProviderIngestor(store)
    response = raw_response()

    assert ingestor.ingest_raw_response(response) == 2
    assert ingestor.ingest_raw_response(response) == 0


def test_generated_identity_uses_absolute_instants_not_timestamp_spelling() -> None:
    store = ObservationStore()
    ingestor = SyntheticProviderIngestor(store)
    response = raw_response()

    assert ingestor.ingest_raw_response(response) == 2
    assert store.all_observations()[0]["source_observation_id"] == (
        "generated-steps-"
        "9cedd6de8ed5afa8918fc18196a63300ee6bf6a47768d7a7d76a956182e50184"
    )
    equivalent = raw_response()
    interval = equivalent["dataPoints"][0]["steps"]["interval"]
    interval["startTime"] = "2024-03-09T18:00:00-05:00"
    interval["endTime"] = "2024-03-09T18:01:00-05:00"

    assert ingestor.ingest_raw_response(equivalent) == 0


def test_changed_count_for_generated_identity_is_a_conflict() -> None:
    store = ObservationStore()
    ingestor = SyntheticProviderIngestor(store)
    response = raw_response()

    assert ingestor.ingest_raw_response(response) == 2
    response["dataPoints"][0]["steps"]["count"] = "41"

    with pytest.raises(DuplicateObservationConflictError, match="conflicting"):
        ingestor.ingest_raw_response(response)

    assert [row["value"] for row in store.all_observations()] == [40.0, 0.0]


def test_populated_supported_device_metadata_remains_narrowly_supported() -> None:
    response = raw_response()
    for index, point in enumerate(response["dataPoints"]):
        point["name"] = f"synthetic-legacy-step-{index}"
        point["dataSource"]["device"] = {
            "manufacturer": "Synthetic",
            "displayName": "Synthetic tracker",
        }
    store = ObservationStore()

    assert SyntheticProviderIngestor(store).ingest_raw_response(response) == 2
    assert [row["source_observation_id"] for row in store.all_observations()] == [
        "synthetic-legacy-step-0",
        "synthetic-legacy-step-1",
    ]
    assert [
        (row["device_manufacturer"], row["device_display_name"])
        for row in store.all_observations()
    ] == [
        ("Synthetic", "Synthetic tracker"),
        ("Synthetic", "Synthetic tracker"),
    ]


def test_equivalent_device_provenance_replay_is_idempotent() -> None:
    response = raw_response()
    response["dataPoints"][0]["dataSource"]["device"] = {
        "manufacturer": "Synthetic",
        "displayName": "Synthetic tracker",
    }
    store = ObservationStore()
    ingestor = SyntheticProviderIngestor(store)

    assert ingestor.ingest_raw_response(response) == 2
    assert ingestor.ingest_raw_response(response) == 0


def test_differing_device_provenance_has_distinct_generated_identity() -> None:
    first = raw_response()
    first["dataPoints"] = [first["dataPoints"][0]]
    first["dataPoints"][0]["dataSource"]["device"] = {
        "manufacturer": "Synthetic",
        "displayName": "Tracker A",
    }
    second = raw_response()
    second["dataPoints"] = [second["dataPoints"][0]]
    second["dataPoints"][0]["dataSource"]["device"] = {
        "manufacturer": "Synthetic",
        "displayName": "Tracker B",
    }
    store = ObservationStore()
    ingestor = SyntheticProviderIngestor(store)

    assert ingestor.ingest_raw_response(first) == 1
    assert ingestor.ingest_raw_response(second) == 1
    rows = store.all_observations()
    assert rows[0]["source_observation_id"] != rows[1]["source_observation_id"]


def test_changed_device_provenance_for_explicit_identifier_is_a_conflict() -> None:
    first = raw_response()
    first["dataPoints"] = [first["dataPoints"][0]]
    first["dataPoints"][0]["name"] = "explicit-step-id"
    first["dataPoints"][0]["dataSource"]["device"] = {
        "manufacturer": "Synthetic",
        "displayName": "Tracker A",
    }
    second = raw_response()
    second["dataPoints"] = [second["dataPoints"][0]]
    second["dataPoints"][0]["name"] = "explicit-step-id"
    second["dataPoints"][0]["dataSource"]["device"] = {
        "manufacturer": "Synthetic",
        "displayName": "Tracker B",
    }
    store = ObservationStore()
    ingestor = SyntheticProviderIngestor(store)

    assert ingestor.ingest_raw_response(first) == 1
    with pytest.raises(DuplicateObservationConflictError, match="conflicting"):
        ingestor.ingest_raw_response(second)

    assert store.all_observations()[0]["device_display_name"] == "Tracker A"


def test_empty_device_object_is_valid_without_synthesizing_metadata() -> None:
    response = raw_response()
    response["dataPoints"][0]["dataSource"]["device"] = {}
    store = ObservationStore()

    assert SyntheticProviderIngestor(store).ingest_raw_response(response) == 2
    assert response["dataPoints"][0]["dataSource"]["device"] == {}


@pytest.mark.parametrize(
    "device",
    [
        {"manufacturer": "Synthetic"},
        {"displayName": "Synthetic tracker"},
    ],
)
def test_independently_optional_supported_device_metadata_is_valid(
    device: dict[str, str],
) -> None:
    response = raw_response()
    response["dataPoints"][0]["dataSource"]["device"] = device
    store = ObservationStore()

    assert SyntheticProviderIngestor(store).ingest_raw_response(response) == 2
    assert response["dataPoints"][0]["dataSource"]["device"] == device


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manufacturer", ""),
        ("manufacturer", "  "),
        ("displayName", ""),
        ("displayName", "  "),
    ],
)
def test_device_rejects_blank_supported_fields_before_writing(
    field: str, value: str
) -> None:
    response = raw_response()
    response["dataPoints"][0]["dataSource"]["device"] = {field: value}
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError, match=f"device.{field}"):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


def test_device_rejects_unknown_fields_without_writing() -> None:
    response = raw_response()
    response["dataPoints"][0]["dataSource"]["device"] = {
        "manufacturer": "Synthetic",
        "formFactor": "FITNESS_BAND",
    }
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError, match="device"):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


@pytest.mark.parametrize("device", [None, [], "Synthetic tracker", 7])
def test_device_rejects_non_object_values_without_writing(device: object) -> None:
    response = raw_response()
    response["dataPoints"][0]["dataSource"]["device"] = device
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError, match="device must be an object"):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manufacturer", None),
        ("manufacturer", True),
        ("manufacturer", 7),
        ("displayName", []),
        ("displayName", {}),
    ],
)
def test_device_rejects_non_string_supported_field_values_without_writing(
    field: str, value: object
) -> None:
    response = raw_response()
    response["dataPoints"][0]["dataSource"]["device"] = {field: value}
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError, match=f"device.{field}"):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda response: response.__setitem__("nextPageToken", 2), "nextPageToken"),
        (
            lambda response: response.__setitem__("nextPageToken", None),
            "nextPageToken",
        ),
        (lambda response: response.__setitem__("unexpected", "field"), "raw response"),
        (
            lambda response: response["dataPoints"][0]["steps"].__setitem__(
                "unexpected", "field"
            ),
            "steps must contain only",
        ),
        (
            lambda response: response["dataPoints"][0]["steps"]["interval"].pop(
                "civilEndTime"
            ),
            "interval must contain only",
        ),
        (
            lambda response: response["dataPoints"][0]["dataSource"].__setitem__(
                "unexpected", "field"
            ),
            "dataSource must contain required fields only",
        ),
        (
            lambda response: response["dataPoints"][0]["steps"].__setitem__(
                "count", "not-a-count"
            ),
            "count",
        ),
    ],
)
def test_ingestion_rejects_unknown_or_malformed_nested_data_without_writing(
    change: object, message: str
) -> None:
    response = raw_response()
    change(response)
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError, match=message):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


@pytest.mark.parametrize(
    "count",
    [None, 7, -1, "", "-1", "+1", "1.5", " 1", "1 ", "١", str(2**53 + 1)],
)
def test_steps_count_requires_an_exact_non_negative_ascii_integer_string(
    count: object,
) -> None:
    response = raw_response()
    response["dataPoints"][0]["steps"]["count"] = count
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError, match="steps.count"):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


def test_steps_count_accepts_largest_exact_canonical_integer() -> None:
    response = raw_response()
    response["dataPoints"][0]["steps"]["count"] = str(2**53)
    store = ObservationStore()

    assert SyntheticProviderIngestor(store).ingest_raw_response(response) == 2
    assert store.all_observations()[0]["value"] == float(2**53)


@pytest.mark.parametrize(
    ("time_shape", "hour", "minute"),
    [
        ({}, 0, 0),
        ({"hours": 5}, 5, 0),
        ({"minutes": 7}, 0, 7),
        ({"hours": 5, "minutes": 7}, 5, 7),
    ],
    ids=["empty", "hours-only", "minutes-only", "hours-and-minutes"],
)
@pytest.mark.parametrize("endpoint", ["civilStartTime", "civilEndTime"])
def test_civil_time_accepts_each_protobuf_zero_omission_shape(
    endpoint: str, time_shape: dict[str, int], hour: int, minute: int
) -> None:
    response = raw_response()
    response["dataPoints"] = [response["dataPoints"][0]]
    interval = response["dataPoints"][0]["steps"]["interval"]
    selected = datetime(2024, 3, 9, hour, minute)
    if endpoint == "civilStartTime":
        other = selected + timedelta(minutes=1)
        interval["startTime"] = f"{selected.isoformat()}Z"
        interval["endTime"] = f"{other.isoformat()}Z"
        interval["civilStartTime"] = {
            "date": {
                "year": selected.year,
                "month": selected.month,
                "day": selected.day,
            },
            "time": time_shape,
        }
        interval["civilEndTime"] = {
            "date": {"year": other.year, "month": other.month, "day": other.day},
            "time": {"hours": other.hour, "minutes": other.minute},
        }
    else:
        other = selected - timedelta(minutes=1)
        interval["startTime"] = f"{other.isoformat()}Z"
        interval["endTime"] = f"{selected.isoformat()}Z"
        interval["civilStartTime"] = {
            "date": {"year": other.year, "month": other.month, "day": other.day},
            "time": {"hours": other.hour, "minutes": other.minute},
        }
        interval["civilEndTime"] = {
            "date": {
                "year": selected.year,
                "month": selected.month,
                "day": selected.day,
            },
            "time": time_shape,
        }
    store = ObservationStore()

    assert SyntheticProviderIngestor(store).ingest_raw_response(response) == 1
    assert interval[endpoint]["time"] == time_shape


@pytest.mark.parametrize("endpoint", ["civilStartTime", "civilEndTime"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hours", True),
        ("hours", 1.5),
        ("hours", "1"),
        ("hours", None),
        ("minutes", False),
        ("minutes", 1.5),
        ("minutes", "1"),
        ("minutes", None),
    ],
)
def test_civil_time_rejects_boolean_and_non_integer_clock_fields_without_writing(
    endpoint: str, field: str, value: object
) -> None:
    response = raw_response()
    response["dataPoints"][0]["steps"]["interval"][endpoint]["time"] = {field: value}
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError, match="fields must be integers"):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


@pytest.mark.parametrize("endpoint", ["civilStartTime", "civilEndTime"])
@pytest.mark.parametrize(
    ("field", "value"),
    [("hours", -1), ("hours", 24), ("minutes", -1), ("minutes", 60)],
)
def test_civil_time_rejects_out_of_range_clock_fields_without_writing(
    endpoint: str, field: str, value: int
) -> None:
    response = raw_response()
    response["dataPoints"][0]["steps"]["interval"][endpoint]["time"] = {field: value}
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError, match="valid civil time"):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


@pytest.mark.parametrize("endpoint", ["civilStartTime", "civilEndTime"])
def test_civil_time_rejects_unknown_clock_fields_without_writing(endpoint: str) -> None:
    response = raw_response()
    response["dataPoints"][0]["steps"]["interval"][endpoint]["time"] = {"seconds": 0}
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError, match=r"\.time"):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


@pytest.mark.parametrize("endpoint", ["civilStartTime", "civilEndTime"])
@pytest.mark.parametrize("value", [None, [], 0, "00:00"])
def test_civil_time_rejects_non_object_time_values_without_writing(
    endpoint: str, value: object
) -> None:
    response = raw_response()
    response["dataPoints"][0]["steps"]["interval"][endpoint]["time"] = value
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError, match=r"\.time must be an object"):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


@pytest.mark.parametrize(
    "remove",
    [
        lambda response: response.pop("dataPoints"),
        lambda response: response["dataPoints"][0].pop("dataSource"),
        lambda response: response["dataPoints"][0]["dataSource"].pop("platform"),
        lambda response: response["dataPoints"][0]["dataSource"].pop("recordingMethod"),
        lambda response: response["dataPoints"][0].pop("steps"),
        lambda response: response["dataPoints"][0]["steps"].pop("count"),
        lambda response: response["dataPoints"][0]["steps"].pop("interval"),
        lambda response: response["dataPoints"][0]["steps"]["interval"].pop(
            "startTime"
        ),
        lambda response: response["dataPoints"][0]["steps"]["interval"].pop("endTime"),
        lambda response: response["dataPoints"][0]["steps"]["interval"].pop(
            "startUtcOffset"
        ),
        lambda response: response["dataPoints"][0]["steps"]["interval"].pop(
            "endUtcOffset"
        ),
        lambda response: response["dataPoints"][0]["steps"]["interval"].pop(
            "civilStartTime"
        ),
        lambda response: response["dataPoints"][0]["steps"]["interval"].pop(
            "civilEndTime"
        ),
        lambda response: response["dataPoints"][0]["steps"]["interval"][
            "civilStartTime"
        ].pop("date"),
        lambda response: response["dataPoints"][0]["steps"]["interval"][
            "civilStartTime"
        ].pop("time"),
        lambda response: response["dataPoints"][0]["steps"]["interval"][
            "civilEndTime"
        ].pop("date"),
        lambda response: response["dataPoints"][0]["steps"]["interval"][
            "civilEndTime"
        ].pop("time"),
    ],
)
def test_missing_required_fields_fail_without_synthesizing_zero(remove: object) -> None:
    response = raw_response()
    remove(response)
    store = ObservationStore()

    with pytest.raises(RawResponseValidationError):
        SyntheticProviderIngestor(store).ingest_raw_response(response)

    assert store.all_observations() == []


def test_ingestion_rejects_unsupported_flat_response_shape_without_writing() -> None:
    store = ObservationStore()
    unsupported_response = {"fixture_type": "synthetic", "observations": []}

    with pytest.raises(RawResponseValidationError, match="raw response"):
        SyntheticProviderIngestor(store).ingest_raw_response(unsupported_response)

    assert store.all_observations() == []


def test_parser_normalizes_omitted_final_token_to_empty() -> None:
    response = raw_response()
    response.pop("nextPageToken")

    observations, token = SyntheticProviderIngestor(ObservationStore()).parse_page(
        response, "UTC"
    )

    assert len(observations) == 2
    assert token == ""


def test_query_window_and_dst_days_are_exact_half_open_local_civil_days() -> None:
    short_start, short_end = half_open_local_day_window(
        date(2024, 3, 10), "America/New_York"
    )
    long_start, long_end = half_open_local_day_window(
        date(2024, 11, 3), "America/New_York"
    )

    assert short_end.timestamp() - short_start.timestamp() == 23 * 3600
    assert long_end.timestamp() - long_start.timestamp() == 25 * 3600
    assert short_start.hour == short_end.hour == long_start.hour == long_end.hour == 0


def test_absolute_times_and_explicit_offsets_survive_a_dst_transition() -> None:
    response = json.loads(DST_FIXTURE_PATH.read_text(encoding="utf-8"))

    observations, token = SyntheticProviderIngestor(ObservationStore()).parse_page(
        response, "America/New_York"
    )

    assert token == ""
    assert len(observations) == 1
    observation = observations[0]
    assert observation.interval_start.isoformat() == "2024-03-10T01:59:00-05:00"
    assert observation.interval_end.isoformat() == "2024-03-10T03:01:00-04:00"
    assert (
        observation.interval_end.timestamp() - observation.interval_start.timestamp()
        == 120
    )
    assert observation.source_platform == "FITBIT"
    assert observation.recording_method == "PASSIVELY_MEASURED"


def test_parser_rejects_contradictory_civil_or_offset_representation() -> None:
    response = raw_response()
    interval = response["dataPoints"][0]["steps"]["interval"]
    interval["civilStartTime"]["time"]["hours"] = 22
    with pytest.raises(RawResponseValidationError, match="civil time contradicts"):
        SyntheticProviderIngestor(ObservationStore()).parse_page(response, "UTC")

    response = raw_response()
    response["dataPoints"][0]["steps"]["interval"]["startUtcOffset"] = "3600s"
    with pytest.raises(RawResponseValidationError, match="UTC offset contradicts"):
        SyntheticProviderIngestor(ObservationStore()).parse_page(response, "UTC")


def test_omitted_civil_clock_fields_still_undergo_consistency_validation() -> None:
    response = raw_response()
    interval = response["dataPoints"][0]["steps"]["interval"]
    interval["civilEndTime"]["time"] = {}

    with pytest.raises(RawResponseValidationError, match="civil time contradicts"):
        SyntheticProviderIngestor(ObservationStore()).parse_page(response, "UTC")
