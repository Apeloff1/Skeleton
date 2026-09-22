from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from skeleton.contracts.memory_record import (
    ConfidenceBand,
    MemoryAuthorityClass,
    MemoryContractError,
    MemoryKind,
    MemoryWriteProposal,
)
from skeleton.persistence.memory_repository import (
    MemoryNotFound,
    MongoMemoryRepository,
)


def _matches(row: dict, query: dict) -> bool:
    return all(row.get(key) == value for key, value in query.items())


class _Result:
    def __init__(self, matched_count: int = 1) -> None:
        self.matched_count = matched_count


class _Cursor:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = [deepcopy(row) for row in rows]

    def sort(self, key: str, direction: int):
        self.rows.sort(key=lambda row: row.get(key, ""), reverse=direction < 0)
        return self

    def limit(self, value: int):
        self.rows = self.rows[:value]
        return self

    def __iter__(self):
        return iter([deepcopy(row) for row in self.rows])


class _Collection:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.indexes: list[tuple] = []

    def create_index(self, spec, **kwargs):
        self.indexes.append((spec, kwargs))
        return str(spec)

    def find_one(self, query: dict):
        for row in self.rows:
            if _matches(row, query):
                return deepcopy(row)
        return None

    def insert_one(self, document: dict):
        self.rows.append(deepcopy(document))
        return object()

    def replace_one(self, query: dict, document: dict, upsert: bool = False):
        for index, row in enumerate(self.rows):
            if _matches(row, query):
                self.rows[index] = deepcopy(document)
                return _Result(1)
        if upsert:
            self.rows.append(deepcopy(document))
            return _Result(1)
        return _Result(0)

    def find(self, query: dict):
        return _Cursor([row for row in self.rows if _matches(row, query)])


class _Database:
    def __init__(self) -> None:
        self.collections: dict[str, _Collection] = {}

    def __getitem__(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())


def _proposal(
    *,
    proposal_id: str = "proposal-1",
    namespace: str = "project:alpha",
    tenant_id: str = "tenant-a",
    user_id: str | None = "user-a",
    digest: str = "a" * 64,
    content_ref: str = "artifact://memory/1",
) -> MemoryWriteProposal:
    return MemoryWriteProposal(
        proposal_id=proposal_id,
        operation_id="operation-1",
        execution_id="execution-1",
        tenant_id=tenant_id,
        user_id=user_id,
        namespace=namespace,
        kind=MemoryKind.TASK_OUTCOME,
        content_ref=content_ref,
        content_digest=digest,
        provenance={"source": "test", "verified": True},
        authority_class=MemoryAuthorityClass.VERIFIED_OUTCOME,
        data_class="confidential",
        purpose="project-continuity",
        retention_class="project",
        dedupe_key="task:42:outcome",
        confidence_band=ConfidenceBand.HIGH,
    )


def test_memory_contract_rejects_bad_digest_and_naive_expiry() -> None:
    with pytest.raises(MemoryContractError, match="sha256"):
        _proposal(digest="not-a-digest")

    with pytest.raises(MemoryContractError, match="timezone-aware"):
        MemoryWriteProposal(
            **{
                **_proposal().__dict__,
                "expires_at": datetime(2030, 1, 1),
            }
        )


def test_memory_survives_repository_restart_and_deduplicates() -> None:
    database = _Database()
    first = MongoMemoryRepository(database)
    first.ensure_indexes()
    committed_at = datetime(2026, 9, 22, 19, 5, tzinfo=timezone.utc)

    record, receipt = first.commit(_proposal(), now=committed_at)
    restarted = MongoMemoryRepository(database)
    restored = restarted.get(
        record.memory_id,
        tenant_id="tenant-a",
        user_id="user-a",
        namespace="project:alpha",
    )
    replayed, replay_receipt = restarted.commit(_proposal(), now=committed_at)

    assert restored == record
    assert receipt.deduplicated is False
    assert replayed == record
    assert replay_receipt.deduplicated is True
    assert database[restarted.DEFAULT_COLLECTION].indexes


def test_namespace_and_tenant_isolation_fail_closed() -> None:
    database = _Database()
    repository = MongoMemoryRepository(database)
    record, _ = repository.commit(_proposal())

    for tenant, namespace in (
        ("tenant-b", "project:alpha"),
        ("tenant-a", "project:beta"),
    ):
        with pytest.raises(MemoryNotFound):
            repository.get(
                record.memory_id,
                tenant_id=tenant,
                user_id="user-a",
                namespace=namespace,
            )

    other, _ = repository.commit(
        _proposal(
            proposal_id="proposal-2",
            namespace="project:beta",
        )
    )
    assert other.memory_id != record.memory_id


def test_same_dedupe_identity_versions_changed_content() -> None:
    database = _Database()
    repository = MongoMemoryRepository(database)
    first, _ = repository.commit(_proposal(digest="a" * 64))

    second, receipt = repository.commit(
        _proposal(
            proposal_id="proposal-2",
            digest="b" * 64,
            content_ref="artifact://memory/2",
        )
    )

    assert second.memory_id == first.memory_id
    assert second.version == 2
    assert second.content_digest == "b" * 64
    assert receipt.deduplicated is False


def test_list_active_is_exact_scope_only() -> None:
    database = _Database()
    repository = MongoMemoryRepository(database)
    repository.commit(_proposal())
    repository.commit(
        _proposal(
            proposal_id="proposal-2",
            namespace="project:beta",
            digest="b" * 64,
            content_ref="artifact://memory/2",
        )
    )

    rows = repository.list_active(
        tenant_id="tenant-a",
        user_id="user-a",
        namespace="project:alpha",
    )

    assert len(rows) == 1
    assert rows[0].namespace == "project:alpha"
