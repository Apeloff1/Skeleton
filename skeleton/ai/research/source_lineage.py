"""Correction-aware research source lineage for P3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Mapping, Sequence


class ResearchLineageError(RuntimeError):
    pass


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ResearchLineageError("research lineage must be deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchLineageError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ResearchLineageError(f"{name} exceeds {maximum} characters")
    return result


def content_digest(content: str) -> str:
    return hashlib.sha256(_text("content", content, 2_000_000).encode("utf-8")).hexdigest()


class SourceStatus(str, Enum):
    ACTIVE = "active"
    CORRECTED = "corrected"
    RETRACTED = "retracted"


@dataclass(frozen=True, slots=True)
class ResearchSource:
    source_id: str
    uri: str
    content_digest: str
    status: SourceStatus
    rights_refs: tuple[str, ...]
    correction_refs: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id, 256))
        object.__setattr__(self, "uri", _text("uri", self.uri, 2048))
        if len(self.content_digest) != 64 or any(ch not in "0123456789abcdef" for ch in self.content_digest):
            raise ResearchLineageError("content_digest must be lowercase sha256")
        if not isinstance(self.status, SourceStatus):
            object.__setattr__(self, "status", SourceStatus(str(self.status)))
        rights = tuple(dict.fromkeys(_text("rights_ref", item, 512) for item in self.rights_refs))
        if not rights:
            raise ResearchLineageError("research source requires rights evidence")
        object.__setattr__(self, "rights_refs", rights)
        corrections = tuple(dict.fromkeys(_text("correction_ref", item, 512) for item in self.correction_refs))
        if self.status is not SourceStatus.ACTIVE and not corrections:
            raise ResearchLineageError("corrected/retracted source requires correction refs")
        object.__setattr__(self, "correction_refs", corrections)
        object.__setattr__(self, "supersedes", tuple(dict.fromkeys(_text("supersedes", item, 256) for item in self.supersedes)))
        frozen = {} if self.metadata is None else dict(self.metadata)
        _json(frozen)
        object.__setattr__(self, "metadata", frozen)

    @classmethod
    def from_content(
        cls,
        *,
        source_id: str,
        uri: str,
        content: str,
        rights_refs: Sequence[str],
        status: SourceStatus = SourceStatus.ACTIVE,
        correction_refs: Sequence[str] = (),
        supersedes: Sequence[str] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> "ResearchSource":
        return cls(
            source_id=source_id,
            uri=uri,
            content_digest=content_digest(content),
            status=status,
            rights_refs=tuple(rights_refs),
            correction_refs=tuple(correction_refs),
            supersedes=tuple(supersedes),
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class ResearchClaim:
    claim_id: str
    statement: str
    source_ids: tuple[str, ...]
    source_digests: tuple[str, ...]
    lineage_digest: str


class ResearchSourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, ResearchSource] = {}
        self._claims: dict[str, ResearchClaim] = {}
        self._source_claims: dict[str, set[str]] = {}

    def register(self, source: ResearchSource) -> ResearchSource:
        if not isinstance(source, ResearchSource):
            raise TypeError("source must be ResearchSource")
        prior = self._sources.get(source.source_id)
        if prior is not None and prior != source:
            raise ResearchLineageError("source identity conflict")
        for predecessor in source.supersedes:
            if predecessor not in self._sources:
                raise ResearchLineageError(f"superseded source is not registered: {predecessor}")
        self._sources[source.source_id] = source
        return source

    def source(self, source_id: str) -> ResearchSource:
        return self._sources[_text("source_id", source_id, 256)]

    def create_claim(self, *, claim_id: str, statement: str, source_ids: Sequence[str]) -> ResearchClaim:
        ids = tuple(dict.fromkeys(_text("source_id", item, 256) for item in source_ids))
        if not ids:
            raise ResearchLineageError("research claim requires at least one source")
        sources: list[ResearchSource] = []
        for source_id in ids:
            source = self._sources.get(source_id)
            if source is None:
                raise ResearchLineageError(f"unregistered research source: {source_id}")
            if source.status is not SourceStatus.ACTIVE:
                raise ResearchLineageError(f"non-active research source cannot support current claim: {source_id}")
            sources.append(source)
        text = _text("statement", statement)
        digests = tuple(source.content_digest for source in sources)
        lineage = _digest({
            "claim_id": claim_id,
            "statement": text,
            "sources": [
                {"source_id": source.source_id, "digest": source.content_digest, "rights_refs": list(source.rights_refs)}
                for source in sources
            ],
        })
        claim = ResearchClaim(_text("claim_id", claim_id, 256), text, ids, digests, lineage)
        prior = self._claims.get(claim.claim_id)
        if prior is not None and prior != claim:
            raise ResearchLineageError("claim identity conflict")
        self._claims[claim.claim_id] = claim
        for source_id in ids:
            self._source_claims.setdefault(source_id, set()).add(claim.claim_id)
        return claim

    def reconcile_claim(self, claim_id: str) -> bool:
        claim = self._claims[_text("claim_id", claim_id, 256)]
        for source_id, digest in zip(claim.source_ids, claim.source_digests):
            source = self._sources.get(source_id)
            if source is None or source.status is not SourceStatus.ACTIVE or source.content_digest != digest:
                return False
        return True

    def affected_claims(self, source_id: str) -> tuple[str, ...]:
        self.source(source_id)
        return tuple(sorted(self._source_claims.get(source_id, ())))


__all__ = [
    "ResearchClaim",
    "ResearchLineageError",
    "ResearchSource",
    "ResearchSourceRegistry",
    "SourceStatus",
    "content_digest",
]
