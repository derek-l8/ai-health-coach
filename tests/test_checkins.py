"""Synthetic persistence, replay, missingness, configuration, and clock boundaries."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from ai_health_coach.checkins import (
    CheckInConflictError,
    CheckInStore,
    private_database_path,
)
from ai_health_coach.study_protocol import (
    EventConfiguration,
    EventType,
    EventWindowConfig,
    StudyValidationError,
    TriggerKind,
)

CONFIG = EventConfiguration.flexible_default("America/Los_Angeles")
CAPTURED = datetime.fromisoformat("2026-01-05T15:00:00-08:00")


def request(**changes) -> dict:
    return {
        "checkin_id": str(uuid4()),
        "event": "afternoon",
        "status": "completed",
        "observed_at": "2026-01-05T14:00:00-08:00",
        "wake_at": "2026-01-05T06:00:00-08:00",
        "rating": 7,
        "google_seen": "unsure",
        "acted_on": "unknown",
        "context": {"illness": False, "academic_stress": "high"},
        "note": "Fictional test note.",
        **changes,
    }


def test_restart_preserves_label_context_exposure_and_exact_retry(tmp_path: Path):
    database = tmp_path / "checkins.sqlite3"
    original = request()
    store = CheckInStore(database)
    first, inserted = store.submit(original, CONFIG, CAPTURED)
    store.close()
    reopened = CheckInStore(database)
    try:
        replay, inserted_again = reopened.submit(
            original, CONFIG, CAPTURED + timedelta(days=1)
        )
        assert inserted and not inserted_again
        assert replay == first == reopened.all_checkins()[0]
        assert first["label"]["rating"] == 7
        assert first["context"]["illness"] is False
        assert first["context"]["alcohol"] is None
        assert first["exposure"]["seen_before_label"] == "unsure"
        assert first["capture_delay_seconds"] == 3600
        assert first["available_at"] == "2026-01-05T15:00:00-08:00"
        assert len(reopened.all_checkins()) == 1
    finally:
        reopened.close()


def test_conflicting_retry_rolls_back_and_records_cannot_be_mutated():
    store = CheckInStore()
    original = request()
    try:
        store.submit(original, CONFIG, CAPTURED)
        with pytest.raises(CheckInConflictError):
            store.submit({**original, "rating": 8}, CONFIG, CAPTURED)
        assert len(store.all_checkins()) == 1
        for query in (
            "UPDATE study_checkin SET payload_json = '{}'",
            "DELETE FROM study_checkin",
            "DELETE FROM checkin_configuration",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                store.connection.execute(query)
            store.connection.rollback()
    finally:
        store.close()


@pytest.mark.parametrize("status", ["skipped", "missing"])
def test_missing_and_skipped_entries_do_not_need_rating_or_wake(status):
    store = CheckInStore()
    try:
        payload, _ = store.submit(
            request(status=status, rating=None, wake_at=None, context={}, note=None),
            CONFIG,
            CAPTURED,
        )
        assert payload["label"]["status"] == status
        assert payload["label"]["rating"] is None
        assert payload["window_status"] == "unanchored"
    finally:
        store.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"rating": 0},
        {"rating": True},
        {"rating": 1.5},
        {"status": "missing", "rating": 5},
        {"event": "invented"},
        {"observed_at": "2026-01-05T14:00:00"},
        {"observed_at": "2026-01-06T14:00:00-08:00"},
        {"wake_at": "2026-01-05T14:30:00-08:00"},
        {"context": {"illness": "false"}},
        {"context": {"academic_stress": []}},
        {"context": {"made_up": 1}},
        {"note": "x" * 2001},
        {"reported_late": "true"},
        {"captured_at": "invented"},
    ],
)
def test_invalid_entries_leave_no_partial_records(changes):
    store = CheckInStore()
    try:
        with pytest.raises(StudyValidationError):
            store.submit(request(**changes), CONFIG, CAPTURED)
        assert store.all_checkins() == []
        assert (
            store.connection.execute(
                "SELECT count(*) FROM checkin_configuration"
            ).fetchone()[0]
            == 0
        )
    finally:
        store.close()


def test_custom_configuration_keeps_old_windows_and_marks_late_submission():
    custom = replace(
        CONFIG,
        windows=(
            CONFIG.windows[0],
            EventWindowConfig(
                EventType.AFTERNOON,
                TriggerKind.RELATIVE_TO_WAKE,
                timedelta(hours=3),
                timedelta(hours=6),
            ),
            CONFIG.windows[2],
        ),
    )
    store = CheckInStore()
    try:
        normal, _ = store.submit(request(), CONFIG, CAPTURED)
        late, _ = store.submit(request(), custom, CAPTURED)
        assert normal["window_status"] == "on_time"
        assert late["window_status"] == "late"
        assert normal["configuration_id"] != late["configuration_id"]
        configs = [
            json.loads(row[0])
            for row in store.connection.execute(
                "SELECT payload_json FROM checkin_configuration"
            )
        ]
        assert {
            config["windows"][1]["closes_after_wake_hours"] for config in configs
        } == {6, 9}
    finally:
        store.close()


def test_dst_elapsed_window_and_repeated_hour_use_actual_instants():
    store = CheckInStore()
    try:
        spring, _ = store.submit(
            request(
                wake_at="2026-03-08T00:00:00-08:00",
                observed_at="2026-03-08T10:00:00-07:00",
            ),
            CONFIG,
            datetime.fromisoformat("2026-03-08T10:00:00-07:00"),
        )
        assert spring["window_status"] == "on_time"  # nine elapsed hours, not ten
        autumn, _ = store.submit(
            request(
                event="wake",
                wake_at=None,
                observed_at="2026-11-01T01:50:00-07:00",
            ),
            CONFIG,
            datetime.fromisoformat("2026-11-01T01:10:00-08:00"),
        )
        assert autumn["capture_delay_seconds"] == 1200
    finally:
        store.close()


def test_private_database_refuses_a_git_checkout(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(StudyValidationError, match="outside"):
        private_database_path(tmp_path / "data" / "study.sqlite3")


def test_caffeine_answer_requires_cutoff_and_old_configurations_are_preserved(tmp_path):
    database = tmp_path / "caffeine.sqlite3"
    store = CheckInStore(database)
    original = request(context={"caffeine_after_cutoff": True})
    try:
        with pytest.raises(StudyValidationError, match="configure a caffeine cutoff"):
            store.submit(original, CONFIG, CAPTURED)
        assert store.all_checkins() == []
        first_config = replace(CONFIG, caffeine_cutoff_local_time="14:00")
        first, _ = store.submit(original, first_config, CAPTURED)
        later_config = replace(CONFIG, caffeine_cutoff_local_time="16:00")
        later, _ = store.submit(
            request(context={"caffeine_after_cutoff": False}), later_config, CAPTURED
        )
        assert first["configuration_id"] != later["configuration_id"]
    finally:
        store.close()
    reopened = CheckInStore(database)
    try:
        configs = [
            json.loads(row[0])
            for row in reopened.connection.execute(
                "SELECT payload_json FROM checkin_configuration"
            )
        ]
        assert {c["caffeine_cutoff_local_time"] for c in configs} == {"14:00", "16:00"}
        assert reopened.all_checkins()[0]["context"]["caffeine_after_cutoff"] is True
        replay, inserted = reopened.submit(original, first_config, CAPTURED)
        assert not inserted and replay == first
    finally:
        reopened.close()
