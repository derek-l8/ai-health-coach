"""Validated daily feedback kept separate from predicted Energy scores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class SleepFeedbackValidationError(ValueError):
    """Raised when daily feedback would lose scale, time, or missingness meaning."""


def _non_empty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SleepFeedbackValidationError(f"{field} must be a non-empty string")
    return value


def _rating(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise SleepFeedbackValidationError(
            f"{field} must be an integer from 1 to 10 or null"
        )
    return value


@dataclass(frozen=True, slots=True)
class DailySleepFeedback:
    """An immutable optional observation submitted after an Energy prediction."""

    feedback_id: str
    energy_score_id: str
    local_date: date
    timezone: str
    submitted_at: datetime
    perceived_energy: int | None = None
    perceived_recovery: int | None = None
    sleep_quality: int | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.feedback_id, "feedback_id")
        _non_empty(self.energy_score_id, "energy_score_id")
        if not isinstance(self.local_date, date) or isinstance(
            self.local_date, datetime
        ):
            raise SleepFeedbackValidationError("local_date must be a date")

        _non_empty(self.timezone, "timezone")
        try:
            zone = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise SleepFeedbackValidationError(
                "timezone must be an IANA time-zone name"
            ) from error
        if not isinstance(self.submitted_at, datetime):
            raise SleepFeedbackValidationError("submitted_at must be a datetime")
        if self.submitted_at.tzinfo is None or self.submitted_at.utcoffset() is None:
            raise SleepFeedbackValidationError("submitted_at must include a UTC offset")
        if (
            self.submitted_at.utcoffset()
            != self.submitted_at.astimezone(zone).utcoffset()
        ):
            raise SleepFeedbackValidationError(
                "submitted_at UTC offset contradicts timezone"
            )

        object.__setattr__(
            self,
            "perceived_energy",
            _rating(self.perceived_energy, "perceived_energy"),
        )
        object.__setattr__(
            self,
            "perceived_recovery",
            _rating(self.perceived_recovery, "perceived_recovery"),
        )
        object.__setattr__(
            self, "sleep_quality", _rating(self.sleep_quality, "sleep_quality")
        )
        if self.note is not None:
            _non_empty(self.note, "note")
