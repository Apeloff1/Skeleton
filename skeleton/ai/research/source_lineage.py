"""Correction-aware research ingestion and citation lineage.

This module is deliberately authority-neutral: it records evidence lineage and detects
stale scientific support, but it cannot promote model/runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Mapping, Sequence


class ResearchLineageError(RuntimeError):
    """Raised when research evidence cannot be represented safely."""


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ResearchLineageError(
                    "research lineage JSON object keys must be text"
                )
            normalized[key] = _json_ready(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ResearchLineageError("research lineage must be deterministic JSON")


def _json(value: object) -> str:
    try:
        return json.dumps(
            _json_ready(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ResearchLineageError("research lineage must be deterministic JSON") from exc


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ResearchLineageError(
                    "research lineage JSON object keys must be text"
                )
            frozen[key] = _freeze_json(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        _json(value)
        return value
    raise ResearchLineageError("research lineage must be deterministic JSON")


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchLineageError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ResearchLineageError(f"{name} exceeds {maximum} characters")
    return result


def _sha256(name: str, value: object) -> str:
    digest = _text(name, value, 64)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ResearchLineageError(f"{name} must be lowercase sha256")
    return digest


def content_digest(content: str) -> str:
    return hashlib.sha256(_text("content", content, 2_000_000).encode("utf-8")).hexdigest()


class SourceStatus(str, Enum):
    ACTIVE = "active"
    CORRECTED = "corrected"
    RETRACTED = "retracted"


class CitationRelation(str, Enum):
    CITES = "cites"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REPLICATES = "replicates"
    CORRECTS = "corrects"


_DEPENDENCY_RELATIONS = frozenset(
    {
        CitationRelation.CITES,
        CitationRelation.SUPPORTS,
        CitationRelation.REPLICATES,
    }
)

_MAX_CITATIONS_PER_INGEST = 4096
_MAX_CLAIM_SOURCES = 512
_MAX_METADATA_BYTES = 64 * 1024


def _capacity(name: str, value: object, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ResearchLineageError(f"{name} must be an integer in [1,{maximum}]")
    return value


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
        object.__setattr__(self, "content_digest", _sha256("content_digest", self.content_digest))
        if not isinstance(self.status, SourceStatus):
            try:
                object.__setattr__(self, "status", SourceStatus(str(self.status)))
            except ValueError as exc:
                raise ResearchLineageError("invalid source status") from exc

        rights = tuple(dict.fromkeys(_text("rights_ref", item, 512) for item in self.rights_refs))
        if not rights:
            raise ResearchLineageError("research source requires rights evidence")
        object.__setattr__(self, "rights_refs", rights)

        corrections = tuple(
            dict.fromkeys(_text("correction_ref", item, 512) for item in self.correction_refs)
        )
        if self.status is not SourceStatus.ACTIVE and not corrections:
            raise ResearchLineageError("corrected/retracted source requires correction refs")
        object.__setattr__(self, "correction_refs", corrections)

        supersedes = tuple(
            dict.fromkeys(_text("supersedes", item, 256) for item in self.supersedes)
        )
        if self.source_id in supersedes:
            raise ResearchLineageError("source cannot supersede itself")
        object.__setattr__(self, "supersedes", supersedes)

        raw_metadata = {} if self.metadata is None else dict(self.metadata)
        frozen = _freeze_json(raw_metadata)
        metadata_json = _json(frozen)
        if len(metadata_json.encode("utf-8")) > _MAX_METADATA_BYTES:
            raise ResearchLineageError("research source metadata exceeds size limit")
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
    method: str = ""
    result: str = ""
    limitations: tuple[str, ...] = ()
    negative_result: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _text("claim_id", self.claim_id, 256))
        object.__setattr__(self, "statement", _text("statement", self.statement))
        source_ids = tuple(_text("source_id", item, 256) for item in self.source_ids)
        if not source_ids or len(source_ids) > _MAX_CLAIM_SOURCES:
            raise ResearchLineageError("research claim has invalid source count")
        if len(set(source_ids)) != len(source_ids):
            raise ResearchLineageError("research claim source ids must be unique")
        source_digests = tuple(
            _sha256("source_digest", item) for item in self.source_digests
        )
        if len(source_digests) != len(source_ids):
            raise ResearchLineageError("research claim source digests must align with sources")
        object.__setattr__(self, "source_ids", source_ids)
        object.__setattr__(self, "source_digests", source_digests)
        object.__setattr__(
            self,
            "lineage_digest",
            _sha256("lineage_digest", self.lineage_digest),
        )
        if not isinstance(self.method, str) or not isinstance(self.result, str):
            raise ResearchLineageError("claim method and result must be text")
        method = self.method.strip()
        result = self.result.strip()
        if len(method) > 4096 or len(result) > 16_384:
            raise ResearchLineageError("claim method/result exceeds bounded size")
        limitations = tuple(
            dict.fromkeys(_text("limitation", item, 2048) for item in self.limitations)
        )
        if len(limitations) > 64:
            raise ResearchLineageError("claim limitations exceed bounded count")
        if not isinstance(self.negative_result, bool):
            raise ResearchLineageError("negative_result must be boolean")
        if self.negative_result and not result:
            raise ResearchLineageError("negative result requires explicit result text")
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "limitations", limitations)


class ReplicationOutcome(str, Enum):
    REPLICATED = "replicated"
    FAILED = "failed"
    MIXED = "mixed"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class ReplicationRecord:
    replication_id: str
    source_id: str
    source_digest: str
    target_source_id: str
    target_digest: str
    outcome: ReplicationOutcome
    method: str
    result: str
    limitations: tuple[str, ...]
    negative_result: bool
    record_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "replication_id",
            _text("replication_id", self.replication_id, 256),
        )
        source_id = _text("source_id", self.source_id, 256)
        target_source_id = _text("target_source_id", self.target_source_id, 256)
        if source_id == target_source_id:
            raise ResearchLineageError("replication source and target must differ")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "target_source_id", target_source_id)
        object.__setattr__(
            self,
            "source_digest",
            _sha256("source_digest", self.source_digest),
        )
        object.__setattr__(
            self,
            "target_digest",
            _sha256("target_digest", self.target_digest),
        )
        if not isinstance(self.outcome, ReplicationOutcome):
            try:
                object.__setattr__(
                    self,
                    "outcome",
                    ReplicationOutcome(str(self.outcome)),
                )
            except ValueError as exc:
                raise ResearchLineageError("invalid replication outcome") from exc
        object.__setattr__(self, "method", _text("replication method", self.method, 4096))
        object.__setattr__(self, "result", _text("replication result", self.result, 16_384))
        limitations = tuple(
            dict.fromkeys(
                _text("replication limitation", item, 2048)
                for item in self.limitations
            )
        )
        if len(limitations) > 64:
            raise ResearchLineageError("replication limitations exceed bounded count")
        object.__setattr__(self, "limitations", limitations)
        if not isinstance(self.negative_result, bool):
            raise ResearchLineageError("replication negative_result must be boolean")
        expected_negative = self.outcome is ReplicationOutcome.FAILED
        if self.negative_result is not expected_negative:
            raise ResearchLineageError(
                "replication negative_result must match failed outcome"
            )
        object.__setattr__(
            self,
            "record_digest",
            _sha256("record_digest", self.record_digest),
        )


@dataclass(frozen=True, slots=True)
class RetractionRecord:
    source_id: str
    source_digest: str
    status: SourceStatus
    evidence_refs: tuple[str, ...]
    transition_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id, 256))
        object.__setattr__(
            self,
            "source_digest",
            _sha256("source_digest", self.source_digest),
        )
        if not isinstance(self.status, SourceStatus):
            try:
                object.__setattr__(self, "status", SourceStatus(str(self.status)))
            except ValueError as exc:
                raise ResearchLineageError("invalid source status") from exc
        if self.status is SourceStatus.ACTIVE:
            raise ResearchLineageError("status transition record cannot be active")
        refs = tuple(
            dict.fromkeys(_text("evidence_ref", item, 512) for item in self.evidence_refs)
        )
        if not refs:
            raise ResearchLineageError("status transition record requires evidence")
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(
            self,
            "transition_digest",
            _sha256("transition_digest", self.transition_digest),
        )


@dataclass(frozen=True, slots=True)
class HistoricalTechnique:
    technique_id: str
    problem: str
    mechanism: str
    failure_modes: tuple[str, ...]
    modern_analogues: tuple[str, ...]
    source_ids: tuple[str, ...]
    source_digests: tuple[str, ...]
    lineage_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "technique_id",
            _text("technique_id", self.technique_id, 256),
        )
        object.__setattr__(self, "problem", _text("historical problem", self.problem, 4096))
        object.__setattr__(
            self,
            "mechanism",
            _text("historical mechanism", self.mechanism, 8192),
        )
        failure_modes = tuple(
            dict.fromkeys(_text("failure mode", item, 2048) for item in self.failure_modes)
        )
        modern_analogues = tuple(
            dict.fromkeys(
                _text("modern analogue", item, 2048)
                for item in self.modern_analogues
            )
        )
        if not failure_modes:
            raise ResearchLineageError("historical technique requires failure modes")
        if not modern_analogues:
            raise ResearchLineageError("historical technique requires modern analogues")
        if len(failure_modes) > 64 or len(modern_analogues) > 64:
            raise ResearchLineageError("historical technique exceeds bounded evidence shape")
        source_ids = tuple(_text("source_id", item, 256) for item in self.source_ids)
        if not source_ids or len(source_ids) > 128:
            raise ResearchLineageError("historical technique has invalid source count")
        if len(set(source_ids)) != len(source_ids):
            raise ResearchLineageError("historical technique source ids must be unique")
        source_digests = tuple(
            _sha256("source_digest", item) for item in self.source_digests
        )
        if len(source_ids) != len(source_digests):
            raise ResearchLineageError(
                "historical technique source digests must align with sources"
            )
        object.__setattr__(self, "failure_modes", failure_modes)
        object.__setattr__(self, "modern_analogues", modern_analogues)
        object.__setattr__(self, "source_ids", source_ids)
        object.__setattr__(self, "source_digests", source_digests)
        object.__setattr__(
            self,
            "lineage_digest",
            _sha256("lineage_digest", self.lineage_digest),
        )


@dataclass(frozen=True, slots=True)
class CitationSpec:
    target_source_id: str
    relation: CitationRelation = CitationRelation.CITES
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_source_id",
            _text("target_source_id", self.target_source_id, 256),
        )
        if not isinstance(self.relation, CitationRelation):
            try:
                object.__setattr__(self, "relation", CitationRelation(str(self.relation)))
            except ValueError as exc:
                raise ResearchLineageError("invalid citation relation") from exc
        if self.evidence_ref is not None:
            object.__setattr__(
                self,
                "evidence_ref",
                _text("evidence_ref", self.evidence_ref, 1024),
            )


@dataclass(frozen=True, slots=True)
class CitationEdge:
    edge_id: str
    source_id: str
    source_digest: str
    target_source_id: str
    target_digest: str
    relation: CitationRelation
    evidence_ref: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_id", _sha256("edge_id", self.edge_id))
        object.__setattr__(self, "source_digest", _sha256("source_digest", self.source_digest))
        object.__setattr__(self, "target_digest", _sha256("target_digest", self.target_digest))


@dataclass(frozen=True, slots=True)
class IngestionReceipt:
    source_id: str
    source_digest: str
    citation_edge_ids: tuple[str, ...]
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class CitationGraphReport:
    total_edges: int
    valid_edges: int
    stale_edge_ids: tuple[str, ...]
    invalid_source_ids: tuple[str, ...]
    affected_claim_ids: tuple[str, ...]
    report_digest: str

    @property
    def healthy(self) -> bool:
        return not self.stale_edge_ids and not self.invalid_source_ids


class ResearchSourceRegistry:
    """Deterministic source/claim/citation registry.

    The registry is intentionally process-local. Persistence layers may serialize its
    receipts/snapshots, but source admission remains fail-closed and content-bound.
    """

    def __init__(
        self,
        *,
        max_sources: int = 100_000,
        max_claims: int = 100_000,
        max_edges: int = 500_000,
        max_replications: int = 100_000,
        max_historical_techniques: int = 50_000,
    ) -> None:
        self._max_sources = _capacity("max_sources", max_sources, maximum=1_000_000)
        self._max_claims = _capacity("max_claims", max_claims, maximum=1_000_000)
        self._max_edges = _capacity("max_edges", max_edges, maximum=5_000_000)
        self._max_replications = _capacity(
            "max_replications",
            max_replications,
            maximum=1_000_000,
        )
        self._max_historical_techniques = _capacity(
            "max_historical_techniques",
            max_historical_techniques,
            maximum=500_000,
        )
        self._sources: dict[str, ResearchSource] = {}
        self._claims: dict[str, ResearchClaim] = {}
        self._source_claims: dict[str, set[str]] = {}
        self._edges: dict[str, CitationEdge] = {}
        self._outgoing: dict[str, set[str]] = {}
        self._incoming: dict[str, set[str]] = {}
        self._replications: dict[str, ReplicationRecord] = {}
        self._status_records: dict[str, RetractionRecord] = {}
        self._historical_techniques: dict[str, HistoricalTechnique] = {}

    def register(self, source: ResearchSource) -> ResearchSource:
        if not isinstance(source, ResearchSource):
            raise TypeError("source must be ResearchSource")
        prior = self._sources.get(source.source_id)
        if prior is not None and prior != source:
            raise ResearchLineageError("source identity conflict")
        if prior is None and len(self._sources) >= self._max_sources:
            raise ResearchLineageError("research source registry capacity exceeded")
        for predecessor in source.supersedes:
            if predecessor not in self._sources:
                raise ResearchLineageError(f"superseded source is not registered: {predecessor}")
            if self._sources[predecessor].status is SourceStatus.ACTIVE:
                raise ResearchLineageError(
                    f"superseded source must be corrected or retracted first: {predecessor}"
                )
        self._sources[source.source_id] = source
        return source

    def transition_source_status(
        self,
        source_id: str,
        *,
        status: SourceStatus | str,
        correction_refs: Sequence[str],
    ) -> ResearchSource:
        source = self.source(source_id)
        try:
            next_status = status if isinstance(status, SourceStatus) else SourceStatus(str(status))
        except ValueError as exc:
            raise ResearchLineageError("invalid source status") from exc
        if next_status is SourceStatus.ACTIVE:
            raise ResearchLineageError("source status transitions cannot reactivate evidence")
        if source.status is not SourceStatus.ACTIVE:
            if source.status is next_status and tuple(correction_refs) == source.correction_refs:
                return source
            raise ResearchLineageError("source status transition is monotonic")
        updated = ResearchSource(
            source_id=source.source_id,
            uri=source.uri,
            content_digest=source.content_digest,
            status=next_status,
            rights_refs=source.rights_refs,
            correction_refs=tuple(correction_refs),
            supersedes=source.supersedes,
            metadata=source.metadata,
        )
        self._sources[source.source_id] = updated
        transition_payload = {
            "source_id": updated.source_id,
            "source_digest": updated.content_digest,
            "status": updated.status.value,
            "evidence_refs": list(updated.correction_refs),
        }
        record = RetractionRecord(
            source_id=updated.source_id,
            source_digest=updated.content_digest,
            status=updated.status,
            evidence_refs=updated.correction_refs,
            transition_digest=_digest(transition_payload),
        )
        self._status_records[record.transition_digest] = record
        return updated

    def status_records(self) -> tuple[RetractionRecord, ...]:
        return tuple(self._status_records[key] for key in sorted(self._status_records))

    def source(self, source_id: str) -> ResearchSource:
        key = _text("source_id", source_id, 256)
        try:
            return self._sources[key]
        except KeyError as exc:
            raise ResearchLineageError(f"unregistered research source: {key}") from exc

    def sources(self) -> tuple[ResearchSource, ...]:
        return tuple(self._sources[key] for key in sorted(self._sources))

    def create_claim(
        self,
        *,
        claim_id: str,
        statement: str,
        source_ids: Sequence[str],
        method: str = "",
        result: str = "",
        limitations: Sequence[str] = (),
        negative_result: bool = False,
    ) -> ResearchClaim:
        ids = tuple(dict.fromkeys(_text("source_id", item, 256) for item in source_ids))
        if not ids:
            raise ResearchLineageError("research claim requires at least one source")
        if len(ids) > _MAX_CLAIM_SOURCES:
            raise ResearchLineageError("research claim exceeds source fan-in limit")
        sources: list[ResearchSource] = []
        for source_id in ids:
            source = self._sources.get(source_id)
            if source is None:
                raise ResearchLineageError(f"unregistered research source: {source_id}")
            if source.status is not SourceStatus.ACTIVE:
                raise ResearchLineageError(
                    f"non-active research source cannot support current claim: {source_id}"
                )
            sources.append(source)

        text = _text("statement", statement)
        normalized_claim_id = _text("claim_id", claim_id, 256)
        if not isinstance(method, str) or not isinstance(result, str):
            raise ResearchLineageError("claim method and result must be text")
        normalized_method = method.strip()
        normalized_result = result.strip()
        if len(normalized_method) > 4096 or len(normalized_result) > 16_384:
            raise ResearchLineageError("claim method/result exceeds bounded size")
        normalized_limitations = tuple(
            dict.fromkeys(_text("limitation", item, 2048) for item in limitations)
        )
        if len(normalized_limitations) > 64:
            raise ResearchLineageError("claim limitations exceed bounded count")
        if not isinstance(negative_result, bool):
            raise ResearchLineageError("negative_result must be boolean")
        if negative_result and not normalized_result:
            raise ResearchLineageError("negative result requires explicit result text")

        digests = tuple(source.content_digest for source in sources)
        lineage_payload = {
            "claim_id": normalized_claim_id,
            "statement": text,
            "sources": [
                {
                    "source_id": source.source_id,
                    "digest": source.content_digest,
                    "rights_refs": list(source.rights_refs),
                }
                for source in sources
            ],
        }
        if normalized_method:
            lineage_payload["method"] = normalized_method
        if normalized_result:
            lineage_payload["result"] = normalized_result
        if normalized_limitations:
            lineage_payload["limitations"] = list(normalized_limitations)
        if negative_result:
            lineage_payload["negative_result"] = True
        lineage = _digest(lineage_payload)
        claim = ResearchClaim(
            normalized_claim_id,
            text,
            ids,
            digests,
            lineage,
            normalized_method,
            normalized_result,
            normalized_limitations,
            negative_result,
        )
        prior = self._claims.get(claim.claim_id)
        if prior is not None and prior != claim:
            raise ResearchLineageError("claim identity conflict")
        if prior is None and len(self._claims) >= self._max_claims:
            raise ResearchLineageError("research claim registry capacity exceeded")
        self._claims[claim.claim_id] = claim
        for source_id in ids:
            self._source_claims.setdefault(source_id, set()).add(claim.claim_id)
        return claim

    def claim(self, claim_id: str) -> ResearchClaim:
        key = _text("claim_id", claim_id, 256)
        try:
            return self._claims[key]
        except KeyError as exc:
            raise ResearchLineageError(f"unregistered research claim: {key}") from exc

    def reconcile_claim(self, claim_id: str) -> bool:
        claim = self.claim(claim_id)
        for source_id, digest in zip(claim.source_ids, claim.source_digests):
            source = self._sources.get(source_id)
            if (
                source is None
                or source.status is not SourceStatus.ACTIVE
                or source.content_digest != digest
            ):
                return False
        return True

    def reconcile_claim_with_graph(self, claim_id: str) -> bool:
        claim = self.claim(claim_id)
        if not self.reconcile_claim(claim_id):
            return False
        graph = self.reconcile_citation_graph()
        if graph.healthy:
            return True
        return claim.claim_id not in graph.affected_claim_ids

    def qualification_snapshot(self) -> Mapping[str, object]:
        """Return deterministic, authority-neutral reconciliation evidence."""
        graph = self.reconcile_citation_graph()
        claims = tuple(sorted(self._claims))
        replications = tuple(sorted(self._replications))
        techniques = tuple(sorted(self._historical_techniques))
        payload = {
            "snapshot_digest": self.snapshot_digest(),
            "citation_report_digest": graph.report_digest,
            "citation_graph_healthy": graph.healthy,
            "claim_results": {key: self.reconcile_claim_with_graph(key) for key in claims},
            "replication_results": {key: self.reconcile_replication(key) for key in replications},
            "historical_results": {key: self.reconcile_historical_technique(key) for key in techniques},
            "authority_scope": "research-evidence-only",
        }
        payload["qualification_digest"] = _digest(payload)
        return MappingProxyType(payload)

    def affected_claims(self, source_id: str) -> tuple[str, ...]:
        self.source(source_id)
        return tuple(sorted(self._source_claims.get(source_id, ())))

    def record_replication(
        self,
        *,
        replication_id: str,
        source_id: str,
        target_source_id: str,
        outcome: ReplicationOutcome | str,
        method: str,
        result: str,
        limitations: Sequence[str] = (),
    ) -> ReplicationRecord:
        source = self.source(source_id)
        target = self.source(target_source_id)
        if source.source_id == target.source_id:
            raise ResearchLineageError("replication source and target must differ")
        if source.status is not SourceStatus.ACTIVE:
            raise ResearchLineageError("replication evidence source must be active")
        try:
            normalized_outcome = (
                outcome
                if isinstance(outcome, ReplicationOutcome)
                else ReplicationOutcome(str(outcome))
            )
        except ValueError as exc:
            raise ResearchLineageError("invalid replication outcome") from exc
        normalized_id = _text("replication_id", replication_id, 256)
        normalized_method = _text("replication method", method, 4096)
        normalized_result = _text("replication result", result, 16_384)
        normalized_limitations = tuple(
            dict.fromkeys(_text("replication limitation", item, 2048) for item in limitations)
        )
        if len(normalized_limitations) > 64:
            raise ResearchLineageError("replication limitations exceed bounded count")
        payload = {
            "replication_id": normalized_id,
            "source_id": source.source_id,
            "source_digest": source.content_digest,
            "target_source_id": target.source_id,
            "target_digest": target.content_digest,
            "outcome": normalized_outcome.value,
            "method": normalized_method,
            "result": normalized_result,
            "limitations": list(normalized_limitations),
            "negative_result": normalized_outcome is ReplicationOutcome.FAILED,
        }
        record = ReplicationRecord(
            replication_id=normalized_id,
            source_id=source.source_id,
            source_digest=source.content_digest,
            target_source_id=target.source_id,
            target_digest=target.content_digest,
            outcome=normalized_outcome,
            method=normalized_method,
            result=normalized_result,
            limitations=normalized_limitations,
            negative_result=normalized_outcome is ReplicationOutcome.FAILED,
            record_digest=_digest(payload),
        )
        prior = self._replications.get(record.replication_id)
        if prior is not None and prior != record:
            raise ResearchLineageError("replication identity conflict")
        if prior is None and len(self._replications) >= self._max_replications:
            raise ResearchLineageError("replication registry capacity exceeded")
        self._replications[record.replication_id] = record
        return record

    def replication_records(
        self,
        target_source_id: str | None = None,
    ) -> tuple[ReplicationRecord, ...]:
        if target_source_id is None:
            records = self._replications.values()
        else:
            target = self.source(target_source_id)
            records = (
                record
                for record in self._replications.values()
                if record.target_source_id == target.source_id
            )
        return tuple(sorted(records, key=lambda record: record.replication_id))

    def reconcile_replication(self, replication_id: str) -> bool:
        key = _text("replication_id", replication_id, 256)
        record = self._replications.get(key)
        if record is None:
            raise ResearchLineageError(f"unregistered replication record: {key}")
        source = self._sources.get(record.source_id)
        target = self._sources.get(record.target_source_id)
        return bool(
            source is not None
            and target is not None
            and source.status is SourceStatus.ACTIVE
            and source.content_digest == record.source_digest
            and target.content_digest == record.target_digest
        )

    def replication_summary(self, target_source_id: str) -> dict[str, int]:
        target = self.source(target_source_id)
        counts = {outcome.value: 0 for outcome in ReplicationOutcome}
        negative_results = 0
        for record in self.replication_records(target.source_id):
            if not self.reconcile_replication(record.replication_id):
                continue
            counts[record.outcome.value] += 1
            if record.negative_result:
                negative_results += 1
        return {
            **counts,
            "negative_results": negative_results,
            "total_current": sum(counts.values()),
        }

    def register_historical_technique(
        self,
        *,
        technique_id: str,
        problem: str,
        mechanism: str,
        failure_modes: Sequence[str],
        modern_analogues: Sequence[str],
        source_ids: Sequence[str],
    ) -> HistoricalTechnique:
        normalized_id = _text("technique_id", technique_id, 256)
        normalized_problem = _text("historical problem", problem, 4096)
        normalized_mechanism = _text("historical mechanism", mechanism, 8192)
        normalized_failures = tuple(
            dict.fromkeys(_text("failure mode", item, 2048) for item in failure_modes)
        )
        normalized_analogues = tuple(
            dict.fromkeys(_text("modern analogue", item, 2048) for item in modern_analogues)
        )
        ids = tuple(dict.fromkeys(_text("source_id", item, 256) for item in source_ids))
        if not normalized_failures:
            raise ResearchLineageError("historical technique requires failure modes")
        if not normalized_analogues:
            raise ResearchLineageError("historical technique requires modern analogues")
        if not ids:
            raise ResearchLineageError("historical technique requires source evidence")
        if len(normalized_failures) > 64 or len(normalized_analogues) > 64 or len(ids) > 128:
            raise ResearchLineageError("historical technique exceeds bounded evidence shape")
        sources = tuple(self.source(source_id) for source_id in ids)
        if any(source.status is not SourceStatus.ACTIVE for source in sources):
            raise ResearchLineageError("historical technique requires active source evidence")
        payload = {
            "technique_id": normalized_id,
            "problem": normalized_problem,
            "mechanism": normalized_mechanism,
            "failure_modes": list(normalized_failures),
            "modern_analogues": list(normalized_analogues),
            "sources": [
                {"source_id": source.source_id, "digest": source.content_digest}
                for source in sources
            ],
        }
        technique = HistoricalTechnique(
            technique_id=normalized_id,
            problem=normalized_problem,
            mechanism=normalized_mechanism,
            failure_modes=normalized_failures,
            modern_analogues=normalized_analogues,
            source_ids=ids,
            source_digests=tuple(source.content_digest for source in sources),
            lineage_digest=_digest(payload),
        )
        prior = self._historical_techniques.get(technique.technique_id)
        if prior is not None and prior != technique:
            raise ResearchLineageError("historical technique identity conflict")
        if (
            prior is None
            and len(self._historical_techniques) >= self._max_historical_techniques
        ):
            raise ResearchLineageError("historical technique registry capacity exceeded")
        self._historical_techniques[technique.technique_id] = technique
        return technique

    def historical_technique(self, technique_id: str) -> HistoricalTechnique:
        key = _text("technique_id", technique_id, 256)
        try:
            return self._historical_techniques[key]
        except KeyError as exc:
            raise ResearchLineageError(f"unregistered historical technique: {key}") from exc

    def reconcile_historical_technique(self, technique_id: str) -> bool:
        technique = self.historical_technique(technique_id)
        for source_id, digest in zip(
            technique.source_ids,
            technique.source_digests,
        ):
            source = self._sources.get(source_id)
            if (
                source is None
                or source.status is not SourceStatus.ACTIVE
                or source.content_digest != digest
            ):
                return False
        return True

    def historical_techniques(self) -> tuple[HistoricalTechnique, ...]:
        return tuple(
            self._historical_techniques[key]
            for key in sorted(self._historical_techniques)
        )

    def _build_edge(self, source: ResearchSource, spec: CitationSpec) -> CitationEdge:
        if spec.target_source_id == source.source_id:
            raise ResearchLineageError("self-citation edge is not permitted")
        target = self._sources.get(spec.target_source_id)
        if target is None:
            raise ResearchLineageError(
                f"citation target is not registered: {spec.target_source_id}"
            )
        if source.status is not SourceStatus.ACTIVE:
            raise ResearchLineageError("non-active source cannot create current citation edges")
        if spec.relation in _DEPENDENCY_RELATIONS and target.status is not SourceStatus.ACTIVE:
            raise ResearchLineageError(
                f"non-active source cannot be a current citation target: {target.source_id}"
            )
        if spec.relation is CitationRelation.CORRECTS:
            if target.status is SourceStatus.ACTIVE:
                raise ResearchLineageError(
                    "correction edge requires a corrected or retracted target"
                )
            if target.source_id not in source.supersedes:
                raise ResearchLineageError(
                    "correction edge must target a source explicitly superseded by its source"
                )
        payload = {
            "source_id": source.source_id,
            "source_digest": source.content_digest,
            "target_source_id": target.source_id,
            "target_digest": target.content_digest,
            "relation": spec.relation.value,
            "evidence_ref": spec.evidence_ref,
        }
        return CitationEdge(
            edge_id=_digest(payload),
            source_id=source.source_id,
            source_digest=source.content_digest,
            target_source_id=target.source_id,
            target_digest=target.content_digest,
            relation=spec.relation,
            evidence_ref=spec.evidence_ref,
        )

    def add_citation(
        self,
        *,
        source_id: str,
        target_source_id: str,
        relation: CitationRelation | str = CitationRelation.CITES,
        evidence_ref: str | None = None,
    ) -> CitationEdge:
        source = self.source(source_id)
        spec = CitationSpec(
            target_source_id=target_source_id,
            relation=relation,
            evidence_ref=evidence_ref,
        )
        edge = self._build_edge(source, spec)
        prior = self._edges.get(edge.edge_id)
        if prior is not None:
            return prior
        if len(self._edges) >= self._max_edges:
            raise ResearchLineageError("citation edge registry capacity exceeded")
        self._edges[edge.edge_id] = edge
        self._outgoing.setdefault(edge.source_id, set()).add(edge.edge_id)
        self._incoming.setdefault(edge.target_source_id, set()).add(edge.edge_id)
        return edge

    def citation_edges(self) -> tuple[CitationEdge, ...]:
        return tuple(self._edges[key] for key in sorted(self._edges))

    def ingest(
        self,
        *,
        source_id: str,
        uri: str,
        content: str,
        rights_refs: Sequence[str],
        citations: Sequence[CitationSpec] = (),
        expected_content_digest: str | None = None,
        status: SourceStatus = SourceStatus.ACTIVE,
        correction_refs: Sequence[str] = (),
        supersedes: Sequence[str] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> IngestionReceipt:
        source = ResearchSource.from_content(
            source_id=source_id,
            uri=uri,
            content=content,
            rights_refs=rights_refs,
            status=status,
            correction_refs=correction_refs,
            supersedes=supersedes,
            metadata=metadata,
        )
        if expected_content_digest is not None:
            expected = _sha256("expected_content_digest", expected_content_digest)
            if expected != source.content_digest:
                raise ResearchLineageError("ingested content digest does not match expectation")

        specs = tuple(citations)
        if len(specs) > _MAX_CITATIONS_PER_INGEST:
            raise ResearchLineageError("ingestion exceeds citation fan-in limit")
        if any(not isinstance(spec, CitationSpec) for spec in specs):
            raise TypeError("citations must contain CitationSpec values")

        # Validate every dependency before mutating registry state. This makes source
        # admission transactional for all validation failures.
        if source.source_id in self._sources and self._sources[source.source_id] != source:
            raise ResearchLineageError("source identity conflict")
        for predecessor in source.supersedes:
            prior = self._sources.get(predecessor)
            if prior is None:
                raise ResearchLineageError(
                    f"superseded source is not registered: {predecessor}"
                )
            if prior.status is SourceStatus.ACTIVE:
                raise ResearchLineageError(
                    f"superseded source must be corrected or retracted first: {predecessor}"
                )
        staged_edges = tuple(self._build_edge(source, spec) for spec in specs)
        if len({edge.edge_id for edge in staged_edges}) != len(staged_edges):
            raise ResearchLineageError("duplicate citation edge in ingestion request")
        novel_edges = sum(edge.edge_id not in self._edges for edge in staged_edges)
        if len(self._edges) + novel_edges > self._max_edges:
            raise ResearchLineageError("citation edge registry capacity exceeded")

        self.register(source)
        for edge in staged_edges:
            self._edges.setdefault(edge.edge_id, edge)
            self._outgoing.setdefault(edge.source_id, set()).add(edge.edge_id)
            self._incoming.setdefault(edge.target_source_id, set()).add(edge.edge_id)

        edge_ids = tuple(edge.edge_id for edge in staged_edges)
        receipt_payload = {
            "source_id": source.source_id,
            "source_digest": source.content_digest,
            "citation_edge_ids": list(edge_ids),
        }
        return IngestionReceipt(
            source_id=source.source_id,
            source_digest=source.content_digest,
            citation_edge_ids=edge_ids,
            receipt_digest=_digest(receipt_payload),
        )

    def _edge_is_current(self, edge: CitationEdge) -> bool:
        source = self._sources.get(edge.source_id)
        target = self._sources.get(edge.target_source_id)
        if source is None or target is None:
            return False
        if source.status is not SourceStatus.ACTIVE:
            return False
        if (
            source.content_digest != edge.source_digest
            or target.content_digest != edge.target_digest
        ):
            return False
        if edge.relation in _DEPENDENCY_RELATIONS:
            return target.status is SourceStatus.ACTIVE
        if edge.relation is CitationRelation.CORRECTS:
            return (
                target.status is not SourceStatus.ACTIVE
                and target.source_id in source.supersedes
            )
        # Contradiction is evidence about a target, not support derived from it.
        # It remains a valid historical relation when that target is corrected
        # or retracted, provided the content identity itself has not drifted.
        return True

    def _invalid_sources(self) -> set[str]:
        invalid = {
            source_id
            for source_id, source in self._sources.items()
            if source.status is not SourceStatus.ACTIVE
        }
        for edge in self._edges.values():
            if not self._edge_is_current(edge):
                invalid.add(edge.source_id)
                invalid.add(edge.target_source_id)
        return invalid

    def _upstream_dependents(self, source_ids: set[str]) -> set[str]:
        impacted = set(source_ids)
        frontier = list(source_ids)
        while frontier:
            target_id = frontier.pop()
            for edge_id in self._incoming.get(target_id, ()):
                edge = self._edges[edge_id]
                if edge.relation not in _DEPENDENCY_RELATIONS:
                    continue
                if edge.source_id not in impacted:
                    impacted.add(edge.source_id)
                    frontier.append(edge.source_id)
        return impacted

    def reconcile_citation_graph(self) -> CitationGraphReport:
        stale: list[str] = []
        invalid_sources = self._invalid_sources()
        for edge_id in sorted(self._edges):
            edge = self._edges[edge_id]
            if not self._edge_is_current(edge):
                stale.append(edge_id)

        impacted_sources = self._upstream_dependents(invalid_sources)
        affected_claims = sorted(
            {
                claim_id
                for source_id in impacted_sources
                for claim_id in self._source_claims.get(source_id, ())
            }
        )
        payload = {
            "total_edges": len(self._edges),
            "valid_edges": len(self._edges) - len(stale),
            "stale_edge_ids": stale,
            "invalid_source_ids": sorted(invalid_sources),
            "affected_claim_ids": affected_claims,
        }
        return CitationGraphReport(
            total_edges=payload["total_edges"],
            valid_edges=payload["valid_edges"],
            stale_edge_ids=tuple(payload["stale_edge_ids"]),
            invalid_source_ids=tuple(payload["invalid_source_ids"]),
            affected_claim_ids=tuple(payload["affected_claim_ids"]),
            report_digest=_digest(payload),
        )

    def snapshot_digest(self) -> str:
        payload = {
            "sources": [
                {
                    "source_id": source.source_id,
                    "uri": source.uri,
                    "content_digest": source.content_digest,
                    "status": source.status.value,
                    "rights_refs": list(source.rights_refs),
                    "correction_refs": list(source.correction_refs),
                    "supersedes": list(source.supersedes),
                    "metadata": source.metadata,
                }
                for source in self.sources()
            ],
            "claims": [
                {
                    "claim_id": self._claims[key].claim_id,
                    "statement": self._claims[key].statement,
                    "source_ids": list(self._claims[key].source_ids),
                    "source_digests": list(self._claims[key].source_digests),
                    "lineage_digest": self._claims[key].lineage_digest,
                    "method": self._claims[key].method,
                    "result": self._claims[key].result,
                    "limitations": list(self._claims[key].limitations),
                    "negative_result": self._claims[key].negative_result,
                }
                for key in sorted(self._claims)
            ],
            "status_records": [
                {
                    "source_id": record.source_id,
                    "source_digest": record.source_digest,
                    "status": record.status.value,
                    "evidence_refs": list(record.evidence_refs),
                    "transition_digest": record.transition_digest,
                }
                for record in self.status_records()
            ],
            "replications": [
                {
                    "replication_id": record.replication_id,
                    "source_id": record.source_id,
                    "source_digest": record.source_digest,
                    "target_source_id": record.target_source_id,
                    "target_digest": record.target_digest,
                    "outcome": record.outcome.value,
                    "method": record.method,
                    "result": record.result,
                    "limitations": list(record.limitations),
                    "negative_result": record.negative_result,
                    "record_digest": record.record_digest,
                }
                for record in self.replication_records()
            ],
            "historical_techniques": [
                {
                    "technique_id": technique.technique_id,
                    "problem": technique.problem,
                    "mechanism": technique.mechanism,
                    "failure_modes": list(technique.failure_modes),
                    "modern_analogues": list(technique.modern_analogues),
                    "source_ids": list(technique.source_ids),
                    "source_digests": list(technique.source_digests),
                    "lineage_digest": technique.lineage_digest,
                }
                for technique in self.historical_techniques()
            ],
            "citations": [
                {
                    "edge_id": edge.edge_id,
                    "source_id": edge.source_id,
                    "source_digest": edge.source_digest,
                    "target_source_id": edge.target_source_id,
                    "target_digest": edge.target_digest,
                    "relation": edge.relation.value,
                    "evidence_ref": edge.evidence_ref,
                }
                for edge in self.citation_edges()
            ],
        }
        return _digest(payload)


__all__ = [
    "CitationEdge",
    "CitationGraphReport",
    "CitationRelation",
    "CitationSpec",
    "HistoricalTechnique",
    "IngestionReceipt",
    "ReplicationOutcome",
    "ReplicationRecord",
    "ResearchClaim",
    "ResearchLineageError",
    "ResearchSource",
    "ResearchSourceRegistry",
    "RetractionRecord",
    "SourceStatus",
    "content_digest",
]
