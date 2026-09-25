"""Format-neutral import boundaries for sources that are not yet verified."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


class AdapterError(ValueError):
    """Base error for adapter discovery or parsing."""


class NoAdapterError(AdapterError):
    """Raised when no registered adapter claims a source artifact."""


class AmbiguousAdapterError(AdapterError):
    """Raised when more than one adapter claims the same source artifact."""


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    """Opaque private source bytes plus the metadata needed for routing."""

    artifact_id: str
    media_type: str
    captured_at: datetime
    content: bytes

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise AdapterError("artifact_id must be non-empty")
        if not self.media_type.strip():
            raise AdapterError("media_type must be non-empty")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise AdapterError("captured_at must be offset-aware")
        if not isinstance(self.content, bytes):
            raise AdapterError("content must be bytes")


@dataclass(frozen=True, slots=True)
class ImportedRecord:
    """A format-neutral parsed record retaining adapter provenance."""

    record_type: str
    source_record_id: str
    observed_at: datetime
    available_at: datetime
    fields: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        if not self.record_type.strip() or not self.source_record_id.strip():
            raise AdapterError("record identity must be non-empty")
        for field in ("observed_at", "available_at"):
            value = getattr(self, field)
            if value.tzinfo is None or value.utcoffset() is None:
                raise AdapterError(f"{field} must be offset-aware")


@dataclass(frozen=True, slots=True)
class ImportBatch:
    """One adapter result without assumptions about a provider's final schema."""

    adapter_id: str
    schema_version: str
    artifact_id: str
    records: tuple[ImportedRecord, ...]


@runtime_checkable
class ImportAdapter(Protocol):
    """Interface implemented only after a real source format is verified."""

    adapter_id: str
    schema_version: str

    def supports(self, artifact: SourceArtifact) -> bool:
        """Return whether this adapter recognizes the artifact."""

    def parse(self, artifact: SourceArtifact) -> ImportBatch:
        """Validate and normalize the recognized artifact."""


@dataclass(frozen=True, slots=True)
class AdapterRegistry:
    """Select exactly one adapter rather than guessing a source format."""

    adapters: tuple[ImportAdapter, ...]

    def adapter_for(self, artifact: SourceArtifact) -> ImportAdapter:
        matches = [adapter for adapter in self.adapters if adapter.supports(artifact)]
        if not matches:
            raise NoAdapterError(
                f"no adapter recognizes media type {artifact.media_type!r}"
            )
        if len(matches) > 1:
            identifiers = sorted(adapter.adapter_id for adapter in matches)
            raise AmbiguousAdapterError(
                f"multiple adapters recognize artifact: {identifiers}"
            )
        return matches[0]

    def parse(self, artifact: SourceArtifact) -> ImportBatch:
        adapter = self.adapter_for(artifact)
        batch = adapter.parse(artifact)
        if batch.adapter_id != adapter.adapter_id:
            raise AdapterError("batch adapter_id does not match selected adapter")
        if batch.schema_version != adapter.schema_version:
            raise AdapterError("batch schema_version does not match selected adapter")
        if batch.artifact_id != artifact.artifact_id:
            raise AdapterError("batch artifact_id does not match source artifact")
        return batch
