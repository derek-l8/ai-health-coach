"""Exercise real local HTTP requests with fictional entries only."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path
from uuid import uuid4

import pytest

from ai_health_coach.checkin_server import CheckInServer
from ai_health_coach.checkins import CheckInStore
from ai_health_coach.cli import main
from ai_health_coach.study_protocol import EventConfiguration, StudyValidationError


@pytest.fixture
def server(tmp_path):
    service = CheckInServer(
        ("127.0.0.1", 0),
        tmp_path / "study.sqlite3",
        EventConfiguration.flexible_default("America/Los_Angeles"),
    )
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    try:
        yield service
    finally:
        service.shutdown()
        service.server_close()
        thread.join(timeout=5)


def send(server, method, path, body=None, **header_changes):
    host, port = server.server_address
    headers = {
        "Authorization": f"Bearer {server.token}",
        "Origin": f"http://{host}:{port}",
        "Content-Type": "application/json",
        **header_changes,
    }
    connection = HTTPConnection(host, port, timeout=5)
    try:
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_form_config_submission_retry_and_restart(server):
    status, headers, page = send(server, "GET", "/")
    assert status == 200 and b'name="viewport"' in page
    assert headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert send(server, "GET", "/app.js")[0] == 200
    status, headers, script = send(server, "GET", "/time.mjs")
    assert status == 200 and b"timeCandidates" in script
    assert headers["Content-Type"].startswith("text/javascript")
    status, _, body = send(server, "GET", "/api/config")
    assert status == 200
    assert json.loads(body)["timezone"] == "America/Los_Angeles"
    assert json.loads(body)["caffeine_cutoff_local_time"] is None
    request = json.dumps(
        {
            "checkin_id": str(uuid4()),
            "event": "wake",
            "status": "completed",
            "observed_at": "2026-01-05T07:00:00-08:00",
            "rating": 6,
        }
    )
    status, _, first = send(server, "POST", "/api/checkins", request)
    assert status == 201
    status, _, replay = send(server, "POST", "/api/checkins", request)
    assert status == 200 and json.loads(replay)["replayed"]
    assert json.loads(first)["captured_at"] == json.loads(replay)["captured_at"]
    # A new connection after HTTP submission proves the data was committed to disk.
    store = CheckInStore(server.database)
    try:
        assert len(store.all_checkins()) == 1
        assert store.all_checkins()[0]["label"]["rating"] == 6
    finally:
        store.close()


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Origin": "https://other.example"}, 403),
        ({"Host": "other.example"}, 403),
        ({"Content-Type": "text/plain"}, 415),
    ],
)
def test_rejects_untrusted_submission(server, headers, expected):
    assert send(server, "POST", "/api/checkins", "{}", **headers)[0] == expected


@pytest.mark.parametrize(
    "body,status",
    [
        ("{broken", 400),
        ("[]", 400),
        ("null", 400),
        ("x" * 17000, 413),
    ],
)
def test_rejects_invalid_and_oversized_bodies(server, body, status):
    assert send(server, "POST", "/api/checkins", body)[0] == status


def test_no_private_history_or_arbitrary_file_routes(server):
    for path in ("/api/checkins", "/../study.sqlite3", "/study.sqlite3"):
        assert send(server, "GET", path)[0] == 404
    assert send(server, "GET", "/api/config", Authorization="")[0] == 401


def test_network_access_requires_tls_before_binding(tmp_path: Path):
    with pytest.raises(StudyValidationError, match="HTTPS"):
        CheckInServer(
            ("192.168.1.10", 8765),
            tmp_path / "study.sqlite3",
            EventConfiguration.flexible_default("America/Los_Angeles"),
        )
    assert not (tmp_path / "study.sqlite3").exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ["--serve-checkins"],
        ["--serve-checkins", "--database", "unused", "--timezone", "invalid"],
        [
            "--serve-checkins",
            "--database",
            "unused",
            "--timezone",
            "UTC",
            "--afternoon-start-hours",
            "nan",
        ],
    ],
)
def test_cli_requires_valid_collection_configuration(arguments):
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2


def test_cli_passes_explicit_caffeine_cutoff(monkeypatch, tmp_path):
    def serve(database, configuration, *args):
        assert configuration.caffeine_cutoff_local_time == "14:00"
        return 0

    monkeypatch.setattr("ai_health_coach.checkin_server.serve_checkins", serve)
    assert (
        main(
            [
                "--serve-checkins",
                "--database",
                str(tmp_path / "study.sqlite3"),
                "--timezone",
                "UTC",
                "--caffeine-cutoff",
                "14:00",
            ]
        )
        == 0
    )
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--serve-checkins",
                "--database",
                str(tmp_path / "study.sqlite3"),
                "--timezone",
                "UTC",
                "--caffeine-cutoff",
                "25:00",
            ]
        )
    assert error.value.code == 2
