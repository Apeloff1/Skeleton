"""Durable, owner-authorized Jeeves Supervisor / Secretary / Worker plan state.

An append-only SQLite journal stores a full canonical ledger revision at every
state transition. The caller must inject an independent authorization decision;
Jeeves never grants itself the right to change the Supervisor plan or execute
a plan merely because a task is READY.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping

from ._canonical import canonical_digest, detached_json
from .contracts import Authority
from .orchestration import OrchestrLedger, OrchestrRecord, OrchestrState

_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS jeeves_orchestration_journal (
    revision INTEGER PRIMARY KEY,
    prior_event_digest TEXT NOT NULL,
    event_digest TEXT NOT NULL UNIQUE,
    event_json TEXT NOT NULL,
    ledger_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jeeves_orchestration_meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    event_digest TEXT NOT NULL,
    revision_count INTEGER NOT NULL
);
"""

GENESIS = "0" * 64
MAX_REVISIONS = 100_000
MAX_LEDGER_BYTES = 512 * 1024


class OrchestrationStoreError(ValueError):
    """Missing authority, stale head, incomplete state or tampered journal."""


def _sha(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        c not in "0123456789abcdef" for c in value
    ):
        raise OrchestrationStoreError("orchestration proof must be SHA-256")
    return value


def _encode(value: Any) -> str:
    out = json.dumps(detached_json(value), sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False)
    if len(out.encode("utf-8")) > MAX_LEDGER_BYTES:
        raise OrchestrationStoreError("orchestration record exceeds byte budget")
    return out


def _serialize(ledger: OrchestrLedger) -> str:
    return _encode({
        "schema": "jeeves.orchestration_ledger.v1",
        "digest": ledger.digest,
        "records": [
            {
                "name": r.name,
                "state": r.state.value,
                "payload": detached_json(r.payload),
                "evidence": list(r.evidence),
                "authority": r.authority.value,
                "parent": r.parent,
                "dependencies": list(r.dependencies),
            } for r in ledger.records
        ],
    })


def _parse(serialized: str) -> OrchestrLedger:
    if not isinstance(serialized, str) or len(serialized.encode("utf-8")) > MAX_LEDGER_BYTES:
        raise OrchestrationStoreError("invalid persisted orchestration length")
    try:
        raw = json.loads(serialized)
    except (TypeError, ValueError) as exc:
        raise OrchestrationStoreError("invalid persisted orchestration JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema", "digest", "records"}:
        raise OrchestrationStoreError("invalid orchestration snapshot schema")
    if raw["schema"] != "jeeves.orchestration_ledger.v1" or not isinstance(raw["records"], list):
        raise OrchestrationStoreError("unsupported orchestration schema")
    records = []
    for item in raw["records"]:
        if not isinstance(item, dict) or set(item) != {
            "name", "state", "payload", "evidence", "authority",
            "parent", "dependencies",
        }:
            raise OrchestrationStoreError("orchestration task identity mismatch")
        if not isinstance(item["dependencies"], list) or not isinstance(item["evidence"], list):
            raise OrchestrationStoreError("orchestration dependency or evidence is malformed")
        try:
            record = OrchestrRecord(
                name=item["name"], state=OrchestrState(item["state"]),
                payload=item["payload"], evidence=tuple(item["evidence"]),
                authority=Authority(item["authority"]), parent=item["parent"],
                dependencies=tuple(item["dependencies"]),
            )
        except (TypeError, ValueError) as exc:
            raise OrchestrationStoreError("persisted orchestration record invalid") from exc
        records.append(record)
    try:
        ledger = OrchestrLedger(tuple(records))
    except (ValueError, TypeError) as exc:
        raise OrchestrationStoreError("persisted orchestration graph is invalid") from exc
    if ledger.digest != raw["digest"]:
        raise OrchestrationStoreError("orchestration digest mismatch")
    return ledger


def _event(*, revision: int, old: str, ledger: OrchestrLedger,
           actor: str, action: str, proof: str, at_ns: int) -> dict[str, Any]:
    if not isinstance(actor, str) or not actor or len(actor) > 192:
        raise OrchestrationStoreError("invalid orchestration actor")
    if type(at_ns) is not int or at_ns < 0:
        raise OrchestrationStoreError("orchestration event time invalid")
    return {
        "schema": "jeeves.orchestration_event.v1",
        "revision": revision, "prior_event_digest": old,
        "ledger_digest": ledger.digest, "actor": actor,
        "action": action, "proof_digest": _sha(proof), "at_ns": at_ns,
    }


Authorization = Callable[[str, Authority, str, str], bool]


class DurableOrchestrLedger:
    """Transactional plan journal, not an executing scheduler."""

    def __init__(
        self, path: str | Path, *,
        authorize: Authorization,
    ) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            raise OrchestrationStoreError("host must choose an absolute orchestration store")
        if not callable(authorize):
            raise OrchestrationStoreError("independent host authorizer required")
        self._authorize = authorize
        self._lock = RLock()
        self._db = sqlite3.connect(
            str(self.path), isolation_level=None, timeout=10,
            check_same_thread=False,
        )
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_SCHEMA)
            self._bootstrap()
        except BaseException:
            self._db.close()
            raise

    def _bootstrap(self) -> None:
        meta = self._db.execute(
            "SELECT event_digest, revision_count "
            "FROM jeeves_orchestration_meta WHERE singleton=1"
        ).fetchone()
        if meta is None:
            count = self._db.execute(
                "SELECT COUNT(*) FROM jeeves_orchestration_journal"
            ).fetchone()[0]
            if count:
                raise OrchestrationStoreError("orphaned orchestration journal")
            self._db.execute(
                "INSERT INTO jeeves_orchestration_meta VALUES (1, ?, 0)", (GENESIS,),
            )
        self.load()

    def load(self) -> tuple[OrchestrLedger, str, int]:
        with self._lock:
            meta = self._db.execute(
                "SELECT event_digest, revision_count "
                "FROM jeeves_orchestration_meta WHERE singleton=1"
            ).fetchone()
            if meta is None:
                raise OrchestrationStoreError("orchestration metadata missing")
            head, count = GENESIS, 0
            ledger = OrchestrLedger()
            for rev, prior, recorded, event_json, ledger_json in self._db.execute(
                "SELECT revision, prior_event_digest, event_digest, "
                "event_json, ledger_json FROM jeeves_orchestration_journal ORDER BY revision"
            ):
                if rev != count or count >= MAX_REVISIONS or prior != head:
                    raise OrchestrationStoreError("orchestration event sequence broken")
                try:
                    event = json.loads(event_json)
                except (TypeError, ValueError) as exc:
                    raise OrchestrationStoreError("orchestration event is not JSON") from exc
                if not isinstance(event, dict) or set(event) != {
                    "schema", "revision", "prior_event_digest", "ledger_digest",
                    "actor", "action", "proof_digest", "at_ns",
                }:
                    raise OrchestrationStoreError("unsupported orchestration event fields")
                previous = ledger
                ledger = _parse(ledger_json)
                if (event["schema"] != "jeeves.orchestration_event.v1"
                        or event["revision"] != rev
                        or event["prior_event_digest"] != head
                        or event["ledger_digest"] != ledger.digest
                        or canonical_digest(event, max_bytes=MAX_LEDGER_BYTES) != recorded):
                    raise OrchestrationStoreError("orchestration event content changed")
                if not isinstance(event["action"], str):
                    raise OrchestrationStoreError("invalid orchestration action")
                # Every journal record must change exactly one task snapshot.
                before = {row.name: row.digest for row in previous.records}
                after = {row.name: row.digest for row in ledger.records}
                changed = [key for key, digest in after.items() if before.get(key) != digest]
                if len(changed) != 1 or any(key not in after for key in before):
                    raise OrchestrationStoreError("orchestration revision must change one task")
                if event["action"].startswith("append:"):
                    if changed[0] in before or event["action"] != "append:" + changed[0]:
                        raise OrchestrationStoreError("orchestration append identity mismatch")
                elif event["action"].startswith("transition:"):
                    if changed[0] not in before or event["action"] != "transition:" + changed[0]:
                        raise OrchestrationStoreError("orchestration transition identity mismatch")
                else:
                    raise OrchestrationStoreError("unsupported orchestration action")
                head = recorded
                count += 1
            if meta != (head, count):
                raise OrchestrationStoreError("orchestration state head mismatch")
            return ledger, head, count

    def _commit(
        self, action: str, ledger: OrchestrLedger, *,
        actor: str, authority: Authority, proof_digest: str, at_ns: int,
        expected_head: str,
    ) -> tuple[OrchestrLedger, str]:
        if not isinstance(authority, Authority):
            raise OrchestrationStoreError("typed authority required")
        if self._authorize(actor, authority, action, proof_digest) is not True:
            raise OrchestrationStoreError("host denied orchestration state transition")
        with self._lock:
            _, active_head, count = self.load()
            if active_head != expected_head:
                raise OrchestrationStoreError("stale orchestration head")
            if count >= MAX_REVISIONS:
                raise OrchestrationStoreError("orchestration event capacity exhausted")
            event = _event(revision=count, old=active_head, ledger=ledger,
                           actor=actor, action=action, proof=proof_digest, at_ns=at_ns)
            event_sha = canonical_digest(event, max_bytes=MAX_LEDGER_BYTES)
            encoded_event = _encode(event)
            encoded_ledger = _serialize(ledger)
            try:
                self._db.execute("BEGIN IMMEDIATE")
                current = self._db.execute(
                    "SELECT event_digest, revision_count "
                    "FROM jeeves_orchestration_meta WHERE singleton=1"
                ).fetchone()
                if current != (active_head, count):
                    raise OrchestrationStoreError("concurrent orchestration writer won lease")
                self._db.execute(
                    "INSERT INTO jeeves_orchestration_journal VALUES (?, ?, ?, ?, ?)",
                    (count, active_head, event_sha, encoded_event, encoded_ledger),
                )
                self._db.execute(
                    "UPDATE jeeves_orchestration_meta "
                    "SET event_digest=?, revision_count=? WHERE singleton=1",
                    (event_sha, count + 1),
                )
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            return ledger, event_sha

    def append(
        self, record: OrchestrRecord, *,
        actor: str, authority: Authority,
        proof_digest: str, at_ns: int,
        expected_head: str,
    ) -> tuple[OrchestrLedger, str]:
        with self._lock:
            ledger, head, _ = self.load()
            if head != expected_head:
                raise OrchestrationStoreError("stale orchestration append")
            if not isinstance(record, OrchestrRecord):
                raise OrchestrationStoreError("typed task record required")
            if authority is Authority.WORKER and record.authority is not Authority.WORKER:
                raise OrchestrationStoreError("worker cannot assign higher authority")
            if authority is Authority.SECRETARY and record.authority is Authority.SUPERVISOR:
                raise OrchestrationStoreError("secretary cannot assign supervisor authority")
            return self._commit(
                "append:" + record.name, ledger.append(record),
                actor=actor, authority=authority,
                proof_digest=proof_digest, at_ns=at_ns,
                expected_head=head,
            )

    def transition(
        self, name: str, state: OrchestrState, *,
        evidence: tuple[str, ...], actor: str, authority: Authority,
        proof_digest: str, at_ns: int,
        expected_head: str,
    ) -> tuple[OrchestrLedger, str]:
        with self._lock:
            ledger, head, _ = self.load()
            if head != expected_head:
                raise OrchestrationStoreError("stale orchestration transition")
            record = next((r for r in ledger.records if r.name == name), None)
            if record is None:
                raise OrchestrationStoreError("unknown orchestration task")
            if authority is Authority.WORKER and record.authority is not Authority.WORKER:
                raise OrchestrationStoreError("worker cannot transition higher authority")
            if authority is Authority.SECRETARY and record.authority is Authority.SUPERVISOR:
                raise OrchestrationStoreError("secretary cannot transition supervisor state")
            if not isinstance(evidence, tuple) or any(
                not isinstance(d, str) or len(d) != 64 or
                any(c not in "0123456789abcdef" for c in d) for d in evidence
            ):
                raise OrchestrationStoreError("transitions require SHA-256 evidence references")
            return self._commit(
                "transition:" + name, ledger.transition(name, state, evidence=evidence),
                actor=actor, authority=authority,
                proof_digest=proof_digest, at_ns=at_ns,
                expected_head=head,
            )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "DurableOrchestrLedger":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = ["OrchestrationStoreError", "DurableOrchestrLedger"]
