"""Fictional Forms snapshots exercise identity, timing, and atomic imports."""

from __future__ import annotations

import copy
import json
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_health_coach.checkins import CheckInConflictError, CheckInStore
from ai_health_coach.cli import main
from ai_health_coach.forms_import import import_form_snapshot
from ai_health_coach.study_protocol import StudyValidationError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/synthetic/form-snapshot.json"
IMPORTED = datetime(2024, 11, 4, tzinfo=UTC)


@pytest.fixture
def store():
    value = CheckInStore()
    yield value
    value.close()


@pytest.fixture
def snapshot():
    return json.loads(FIXTURE.read_bytes())


def load(store, snapshot, at=IMPORTED):
    return import_form_snapshot(store, json.dumps(snapshot).encode(), at)


def test_preserves_second_dst_occurrence_and_first_import(store, snapshot):
    result = load(store, snapshot)
    assert (result.inserted, result.replayed) == (1, 0)
    checkin = store.all_checkins()[0]
    assert checkin["label"]["observed_at"] == "2024-11-03T01:30:00-08:00"
    assert checkin["label"]["captured_at"] == "2024-11-03T01:30:00-08:00"
    assert checkin["label"]["capture_method"] == "google_form"
    assert checkin["available_at"] == IMPORTED.isoformat()
    assert checkin["source"]["snapshot_sha256"] == result.snapshot_sha256
    assert checkin["context"]["illness"] is None
    assert checkin["configuration_id"]
    replay = load(store, snapshot, IMPORTED + timedelta(days=1))
    assert (replay.inserted, replay.replayed) == (0, 1)
    assert store.all_checkins() == [checkin]
    row = store.connection.execute(
        "SELECT content, imported_at FROM checkin_import_snapshot"
    ).fetchone()
    assert json.loads(row[0]) == snapshot
    assert row[1] == IMPORTED.isoformat()


def test_new_export_keeps_history_and_links_both_artifacts(store, snapshot):
    load(store, snapshot)
    original = store.all_checkins()
    snapshot["exported_at"] = "2024-11-04T01:00:00Z"
    assert load(store, snapshot, IMPORTED + timedelta(hours=2)).replayed == 1
    assert store.all_checkins() == original
    assert (
        store.connection.execute(
            "SELECT count(*) FROM checkin_import_member"
        ).fetchone()[0]
        == 2
    )


def test_form_identity_namespaces_responses(store, snapshot):
    load(store, snapshot)
    snapshot["form_id"] = "other-synthetic-form"
    assert load(store, snapshot).inserted == 1
    assert len(store.all_checkins()) == 2


def test_changed_response_rolls_back_new_rows_and_snapshot(store, snapshot):
    load(store, snapshot)
    new = copy.deepcopy(snapshot["responses"][0])
    new["response_id"] = "new-synthetic-response"
    snapshot["responses"].insert(0, new)
    snapshot["responses"][1]["answers"]["rating"] = "8"
    with pytest.raises(CheckInConflictError, match="history was not overwritten"):
        load(store, snapshot)
    assert len(store.all_checkins()) == 1
    assert (
        store.connection.execute(
            "SELECT count(*) FROM checkin_import_snapshot"
        ).fetchone()[0]
        == 1
    )


def test_configuration_changes_require_new_form(store, snapshot):
    load(store, snapshot)
    snapshot["configuration"]["caffeine_cutoff_local_time"] = "14:00"
    with pytest.raises(CheckInConflictError, match="configuration changed"):
        load(store, snapshot)
    snapshot["form_id"] = "new-synthetic-form"
    assert load(store, snapshot).inserted == 1


@pytest.mark.parametrize("status", ["Skipped", "Missing"])
def test_absent_ratings_remain_null(store, snapshot, status):
    snapshot["responses"][0]["answers"].update(status=status, rating="")
    load(store, snapshot)
    assert store.all_checkins()[0]["label"]["rating"] is None
    assert store.all_checkins()[0]["label"]["status"] == status.lower()


def test_backfill_context_cutoff_and_submission_window(store, snapshot):
    snapshot["configuration"]["caffeine_cutoff_local_time"] = "14:00"
    response = snapshot["responses"][0]
    response["submitted_at"] = "2024-11-03T17:30:00Z"
    response["answers"].update(
        event="Afternoon energy",
        observed_at="2024-11-03T09:00:00-08:00",
        wake_at="2024-11-03T01:30:00-08:00",
        reported_late="Yes",
        caffeine_after_cutoff="No",
        illness="No",
        academic_stress="High",
    )
    load(store, snapshot)
    checkin = store.all_checkins()[0]
    assert checkin["capture_delay_seconds"] == 1800
    assert (
        checkin["window_status"] == "on_time"
    )  # eight hours after wake, not the later import
    assert checkin["reported_late"] is True
    assert checkin["context"]["caffeine_after_cutoff"] is False
    assert checkin["context"]["academic_stress"] == "high"
    assert checkin["available_at"] == IMPORTED.isoformat()


@pytest.mark.parametrize(
    "answers",
    [
        {"rating": "0"},
        {"rating": "7.0"},
        {"rating": True},
        {"rating": ""},
        {"event": "Tomorrow"},
        {"status": ""},
        {"unknown": "secret"},
        {"illness": "unknown"},
        {"caffeine_after_cutoff": "Yes"},
        {"observed_at": "2024-11-03T01:30:00"},
        {"observed_at": "2024-11-04T01:00:00Z"},
        {"wake_at": "2024-11-04T01:00:00Z"},
        {"note": "x" * 2001},
        {"status": "Missing", "rating": "7"},
    ],
)
def test_invalid_response_does_not_partially_import(store, snapshot, answers):
    invalid = copy.deepcopy(snapshot["responses"][0])
    invalid["response_id"] = "invalid-synthetic-response"
    invalid["answers"].update(answers)
    snapshot["responses"].append(invalid)
    with pytest.raises(StudyValidationError):
        load(store, snapshot)
    assert store.all_checkins() == []
    assert (
        store.connection.execute(
            "SELECT count(*) FROM checkin_configuration"
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.update(schema_version=True),
        lambda s: s.update(kind="sheet_csv"),
        lambda s: s.update(extra="secret"),
        lambda s: s.update(responses={}),
        lambda s: s["responses"].append(copy.deepcopy(s["responses"][0])),
        lambda s: s["responses"][0].update(submitted_at="2024-11-03T19:00:00Z"),
        lambda s: s["configuration"].update(timezone="Not/AZone"),
        lambda s: s["configuration"]["windows"][1].update(opens_after_wake_hours=True),
        lambda s: s["configuration"].update(version="future-version"),
    ],
)
def test_invalid_snapshot_is_rejected(store, snapshot, change):
    change(snapshot)
    with pytest.raises(StudyValidationError):
        load(store, snapshot)
    assert store.all_checkins() == []


@pytest.mark.parametrize(
    "content",
    [
        b'{"kind": 1, "kind": 2}',
        b'{"kind": NaN}',
        b"\xff",
        b"[]",
        b"x" * (5 * 1024 * 1024 + 1),
    ],
    ids=["duplicate-key", "nonfinite", "invalid-utf8", "not-object", "oversize"],
)
def test_invalid_json_or_oversize_file(store, content):
    with pytest.raises(StudyValidationError):
        import_form_snapshot(store, content, IMPORTED)


def test_import_time_must_follow_export(store, snapshot):
    with pytest.raises(StudyValidationError, match="precede"):
        load(store, snapshot, datetime(2024, 11, 3, tzinfo=UTC))
    with pytest.raises(StudyValidationError, match="offset"):
        load(store, snapshot, datetime(2024, 11, 4))


@pytest.mark.parametrize(
    "table",
    [
        "study_checkin",
        "checkin_configuration",
        "checkin_form_configuration",
        "checkin_import_snapshot",
        "checkin_import_member",
    ],
)
def test_import_history_is_immutable(store, snapshot, table):
    load(store, snapshot)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.connection.execute(f"DELETE FROM {table}")


def test_cli_import_replay_and_private_path(tmp_path, capsys):
    database = tmp_path / "private" / "study.sqlite3"
    args = ["--import-form-snapshot", str(FIXTURE), "--database", str(database)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["inserted"] == 1
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["replayed"] == 1
    with pytest.raises(SystemExit):
        main(["--import-form-snapshot", str(FIXTURE)])
    with pytest.raises(SystemExit):
        main(
            [
                "--import-form-snapshot",
                str(FIXTURE),
                "--database",
                str(ROOT / "forbidden.sqlite3"),
            ]
        )
    assert not (ROOT / "forbidden.sqlite3").exists()


def test_apps_script_export_matches_python_contract(store):
    result = subprocess.run(
        ["node", str(ROOT / "tests/web/forms_mock.mjs"), "--snapshot"],
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout) == json.loads(FIXTURE.read_bytes())
    assert import_form_snapshot(store, result.stdout, IMPORTED).inserted == 1
