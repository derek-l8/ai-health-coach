"""Private, append-only check-ins using the existing study record contracts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from ai_health_coach.study_protocol import (
    ActionState,
    ContextObservation,
    EventConfiguration,
    EventType,
    ExposureState,
    PersonalLabel,
    PredictionExposure,
    RecordStatus,
    StudyValidationError,
    Target,
    TriggerKind,
)

TARGETS = {
    EventType.WAKE: Target.MORNING_READINESS,
    EventType.AFTERNOON: Target.AFTERNOON_ENERGY,
    EventType.DAY_CLOSE: Target.OVERALL_ENERGY,
}


def configuration_payload(config: EventConfiguration) -> dict:
    """Serialize exact window boundaries without an assumed wake time."""
    return {
        "version": config.version,
        "timezone": config.timezone,
        "caffeine_cutoff_local_time": config.caffeine_cutoff_local_time,
        "windows": [
            {
                "event": window.event_type.value,
                "trigger": window.trigger.value,
                "opens_after_wake_hours": (
                    window.opens_after_wake.total_seconds() / 3600
                    if window.opens_after_wake is not None
                    else None
                ),
                "closes_after_wake_hours": (
                    window.closes_after_wake.total_seconds() / 3600
                    if window.closes_after_wake is not None
                    else None
                ),
            }
            for window in config.windows
        ],
    }


def _json(value: object) -> str:
    def timestamp(value: object) -> str:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        raise TypeError("value cannot be serialized")

    return json.dumps(value, default=timestamp, sort_keys=True, allow_nan=False)


def _instant(value: object, zone: ZoneInfo, name: str) -> datetime:
    if not isinstance(value, str):
        raise StudyValidationError(f"{name} must include a timestamp and UTC offset")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as error:
        raise StudyValidationError(f"{name} is not a valid timestamp") from error
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise StudyValidationError(f"{name} must include a UTC offset")
    try:
        return instant.astimezone(zone)
    except (OverflowError, ValueError) as error:
        raise StudyValidationError(
            f"{name} is outside the supported date range"
        ) from error


class CheckInConflictError(ValueError):
    """A retry reused an identity with changed content."""


class CheckInStore:
    """One private database, independent of the older observation schema."""

    def __init__(self, database: Path | str = ":memory:") -> None:
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        try:
            with self.connection:
                self.connection.execute(
                    "CREATE TABLE IF NOT EXISTS checkin_schema "
                    "(version INTEGER NOT NULL)"
                )
                versions = self.connection.execute(
                    "SELECT version FROM checkin_schema"
                ).fetchall()
                if versions and [row[0] for row in versions] != [1]:
                    raise StudyValidationError("unsupported check-in database schema")
                if not versions:
                    self.connection.execute("INSERT INTO checkin_schema VALUES (1)")
                self.connection.execute(
                    "CREATE TABLE IF NOT EXISTS checkin_configuration "
                    "(configuration_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
                )
                self.connection.execute(
                    "CREATE TABLE IF NOT EXISTS study_checkin "
                    "(checkin_id TEXT PRIMARY KEY, configuration_id TEXT NOT NULL "
                    "REFERENCES checkin_configuration(configuration_id), "
                    "request_json TEXT NOT NULL, payload_json TEXT NOT NULL)"
                )
                for table in ("checkin_configuration", "study_checkin"):
                    for operation in ("UPDATE", "DELETE"):
                        self.connection.execute(
                            f"CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()} "
                            f"BEFORE {operation} ON {table} BEGIN "
                            "SELECT RAISE(ABORT, 'check-in records are immutable'); END"
                        )
            self.connection.execute("PRAGMA foreign_keys = ON")
        except BaseException:
            self.connection.close()
            raise

    def submit(
        self, request: dict, config: EventConfiguration, captured_at: datetime
    ) -> tuple[dict, bool]:
        """Validate and save atomically; an exact retry keeps its first timestamp."""
        if not isinstance(request, dict):
            raise StudyValidationError("check-in must be a JSON object")
        allowed = {
            "checkin_id",
            "event",
            "observed_at",
            "wake_at",
            "status",
            "rating",
            "google_seen",
            "acted_on",
            "context",
            "note",
            "reported_late",
        }
        if set(request) - allowed:
            raise StudyValidationError("check-in contains unknown fields")
        try:
            checkin_id = str(UUID(request["checkin_id"]))
        except (KeyError, ValueError, TypeError, AttributeError) as error:
            raise StudyValidationError("checkin_id must be a UUID") from error
        config_json = _json(configuration_payload(config))
        config_id = hashlib.sha256(config_json.encode()).hexdigest()
        try:
            request_json = _json(request)
        except (TypeError, ValueError) as error:
            raise StudyValidationError(
                "check-in must contain valid JSON values"
            ) from error
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute(
                "SELECT * FROM study_checkin WHERE checkin_id = ?", (checkin_id,)
            ).fetchone()
            if existing:
                if (
                    existing["request_json"] != request_json
                    or existing["configuration_id"] != config_id
                ):
                    raise CheckInConflictError("check-in identity has changed content")
                payload, inserted = json.loads(existing["payload_json"]), False
            else:
                payload = self._validate(request, checkin_id, config, captured_at)
                payload["configuration_id"] = config_id
                self.connection.execute(
                    "INSERT OR IGNORE INTO checkin_configuration VALUES (?, ?)",
                    (config_id, config_json),
                )
                self.connection.execute(
                    "INSERT INTO study_checkin VALUES (?, ?, ?, ?)",
                    (checkin_id, config_id, request_json, _json(payload)),
                )
                inserted = True
            self.connection.commit()
            return payload, inserted
        except BaseException:
            self.connection.rollback()
            raise

    @staticmethod
    def _validate(
        request: dict,
        identity: str,
        config: EventConfiguration,
        captured_at: datetime,
        *,
        capture_method: str = "phone_form",
    ) -> dict:
        zone = ZoneInfo(config.timezone)
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise StudyValidationError("captured_at must include a UTC offset")
        captured_at = captured_at.astimezone(zone)
        try:
            event = EventType(request["event"])
            status = RecordStatus(request["status"])
            seen = ExposureState(request.get("google_seen", "unsure"))
            acted = ActionState(request.get("acted_on", "unknown"))
        except (ValueError, KeyError, TypeError) as error:
            raise StudyValidationError(
                "event, status, or exposure is invalid"
            ) from error
        observed = _instant(request.get("observed_at"), zone, "observed_at")
        if captured_at.timestamp() < observed.timestamp():
            raise StudyValidationError("captured_at cannot precede observed_at")
        label = PersonalLabel(
            label_id=identity,
            target=TARGETS[event],
            local_date=observed.date(),
            timezone=config.timezone,
            observed_at=observed,
            captured_at=captured_at,
            status=status,
            prompt_version=f"{TARGETS[event].value}-1.0.0",
            rating=request.get("rating"),
            capture_method=capture_method,
        )
        wake = (
            _instant(request["wake_at"], zone, "wake_at")
            if request.get("wake_at") is not None
            else None
        )
        if wake is not None and wake.timestamp() > observed.timestamp():
            raise StudyValidationError("wake_at cannot follow the described event")
        context_values = request.get("context", {})
        if not isinstance(context_values, dict):
            raise StudyValidationError("context must be an object")
        context_fields = set(ContextObservation.__dataclass_fields__) - {
            "context_id",
            "local_date",
            "captured_at",
        }
        if set(context_values) - context_fields:
            raise StudyValidationError("context contains unknown fields")
        if (
            context_values.get("caffeine_after_cutoff") is not None
            and config.caffeine_cutoff_local_time is None
        ):
            raise StudyValidationError(
                "configure a caffeine cutoff before recording it"
            )
        for name, value in context_values.items():
            if name in {"exercise_level", "academic_stress", "alcohol"}:
                if value is not None and not isinstance(value, str):
                    raise StudyValidationError(f"{name} must be text or null")
            else:
                if value is not None and not isinstance(value, bool):
                    raise StudyValidationError(f"{name} must be boolean or null")
        context = ContextObservation(
            context_id=identity,
            local_date=observed.date(),
            captured_at=captured_at,
            **context_values,
        )
        exposure = PredictionExposure(
            exposure_id=identity,
            target=label.target,
            provider="google_health",
            seen_before_label=seen,
            recommendation_acted_on=acted,
            captured_at=captured_at,
        )
        note = request.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > 2000):
            raise StudyValidationError("note must be text of at most 2000 characters")
        reported_late = request.get("reported_late", False)
        if not isinstance(reported_late, bool):
            raise StudyValidationError("reported_late must be boolean")
        window = next(w for w in config.windows if w.event_type is event)
        timing = "manual"
        if window.trigger is TriggerKind.RELATIVE_TO_WAKE:
            timing = "unanchored"
            if wake is not None:
                # Subtract UTC instants: elapsed hours remain correct across DST.
                elapsed = captured_at.timestamp() - wake.timestamp()
                assert window.opens_after_wake is not None
                assert window.closes_after_wake is not None
                timing = (
                    "early"
                    if elapsed < window.opens_after_wake.total_seconds()
                    else "late"
                    if elapsed > window.closes_after_wake.total_seconds()
                    else "on_time"
                )
        return json.loads(
            _json(
                {
                    "schema_version": 1,
                    "checkin_id": identity,
                    "event": event,
                    "label": asdict(label),
                    "context": asdict(context),
                    "exposure": asdict(exposure),
                    "note": note,
                    "wake_at": wake,
                    "window_status": timing,
                    "reported_late": reported_late,
                    "capture_delay_seconds": (
                        captured_at.timestamp() - observed.timestamp()
                    ),
                    # Backfilled context/exposure became usable only at capture.
                    "available_at": captured_at,
                }
            )
        )

    def all_checkins(self) -> list[dict]:
        """Read private records in insertion order for later analysis."""
        return [
            json.loads(row[0])
            for row in self.connection.execute(
                "SELECT payload_json FROM study_checkin ORDER BY rowid"
            )
        ]

    def close(self) -> None:
        self.connection.close()


def private_database_path(path: Path) -> Path:
    """Refuse a personal database anywhere inside a Git checkout."""
    resolved = path.expanduser().resolve()
    if any((parent / ".git").exists() for parent in resolved.parents):
        raise StudyValidationError("choose a database outside every Git checkout")
    return resolved
