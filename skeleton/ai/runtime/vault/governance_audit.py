"""Governance lifecycle audit timeline.

This bridge records lifecycle control-plane facts into the canonical hash-chained
WORM audit log and tracing plane. It intentionally excludes user payloads and
raw source references. Record/tenant identities are represented by SHA-256
fingerprints in telemetry; the WORM log also fingerprints its subject key.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Iterable
from uuid import uuid4

from skeleton.observability.correlation import get_correlation_id
from skeleton.observability.redaction import redact_payload
from skeleton.observability.tracing import Tracer
from skeleton.vault.audit import AuditEntry, AuditLog
from skeleton.vault.data_lifecycle import (
    DeletionAction,
    DeletionPlan,
    DeletionReceipt,
    GovernedDataRecord,
)


def _fingerprint(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _event_id(kind: str, *parts: object) -> str:
    material = "\x1f".join((kind, *(str(part) for part in parts)))
    return "gova-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


class GovernanceAuditTimeline:
    """Write payload-free governance facts to WORM audit + tracing."""

    def __init__(
        self,
        audit_log: AuditLog,
        *,
        tracer: Tracer | None = None,
        actor: str = "governance-runtime",
    ) -> None:
        if not isinstance(audit_log, AuditLog):
            raise TypeError("audit_log must be an AuditLog")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor must be a non-empty string")
        self.audit_log = audit_log
        self.tracer = tracer
        self.actor = actor.strip()

    def _correlation_id(self) -> str:
        return get_correlation_id() or uuid4().hex

    def _append(
        self,
        *,
        entry_id: str,
        action: str,
        subject_key: str | None,
        outcome: str,
        metadata: dict[str, Any],
        correlation_id: str | None = None,
    ) -> AuditEntry:
        cid = correlation_id or self._correlation_id()
        safe_metadata = dict(
            redact_payload(
                {
                    **metadata,
                    "correlation_id": cid,
                }
            )
        )
        entry = self.audit_log.append(
            entry_id=entry_id,
            actor=self.actor,
            action=action,
            subject_key=subject_key,
            outcome=outcome,
            metadata=safe_metadata,
        )
        if self.tracer is not None:
            span = self.tracer.start_span(
                "governance.lifecycle",
                trace_id=cid,
                governance_action=action,
                outcome=outcome,
            )
            span.add_event(action, **safe_metadata)
            span.ended_at = time.time()
            try:
                self.tracer.exporter.export(span)
            except Exception:
                # Audit is authoritative. Telemetry export is best-effort.
                pass
        return entry

    def record_registration(
        self,
        record: GovernedDataRecord,
        *,
        mode: str = "register",
        correlation_id: str | None = None,
    ) -> AuditEntry:
        normalized_mode = str(mode).strip().lower()
        if normalized_mode not in {"register", "reconcile"}:
            raise ValueError("governance registration audit mode is invalid")
        return self._append(
            entry_id=_event_id(
                normalized_mode,
                record.record_id,
                record.tenant_id,
                record.owner_plane,
                record.data_class.label,
                ",".join(record.purposes),
                ",".join(record.deletion_targets),
                record.retention_until,
                record.exportable,
            ),
            action=f"governance.lifecycle.{normalized_mode}",
            subject_key=record.record_id,
            outcome="success",
            correlation_id=correlation_id,
            metadata={
                "record_fp": _fingerprint(record.record_id),
                "tenant_fp": _fingerprint(record.tenant_id),
                "owner_plane": record.owner_plane,
                "data_class": record.data_class.label,
                "purposes": list(record.purposes),
                "deletion_targets": list(record.deletion_targets),
                "has_retention": record.retention_until is not None,
                "exportable": record.exportable,
                "source_ref_fp": _fingerprint(record.source_ref),
            },
        )

    def record_plan(
        self,
        plan: DeletionPlan,
        *,
        correlation_id: str | None = None,
    ) -> AuditEntry:
        targets = sorted({action.target for action in plan.actions})
        return self._append(
            entry_id=_event_id("plan", plan.plan_id),
            action="governance.lifecycle.plan",
            subject_key=plan.plan_id,
            outcome="planned",
            correlation_id=correlation_id,
            metadata={
                "plan_id": plan.plan_id,
                "tenant_fp": _fingerprint(plan.tenant_id),
                "reason": plan.reason,
                "action_count": len(plan.actions),
                "targets": targets,
            },
        )

    def record_preflight_denied(
        self,
        plan: DeletionPlan,
        missing_targets: Iterable[str],
        *,
        correlation_id: str | None = None,
    ) -> AuditEntry:
        missing = tuple(sorted({str(target).strip().lower() for target in missing_targets}))
        return self._append(
            entry_id=_event_id("preflight-denied", plan.plan_id, ",".join(missing)),
            action="governance.lifecycle.preflight_denied",
            subject_key=plan.plan_id,
            outcome="denied",
            correlation_id=correlation_id,
            metadata={
                "plan_id": plan.plan_id,
                "tenant_fp": _fingerprint(plan.tenant_id),
                "missing_targets": list(missing),
            },
        )

    def record_receipt(
        self,
        action: DeletionAction,
        receipt: DeletionReceipt,
        *,
        correlation_id: str | None = None,
    ) -> AuditEntry:
        return self._append(
            entry_id=_event_id("receipt", receipt.receipt_id),
            action="governance.lifecycle.delete",
            subject_key=action.record_id,
            outcome="success",
            correlation_id=correlation_id,
            metadata={
                "plan_id": receipt.plan_id,
                "receipt_id": receipt.receipt_id,
                "record_fp": _fingerprint(action.record_id),
                "tenant_fp": _fingerprint(action.tenant_id),
                "target": action.target,
                "state": receipt.state.value,
                "reason": action.reason,
            },
        )

    def record_failure(
        self,
        action: DeletionAction,
        error: BaseException,
        *,
        correlation_id: str | None = None,
    ) -> AuditEntry:
        # Deliberately record only the exception class, never its message.
        return self._append(
            entry_id=_event_id(
                "failure",
                action.record_id,
                action.target,
                type(error).__name__,
                correlation_id or get_correlation_id(),
            ),
            action="governance.lifecycle.delete",
            subject_key=action.record_id,
            outcome="failure",
            correlation_id=correlation_id,
            metadata={
                "record_fp": _fingerprint(action.record_id),
                "tenant_fp": _fingerprint(action.tenant_id),
                "target": action.target,
                "reason": action.reason,
                "error_type": type(error).__name__,
            },
        )

    def record_export_denied(
        self,
        tenant_id: str,
        missing_owner_planes: Iterable[str],
        *,
        correlation_id: str | None = None,
    ) -> AuditEntry:
        missing = tuple(
            sorted({str(owner).strip().lower() for owner in missing_owner_planes})
        )
        return self._append(
            entry_id=_event_id(
                "export-denied",
                _fingerprint(tenant_id),
                ",".join(missing),
            ),
            action="governance.lifecycle.export",
            subject_key=tenant_id,
            outcome="denied",
            correlation_id=correlation_id,
            metadata={
                "tenant_fp": _fingerprint(tenant_id),
                "missing_owner_planes": list(missing),
            },
        )

    def record_export_failure(
        self,
        tenant_id: str,
        owner_plane: str,
        error: BaseException,
        *,
        correlation_id: str | None = None,
    ) -> AuditEntry:
        return self._append(
            entry_id=_event_id(
                "export-failure",
                _fingerprint(tenant_id),
                owner_plane,
                type(error).__name__,
                correlation_id or get_correlation_id(),
            ),
            action="governance.lifecycle.export",
            subject_key=tenant_id,
            outcome="failure",
            correlation_id=correlation_id,
            metadata={
                "tenant_fp": _fingerprint(tenant_id),
                "owner_plane": str(owner_plane),
                "error_type": type(error).__name__,
            },
        )

    def record_export(
        self,
        tenant_id: str,
        records: Iterable[dict[str, Any]],
        *,
        correlation_id: str | None = None,
    ) -> AuditEntry:
        rows = tuple(records)
        owner_planes = sorted(
            {
                str(row.get("governance", {}).get("owner_plane", "unknown"))
                for row in rows
            }
        )
        record_fps = sorted(
            _fingerprint(row.get("governance", {}).get("record_id", ""))
            for row in rows
        )
        return self._append(
            entry_id=_event_id(
                "export",
                _fingerprint(tenant_id),
                ",".join(record_fps),
            ),
            action="governance.lifecycle.export",
            subject_key=tenant_id,
            outcome="success",
            correlation_id=correlation_id,
            metadata={
                "tenant_fp": _fingerprint(tenant_id),
                "record_count": len(rows),
                "record_fps": record_fps,
                "owner_planes": owner_planes,
            },
        )


__all__ = ["GovernanceAuditTimeline"]
