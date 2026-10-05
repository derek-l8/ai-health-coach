"""Event configuration and study-record validation."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from ai_health_coach.study_protocol import (
    ActionState,
    CoachInsight,
    ContextObservation,
    EventConfiguration,
    EventType,
    ExposureState,
    InsightOrigin,
    PersonalLabel,
    PredictionExposure,
    RecordStatus,
    StudyValidationError,
    Target,
    TextFidelity,
    TriggerKind,
)


def test_default_configuration_has_no_assumed_wake_clock_time() -> None:
    configuration = EventConfiguration.flexible_default("America/Los_Angeles")
    windows = {window.event_type: window for window in configuration.windows}

    assert windows[EventType.WAKE].trigger is TriggerKind.MANUAL
    assert windows[EventType.WAKE].opens_after_wake is None
    assert windows[EventType.AFTERNOON].opens_after_wake == timedelta(hours=5)
    assert windows[EventType.AFTERNOON].closes_after_wake == timedelta(hours=9)
    assert windows[EventType.DAY_CLOSE].trigger is TriggerKind.MANUAL
    assert configuration.caffeine_cutoff_local_time is None


@pytest.mark.parametrize("cutoff", ["00:00", "14:00", "23:59"])
def test_caffeine_cutoff_is_explicit_study_local_time(cutoff):
    config = replace(
        EventConfiguration.flexible_default("UTC"), caffeine_cutoff_local_time=cutoff
    )
    assert config.caffeine_cutoff_local_time == cutoff


@pytest.mark.parametrize(
    "cutoff", ["24:00", "9:00", "14:60", "14:00:00", "noon", True, 14]
)
def test_caffeine_cutoff_rejects_ambiguous_or_invalid_values(cutoff):
    with pytest.raises(StudyValidationError, match="HH:MM"):
        replace(
            EventConfiguration.flexible_default("UTC"),
            caffeine_cutoff_local_time=cutoff,
        )


def test_completed_and_skipped_labels_preserve_missingness() -> None:
    completed = PersonalLabel(
        label_id="label-1",
        target=Target.MORNING_READINESS,
        local_date=date(2026, 1, 5),
        timezone="America/Los_Angeles",
        observed_at=datetime.fromisoformat("2026-01-05T07:15:00-08:00"),
        captured_at=datetime.fromisoformat("2026-01-05T07:18:00-08:00"),
        status=RecordStatus.COMPLETED,
        prompt_version="readiness-1.0.0",
        rating=7,
    )
    skipped = PersonalLabel(
        label_id="label-2",
        target=Target.AFTERNOON_ENERGY,
        local_date=date(2026, 1, 5),
        timezone="America/Los_Angeles",
        observed_at=datetime.fromisoformat("2026-01-05T14:00:00-08:00"),
        captured_at=datetime.fromisoformat("2026-01-05T14:20:00-08:00"),
        status=RecordStatus.SKIPPED,
        prompt_version="energy-1.0.0",
    )

    assert completed.rating == 7
    assert skipped.rating is None


def test_label_rejects_rating_for_missing_status() -> None:
    with pytest.raises(StudyValidationError, match="cannot have ratings"):
        PersonalLabel(
            label_id="label-3",
            target=Target.OVERALL_ENERGY,
            local_date=date(2026, 1, 5),
            timezone="America/Los_Angeles",
            observed_at=datetime.fromisoformat("2026-01-05T21:00:00-08:00"),
            captured_at=datetime.fromisoformat("2026-01-05T21:01:00-08:00"),
            status=RecordStatus.MISSING,
            prompt_version="energy-1.0.0",
            rating=0,
        )


def test_exposure_context_and_insight_keep_distinct_meanings() -> None:
    exposure = PredictionExposure(
        exposure_id="exposure-1",
        target=Target.MORNING_READINESS,
        provider="synthetic-google",
        seen_before_label=ExposureState.UNSURE,
        recommendation_acted_on=ActionState.UNKNOWN,
        captured_at=datetime.fromisoformat("2026-01-05T07:18:00-08:00"),
    )
    context = ContextObservation(
        context_id="context-1",
        local_date=date(2026, 1, 5),
        captured_at=datetime.fromisoformat("2026-01-05T07:18:00-08:00"),
        illness=False,
        academic_stress="high",
        alcohol=None,
    )
    insight = CoachInsight(
        insight_id="insight-1",
        provider="synthetic-google",
        origin=InsightOrigin.RECONSTRUCTED,
        fidelity=TextFidelity.SUMMARIZED,
        interval_start=datetime.fromisoformat("2026-01-04T23:00:00-08:00"),
        interval_end=datetime.fromisoformat("2026-01-05T07:00:00-08:00"),
        available_at=datetime.fromisoformat("2026-01-10T10:00:00-08:00"),
        captured_at=datetime.fromisoformat("2026-01-10T10:01:00-08:00"),
        text="Synthetic reconstruction.",
    )

    assert exposure.seen_before_label is ExposureState.UNSURE
    assert context.alcohol is None
    assert insight.origin is InsightOrigin.RECONSTRUCTED
