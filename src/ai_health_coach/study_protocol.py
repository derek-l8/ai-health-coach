"""Versioned study configuration and records with explicit timing semantics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class StudyValidationError(ValueError):
    """Raised when a study record loses timing, scale, or provenance meaning."""


class EventType(StrEnum):
    """User-driven events in the collection protocol."""

    WAKE = "wake"
    AFTERNOON = "afternoon"
    DAY_CLOSE = "day_close"


class TriggerKind(StrEnum):
    """How an event window is opened."""

    MANUAL = "manual"
    RELATIVE_TO_WAKE = "relative_to_wake"


class Target(StrEnum):
    """Initial subjective outcomes."""

    MORNING_READINESS = "morning_readiness"
    AFTERNOON_ENERGY = "afternoon_energy"
    OVERALL_ENERGY = "overall_energy"
    NEXT_DAY_ENERGY = "next_day_energy"


class RecordStatus(StrEnum):
    """Capture state without conflating absence with zero."""

    COMPLETED = "completed"
    SKIPPED = "skipped"
    MISSING = "missing"


class ExposureState(StrEnum):
    """Whether provider guidance was seen before the outcome label."""

    YES = "yes"
    NO = "no"
    UNSURE = "unsure"


class ActionState(StrEnum):
    """Whether a seen recommendation influenced behavior."""

    NO = "no"
    PARTLY = "partly"
    YES = "yes"
    UNKNOWN = "unknown"


class InsightOrigin(StrEnum):
    """How a provider insight relates to the original presentation."""

    ORIGINAL = "original_insight"
    HISTORICAL = "historical_insight"
    RECONSTRUCTED = "reconstructed_insight"


class TextFidelity(StrEnum):
    """How closely stored text matches the displayed provider text."""

    EXACT = "exact"
    TRANSCRIBED = "transcribed"
    SUMMARIZED = "summarized"
    PARSED = "parsed"


def _non_empty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise StudyValidationError(f"{field} must be a non-empty string")


def _aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise StudyValidationError(f"{field} must be an offset-aware datetime")
    if value.utcoffset() is None:
        raise StudyValidationError(f"{field} must include a valid UTC offset")


def _timezone(value: str) -> ZoneInfo:
    _non_empty(value, "timezone")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise StudyValidationError("timezone must be an IANA time-zone name") from error


def _matches_zone(value: datetime, zone: ZoneInfo, field: str) -> None:
    _aware(value, field)
    if value.utcoffset() != value.astimezone(zone).utcoffset():
        raise StudyValidationError(f"{field} UTC offset contradicts timezone")


@dataclass(frozen=True, slots=True)
class EventWindowConfig:
    """A configurable window anchored to user action or the actual wake event."""

    event_type: EventType
    trigger: TriggerKind
    opens_after_wake: timedelta | None = None
    closes_after_wake: timedelta | None = None

    def __post_init__(self) -> None:
        relative = self.trigger is TriggerKind.RELATIVE_TO_WAKE
        if relative:
            if self.opens_after_wake is None or self.closes_after_wake is None:
                raise StudyValidationError(
                    "relative windows require both wake-relative boundaries"
                )
            if self.opens_after_wake < timedelta(0):
                raise StudyValidationError("opens_after_wake cannot be negative")
            if self.closes_after_wake <= self.opens_after_wake:
                raise StudyValidationError(
                    "closes_after_wake must be after opens_after_wake"
                )
        elif self.opens_after_wake is not None or self.closes_after_wake is not None:
            raise StudyValidationError(
                "manual windows cannot contain assumed wake-relative boundaries"
            )


@dataclass(frozen=True, slots=True)
class EventConfiguration:
    """Versioned event configuration with no assumed wall-clock wake time."""

    version: str
    timezone: str
    windows: tuple[EventWindowConfig, ...]
    caffeine_cutoff_local_time: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.version, "version")
        _timezone(self.timezone)
        cutoff = self.caffeine_cutoff_local_time
        if cutoff is not None and (
            not isinstance(cutoff, str)
            or re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cutoff) is None
        ):
            raise StudyValidationError("caffeine cutoff must be HH:MM in 24-hour time")
        actual = [window.event_type for window in self.windows]
        if len(actual) != len(set(actual)):
            raise StudyValidationError("event windows must be unique by event type")
        if set(actual) != set(EventType):
            raise StudyValidationError("configuration must define all three events")

    @classmethod
    def flexible_default(cls, timezone: str) -> EventConfiguration:
        """Return defaults anchored to actual wake, never a fixed hour."""

        return cls(
            version="event-config-1.1.0",
            timezone=timezone,
            windows=(
                EventWindowConfig(EventType.WAKE, TriggerKind.MANUAL),
                EventWindowConfig(
                    EventType.AFTERNOON,
                    TriggerKind.RELATIVE_TO_WAKE,
                    opens_after_wake=timedelta(hours=5),
                    closes_after_wake=timedelta(hours=9),
                ),
                EventWindowConfig(EventType.DAY_CLOSE, TriggerKind.MANUAL),
            ),
        )


@dataclass(frozen=True, slots=True)
class PersonalLabel:
    """One append-only subjective target observation."""

    label_id: str
    target: Target
    local_date: date
    timezone: str
    observed_at: datetime
    captured_at: datetime
    status: RecordStatus
    prompt_version: str
    rating: int | None = None
    capture_method: str = "phone_form"

    def __post_init__(self) -> None:
        _non_empty(self.label_id, "label_id")
        _non_empty(self.prompt_version, "prompt_version")
        _non_empty(self.capture_method, "capture_method")
        zone = _timezone(self.timezone)
        _matches_zone(self.observed_at, zone, "observed_at")
        _matches_zone(self.captured_at, zone, "captured_at")
        if self.observed_at.astimezone(zone).date() != self.local_date:
            raise StudyValidationError("local_date must match observed_at")
        if self.captured_at.timestamp() < self.observed_at.timestamp():
            raise StudyValidationError("captured_at cannot precede observed_at")
        if self.status is RecordStatus.COMPLETED:
            if isinstance(self.rating, bool) or not isinstance(self.rating, int):
                raise StudyValidationError("completed labels require an integer rating")
            if not 1 <= self.rating <= 10:
                raise StudyValidationError("rating must be from 1 to 10")
        elif self.rating is not None:
            raise StudyValidationError("skipped or missing labels cannot have ratings")


@dataclass(frozen=True, slots=True)
class PredictionExposure:
    """Provider exposure and action state for one target label."""

    exposure_id: str
    target: Target
    provider: str
    seen_before_label: ExposureState
    recommendation_acted_on: ActionState
    captured_at: datetime

    def __post_init__(self) -> None:
        _non_empty(self.exposure_id, "exposure_id")
        _non_empty(self.provider, "provider")
        _aware(self.captured_at, "captured_at")


@dataclass(frozen=True, slots=True)
class ContextObservation:
    """Compact nullable context without inferred defaults."""

    context_id: str
    local_date: date
    captured_at: datetime
    caffeine_after_cutoff: bool | None = None
    exercise_level: str | None = None
    illness: bool | None = None
    academic_stress: str | None = None
    deadline_within_48h: bool | None = None
    alcohol: str | None = None
    medication_changed_or_missed: bool | None = None
    unusual_sleep: bool | None = None

    def __post_init__(self) -> None:
        _non_empty(self.context_id, "context_id")
        _aware(self.captured_at, "captured_at")
        if self.exercise_level not in {None, "none", "light", "moderate", "hard"}:
            raise StudyValidationError("exercise_level is not recognized")
        if self.academic_stress not in {None, "low", "medium", "high"}:
            raise StudyValidationError("academic_stress is not recognized")
        if self.alcohol not in {None, "none", "one", "two_or_more"}:
            raise StudyValidationError("alcohol is not recognized")


@dataclass(frozen=True, slots=True)
class CoachInsight:
    """A provider message with origin, fidelity, and availability preserved."""

    insight_id: str
    provider: str
    origin: InsightOrigin
    fidelity: TextFidelity
    interval_start: datetime
    interval_end: datetime
    available_at: datetime
    captured_at: datetime
    text: str

    def __post_init__(self) -> None:
        _non_empty(self.insight_id, "insight_id")
        _non_empty(self.provider, "provider")
        _non_empty(self.text, "text")
        for field in (
            "interval_start",
            "interval_end",
            "available_at",
            "captured_at",
        ):
            _aware(getattr(self, field), field)
        if self.interval_end <= self.interval_start:
            raise StudyValidationError("insight interval must have positive duration")
        if self.captured_at < self.available_at:
            raise StudyValidationError("captured_at cannot precede available_at")
