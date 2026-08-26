"""Nightly identity and timing context for three separate sleep scores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class SleepContextValidationError(ValueError):
    """Raised when a nightly context has ambiguous identity or timing."""


def _non_empty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SleepContextValidationError(f"{field} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class NightlyScoringContext:
    """Group score identities for one sleep window without making a composite."""

    context_id: str
    local_date: date
    timezone: str
    sleep_window_start: datetime
    sleep_window_end: datetime
    input_data_cutoff: datetime
    efficiency_score_id: str
    recovery_score_id: str
    energy_score_id: str

    def __post_init__(self) -> None:
        _non_empty(self.context_id, "context_id")
        if not isinstance(self.local_date, date) or isinstance(
            self.local_date, datetime
        ):
            raise SleepContextValidationError("local_date must be a date")
        _non_empty(self.timezone, "timezone")
        try:
            zone = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise SleepContextValidationError(
                "timezone must be an IANA time-zone name"
            ) from error

        for field in (
            "sleep_window_start",
            "sleep_window_end",
            "input_data_cutoff",
        ):
            timestamp = getattr(self, field)
            if not isinstance(timestamp, datetime):
                raise SleepContextValidationError(f"{field} must be a datetime")
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise SleepContextValidationError(f"{field} must include a UTC offset")
            if timestamp.utcoffset() != timestamp.astimezone(zone).utcoffset():
                raise SleepContextValidationError(
                    f"{field} UTC offset contradicts timezone"
                )

        if self.sleep_window_end <= self.sleep_window_start:
            raise SleepContextValidationError(
                "sleep_window_end must follow sleep_window_start"
            )
        if self.input_data_cutoff < self.sleep_window_end:
            raise SleepContextValidationError(
                "input_data_cutoff cannot precede sleep_window_end"
            )
        if self.sleep_window_end.astimezone(zone).date() != self.local_date:
            raise SleepContextValidationError(
                "local_date must match the sleep window end date"
            )

        score_ids = (
            _non_empty(self.efficiency_score_id, "efficiency_score_id"),
            _non_empty(self.recovery_score_id, "recovery_score_id"),
            _non_empty(self.energy_score_id, "energy_score_id"),
        )
        if len(set(score_ids)) != 3:
            raise SleepContextValidationError("score identifiers must be distinct")
