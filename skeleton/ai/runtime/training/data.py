"""Data, provenance, rights and synthetic-data primitives for P3-T2."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Mapping, Sequence

from .native import DatasetManifest, DatasetRecord


def _stable_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CacheEntry:
    namespace: str
    tenant_id: str
    key_digest: str
    value_digest: str
    source_digest: str
    payload: object

    @property
    def identity(self) -> str:
        return _digest(
            {
                "namespace": self.namespace,
                "tenant_id": self.tenant_id,
                "key_digest": self.key_digest,
                "value_digest": self.value_digest,
                "source_digest": self.source_digest,
            }
        )


class ContentAddressedCache:
    """Tenant/namespace isolated cache whose keys and values are content-bound."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str], CacheEntry] = {}

    def put(
        self,
        *,
        namespace: str,
        tenant_id: str,
        key: object,
        payload: object,
        source_digest: str,
    ) -> CacheEntry:
        if not namespace.strip() or not tenant_id.strip():
            raise ValueError("cache namespace and tenant_id are required")
        if len(source_digest) != 64:
            raise ValueError("source_digest must be sha256")
        key_digest = _digest(key)
        value_digest = _digest(payload)
        entry = CacheEntry(
            namespace=namespace.strip(),
            tenant_id=tenant_id.strip(),
            key_digest=key_digest,
            value_digest=value_digest,
            source_digest=source_digest,
            payload=payload,
        )
        self._entries[(entry.namespace, entry.tenant_id, key_digest)] = entry
        return entry

    def get(self, *, namespace: str, tenant_id: str, key: object) -> object | None:
        entry = self._entries.get((namespace, tenant_id, _digest(key)))
        return None if entry is None else entry.payload

    def invalidate_source(self, source_digest: str) -> int:
        doomed = [
            key for key, entry in self._entries.items()
            if entry.source_digest == source_digest
        ]
        for key in doomed:
            del self._entries[key]
        return len(doomed)


@dataclass(frozen=True, slots=True)
class IngestionReceipt:
    record_id: str
    source_ref: str
    content_digest: str
    byte_count: int
    quarantined: bool
    reason: str | None


class DataIngestionEngine:
    """Bounded text ingestion with dedupe and fail-closed quarantine."""

    def __init__(self, *, max_bytes: int = 1_000_000) -> None:
        if not 1 <= max_bytes <= 100_000_000:
            raise ValueError("max_bytes out of range")
        self.max_bytes = max_bytes
        self._seen: set[str] = set()

    def ingest(
        self,
        *,
        record_id: str,
        text: str,
        source_ref: str,
        license_id: str,
        usage_grant: str,
        classification: str = "internal",
    ) -> tuple[DatasetRecord | None, IngestionReceipt]:
        if not record_id.strip() or not source_ref.strip():
            raise ValueError("record_id/source_ref are required")
        data = text.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        if len(data) > self.max_bytes:
            return None, IngestionReceipt(
                record_id, source_ref, digest, len(data), True, "size_limit"
            )
        if not text.strip():
            return None, IngestionReceipt(
                record_id, source_ref, digest, len(data), True, "empty_content"
            )
        if digest in self._seen:
            return None, IngestionReceipt(
                record_id, source_ref, digest, len(data), True, "duplicate_content"
            )
        self._seen.add(digest)
        record = DatasetRecord(
            record_id=record_id,
            text=text,
            source_ref=source_ref,
            license_id=license_id,
            usage_grant=usage_grant,
            classification=classification,
        )
        return record, IngestionReceipt(
            record_id, source_ref, digest, len(data), False, None
        )


@dataclass(frozen=True, slots=True)
class DocumentRegion:
    region_id: str
    page_index: int
    start: int
    end: int
    text: str
    source_digest: str

    @property
    def evidence_digest(self) -> str:
        return _digest(
            {
                "region_id": self.region_id,
                "page_index": self.page_index,
                "start": self.start,
                "end": self.end,
                "text": self.text,
                "source_digest": self.source_digest,
            }
        )


class DocumentIntelligence:
    """Deterministic page/region extraction that preserves offsets and source hash."""

    @staticmethod
    def extract(text: str, *, page_separator: str = "\f") -> tuple[DocumentRegion, ...]:
        source_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        pages = text.split(page_separator)
        regions: list[DocumentRegion] = []
        cursor = 0
        for page_index, page in enumerate(pages):
            start = cursor
            end = start + len(page)
            regions.append(
                DocumentRegion(
                    region_id=f"page-{page_index}:{source_digest[:16]}",
                    page_index=page_index,
                    start=start,
                    end=end,
                    text=page,
                    source_digest=source_digest,
                )
            )
            cursor = end + (0 if page_index == len(pages) - 1 else len(page_separator))
        return tuple(regions)


@dataclass(frozen=True, slots=True)
class LineageEdge:
    parent_digest: str
    child_digest: str
    transformation: str
    receipt_digest: str


class LineageGraph:
    def __init__(self) -> None:
        self._nodes: set[str] = set()
        self._edges: list[LineageEdge] = []

    def add_node(self, digest: str) -> None:
        if len(digest) != 64:
            raise ValueError("lineage node must be sha256")
        self._nodes.add(digest)

    def transform(
        self,
        *,
        parent_digest: str,
        child_digest: str,
        transformation: str,
        metadata: Mapping[str, object] | None = None,
    ) -> LineageEdge:
        if parent_digest not in self._nodes:
            raise ValueError("unknown lineage parent")
        if len(child_digest) != 64 or not transformation.strip():
            raise ValueError("invalid lineage transform")
        self._nodes.add(child_digest)
        receipt = _digest(
            {
                "parent": parent_digest,
                "child": child_digest,
                "transformation": transformation,
                "metadata": dict(metadata or {}),
            }
        )
        edge = LineageEdge(
            parent_digest=parent_digest,
            child_digest=child_digest,
            transformation=transformation,
            receipt_digest=receipt,
        )
        self._edges.append(edge)
        return edge

    def ancestors(self, digest: str) -> tuple[str, ...]:
        found: set[str] = set()
        frontier = [digest]
        while frontier:
            child = frontier.pop()
            for edge in self._edges:
                if edge.child_digest == child and edge.parent_digest not in found:
                    found.add(edge.parent_digest)
                    frontier.append(edge.parent_digest)
        return tuple(sorted(found))


@dataclass(frozen=True, slots=True)
class LicensePolicy:
    license_id: str
    allow_training: bool
    allow_derivatives: bool
    allowed_purposes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RightsDecision:
    permitted: bool
    reason_code: str
    policy_digest: str


class LicensePolicyRegistry:
    def __init__(self, policies: Sequence[LicensePolicy] = ()) -> None:
        self._policies = {policy.license_id: policy for policy in policies}

    def register(self, policy: LicensePolicy) -> None:
        prior = self._policies.get(policy.license_id)
        if prior is not None and prior != policy:
            raise ValueError("license policy cannot be silently rebound")
        self._policies[policy.license_id] = policy

    def evaluate(
        self,
        record: DatasetRecord,
        *,
        purpose: str = "local-model-training",
        derivative: bool = False,
    ) -> RightsDecision:
        policy = self._policies.get(record.license_id)
        if policy is None:
            return RightsDecision(False, "unknown_license", _digest({"license": record.license_id}))
        if record.usage_grant not in {"train", "train_eval"}:
            reason = "record_usage_grant_denies_training"
            permitted = False
        elif not policy.allow_training:
            reason = "license_denies_training"
            permitted = False
        elif derivative and not policy.allow_derivatives:
            reason = "license_denies_derivatives"
            permitted = False
        elif purpose not in policy.allowed_purposes:
            reason = "purpose_not_allowed"
            permitted = False
        else:
            reason = "rights_permit"
            permitted = True
        return RightsDecision(
            permitted,
            reason,
            _digest(
                {
                    "license": policy.license_id,
                    "train": policy.allow_training,
                    "derivatives": policy.allow_derivatives,
                    "purposes": policy.allowed_purposes,
                }
            ),
        )


class SyntheticDataFactory:
    """Deterministic bounded derivation preserving parent lineage."""

    def derive(
        self,
        manifest: DatasetManifest,
        *,
        transform_id: str,
        transform: Callable[[str], str],
        max_records: int | None = None,
    ) -> DatasetManifest:
        if not transform_id.strip() or not callable(transform):
            raise ValueError("synthetic transform id/callable are required")
        limit = len(manifest.records) if max_records is None else max_records
        if not 1 <= limit <= 100_000:
            raise ValueError("max_records out of range")
        generated: list[DatasetRecord] = []
        for index, parent in enumerate(manifest.records[:limit]):
            text = transform(parent.text)
            if not isinstance(text, str) or not text.strip():
                raise ValueError("synthetic transform produced empty text")
            generated.append(
                DatasetRecord(
                    record_id=f"syn-{transform_id}-{index}-{parent.record_id}",
                    text=text,
                    source_ref=f"synthetic:{transform_id}:{parent.source_ref}",
                    license_id=parent.license_id,
                    usage_grant=parent.usage_grant,
                    classification=parent.classification,
                    synthetic_parent_refs=(parent.record_id,),
                )
            )
        return DatasetManifest(
            dataset_id=manifest.dataset_id+"-synthetic-"+transform_id,
            version=manifest.version+"+syn",
            records=tuple(generated),
            purpose="synthetic-data",
        )
