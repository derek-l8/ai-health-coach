"""Strict synthetic Google Health response validation and mapping."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time
from hashlib import sha256
from typing import Any
from zoneinfo import ZoneInfo

from ai_health_coach.observations import MetricObservation, ObservationValidationError
from ai_health_coach.sleep_metrics import SUPPORTED_SLEEP_METRICS
from ai_health_coach.storage import ObservationStore

SYNTHETIC_SOURCE = "synthetic-google-health"
_UTC_OFFSET_PATTERN = re.compile(r"-?\d+s")
_STEPS_COUNT_PATTERN = re.compile(r"[0-9]+")
_MAX_EXACT_FLOAT_INTEGER = 2**53


class RawResponseValidationError(ValueError):
    """Raised when a response is outside the supported synthetic boundary."""


def half_open_local_day_window(
    local_day: date, timezone: str
) -> tuple[datetime, datetime]:
    """Return the exact local civil-day interval, including DST-short/long days."""
    zone = ZoneInfo(timezone)
    start = datetime.combine(local_day, time.min, tzinfo=zone)
    end_day = local_day.fromordinal(local_day.toordinal() + 1)
    return start, datetime.combine(end_day, time.min, tzinfo=zone)


def _object_with_exact_fields(
    value: object, expected_fields: set[str], location: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise RawResponseValidationError(
            f"{location} must contain only {', '.join(sorted(expected_fields))}"
        )
    return value


def _object_with_optional_fields(
    value: object,
    required_fields: set[str],
    optional_fields: set[str],
    location: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RawResponseValidationError(f"{location} must be an object")
    fields = set(value)
    if not required_fields <= fields or not fields <= required_fields | optional_fields:
        raise RawResponseValidationError(
            f"{location} must contain required fields only"
        )
    return value


def _non_empty_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RawResponseValidationError(f"{location} must be a non-empty string")
    return value


def _list_response_fields(
    value: object,
) -> tuple[Mapping[str, Any], str]:
    if not isinstance(value, Mapping):
        raise RawResponseValidationError(
            "raw response must contain dataPoints and optional nextPageToken only"
        )
    fields = set(value)
    if "dataPoints" not in fields or not fields <= {"dataPoints", "nextPageToken"}:
        raise RawResponseValidationError(
            "raw response must contain dataPoints and optional nextPageToken only"
        )
    token = value.get("nextPageToken", "")
    if not isinstance(token, str):
        raise RawResponseValidationError("nextPageToken must be a string when present")
    return value, token


def _utc_offset(value: object, location: str) -> str:
    value = _non_empty_string(value, location)
    if not _UTC_OFFSET_PATTERN.fullmatch(value):
        raise RawResponseValidationError(f"{location} must be a whole-second duration")
    return value


def _civil_time(value: object, location: str) -> datetime:
    civil_time = _object_with_exact_fields(value, {"date", "time"}, location)
    civil_date = _object_with_exact_fields(
        civil_time["date"], {"year", "month", "day"}, f"{location}.date"
    )
    clock = _object_with_optional_fields(
        civil_time["time"], set(), {"hours", "minutes"}, f"{location}.time"
    )
    hours = clock.get("hours", 0)
    minutes = clock.get("minutes", 0)
    fields = (*civil_date.values(), hours, minutes)
    if any(isinstance(field, bool) or not isinstance(field, int) for field in fields):
        raise RawResponseValidationError(f"{location} fields must be integers")
    try:
        civil = datetime(
            civil_date["year"],
            civil_date["month"],
            civil_date["day"],
            hours,
            minutes,
        )
    except ValueError as error:
        raise RawResponseValidationError(
            f"{location} must be a valid civil time"
        ) from error
    return civil


def _offset_seconds(value: str) -> int:
    return int(value.removesuffix("s"))


def _steps_count(value: object) -> float:
    value = _non_empty_string(value, "steps.count")
    if not _STEPS_COUNT_PATTERN.fullmatch(value):
        raise RawResponseValidationError(
            "steps.count must be a non-negative integer string"
        )
    count = int(value)
    if count > _MAX_EXACT_FLOAT_INTEGER:
        raise RawResponseValidationError("steps.count exceeds exact numeric storage")
    return float(count)


def _absolute_timestamp(value: object, location: str) -> datetime:
    value = _non_empty_string(value, location)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RawResponseValidationError(
            f"{location} must be an ISO 8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RawResponseValidationError(f"{location} must include a UTC offset")
    return parsed


def _generated_steps_identifier(
    platform: str,
    recording_method: str,
    device_manufacturer: str | None,
    device_display_name: str | None,
    start: datetime,
    end: datetime,
) -> str:
    identity_parts = ["steps", platform, recording_method]
    if device_manufacturer is not None or device_display_name is not None:
        identity_parts.extend(
            ["device", device_manufacturer or "", device_display_name or ""]
        )
    identity_parts.extend(
        [start.astimezone(UTC).isoformat(), end.astimezone(UTC).isoformat()]
    )
    identity = "\x1f".join(identity_parts)
    return f"generated-steps-{sha256(identity.encode()).hexdigest()}"


def _generated_metric_identifier(
    metric_type: str,
    platform: str,
    recording_method: str,
    device_manufacturer: str | None,
    device_display_name: str | None,
    start: datetime,
    end: datetime,
) -> str:
    identity_parts = [metric_type, platform, recording_method]
    if device_manufacturer is not None or device_display_name is not None:
        identity_parts.extend(
            ["device", device_manufacturer or "", device_display_name or ""]
        )
    identity_parts.extend(
        [start.astimezone(UTC).isoformat(), end.astimezone(UTC).isoformat()]
    )
    identity = "\x1f".join(identity_parts)
    return f"generated-{metric_type}-{sha256(identity.encode()).hexdigest()}"


class SyntheticProviderIngestor:
    """Validate a complete synthetic list response before storing observations."""

    def __init__(self, store: ObservationStore) -> None:
        self._store = store

    def ingest_raw_response(self, raw_response: Mapping[str, Any]) -> int:
        """Ingest a supported documented response shape, rejecting it before writes."""
        return self._store.ingest(self._validated_observations(raw_response))

    def parse_page(
        self, raw_response: Mapping[str, Any], timezone: str
    ) -> tuple[list[MetricObservation], str]:
        """Validate one official-shape page and return its opaque continuation token."""
        response, token = _list_response_fields(raw_response)
        raw_points = response["dataPoints"]
        if not isinstance(raw_points, Sequence) or isinstance(raw_points, str | bytes):
            raise RawResponseValidationError("dataPoints must be a list")
        observations = [
            self._validated_point(raw_point, index, timezone)
            for index, raw_point in enumerate(raw_points)
        ]
        return observations, token

    def _validated_observations(
        self, raw_response: Mapping[str, Any]
    ) -> list[MetricObservation]:
        response, _ = _list_response_fields(raw_response)
        raw_points = response["dataPoints"]
        if not isinstance(raw_points, Sequence) or isinstance(raw_points, str | bytes):
            raise RawResponseValidationError("dataPoints must be a list")

        return [
            self._validated_point(raw_point, index, "UTC")
            for index, raw_point in enumerate(raw_points)
        ]

    def _validated_point(
        self, raw_point: object, index: int, timezone: str
    ) -> MetricObservation:
        location = f"dataPoints[{index}]"
        if not isinstance(raw_point, Mapping):
            raise RawResponseValidationError(f"{location} must be an object")
        if "steps" in raw_point:
            return self._validated_steps_point(raw_point, index, timezone)
        if "metricType" in raw_point:
            return self._validated_sleep_metric_point(raw_point, index, timezone)
        raise RawResponseValidationError(
            f"{location} must contain a steps or supported sleep-metric point"
        )

    def _validated_data_source(
        self, raw_point: Mapping[str, Any], location: str
    ) -> tuple[str, str, str | None, str | None]:
        data_source = _object_with_optional_fields(
            raw_point["dataSource"],
            {"recordingMethod", "platform"},
            {"device"},
            f"{location}.dataSource",
        )
        recording_method = _non_empty_string(
            data_source["recordingMethod"], f"{location}.dataSource.recordingMethod"
        )
        platform = _non_empty_string(
            data_source["platform"], f"{location}.dataSource.platform"
        )
        device_manufacturer = None
        device_display_name = None
        if "device" in data_source:
            device = _object_with_optional_fields(
                data_source["device"],
                set(),
                {"manufacturer", "displayName"},
                f"{location}.dataSource.device",
            )
            if "manufacturer" in device:
                device_manufacturer = _non_empty_string(
                    device["manufacturer"],
                    f"{location}.dataSource.device.manufacturer",
                )
            if "displayName" in device:
                device_display_name = _non_empty_string(
                    device["displayName"],
                    f"{location}.dataSource.device.displayName",
                )
        return platform, recording_method, device_manufacturer, device_display_name

    def _validated_localized_interval(
        self,
        interval_value: object,
        location: str,
        timezone: str,
    ) -> tuple[datetime, datetime]:
        """Validate the shared six-field envelope against physical time."""
        interval = _object_with_exact_fields(
            interval_value,
            {
                "startTime",
                "startUtcOffset",
                "endTime",
                "endUtcOffset",
                "civilStartTime",
                "civilEndTime",
            },
            f"{location}.interval",
        )
        start = _absolute_timestamp(
            interval["startTime"], f"{location}.interval.startTime"
        )
        end = _absolute_timestamp(interval["endTime"], f"{location}.interval.endTime")
        start_offset = _utc_offset(
            interval["startUtcOffset"], f"{location}.interval.startUtcOffset"
        )
        end_offset = _utc_offset(
            interval["endUtcOffset"], f"{location}.interval.endUtcOffset"
        )
        start_civil = _civil_time(
            interval["civilStartTime"], f"{location}.interval.civilStartTime"
        )
        end_civil = _civil_time(
            interval["civilEndTime"], f"{location}.interval.civilEndTime"
        )

        try:
            zone = ZoneInfo(timezone)
            for instant, offset, civil, label in (
                (start, start_offset, start_civil, "start"),
                (end, end_offset, end_civil, "end"),
            ):
                local = instant.astimezone(zone)
                if int(local.utcoffset().total_seconds()) != _offset_seconds(offset):
                    raise RawResponseValidationError(
                        f"{location} {label} UTC offset contradicts timezone"
                    )
                if local.replace(tzinfo=None) != civil:
                    raise RawResponseValidationError(
                        f"{location} {label} civil time contradicts physical time"
                    )
        except (ObservationValidationError, ValueError) as error:
            raise RawResponseValidationError(
                f"{location} is invalid: {error}"
            ) from error
        return start, end

    def _validated_steps_point(
        self, raw_point: object, index: int, timezone: str
    ) -> MetricObservation:
        location = f"dataPoints[{index}]"
        point = _object_with_optional_fields(
            raw_point,
            {"dataSource", "steps"},
            {"name"},
            location,
        )
        platform, recording_method, device_manufacturer, device_display_name = (
            self._validated_data_source(point, location)
        )

        steps = _object_with_exact_fields(
            point["steps"], {"interval", "count"}, f"{location}.steps"
        )
        start, end = self._validated_localized_interval(
            steps["interval"], location, timezone
        )
        start_local = start.astimezone(ZoneInfo(timezone))
        end_local = end.astimezone(ZoneInfo(timezone))

        identifier = (
            _non_empty_string(point["name"], f"{location}.name")
            if "name" in point
            else _generated_steps_identifier(
                platform,
                recording_method,
                device_manufacturer,
                device_display_name,
                start,
                end,
            )
        )
        try:
            return MetricObservation.from_mapping(
                {
                    "source": SYNTHETIC_SOURCE,
                    "source_observation_id": identifier,
                    "metric_type": "steps",
                    "interval_start": start_local.isoformat(),
                    "interval_end": end_local.isoformat(),
                    "value": _steps_count(steps["count"]),
                    "unit": "count",
                    "timezone": timezone,
                    "quality_status": "complete",
                    "source_platform": platform,
                    "recording_method": recording_method,
                    "device_manufacturer": device_manufacturer,
                    "device_display_name": device_display_name,
                }
            )
        except (ObservationValidationError, ValueError) as error:
            raise RawResponseValidationError(
                f"{location} is invalid: {error}"
            ) from error

    def _validated_sleep_metric_point(
        self, raw_point: object, index: int, timezone: str
    ) -> MetricObservation:
        location = f"dataPoints[{index}]"
        point = _object_with_optional_fields(
            raw_point,
            {"dataSource", "metricType", "interval", "value"},
            {"name", "unit"},
            location,
        )
        platform, recording_method, device_manufacturer, device_display_name = (
            self._validated_data_source(point, location)
        )
        metric_type = _non_empty_string(point["metricType"], f"{location}.metricType")
        definition = SUPPORTED_SLEEP_METRICS.get(metric_type)
        if definition is None:
            raise RawResponseValidationError(
                f"{location}.metricType is not a supported sleep metric"
            )

        start, end = self._validated_localized_interval(
            point["interval"], location, timezone
        )
        start_local = start.astimezone(ZoneInfo(timezone))
        end_local = end.astimezone(ZoneInfo(timezone))

        raw_value = point["value"]
        if raw_value is None:
            value = None
            unit = None
            quality_status = "missing"
            if point.get("unit") is not None:
                raise RawResponseValidationError(
                    f"{location}.unit cannot accompany a missing value"
                )
        else:
            if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
                raise RawResponseValidationError(f"{location}.value must be a number")
            value = float(raw_value)
            unit = _non_empty_string(point.get("unit"), f"{location}.unit")
            if unit != definition.unit:
                raise RawResponseValidationError(
                    f"{location}.unit must be {definition.unit} for {metric_type}"
                )
            quality_status = "complete"

        identifier = (
            _non_empty_string(point["name"], f"{location}.name")
            if "name" in point
            else _generated_metric_identifier(
                metric_type,
                platform,
                recording_method,
                device_manufacturer,
                device_display_name,
                start,
                end,
            )
        )
        try:
            return MetricObservation.from_mapping(
                {
                    "source": SYNTHETIC_SOURCE,
                    "source_observation_id": identifier,
                    "metric_type": metric_type,
                    "interval_start": start_local.isoformat(),
                    "interval_end": end_local.isoformat(),
                    "value": value,
                    "unit": unit,
                    "timezone": timezone,
                    "quality_status": quality_status,
                    "source_platform": platform,
                    "recording_method": recording_method,
                    "device_manufacturer": device_manufacturer,
                    "device_display_name": device_display_name,
                }
            )
        except (ObservationValidationError, ValueError) as error:
            raise RawResponseValidationError(
                f"{location} is invalid: {error}"
            ) from error
