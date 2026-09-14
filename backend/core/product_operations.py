"""Canonical admission and execution pipeline for consequential product operations.

Capability ownership, charter policy, immutable artifact staging, durable intent,
idempotent retries, executor acknowledgement and WORM audit converge here.
Admissions are serialized across processes: the idempotency index is refreshed
under a FileLease and CAS staging occurs inside the outbox's leased intent factory,
closing duplicate-key and capacity/staging races between workers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import inspect
import json
import os
from pathlib import Path
import threading
import uuid
from typing import Any, Awaitable, Callable

from core.charter_policy import CharterPolicy
from core.content_store import ContentAddressedStore, Manifest
from core.durable_outbox import DurableOutbox, OutboxEntry
from core.file_lease import FileLease
from core.product_kernel import ProductKernel
from core.worm_audit import AuditEntry, WormAuditLog


class OperationRejected(RuntimeError): pass
class OperationExecutionError(RuntimeError): pass


@dataclass(frozen=True, slots=True)
class AdmittedOperation:
    id: str
    capability_id: str
    pillar: str
    domain: str
    action: str
    principal: str
    artifact_manifest_id: str
    outbox_seq: int
    admitted_at: str
    audit_hash: str
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    operation_id: str
    outbox_seq: int
    executed: bool
    confirmed: bool
    audit_hash: str


Executor = Callable[[AdmittedOperation, dict[str, Any]], bool | Awaitable[bool]]


class ProductOperationCoordinator:
    INDEX_VERSION = 1

    def __init__(self, root: str | Path, *, kernel: ProductKernel, policy: CharterPolicy, outbox_cap: int = 4096) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.kernel = kernel; self.policy = policy
        self.store = ContentAddressedStore(self.root / "artifacts")
        self.outbox = DurableOutbox(self.root / "outbox", cap=outbox_cap)
        self.audit = WormAuditLog(self.root / "audit")
        self._index_path = self.root / "operation-index.json"
        self._process_lock = FileLease(self.root / ".operations.lock")
        self._lock = threading.RLock()
        with self._process_lock.acquire(): self._idempotency = self._load_index()

    @staticmethod
    def _encode_payload(payload: dict[str, Any]) -> bytes: return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    @staticmethod
    def _canonical(value: Any) -> bytes: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    @classmethod
    def _index_digest(cls, records: dict[str, dict[str, Any]]) -> str:
        return hashlib.sha256(cls._canonical({"version": cls.INDEX_VERSION, "records": records})).hexdigest()

    def _load_index(self) -> dict[str, dict[str, Any]]:
        if not self._index_path.exists(): return {}
        try: envelope = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise OperationRejected("operation idempotency index is unreadable") from exc
        if not isinstance(envelope, dict): raise OperationRejected("operation idempotency index envelope must be an object")
        if envelope.get("version") != self.INDEX_VERSION: raise OperationRejected("unsupported operation idempotency index version")
        records = envelope.get("records"); digest = envelope.get("sha256")
        if not isinstance(records, dict) or not isinstance(digest, str): raise OperationRejected("operation idempotency index envelope is malformed")
        normalized = {str(k): dict(v) for k, v in records.items() if isinstance(v, dict)}
        if len(normalized) != len(records): raise OperationRejected("operation idempotency index contains invalid records")
        if not hmac.compare_digest(self._index_digest(normalized), digest): raise OperationRejected("operation idempotency index checksum mismatch")
        for raw in normalized.values():
            try: self._restore_operation(raw)
            except (TypeError, ValueError) as exc: raise OperationRejected("operation idempotency index contains invalid operation") from exc
        return normalized

    def _persist_index(self) -> None:
        envelope = {"version": self.INDEX_VERSION, "records": self._idempotency, "sha256": self._index_digest(self._idempotency)}
        temp = self._index_path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with temp.open("xb") as handle: handle.write(self._canonical(envelope)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self._index_path)
        finally: temp.unlink(missing_ok=True)

    @staticmethod
    def _restore_operation(raw: dict[str, Any]) -> AdmittedOperation: return AdmittedOperation(**raw)

    @staticmethod
    def _from_intent(entry: OutboxEntry) -> AdmittedOperation:
        p = entry.payload
        return AdmittedOperation(id=str(p["operation_id"]), capability_id=str(p["capability_id"]), pillar=str(p["pillar"]),
            domain=str(p["domain"]), action=str(p["action"]), principal=str(p["principal"]),
            artifact_manifest_id=str(p["artifact_manifest_id"]), outbox_seq=entry.seq, admitted_at=str(p["admitted_at"]),
            audit_hash=str(p.get("audit_hash", "")), idempotency_key=p.get("idempotency_key"))

    def admit(self, *, capability_id: str, domain: str, action: str, principal: str, actor_weight: int,
              payload: dict[str, Any], quorum_approved: bool = False, idempotency_key: str | None = None) -> AdmittedOperation:
        if not isinstance(payload, dict): raise ValueError("payload must be an object")
        if idempotency_key is not None:
            idempotency_key = idempotency_key.strip()
            if not idempotency_key: raise ValueError("idempotency_key cannot be blank")
        with self._lock:
            with self._process_lock.acquire():
                self._idempotency = self._load_index()
                if idempotency_key is not None and idempotency_key in self._idempotency:
                    return self._restore_operation(self._idempotency[idempotency_key])
                capability = self.kernel.by_id(capability_id)
                if capability is None: raise OperationRejected(f"unknown product capability: {capability_id}")
                decision = self.policy.decide(domain, action, actor_weight)
                if not decision.permitted:
                    self.audit.append(kind="operation_rejected", seal=decision.cited_rule or "NO_RULE", principal=principal,
                        route=f"product:{capability_id}", detail=decision.reason)
                    raise OperationRejected(decision.reason)
                if decision.quorum_required and not quorum_approved:
                    self.audit.append(kind="operation_rejected", seal=decision.cited_rule or "QUORUM", principal=principal,
                        route=f"product:{capability_id}", detail="charter permits action but quorum approval is missing")
                    raise OperationRejected("quorum approval required")

                op_id = uuid.uuid4().hex; admitted_at = datetime.now(UTC).isoformat(); artifact_box: dict[str, Manifest] = {}
                def build_intent(_seq: int) -> dict[str, Any]:
                    artifact = self.store.put_bytes(f"operation-{op_id}.json", self._encode_payload(payload)); artifact_box["value"] = artifact
                    return {"operation_id": op_id, "capability_id": capability.id, "pillar": capability.pillar.value,
                        "domain": domain, "action": action, "principal": principal, "artifact_manifest_id": artifact.id,
                        "admitted_at": admitted_at, "idempotency_key": idempotency_key}
                outbox_entry = self.outbox.journal_factory("product_operations", build_intent)
                artifact = artifact_box["value"]
                audit_entry: AuditEntry = self.audit.append(kind="operation_admitted", seal=decision.cited_rule or "CHARTER", principal=principal,
                    route=f"product:{capability_id}", detail=json.dumps({"operation_id": op_id, "outbox_seq": outbox_entry.seq, "artifact": artifact.id}, sort_keys=True, separators=(",", ":")))
                operation = AdmittedOperation(id=op_id, capability_id=capability.id, pillar=capability.pillar.value, domain=domain,
                    action=action, principal=principal, artifact_manifest_id=artifact.id, outbox_seq=outbox_entry.seq,
                    admitted_at=admitted_at, audit_hash=audit_entry.hash, idempotency_key=idempotency_key)
                if idempotency_key is not None:
                    self._idempotency[idempotency_key] = asdict(operation); self._persist_index()
                return operation

    def load_payload(self, operation: AdmittedOperation) -> dict[str, Any]:
        manifest = self.store.load_manifest(operation.artifact_manifest_id)
        payload = json.loads(self.store.read_manifest(manifest).decode("utf-8"))
        if not isinstance(payload, dict): raise OperationExecutionError("operation payload must decode to an object")
        return payload

    def pending_operations(self) -> tuple[AdmittedOperation, ...]:
        return tuple(self._from_intent(e) for e in self.outbox.pending() if e.collection == "product_operations")

    async def execute_one(self, seq: int, executor: Executor) -> ExecutionResult:
        entry = next((x for x in self.outbox.pending() if x.seq == seq), None)
        if entry is None: raise OperationExecutionError(f"unknown pending operation sequence: {seq}")
        if entry.collection != "product_operations": raise OperationExecutionError(f"outbox sequence {seq} is not a product operation")
        operation = self._from_intent(entry); payload = self.load_payload(operation)
        try:
            executed = executor(operation, payload)
            if inspect.isawaitable(executed): executed = await executed
        except Exception as exc:
            self.audit.append(kind="operation_execution_failed", seal="EXECUTOR", principal=operation.principal,
                route=f"product:{operation.capability_id}", detail=json.dumps({"operation_id": operation.id, "outbox_seq": seq, "error": type(exc).__name__}, sort_keys=True, separators=(",", ":")))
            raise OperationExecutionError(f"executor raised for operation {operation.id}") from exc
        if not executed:
            audit = self.audit.append(kind="operation_execution_deferred", seal="EXECUTOR", principal=operation.principal,
                route=f"product:{operation.capability_id}", detail=json.dumps({"operation_id": operation.id, "outbox_seq": seq}, sort_keys=True, separators=(",", ":")))
            return ExecutionResult(operation.id, seq, False, False, audit.hash)
        audit = self.audit.append(kind="operation_executed", seal="EXECUTOR", principal=operation.principal,
            route=f"product:{operation.capability_id}", detail=json.dumps({"operation_id": operation.id, "outbox_seq": seq}, sort_keys=True, separators=(",", ":")))
        confirmed = await self.outbox.confirm_one(seq, lambda _: True)
        return ExecutionResult(operation.id, seq, True, confirmed, audit.hash)

    async def execute_pending(self, executor: Executor, *, limit: int | None = None) -> int:
        pending = self.pending_operations()
        if limit is not None:
            if limit < 0: raise ValueError("limit cannot be negative")
            pending = pending[:limit]
        completed = 0
        for operation in pending:
            if (await self.execute_one(operation.outbox_seq, executor)).confirmed: completed += 1
        return completed

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            with self._process_lock.acquire(): self._idempotency = self._load_index(); idempotency_count = len(self._idempotency)
        audit_health = self.audit.health()
        return {"capabilities": len(self.kernel.all()), "pending_operations": self.outbox.pending_count,
            "outbox_capacity_remaining": self.outbox.capacity_remaining, "idempotency_records": idempotency_count,
            "content_store": self.store.stats(), "audit_sequence": audit_health["sequence"], "audit_head": audit_health["head"],
            "audit_health": audit_health, "admission_cross_process_locking": True, "admission_lock_backend": self._process_lock.backend}
