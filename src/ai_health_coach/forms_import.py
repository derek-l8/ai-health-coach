"""Import this project's Google Forms snapshots, not arbitrary Sheet exports."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from ai_health_coach.checkins import (
    CheckInConflictError,
    CheckInStore,
    _instant,
    _json,
    configuration_payload,
)
from ai_health_coach.study_protocol import (
    EventConfiguration,
    EventType,
    EventWindowConfig,
    StudyValidationError,
    TriggerKind,
)

MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024
EVENTS = {
    "Morning readiness": "wake",
    "Afternoon energy": "afternoon",
    "Overall energy": "day_close",
}
BOOLEANS = {
    "illness",
    "deadline_within_48h",
    "medication_changed_or_missed",
    "unusual_sleep",
    "caffeine_after_cutoff",
}
CHOICES = {
    "exercise_level": {
        "None": "none",
        "Light": "light",
        "Moderate": "moderate",
        "Hard": "hard",
    },
    "academic_stress": {"Low": "low", "Medium": "medium", "High": "high"},
    "alcohol": {"None": "none", "One drink": "one", "Two or more": "two_or_more"},
}


@dataclass(frozen=True)
class ImportResult:
    snapshot_sha256: str
    inserted: int
    replayed: int


def _object(value: object, fields: set[str], name: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise StudyValidationError(f"{name} has unsupported or missing fields")
    return value


def _identity(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise StudyValidationError(
            f"{name} must be nonempty text of at most 1024 characters"
        )
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise StudyValidationError("snapshot contains duplicate JSON keys")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise StudyValidationError("snapshot contains a non-finite JSON number")


def _configuration(value: object) -> EventConfiguration:
    value = _object(
        value,
        {"version", "timezone", "windows", "caffeine_cutoff_local_time"},
        "configuration",
    )
    if value["version"] != "forms-config-1.0.0":
        raise StudyValidationError("unsupported Forms configuration version")
    if not isinstance(value["windows"], list) or len(value["windows"]) != 3:
        raise StudyValidationError("configuration must define three windows")
    windows = []
    for item in value["windows"]:
        item = _object(
            item,
            {"event", "trigger", "opens_after_wake_hours", "closes_after_wake_hours"},
            "window",
        )
        boundaries = []
        for name in ("opens_after_wake_hours", "closes_after_wake_hours"):
            hours = item[name]
            if hours is not None and (
                type(hours) not in (int, float) or not 0 <= hours <= 168
            ):
                raise StudyValidationError(
                    "window boundaries must be finite hours from 0 to 168"
                )
            boundaries.append(None if hours is None else timedelta(hours=hours))
        try:
            windows.append(
                EventWindowConfig(
                    EventType(item["event"]), TriggerKind(item["trigger"]), *boundaries
                )
            )
        except (TypeError, ValueError) as error:
            raise StudyValidationError("invalid Forms event window") from error
    return EventConfiguration(
        value["version"],
        value["timezone"],
        tuple(windows),
        value["caffeine_cutoff_local_time"],
    )


def _choice(answers: dict, name: str, choices: dict, default: object = None) -> object:
    value = answers.get(name, "")
    if value == "":
        return default
    if not isinstance(value, str) or value not in choices:
        raise StudyValidationError(f"{name} contains an unsupported answer")
    return choices[value]


def _request(
    response: object, form_id: str, config: EventConfiguration
) -> tuple[dict, datetime, str]:
    response = _object(response, {"response_id", "submitted_at", "answers"}, "response")
    response_id = _identity(response["response_id"], "response_id")
    submitted = _instant(
        response["submitted_at"], ZoneInfo(config.timezone), "submitted_at"
    )
    answers = response["answers"]
    allowed = (
        {
            "event",
            "status",
            "rating",
            "observed_at",
            "wake_at",
            "google_seen",
            "acted_on",
            "reported_late",
            "note",
        }
        | BOOLEANS
        | set(CHOICES)
    )
    if not isinstance(answers, dict) or set(answers) - allowed:
        raise StudyValidationError("answers contains unsupported fields")
    if any(
        not isinstance(value, str) or len(value) > 2000 for value in answers.values()
    ):
        raise StudyValidationError("answers must be text of at most 2000 characters")
    event = _choice(answers, "event", EVENTS)
    status = _choice(
        answers,
        "status",
        {"Completed": "completed", "Skipped": "skipped", "Missing": "missing"},
    )
    rating = answers.get("rating", "")
    if rating and rating not in {str(i) for i in range(1, 11)}:
        raise StudyValidationError("rating must be an integer from 1 to 10")
    context = {
        name: _choice(answers, name, {"Yes": True, "No": False}) for name in BOOLEANS
    }
    context.update(
        {name: _choice(answers, name, choices) for name, choices in CHOICES.items()}
    )
    identity = str(uuid5(NAMESPACE_URL, _json(["google_forms", form_id, response_id])))
    request = {
        "checkin_id": identity,
        "event": event,
        "status": status,
        "rating": int(rating) if rating else None,
        "observed_at": answers.get("observed_at") or submitted.isoformat(),
        "wake_at": answers.get("wake_at") or None,
        "google_seen": _choice(
            answers,
            "google_seen",
            {"Yes": "yes", "No": "no", "Unsure": "unsure"},
            "unsure",
        ),
        "acted_on": _choice(
            answers,
            "acted_on",
            {"Yes": "yes", "No": "no", "Partly": "partly", "Unknown": "unknown"},
            "unknown",
        ),
        "reported_late": _choice(
            answers, "reported_late", {"Yes": True, "No": False}, False
        ),
        "context": context,
        "note": answers.get("note") or None,
    }
    return request, submitted, response_id


def import_form_snapshot(
    store: CheckInStore, content: bytes, imported_at: datetime
) -> ImportResult:
    """Append one whole snapshot atomically, preserving first-import availability."""
    if len(content) > MAX_SNAPSHOT_BYTES:
        raise StudyValidationError("snapshot exceeds the 5 MiB limit")
    if imported_at.tzinfo is None or imported_at.utcoffset() is None:
        raise StudyValidationError("imported_at must include a UTC offset")
    imported_at = imported_at.astimezone(UTC)
    try:
        snapshot = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise StudyValidationError(
            "snapshot must be valid UTF-8 JSON with unique keys"
        ) from error
    snapshot = _object(
        snapshot,
        {
            "kind",
            "schema_version",
            "form_id",
            "exported_at",
            "configuration",
            "responses",
        },
        "snapshot",
    )
    if (
        snapshot["kind"] != "google_forms_checkins"
        or type(snapshot["schema_version"]) is not int
        or snapshot["schema_version"] != 1
    ):
        raise StudyValidationError("unsupported Forms snapshot schema")
    form_id = _identity(snapshot["form_id"], "form_id")
    config = _configuration(snapshot["configuration"])
    exported_at = _instant(snapshot["exported_at"], ZoneInfo("UTC"), "exported_at")
    if imported_at < exported_at:
        raise StudyValidationError("import cannot precede snapshot export")
    responses = snapshot["responses"]
    if not isinstance(responses, list) or len(responses) > 10000:
        raise StudyValidationError("responses must be a list of at most 10000 entries")
    prepared = [_request(response, form_id, config) for response in responses]
    if len({response_id for _, _, response_id in prepared}) != len(prepared):
        raise StudyValidationError("snapshot contains duplicate response IDs")
    if any(
        submitted.timestamp() > exported_at.timestamp() for _, submitted, _ in prepared
    ):
        raise StudyValidationError("submission cannot follow snapshot export")
    config_json = _json(configuration_payload(config))
    config_id = hashlib.sha256(config_json.encode()).hexdigest()
    digest = hashlib.sha256(content).hexdigest()
    connection = store.connection
    connection.execute("BEGIN IMMEDIATE")
    try:
        for table, columns in (
            (
                "checkin_form_configuration",
                "form_id TEXT PRIMARY KEY, configuration_id TEXT NOT NULL "
                "REFERENCES checkin_configuration(configuration_id)",
            ),
            (
                "checkin_import_snapshot",
                "snapshot_sha256 TEXT PRIMARY KEY, form_id TEXT NOT NULL, "
                "configuration_id TEXT NOT NULL "
                "REFERENCES checkin_configuration(configuration_id), "
                "imported_at TEXT NOT NULL, content BLOB NOT NULL",
            ),
            (
                "checkin_import_member",
                "snapshot_sha256 TEXT NOT NULL "
                "REFERENCES checkin_import_snapshot(snapshot_sha256), "
                "checkin_id TEXT NOT NULL REFERENCES study_checkin(checkin_id), "
                "PRIMARY KEY(snapshot_sha256, checkin_id)",
            ),
        ):
            connection.execute(f"CREATE TABLE IF NOT EXISTS {table} ({columns})")
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()} "
                    f"BEFORE {operation} ON {table} BEGIN "
                    "SELECT RAISE(ABORT, 'import records are immutable'); END"
                )
        binding = connection.execute(
            "SELECT configuration_id FROM checkin_form_configuration WHERE form_id = ?",
            (form_id,),
        ).fetchone()
        if binding and binding[0] != config_id:
            raise CheckInConflictError(
                "Form configuration changed; use a new Form for new definitions"
            )
        connection.execute(
            "INSERT OR IGNORE INTO checkin_configuration VALUES (?, ?)",
            (config_id, config_json),
        )
        connection.execute(
            "INSERT OR IGNORE INTO checkin_form_configuration VALUES (?, ?)",
            (form_id, config_id),
        )
        connection.execute(
            "INSERT OR IGNORE INTO checkin_import_snapshot VALUES (?, ?, ?, ?, ?)",
            (digest, form_id, config_id, imported_at.isoformat(), content),
        )
        inserted = 0
        for (request, submitted, response_id), response in zip(
            prepared, responses, strict=True
        ):
            identity = request["checkin_id"]
            # Preserve source answers as well as normalized values when detecting edits.
            request_json = _json(
                {
                    "request": request,
                    "answers": response["answers"],
                    "form_id": form_id,
                    "response_id": response_id,
                    "submitted_at": submitted,
                }
            )
            existing = connection.execute(
                "SELECT request_json, configuration_id FROM study_checkin "
                "WHERE checkin_id = ?",
                (identity,),
            ).fetchone()
            if existing:
                if existing[0] != request_json or existing[1] != config_id:
                    raise CheckInConflictError(
                        "Form response changed; imported history was not overwritten"
                    )
            else:
                payload = store._validate(
                    request, identity, config, submitted, capture_method="google_form"
                )
                payload.update(
                    {
                        "configuration_id": config_id,
                        "available_at": imported_at.isoformat(),
                        "imported_at": imported_at.isoformat(),
                        "import_delay_seconds": imported_at.timestamp()
                        - submitted.timestamp(),
                        "source": {
                            "provider": "google_forms",
                            "form_id": form_id,
                            "response_id": response_id,
                            "submitted_at": submitted.isoformat(),
                            "snapshot_sha256": digest,
                        },
                    }
                )
                connection.execute(
                    "INSERT INTO study_checkin VALUES (?, ?, ?, ?)",
                    (identity, config_id, request_json, _json(payload)),
                )
                inserted += 1
            connection.execute(
                "INSERT OR IGNORE INTO checkin_import_member VALUES (?, ?)",
                (digest, identity),
            )
        connection.commit()
        return ImportResult(digest, inserted, len(prepared) - inserted)
    except BaseException:
        connection.rollback()
        raise
