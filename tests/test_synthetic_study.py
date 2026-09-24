"""Deterministic fictional longitudinal data and public fixtures."""

from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path

from ai_health_coach.study_protocol import Target
from ai_health_coach.synthetic_study import (
    generate_labeled_examples,
    generate_synthetic_days,
    write_synthetic_dataset,
)


def test_sixty_day_dataset_is_deterministic_and_irregular() -> None:
    first = generate_synthetic_days()
    second = generate_synthetic_days()

    assert first == second
    assert len(first) == 60
    assert len({day.day_id for day in first}) == 60
    assert len({day.wake_at.timetz() for day in first}) > 20
    assert all(1 <= day.morning_readiness <= 10 for day in first)
    assert all(day.local_date >= date(2026, 1, 5) for day in first)
    assert all(
        math.isfinite(value)
        for day in first
        for value in (
            day.sleep_efficiency,
            day.hrv_ms,
            day.resting_heart_rate_bpm,
            day.google_readiness,
        )
    )


def test_generated_examples_preserve_cutoff_availability() -> None:
    examples = generate_labeled_examples(Target.AFTERNOON_ENERGY)

    assert len(examples) == 60
    assert all(
        feature.available_at <= example.prediction_cutoff
        for example in examples
        for feature in example.features
    )
    assert all(
        example.google_available_at <= example.prediction_cutoff
        for example in examples
        if example.google_available_at is not None
    )
    assert all(
        example.label_available_at > example.prediction_cutoff for example in examples
    )


def test_dataset_writer_marks_fixture_as_synthetic(tmp_path: Path) -> None:
    output = tmp_path / "longitudinal.csv"
    write_synthetic_dataset(output)
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 60
    assert {row["synthetic"] for row in rows} == {"true"}
    assert {row["private_data_accessed"] for row in rows} == {"false"}


def test_checked_in_longitudinal_fixture_matches_generator(tmp_path: Path) -> None:
    expected = Path("fixtures/synthetic/longitudinal-60-days.csv")
    generated = tmp_path / "longitudinal-60-days.csv"
    write_synthetic_dataset(generated)
    assert generated.read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")


def test_static_phone_form_is_explicitly_synthetic() -> None:
    document = Path("prototype/phone-form/index.html").read_text(encoding="utf-8")

    assert 'name="viewport"' in document
    assert "Synthetic check-in prototype" in document
    assert "not sent or stored" in document
    assert "5 to 9 hours after the recorded wake event" in document
    assert "https://" not in document
    assert 'action="' not in document


def test_coach_insight_fixtures_are_explicitly_synthetic() -> None:
    root = Path("fixtures/synthetic")
    payload = json.loads((root / "coach-insights.json").read_text(encoding="utf-8"))

    assert payload["synthetic"] is True
    assert {item["origin"] for item in payload["insights"]} == {
        "original_insight",
        "historical_insight",
        "reconstructed_insight",
    }
    for filename in (
        "coach-insight-original.svg",
        "coach-insight-reconstructed.svg",
    ):
        text = (root / filename).read_text(encoding="utf-8")
        assert "SYNTHETIC" in text
        assert "No real account" in text
