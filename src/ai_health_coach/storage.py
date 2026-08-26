"""Transactional SQLite storage for observations and immutable score snapshots."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from ai_health_coach.observations import MetricObservation
from ai_health_coach.provider_scores import ProviderScoreComparison
from ai_health_coach.sleep_context import NightlyScoringContext
from ai_health_coach.sleep_feedback import DailySleepFeedback
from ai_health_coach.sleep_scores import SleepScore


class DuplicateObservationConflictError(ValueError):
    """Raised when an identifier is replayed with a different payload."""


class DuplicateSleepScoreConflictError(ValueError):
    """Raised when a score identifier is replayed with a different snapshot."""


class DuplicateSleepFeedbackConflictError(ValueError):
    """Raised when a feedback identifier is replayed with different content."""


class MissingEnergyPredictionError(ValueError):
    """Raised when feedback does not reference a stored Energy prediction."""


class DuplicateSleepContextConflictError(ValueError):
    """Raised when a nightly context identity or score linkage conflicts."""


class InvalidSleepContextScoresError(ValueError):
    """Raised when a context does not reference its three expected score types."""


class DuplicateProviderComparisonConflictError(ValueError):
    """Raised when a provider comparison identifier is replayed differently."""


class StoreSchemaVersionError(RuntimeError):
    """Raised when a database was created by unsupported newer code."""


class ObservationStore:
    """Store canonical observations and formula-neutral sleep-score snapshots."""

    SCHEMA_VERSION = 5

    def __init__(self, database: Path | str = ":memory:") -> None:
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        try:
            self._initialize()
        except BaseException:
            self.connection.close()
            raise

    def _initialize(self) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version > self.SCHEMA_VERSION:
                raise StoreSchemaVersionError(
                    f"database schema version {version} is newer than supported "
                    f"version {self.SCHEMA_VERSION}"
                )
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
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_sleep_feedback (
                    id INTEGER PRIMARY KEY,
                    feedback_id TEXT NOT NULL UNIQUE,
                    energy_score_id TEXT NOT NULL UNIQUE,
                    local_date TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    perceived_energy INTEGER CHECK (
                        perceived_energy IS NULL OR
                        perceived_energy BETWEEN 1 AND 10
                    ),
                    perceived_recovery INTEGER CHECK (
                        perceived_recovery IS NULL OR
                        perceived_recovery BETWEEN 1 AND 10
                    ),
                    sleep_quality INTEGER CHECK (
                        sleep_quality IS NULL OR sleep_quality BETWEEN 1 AND 10
                    ),
                    note TEXT,
                    FOREIGN KEY (energy_score_id) REFERENCES sleep_score(score_id)
                )
                """
            )
            columns = {
                row[1]
                for row in self.connection.execute(
                    "PRAGMA table_info(metric_observation)"
                )
            }
            for column in (
                "source_platform",
                "recording_method",
                "device_manufacturer",
                "device_display_name",
            ):
                if column not in columns:
                    self.connection.execute(
                        f"ALTER TABLE metric_observation ADD COLUMN {column} TEXT"
                    )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sleep_score (
                    id INTEGER PRIMARY KEY,
                    score_id TEXT NOT NULL UNIQUE,
                    score_type TEXT NOT NULL CHECK (
                        score_type IN ('efficiency', 'recovery', 'energy')
                    ),
                    value REAL NOT NULL CHECK (value >= 0 AND value <= 100),
                    confidence REAL NOT NULL CHECK (
                        confidence >= 0 AND confidence <= 1
                    ),
                    completeness REAL NOT NULL CHECK (
                        completeness >= 0 AND completeness <= 1
                    ),
                    inputs_json TEXT NOT NULL,
                    missing_inputs_json TEXT NOT NULL,
                    limitations_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    algorithm_version TEXT NOT NULL,
                    calibration_revision TEXT NOT NULL,
                    calculated_at TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS nightly_scoring_context (
                    id INTEGER PRIMARY KEY,
                    context_id TEXT NOT NULL UNIQUE,
                    local_date TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    sleep_window_start TEXT NOT NULL,
                    sleep_window_end TEXT NOT NULL,
                    input_data_cutoff TEXT NOT NULL,
                    efficiency_score_id TEXT NOT NULL UNIQUE,
                    recovery_score_id TEXT NOT NULL UNIQUE,
                    energy_score_id TEXT NOT NULL UNIQUE,
                    FOREIGN KEY (efficiency_score_id) REFERENCES sleep_score(score_id),
                    FOREIGN KEY (recovery_score_id) REFERENCES sleep_score(score_id),
                    FOREIGN KEY (energy_score_id) REFERENCES sleep_score(score_id)
                )
                """
            )
            self.connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS require_score_types_for_context
                BEFORE INSERT ON nightly_scoring_context
                WHEN (
                    SELECT score_type FROM sleep_score
                    WHERE score_id = NEW.efficiency_score_id
                ) IS NOT 'efficiency'
                   OR (
                    SELECT score_type FROM sleep_score
                    WHERE score_id = NEW.recovery_score_id
                ) IS NOT 'recovery'
                   OR (
                    SELECT score_type FROM sleep_score
                    WHERE score_id = NEW.energy_score_id
                ) IS NOT 'energy'
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'nightly context requires all three expected score types'
                    );
                END
                """
            )
            self.connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS prevent_nightly_scoring_context_update
                BEFORE UPDATE ON nightly_scoring_context
                BEGIN
                    SELECT RAISE(ABORT, 'nightly scoring contexts are immutable');
                END
                """
            )
            self.connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS require_matching_context_for_feedback
                BEFORE INSERT ON daily_sleep_feedback
                WHEN NOT EXISTS (
                    SELECT 1 FROM nightly_scoring_context
                    WHERE energy_score_id = NEW.energy_score_id
                      AND local_date = NEW.local_date
                      AND timezone = NEW.timezone
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'feedback requires a matching nightly scoring context'
                    );
                END
                """
            )
            self.connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS require_energy_prediction_for_feedback
                BEFORE INSERT ON daily_sleep_feedback
                WHEN (
                    SELECT score_type FROM sleep_score
                    WHERE score_id = NEW.energy_score_id
                ) IS NOT 'energy'
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'feedback requires an existing predicted Energy score'
                    );
                END
                """
            )
            self.connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS prevent_daily_sleep_feedback_update
                BEFORE UPDATE ON daily_sleep_feedback
                BEGIN
                    SELECT RAISE(ABORT, 'daily sleep feedback is immutable');
                END
                """
            )
            self.connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS prevent_sleep_score_update
                BEFORE UPDATE ON sleep_score
                BEGIN
                    SELECT RAISE(ABORT, 'sleep score snapshots are immutable');
                END
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_score_comparison (
                    id INTEGER PRIMARY KEY,
                    comparison_id TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL,
                    score_label TEXT NOT NULL,
                    value REAL,
                    unit TEXT,
                    local_date TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    source_observation_id TEXT
                )
                """
            )
            self.connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS prevent_provider_comparison_update
                BEFORE UPDATE ON provider_score_comparison
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'provider score comparisons are immutable'
                    );
                END
                """
            )
            self.connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def ingest(self, observations: Iterable[MetricObservation]) -> int:
        """Atomically insert a batch, accepting only equivalent replays."""
        batch = list(observations)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
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
            inserted = self.connection.total_changes - before
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()
            return inserted

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

    def store_sleep_scores(self, scores: Iterable[SleepScore]) -> int:
        """Atomically store immutable score snapshots with idempotent replay."""
        batch = list(scores)
        payloads = [(score, self._sleep_score_payload(score)) for score in batch]
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            before = self.connection.total_changes
            for score, payload in payloads:
                existing = self.connection.execute(
                    "SELECT * FROM sleep_score WHERE score_id = ?", (score.score_id,)
                ).fetchone()
                if existing is not None:
                    if all(existing[key] == value for key, value in payload.items()):
                        continue
                    raise DuplicateSleepScoreConflictError(
                        "conflicting payload for existing sleep score identifier"
                    )
                columns = ", ".join(payload)
                placeholders = ", ".join("?" for _ in payload)
                self.connection.execute(
                    f"INSERT INTO sleep_score ({columns}) VALUES ({placeholders})",
                    tuple(payload.values()),
                )
            inserted = self.connection.total_changes - before
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()
            return inserted

    @staticmethod
    def _sleep_score_payload(score: SleepScore) -> dict[str, object]:
        def encode(value: object) -> str:
            return json.dumps(value, separators=(",", ":"), ensure_ascii=False)

        inputs = [
            {
                "name": item.name,
                "value": item.value,
                "unit": item.unit,
                "observations": [
                    {
                        "source": reference.source,
                        "source_observation_id": reference.source_observation_id,
                    }
                    for reference in item.observations
                ],
            }
            for item in score.inputs
        ]
        return {
            "score_id": score.score_id,
            "score_type": score.score_type,
            "value": score.value,
            "confidence": score.confidence,
            "completeness": score.completeness,
            "inputs_json": encode(inputs),
            "missing_inputs_json": encode(score.missing_inputs),
            "limitations_json": encode(score.limitations),
            "evidence_json": encode(score.evidence),
            "algorithm_version": score.algorithm_version,
            "calibration_revision": score.calibration_revision,
            "calculated_at": score.calculated_at.isoformat(),
        }

    def all_sleep_scores(self) -> list[sqlite3.Row]:
        """Return score snapshots in deterministic insertion order."""
        return list(self.connection.execute("SELECT * FROM sleep_score ORDER BY id"))

    def store_nightly_contexts(self, contexts: Iterable[NightlyScoringContext]) -> int:
        """Store immutable nightly groupings after all three scores exist."""
        batch = list(contexts)
        payloads = [self._nightly_context_payload(item) for item in batch]
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            before = self.connection.total_changes
            for context, payload in zip(batch, payloads, strict=True):
                expected = {
                    context.efficiency_score_id: "efficiency",
                    context.recovery_score_id: "recovery",
                    context.energy_score_id: "energy",
                }
                rows = self.connection.execute(
                    """
                    SELECT score_id, score_type, calculated_at FROM sleep_score
                    WHERE score_id IN (?, ?, ?)
                    """,
                    tuple(expected),
                ).fetchall()
                actual = {row["score_id"]: row["score_type"] for row in rows}
                if actual != expected or any(
                    datetime.fromisoformat(row["calculated_at"])
                    < context.input_data_cutoff
                    for row in rows
                ):
                    raise InvalidSleepContextScoresError(
                        "context requires correctly typed scores calculated at or "
                        "after the input data cutoff"
                    )
                existing = self.connection.execute(
                    """
                    SELECT * FROM nightly_scoring_context
                    WHERE context_id = ? OR efficiency_score_id = ?
                       OR recovery_score_id = ? OR energy_score_id = ?
                    """,
                    (
                        context.context_id,
                        context.efficiency_score_id,
                        context.recovery_score_id,
                        context.energy_score_id,
                    ),
                ).fetchone()
                if existing is not None:
                    if all(existing[key] == value for key, value in payload.items()):
                        continue
                    raise DuplicateSleepContextConflictError(
                        "conflicting nightly scoring context or score linkage"
                    )
                columns = ", ".join(payload)
                placeholders = ", ".join("?" for _ in payload)
                self.connection.execute(
                    f"INSERT INTO nightly_scoring_context ({columns}) "
                    f"VALUES ({placeholders})",
                    tuple(payload.values()),
                )
            inserted = self.connection.total_changes - before
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()
            return inserted

    @staticmethod
    def _nightly_context_payload(
        context: NightlyScoringContext,
    ) -> dict[str, object]:
        return {
            "context_id": context.context_id,
            "local_date": context.local_date.isoformat(),
            "timezone": context.timezone,
            "sleep_window_start": context.sleep_window_start.isoformat(),
            "sleep_window_end": context.sleep_window_end.isoformat(),
            "input_data_cutoff": context.input_data_cutoff.isoformat(),
            "efficiency_score_id": context.efficiency_score_id,
            "recovery_score_id": context.recovery_score_id,
            "energy_score_id": context.energy_score_id,
        }

    def all_nightly_contexts(self) -> list[sqlite3.Row]:
        """Return nightly contexts in deterministic insertion order."""
        return list(
            self.connection.execute("SELECT * FROM nightly_scoring_context ORDER BY id")
        )

    def store_sleep_feedback(
        self, feedback_records: Iterable[DailySleepFeedback]
    ) -> int:
        """Store feedback only after its distinct Energy prediction exists."""
        batch = list(feedback_records)
        payloads = [self._sleep_feedback_payload(item) for item in batch]
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            before = self.connection.total_changes
            for item, payload in zip(batch, payloads, strict=True):
                prediction = self.connection.execute(
                    """
                    SELECT score_type
                    FROM sleep_score
                    JOIN nightly_scoring_context AS context
                      ON context.energy_score_id = sleep_score.score_id
                    WHERE sleep_score.score_id = ?
                      AND context.local_date = ? AND context.timezone = ?
                    """,
                    (
                        item.energy_score_id,
                        item.local_date.isoformat(),
                        item.timezone,
                    ),
                ).fetchone()
                if prediction is None or prediction["score_type"] != "energy":
                    raise MissingEnergyPredictionError(
                        "feedback requires an existing predicted Energy score"
                    )
                existing = self.connection.execute(
                    """
                    SELECT * FROM daily_sleep_feedback
                    WHERE feedback_id = ? OR energy_score_id = ?
                    """,
                    (item.feedback_id, item.energy_score_id),
                ).fetchone()
                if existing is not None:
                    if all(existing[key] == value for key, value in payload.items()):
                        continue
                    raise DuplicateSleepFeedbackConflictError(
                        "conflicting payload for existing daily sleep feedback"
                    )
                columns = ", ".join(payload)
                placeholders = ", ".join("?" for _ in payload)
                self.connection.execute(
                    f"INSERT INTO daily_sleep_feedback ({columns}) "
                    f"VALUES ({placeholders})",
                    tuple(payload.values()),
                )
            inserted = self.connection.total_changes - before
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()
            return inserted

    @staticmethod
    def _sleep_feedback_payload(
        feedback: DailySleepFeedback,
    ) -> dict[str, object]:
        return {
            "feedback_id": feedback.feedback_id,
            "energy_score_id": feedback.energy_score_id,
            "local_date": feedback.local_date.isoformat(),
            "timezone": feedback.timezone,
            "submitted_at": feedback.submitted_at.isoformat(),
            "perceived_energy": feedback.perceived_energy,
            "perceived_recovery": feedback.perceived_recovery,
            "sleep_quality": feedback.sleep_quality,
            "note": feedback.note,
        }

    def all_sleep_feedback(self) -> list[sqlite3.Row]:
        """Return feedback snapshots in deterministic insertion order."""
        return list(
            self.connection.execute("SELECT * FROM daily_sleep_feedback ORDER BY id")
        )

    def store_provider_comparisons(
        self, comparisons: Iterable[ProviderScoreComparison]
    ) -> int:
        """Atomically store labeled provider comparisons with idempotent replay."""
        batch = list(comparisons)
        payloads = [self._provider_comparison_payload(item) for item in batch]
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            before = self.connection.total_changes
            for comparison, payload in zip(batch, payloads, strict=True):
                existing = self.connection.execute(
                    "SELECT * FROM provider_score_comparison WHERE comparison_id = ?",
                    (comparison.comparison_id,),
                ).fetchone()
                if existing is not None:
                    if all(existing[key] == value for key, value in payload.items()):
                        continue
                    raise DuplicateProviderComparisonConflictError(
                        "conflicting payload for existing provider score comparison"
                    )
                columns = ", ".join(payload)
                placeholders = ", ".join("?" for _ in payload)
                self.connection.execute(
                    f"INSERT INTO provider_score_comparison ({columns}) "
                    f"VALUES ({placeholders})",
                    tuple(payload.values()),
                )
            inserted = self.connection.total_changes - before
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()
            return inserted

    @staticmethod
    def _provider_comparison_payload(
        comparison: ProviderScoreComparison,
    ) -> dict[str, object]:
        return {
            "comparison_id": comparison.comparison_id,
            "provider": comparison.provider,
            "score_label": comparison.score_label,
            "value": comparison.value,
            "unit": comparison.unit,
            "local_date": comparison.local_date.isoformat(),
            "timezone": comparison.timezone,
            "recorded_at": comparison.recorded_at.isoformat(),
            "source_observation_id": comparison.source_observation_id,
        }

    def all_provider_comparisons(self) -> list[sqlite3.Row]:
        """Return labeled provider comparisons in insertion order."""
        return list(
            self.connection.execute(
                "SELECT * FROM provider_score_comparison ORDER BY id"
            )
        )

    def close(self) -> None:
        """Close the owned SQLite connection."""
        self.connection.close()
