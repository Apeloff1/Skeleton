"""Canonical admission pipeline for consequential product operations.

This is the convergence seam for the redesign: product capability ownership,
charter policy, immutable artifact staging, durable intent journaling, and WORM
audit all happen before an executor is allowed to see work.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import uuid
from typing import Any

from core.charter_policy import CharterPolicy
from core.content_store import ContentAddressedStore, Manifest
from core.durable_outbox import DurableOutbox, OutboxEntry
from core.product_kernel import ProductKernel
from core.worm_audit import AuditEntry, WormAuditLog


class OperationRejected(RuntimeError):
    pass


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


class ProductOperationCoordinator:
    def __init__(
        self,
        root: str | Path,
        *,
        kernel: ProductKernel,
        policy: CharterPolicy,
        outbox_cap: int = 4096,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.kernel = kernel
        self.policy = policy
        self.store = ContentAddressedStore(self.root / "artifacts")
        self.outbox = DurableOutbox(self.root / "outbox", cap=outbox_cap)
        self.audit = WormAuditLog(self.root / "audit")

    @staticmethod
    def _encode_payload(payload: dict[str, Any]) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def admit(
        self,
        *,
        capability_id: str,
        domain: str,
        action: str,
        principal: str,
        actor_weight: int,
        payload: dict[str, Any],
        quorum_approved: bool = False,
    ) -> AdmittedOperation:
        capability = self.kernel.by_id(capability_id)
        if capability is None:
            raise OperationRejected(f"unknown product capability: {capability_id}")
        decision = self.policy.decide(domain, action, actor_weight)
        if not decision.permitted:
            self.audit.append(
                kind="operation_rejected",
                seal=decision.cited_rule or "NO_RULE",
                principal=principal,
                route=f"product:{capability_id}",
                detail=decision.reason,
            )
            raise OperationRejected(decision.reason)
        if decision.quorum_required and not quorum_approved:
            self.audit.append(
                kind="operation_rejected",
                seal=decision.cited_rule or "QUORUM",
                principal=principal,
                route=f"product:{capability_id}",
                detail="charter permits action but quorum approval is missing",
            )
            raise OperationRejected("quorum approval required")

        op_id = uuid.uuid4().hex
        artifact: Manifest = self.store.put_bytes(
            f"operation-{op_id}.json", self._encode_payload(payload)
        )
        admitted_at = datetime.now(UTC).isoformat()
        intent = {
            "operation_id": op_id,
            "capability_id": capability.id,
            "pillar": capability.pillar.value,
            "domain": domain,
            "action": action,
            "principal": principal,
            "artifact_manifest_id": artifact.id,
            "admitted_at": admitted_at,
        }
        outbox_entry: OutboxEntry = self.outbox.journal("product_operations", intent)
        audit_entry: AuditEntry = self.audit.append(
            kind="operation_admitted",
            seal=decision.cited_rule or "CHARTER",
            principal=principal,
            route=f"product:{capability_id}",
            detail=json.dumps(
                {"operation_id": op_id, "outbox_seq": outbox_entry.seq, "artifact": artifact.id},
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        return AdmittedOperation(
            id=op_id,
            capability_id=capability.id,
            pillar=capability.pillar.value,
            domain=domain,
            action=action,
            principal=principal,
            artifact_manifest_id=artifact.id,
            outbox_seq=outbox_entry.seq,
            admitted_at=admitted_at,
            audit_hash=audit_entry.hash,
        )

    def load_payload(self, operation: AdmittedOperation) -> dict[str, Any]:
        manifest = self.store.load_manifest(operation.artifact_manifest_id)
        return json.loads(self.store.read_manifest(manifest).decode("utf-8"))

    def snapshot(self) -> dict[str, Any]:
        latest = self.audit.latest
        return {
            "capabilities": len(self.kernel.all()),
            "pending_operations": self.outbox.pending_count,
            "content_store": self.store.stats(),
            "audit_sequence": self.audit.sequence,
            "audit_head": latest.hash if latest else None,
        }
