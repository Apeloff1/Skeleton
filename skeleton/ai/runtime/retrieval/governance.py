"""Governed tenant-scoped owner for canonical retrieval index writes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
from urllib.parse import quote, unquote

from skeleton.retrieval.index import InvertedIndex
from skeleton.retrieval.fusion import ScoredResult
from skeleton.vault.governance_registry import GovernanceRegistry


class GovernedRetrievalError(RuntimeError):
    """Governed retrieval ownership contract was violated."""


def _required_text(value: object, field: str, *, max_length: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernedRetrievalError(f"{field} is required")
    text = value.strip()
    if text != value:
        raise GovernedRetrievalError(f"{field} must be normalized")
    if len(text) > max_length:
        raise GovernedRetrievalError(f"{field} exceeds maximum length")
    return text


def _record_id(tenant_id: str, doc_id: str) -> str:
    digest = hashlib.sha256(
        (tenant_id + "\x1f" + doc_id).encode("utf-8")
    ).hexdigest()
    return "retrieval-" + digest[:32]


@dataclass(frozen=True, slots=True)
class RetrievalRecord:
    record_id: str
    tenant_id: str
    doc_id: str
    text: str

    def as_dict(self) -> dict[str, str]:
        return {
            "record_id": self.record_id,
            "tenant_id": self.tenant_id,
            "doc_id": self.doc_id,
            "text": self.text,
        }


class GovernedRetrievalIndex:
    """Tenant-scoped retrieval indexes with lifecycle registration before write."""

    _SOURCE_PREFIX = "retrieval://"

    def __init__(self, governance: GovernanceRegistry) -> None:
        if not isinstance(governance, GovernanceRegistry):
            raise TypeError("governance must be GovernanceRegistry")
        self.governance = governance
        self._indexes: dict[str, InvertedIndex] = {}
        self._records: dict[tuple[str, str], RetrievalRecord] = {}

    @classmethod
    def source_ref(cls, tenant_id: str, doc_id: str) -> str:
        tenant = _required_text(tenant_id, "tenant_id", max_length=256)
        document = _required_text(doc_id, "doc_id", max_length=1024)
        return (
            cls._SOURCE_PREFIX
            + quote(tenant, safe="")
            + "/"
            + quote(document, safe="")
        )

    @classmethod
    def parse_source_ref(cls, source_ref: object) -> tuple[str, str]:
        raw = _required_text(source_ref, "source_ref", max_length=4096)
        if not raw.startswith(cls._SOURCE_PREFIX):
            raise GovernedRetrievalError("retrieval source_ref is invalid")
        tail = raw[len(cls._SOURCE_PREFIX):]
        tenant_raw, separator, doc_raw = tail.partition("/")
        if not separator or not tenant_raw or not doc_raw:
            raise GovernedRetrievalError("retrieval source_ref is invalid")
        tenant = unquote(tenant_raw)
        doc_id = unquote(doc_raw)
        _required_text(tenant, "tenant_id", max_length=256)
        _required_text(doc_id, "doc_id", max_length=1024)
        return tenant, doc_id

    @staticmethod
    def lifecycle_record_id(tenant_id: str, doc_id: str) -> str:
        tenant = _required_text(tenant_id, "tenant_id", max_length=256)
        document = _required_text(doc_id, "doc_id", max_length=1024)
        return _record_id(tenant, document)

    def _index(self, tenant_id: str) -> InvertedIndex:
        return self._indexes.setdefault(tenant_id, InvertedIndex())

    def add(
        self,
        *,
        tenant_id: str,
        doc_id: str,
        text: str,
        data_class: str = "internal",
        purposes: tuple[str, ...] = ("retrieval",),
        created_at: float | None = None,
        retention_until: float | None = None,
        exportable: bool = True,
    ) -> RetrievalRecord:
        tenant = _required_text(tenant_id, "tenant_id", max_length=256)
        document = _required_text(doc_id, "doc_id", max_length=1024)
        if not isinstance(text, str):
            raise GovernedRetrievalError("text must be a string")
        if not InvertedIndex._tokenise(text):
            raise GovernedRetrievalError("text must contain a token")
        timestamp = time.time() if created_at is None else float(created_at)
        record = RetrievalRecord(
            record_id=self.lifecycle_record_id(tenant, document),
            tenant_id=tenant,
            doc_id=document,
            text=text,
        )
        self.governance.register_canonical_write(
            "retrieval",
            record_id=record.record_id,
            tenant_id=tenant,
            source_ref=self.source_ref(tenant, document),
            data_class=data_class,
            purposes=purposes,
            created_at=timestamp,
            retention_until=retention_until,
            exportable=exportable,
        )
        self._index(tenant).add(document, text)
        self._records[(tenant, document)] = record
        return record

    def remove(self, tenant_id: str, doc_id: str) -> bool:
        tenant = _required_text(tenant_id, "tenant_id", max_length=256)
        document = _required_text(doc_id, "doc_id", max_length=1024)
        index = self._indexes.get(tenant)
        if index is None:
            return False
        removed = index.remove(document)
        if removed:
            self._records.pop((tenant, document), None)
        return removed

    def export_record(
        self,
        tenant_id: str,
        doc_id: str,
    ) -> dict[str, str] | None:
        tenant = _required_text(tenant_id, "tenant_id", max_length=256)
        document = _required_text(doc_id, "doc_id", max_length=1024)
        record = self._records.get((tenant, document))
        return None if record is None else record.as_dict()

    def search(
        self,
        tenant_id: str,
        query: str,
        *,
        top_k: int = 10,
    ) -> tuple[ScoredResult, ...]:
        tenant = _required_text(tenant_id, "tenant_id", max_length=256)
        index = self._indexes.get(tenant)
        if index is None:
            return ()
        return index.search(query, top_k=top_k)

    def size(self, tenant_id: str) -> int:
        tenant = _required_text(tenant_id, "tenant_id", max_length=256)
        index = self._indexes.get(tenant)
        return 0 if index is None else index.size()


__all__ = [
    "GovernedRetrievalError",
    "GovernedRetrievalIndex",
    "RetrievalRecord",
]
