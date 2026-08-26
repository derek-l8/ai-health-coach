"""Labeled storage for provider proprietary scores, never treated as ground truth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ProviderScoreValidationError(ValueError):
    """Raised when a provider comparison record would lose required context."""


def _non_empty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderScoreValidationError(f"{field} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class ProviderScoreComparison:
    """One proprietary provider score retained only as a labeled comparison."""

    comparison_id: str
    provider: str
    score_label: str
    value: float | None
    unit: str | None
    local_date: date
    timezone: str
    recorded_at: datetime
    source_observation_id: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.comparison_id, "comparison_id")
        _non_empty(self.provider, "provider")
        _non_empty(self.score_label, "score_label")
        if self.value is None:
            if self.unit is not None:
                raise ProviderScoreValidationError(
                    "unit is required when a comparison value is present"
                )
        else:
            if isinstance(self.value, bool) or not isinstance(self.value, int | float):
                raise ProviderScoreValidationError("value must be a number")
            if self.unit is None:
                raise ProviderScoreValidationError(
                    "unit is required when a comparison value is present"
                )
            object.__setattr__(self, "value", float(self.value))
        if not isinstance(self.local_date, date) or isinstance(
            self.local_date, datetime
        ):
            raise ProviderScoreValidationError("local_date must be a date")
        try:
            zone = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ProviderScoreValidationError(
                "timezone must be an IANA time-zone name"
            ) from error
        recorded_offset = self.recorded_at.utcoffset()
        if (
            self.recorded_at.tzinfo is None
            or recorded_offset is None
            or recorded_offset != self.recorded_at.astimezone(zone).utcoffset()
        ):
            raise ProviderScoreValidationError(
                "recorded_at must include a UTC offset consistent with timezone"
            )
