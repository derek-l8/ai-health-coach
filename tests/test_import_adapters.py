"""Format-neutral import adapter selection and provenance checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from ai_health_coach.import_adapters import (
    AdapterRegistry,
    AmbiguousAdapterError,
    ImportBatch,
    ImportedRecord,
    NoAdapterError,
    SourceArtifact,
)


@dataclass(frozen=True)
class _FixtureAdapter:
    adapter_id: str
    schema_version: str
    accepted_media_type: str

    def supports(self, artifact: SourceArtifact) -> bool:
        return artifact.media_type == self.accepted_media_type

    def parse(self, artifact: SourceArtifact) -> ImportBatch:
        instant = datetime.fromisoformat("2026-01-05T07:00:00-08:00")
        return ImportBatch(
            adapter_id=self.adapter_id,
            schema_version=self.schema_version,
            artifact_id=artifact.artifact_id,
            records=(
                ImportedRecord(
                    record_type="synthetic_metric",
                    source_record_id="row-1",
                    observed_at=instant,
                    available_at=instant,
                    fields=(("value", 7.0),),
                ),
            ),
        )


def _artifact(media_type: str = "application/x-synthetic") -> SourceArtifact:
    return SourceArtifact(
        artifact_id="artifact-1",
        media_type=media_type,
        captured_at=datetime.fromisoformat("2026-01-05T07:30:00-08:00"),
        content=b"synthetic",
    )


def test_registry_selects_one_verified_adapter() -> None:
    adapter = _FixtureAdapter(
        "synthetic-adapter-1", "synthetic-schema-1", "application/x-synthetic"
    )
    batch = AdapterRegistry((adapter,)).parse(_artifact())

    assert batch.adapter_id == adapter.adapter_id
    assert batch.records[0].fields == (("value", 7.0),)


def test_registry_refuses_to_guess_unknown_or_ambiguous_formats() -> None:
    adapter_one = _FixtureAdapter("one", "v1", "application/x-synthetic")
    adapter_two = _FixtureAdapter("two", "v1", "application/x-synthetic")
    with pytest.raises(NoAdapterError):
        AdapterRegistry((adapter_one,)).parse(_artifact("application/unknown"))
    with pytest.raises(AmbiguousAdapterError):
        AdapterRegistry((adapter_one, adapter_two)).parse(_artifact())
