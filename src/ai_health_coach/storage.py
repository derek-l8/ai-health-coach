"""Transactional SQLite storage for canonical metric observations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from ai_health_coach.observations import MetricObservation


class DuplicateObservationConflictError(ValueError):
    """Raised when an identifier is replayed with a different payload."""


class ObservationStore:
    """Own a SQLite connection and idempotently ingest normalized observations."""

    def __init__(self, database: Path | str = ":memory:") -> None:
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_observation (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                source_observation_id TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                interval_start TEXT NOT NULL,
                interval_end TEXT NOT NULL,
                value REAL,
                unit TEXT,
                timezone TEXT NOT NULL,
                quality_status TEXT NOT NULL,
                source_platform TEXT,
                recording_method TEXT,
                device_manufacturer TEXT,
                device_display_name TEXT,
                UNIQUE(source, source_observation_id)
            )
            """
        )
        columns = {
            row[1]
            for row in self.connection.execute("PRAGMA table_info(metric_observation)")
        }
        if "source_platform" not in columns:
            self.connection.execute(
                "ALTER TABLE metric_observation ADD COLUMN source_platform TEXT"
            )
        if "recording_method" not in columns:
            self.connection.execute(
                "ALTER TABLE metric_observation ADD COLUMN recording_method TEXT"
            )
        if "device_manufacturer" not in columns:
            self.connection.execute(
                "ALTER TABLE metric_observation ADD COLUMN device_manufacturer TEXT"
            )
        if "device_display_name" not in columns:
            self.connection.execute(
                "ALTER TABLE metric_observation ADD COLUMN device_display_name TEXT"
            )
        self.connection.commit()

    def ingest(self, observations: Iterable[MetricObservation]) -> int:
        """Atomically insert a batch, accepting only equivalent replays."""
        batch = list(observations)
        with self.connection:
            before = self.connection.total_changes
            for observation in batch:
                existing = self.connection.execute(
                    """
                    SELECT source, source_observation_id, metric_type, interval_start,
                           interval_end, value, unit, timezone, quality_status,
                           source_platform, recording_method, device_manufacturer,
                           device_display_name
                    FROM metric_observation
                    WHERE source = ? AND source_observation_id = ?
                    """,
                    (observation.source, observation.source_observation_id),
                ).fetchone()
                if existing is not None:
                    if self._matches_existing(existing, observation):
                        continue
                    raise DuplicateObservationConflictError(
                        "conflicting payload for existing source observation identifier"
                    )
                self.connection.execute(
                    """
                    INSERT INTO metric_observation (
                        source, source_observation_id, metric_type, interval_start,
                        interval_end, value, unit, timezone, quality_status,
                        source_platform, recording_method, device_manufacturer,
                        device_display_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation.source,
                        observation.source_observation_id,
                        observation.metric_type,
                        observation.interval_start.isoformat(),
                        observation.interval_end.isoformat(),
                        observation.value,
                        observation.unit,
                        observation.timezone,
                        observation.quality_status,
                        observation.source_platform,
                        observation.recording_method,
                        observation.device_manufacturer,
                        observation.device_display_name,
                    ),
                )
            return self.connection.total_changes - before

    @staticmethod
    def _matches_existing(
        existing: sqlite3.Row, observation: MetricObservation
    ) -> bool:
        return (
            existing["metric_type"] == observation.metric_type
            and existing["interval_start"] == observation.interval_start.isoformat()
            and existing["interval_end"] == observation.interval_end.isoformat()
            and existing["value"] == observation.value
            and existing["unit"] == observation.unit
            and existing["timezone"] == observation.timezone
            and existing["quality_status"] == observation.quality_status
            and existing["source_platform"] == observation.source_platform
            and existing["recording_method"] == observation.recording_method
            and existing["device_manufacturer"] == observation.device_manufacturer
            and existing["device_display_name"] == observation.device_display_name
        )

    def all_observations(self) -> list[sqlite3.Row]:
        """Return observations in deterministic insertion order for consumers/tests."""
        return list(
            self.connection.execute("SELECT * FROM metric_observation ORDER BY id")
        )

    def close(self) -> None:
        """Close the owned SQLite connection."""
        self.connection.close()
