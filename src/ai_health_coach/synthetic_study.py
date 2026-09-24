"""Deterministic synthetic longitudinal data for development and evaluation."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ai_health_coach.evaluation import FeatureValue, LabeledExample
from ai_health_coach.study_protocol import Target


@dataclass(frozen=True, slots=True)
class SyntheticStudyDay:
    """One explicitly fictional day with inputs, provider output, and labels."""

    day_id: str
    local_date: date
    timezone: str
    wake_at: datetime
    prediction_cutoff: datetime
    sleep_minutes: int
    sleep_efficiency: float
    hrv_ms: float
    resting_heart_rate_bpm: float
    academic_stress: str
    caffeine_after_cutoff: bool
    deadline_within_48h: bool
    illness: bool
    google_readiness: float
    morning_readiness: int
    afternoon_energy: int
    overall_energy: int
    coach_insight_id: str

    def to_mapping(self) -> dict[str, object]:
        """Return a flat, serialization-ready representation."""

        payload = asdict(self)
        payload["local_date"] = self.local_date.isoformat()
        payload["wake_at"] = self.wake_at.isoformat()
        payload["prediction_cutoff"] = self.prediction_cutoff.isoformat()
        return payload


def _rating(value: float) -> int:
    return min(10, max(1, round(value)))


def generate_synthetic_days(
    count: int = 60,
    *,
    start_date: date = date(2026, 1, 5),
    timezone: str = "America/Los_Angeles",
) -> tuple[SyntheticStudyDay, ...]:
    """Generate a deterministic fictional study with irregular wake times."""

    if count < 1:
        raise ValueError("count must be positive")
    zone = ZoneInfo(timezone)
    stress_levels = ("low", "medium", "high")
    noise = (-0.7, 0.2, 0.8, -0.1, 0.4, -0.5, 0.0)
    days: list[SyntheticStudyDay] = []

    for index in range(count):
        local_date = start_date + timedelta(days=index)
        wake_minutes = 6 * 60 + ((index * 37) % 181)
        wake_at = datetime.combine(local_date, time.min, zone) + timedelta(
            minutes=wake_minutes
        )
        prediction_cutoff = wake_at + timedelta(minutes=20)
        sleep_minutes = 375 + ((index * 29) % 151)
        sleep_efficiency = round(0.76 + ((index * 7) % 20) / 100, 2)
        hrv_ms = float(38 + ((index * 11) % 29))
        resting_heart_rate = float(55 + ((index * 5) % 13))
        stress = stress_levels[(index // 2) % len(stress_levels)]
        caffeine = index % 5 == 0
        deadline = index % 11 in {0, 1}
        illness = index in {17, 18, 43}

        stress_penalty = {"low": 0.0, "medium": 0.7, "high": 1.4}[stress]
        latent = (
            5.2
            + (sleep_minutes - 420) / 75
            + (sleep_efficiency - 0.84) * 5
            + (hrv_ms - 50) / 18
            - (resting_heart_rate - 60) / 20
            - stress_penalty
            - (0.4 if caffeine else 0.0)
            - (0.5 if deadline else 0.0)
            - (2.0 if illness else 0.0)
        )
        morning = _rating(latent + noise[index % len(noise)])
        afternoon = _rating(
            latent - 0.5 - (0.6 if deadline else 0.0) + noise[(index + 2) % len(noise)]
        )
        overall = _rating(
            (morning + afternoon) / 2
            - (0.4 if stress == "high" else 0.0)
            + noise[(index + 4) % len(noise)] / 2
        )
        google = float(
            _rating(
                5.4
                + (sleep_minutes - 420) / 85
                + (sleep_efficiency - 0.84) * 4
                + (hrv_ms - 50) / 22
                - (1.2 if illness else 0.0)
                + noise[(index + 1) % len(noise)]
            )
        )
        days.append(
            SyntheticStudyDay(
                day_id=f"synthetic-day-{index + 1:03d}",
                local_date=local_date,
                timezone=timezone,
                wake_at=wake_at,
                prediction_cutoff=prediction_cutoff,
                sleep_minutes=sleep_minutes,
                sleep_efficiency=sleep_efficiency,
                hrv_ms=hrv_ms,
                resting_heart_rate_bpm=resting_heart_rate,
                academic_stress=stress,
                caffeine_after_cutoff=caffeine,
                deadline_within_48h=deadline,
                illness=illness,
                google_readiness=google,
                morning_readiness=morning,
                afternoon_energy=afternoon,
                overall_energy=overall,
                coach_insight_id=f"synthetic-insight-{(index % 3) + 1:03d}",
            )
        )
    return tuple(days)


def _target_details(
    day: SyntheticStudyDay, target: Target
) -> tuple[datetime, datetime, float]:
    if target is Target.MORNING_READINESS:
        target_time = day.wake_at + timedelta(minutes=25)
        return target_time, target_time + timedelta(minutes=2), day.morning_readiness
    if target is Target.AFTERNOON_ENERGY:
        target_time = day.wake_at + timedelta(hours=7)
        return target_time, target_time + timedelta(minutes=10), day.afternoon_energy
    if target is Target.OVERALL_ENERGY:
        target_time = day.wake_at + timedelta(hours=15)
        return target_time, target_time + timedelta(minutes=5), day.overall_energy
    raise ValueError("synthetic generator does not define next-day energy")


def generate_labeled_examples(
    target: Target = Target.MORNING_READINESS,
    *,
    count: int = 60,
) -> tuple[LabeledExample, ...]:
    """Convert synthetic days into cutoff-aware evaluation examples."""

    examples: list[LabeledExample] = []
    for day in generate_synthetic_days(count):
        target_time, label_available_at, outcome = _target_details(day, target)
        feature_available_at = day.wake_at + timedelta(minutes=15)
        stress_numeric = {"low": 0.0, "medium": 1.0, "high": 2.0}[day.academic_stress]
        features = (
            FeatureValue("sleep_minutes", day.sleep_minutes, feature_available_at),
            FeatureValue(
                "sleep_efficiency", day.sleep_efficiency, feature_available_at
            ),
            FeatureValue("hrv_ms", day.hrv_ms, feature_available_at),
            FeatureValue(
                "resting_heart_rate_bpm",
                day.resting_heart_rate_bpm,
                feature_available_at,
            ),
            FeatureValue("academic_stress", stress_numeric, day.wake_at),
            FeatureValue(
                "caffeine_after_cutoff",
                float(day.caffeine_after_cutoff),
                day.wake_at,
            ),
            FeatureValue(
                "deadline_within_48h",
                float(day.deadline_within_48h),
                day.wake_at,
            ),
            FeatureValue("illness", float(day.illness), day.wake_at),
        )
        examples.append(
            LabeledExample(
                example_id=f"{day.day_id}-{target.value}",
                target=target,
                target_time=target_time,
                label_available_at=label_available_at,
                prediction_cutoff=day.prediction_cutoff,
                outcome=outcome,
                features=features,
                google_prediction=day.google_readiness,
                google_available_at=day.wake_at + timedelta(minutes=18),
            )
        )
    return tuple(examples)


def write_synthetic_dataset(path: Path, count: int = 60) -> None:
    """Write a deterministic, explicitly synthetic CSV fixture."""

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "schema_version": "synthetic-study-1.0.0",
            "synthetic": "true",
            "private_data_accessed": "false",
            **day.to_mapping(),
        }
        for day in generate_synthetic_days(count)
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
