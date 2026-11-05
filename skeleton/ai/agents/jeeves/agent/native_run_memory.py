"""Durable one-run Jeeves working memory on the canonical protected SQLite.

This is a narrowly scoped replacement for the default InMemoryStore in the
reasoning-only durable agent. The existing MemoryManager, retrieval weights and
epistemic rules remain authoritative. No hosted provider, automatic promotion,
cross-run recall, or memory-derived tool permission is introduced.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any

from .memory import InMemoryStore, MemoryManager, MemoryNamespace, MemoryRecord
from .native_checkpoint_journal import (
    NativeCheckpointHold, NativeSQLiteCheckpointer, _input_digest,
)
from .runtime import RunInputs
from .types import EvidenceRef


class NativeMemoryHold(NativeCheckpointHold):
    """Run-bound memory bytes or privacy semantics cannot be trusted."""


_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS jeeves_native_memories (
    run_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    namespace_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    payload BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL,
    PRIMARY KEY (run_id, memory_id),
    FOREIGN KEY (run_id) REFERENCES jeeves_native_runs(run_id)
)
"""


def _bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


class NativeRunMemoryStore(InMemoryStore):
    """A private host memory cache that cannot outlive its SQLite authority.

    SQLite commits PRECEDE mutating the in-memory view. Interrupted or
    corrupt durable reads abort recovery rather than creating a different
    context projection for another inference request.
    """

    def __init__(
        self, journal: NativeSQLiteCheckpointer, inputs: RunInputs, *,
        max_records: int = 256,
    ) -> None:
        if not isinstance(journal, NativeSQLiteCheckpointer):
            raise NativeMemoryHold("protected native run journal required")
        if not isinstance(inputs, RunInputs) or inputs.run_id is None:
            raise NativeMemoryHold("explicit typed run identity required")
        if type(max_records) is not int or not 1 <= max_records <= 256:
            raise NativeMemoryHold("invalid bounded memory inventory")
        self._journal = journal
        self._inputs = inputs
        super().__init__(max_records=max_records)
        self._journal.bind_existing(inputs)
        with self._journal.db.transaction() as conn:
            conn.execute(_MEMORY_SCHEMA)
        records = self._load()
        # The historical records have ALREADY been durably committed; do
        # not write them a second time merely because a process restarted.
        for record in records:
            InMemoryStore.put(self, record)

    def _require_run(self, conn: Any) -> None:
        self._journal._live()
        row = self._journal._row(conn, self._inputs.run_id)
        if row is None or row[0] != _input_digest(self._inputs):
            raise NativeMemoryHold("memory record no longer bound to active run")

    @staticmethod
    def _decode(payload: bytes) -> MemoryRecord:
        try:
            raw = json.loads(payload)
            if raw.get("schema") != "jeeves.native_memory_record.v1":
                raise ValueError("unsupported durable memory schema")
            values = dict(raw["record"])
            values["namespace"] = MemoryNamespace(**values["namespace"])
            values["evidence"] = tuple(
                EvidenceRef(**item) for item in values["evidence"]
            )
            return MemoryRecord(**values)
        except (TypeError, KeyError, ValueError, AttributeError) as exc:
            raise NativeMemoryHold("invalid durable memory record") from exc

    def _load(self) -> tuple[MemoryRecord, ...]:
        with self._journal.db.snapshot() as conn:
            self._require_run(conn)
            rows = conn.execute(
                "SELECT memory_id,namespace_key,fingerprint,payload,payload_sha256 "
                "FROM jeeves_native_memories WHERE run_id=? ORDER BY memory_id",
                (self._inputs.run_id,),
            ).fetchall()
            if len(rows) > self.max_records:
                raise NativeMemoryHold("durable memory inventory too large")
            result = []
            for memory_id, namespace_key, fingerprint, payload, checksum in rows:
                if (type(payload) is not bytes or len(payload) > 262144
                        or _digest(payload) != checksum):
                    raise NativeMemoryHold("memory record checksum or byte ceiling mismatch")
                record = self._decode(payload)
                if (record.memory_id != memory_id
                        or record.namespace.key != namespace_key
                        or record.namespace != self._inputs.namespace
                        or record.fingerprint != fingerprint):
                    raise NativeMemoryHold("memory provenance or principal changed")
                result.append(record)
            return tuple(result)

    @property
    def persisted_records(self) -> int:
        return len(self._load())

    def put(self, record: MemoryRecord) -> MemoryRecord:
        if not isinstance(record, MemoryRecord):
            raise NativeMemoryHold("typed MemoryRecord required")
        if record.namespace != self._inputs.namespace:
            raise NativeMemoryHold("cross-run or foreign memory cannot be persisted")
        payload = _bytes({
            "schema": "jeeves.native_memory_record.v1",
            "record": asdict(record),
        })
        if len(payload) > 262144:
            raise NativeMemoryHold("memory exceeds protected byte limit")
        with self._journal.db.transaction() as conn:
            self._require_run(conn)
            prior = conn.execute(
                "SELECT fingerprint FROM jeeves_native_memories "
                "WHERE run_id=? AND memory_id=?",
                (self._inputs.run_id, record.memory_id),
            ).fetchone()
            if prior is not None and prior[0] != record.fingerprint:
                raise NativeMemoryHold("existing memory ID changed semantic contents")
            if prior is None and conn.execute(
                "SELECT COUNT(*) FROM jeeves_native_memories WHERE run_id=?",
                (self._inputs.run_id,),
            ).fetchone()[0] >= self.max_records:
                raise NativeMemoryHold("durable memory capacity exhausted")
            conn.execute(
                "INSERT INTO jeeves_native_memories "
                "(run_id,memory_id,namespace_key,fingerprint,payload,payload_sha256) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(run_id,memory_id) DO UPDATE SET "
                "payload=excluded.payload,payload_sha256=excluded.payload_sha256 "
                "WHERE fingerprint=excluded.fingerprint",
                (self._inputs.run_id, record.memory_id, record.namespace.key,
                 record.fingerprint, payload, _digest(payload)),
            )
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                raise NativeMemoryHold("memory write failed immutable identity CAS")
        return InMemoryStore.put(self, record)

    def delete(self, memory_id: str) -> bool:
        raise NativeMemoryHold("run memory deletion needs reviewed durable tombstones")

    def privacy_delete_subject(
        self, tenant_id: str, user_id: str, *,
        authority_receipt_digest: str,
    ) -> tuple[str, ...]:
        raise NativeMemoryHold(
            "privacy deletion cannot be simulated by clearing process cache"
        )

    def _evict_one(self) -> None:
        raise NativeMemoryHold("durable memory must not silently evict records")


def run_memory_manager(
    journal: NativeSQLiteCheckpointer,
    inputs: RunInputs,
) -> MemoryManager:
    """Reuse ordinary Jeeves search and retrieval against restored custody."""
    return MemoryManager(store=NativeRunMemoryStore(journal, inputs))


__all__ = ["NativeMemoryHold", "NativeRunMemoryStore", "run_memory_manager"]
