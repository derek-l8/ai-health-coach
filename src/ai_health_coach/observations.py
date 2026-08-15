"""Canonical, provider-neutral observation validation for synthetic ingestion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

QualityStatus = Literal["complete", "partial", "missing"]


class ObservationValidationError(ValueError):
    """Raised when data at the ingestion boundary is not canonical."""


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ObservationValidationError(f"{key} must be a non-empty string")
    return value


def _timestamp(data: Mapping[str, Any], key: str) -> datetime:
    value = _required_string(data, key)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ObservationValidationError(
            f"{key} must be an ISO 8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ObservationValidationError(f"{key} must include a UTC offset")
    return parsed


def _validate_timezone_offset(timestamp: datetime, timezone: str, key: str) -> None:
    zone_offset = timestamp.astimezone(ZoneInfo(timezone)).utcoffset()
    if timestamp.utcoffset() != zone_offset:
        raise ObservationValidationError(
            f"{key} UTC offset contradicts timezone {timezone}"
        )


@dataclass(frozen=True, slots=True)
class MetricObservation:
    """One normalized metric interval, retaining provider and time-zone provenance."""

    source: str
    source_observation_id: str
    metric_type: str
    interval_start: datetime
    interval_end: datetime
    value: float | None
    unit: str | None
    timezone: str
    quality_status: QualityStatus
    source_platform: str | None = None
    recording_method: str | None = None
    device_manufacturer: str | None = None
    device_display_name: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> MetricObservation:
        """Validate untrusted provider-shaped data without filling missing values."""
        source = _required_string(data, "source")
        source_observation_id = _required_string(data, "source_observation_id")
        metric_type = _required_string(data, "metric_type")
        interval_start = _timestamp(data, "interval_start")
        interval_end = _timestamp(data, "interval_end")
        if interval_end < interval_start:
            raise ObservationValidationError(
                "interval_end cannot precede interval_start"
            )

        timezone = _required_string(data, "timezone")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise ObservationValidationError(
                "timezone must be an IANA time-zone name"
            ) from error
        _validate_timezone_offset(interval_start, timezone, "interval_start")
        _validate_timezone_offset(interval_end, timezone, "interval_end")

        quality_status = data.get("quality_status")
        if quality_status not in {"complete", "partial", "missing"}:
            raise ObservationValidationError(
                "quality_status must be complete, partial, or missing"
            )

        raw_value = data.get("value")
        if raw_value is None:
            value = None
        elif isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
            raise ObservationValidationError("value must be a number or null")
        else:
            value = float(raw_value)
        if value is not None and not isfinite(value):
            raise ObservationValidationError("value must be finite")
        if quality_status == "missing" and value is not None:
            raise ObservationValidationError(
                "missing observations cannot contain a value"
            )

        raw_unit = data.get("unit")
        if raw_unit is None:
            unit = None
        elif not isinstance(raw_unit, str) or not raw_unit.strip():
            raise ObservationValidationError("unit must be a non-empty string or null")
        else:
            unit = raw_unit
        if value is not None and unit is None:
            raise ObservationValidationError("unit is required when value is present")

        source_platform = _optional_string(data, "source_platform")
        recording_method = _optional_string(data, "recording_method")
        device_manufacturer = _optional_string(data, "device_manufacturer")
        device_display_name = _optional_string(data, "device_display_name")

        return cls(
            source=source,
            source_observation_id=source_observation_id,
            metric_type=metric_type,
            interval_start=interval_start,
            interval_end=interval_end,
            value=value,
            unit=unit,
            timezone=timezone,
            quality_status=quality_status,
            source_platform=source_platform,
            recording_method=recording_method,
            device_manufacturer=device_manufacturer,
            device_display_name=device_display_name,
        )


def _optional_string(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ObservationValidationError(f"{key} must be a non-empty string or null")
    return value
