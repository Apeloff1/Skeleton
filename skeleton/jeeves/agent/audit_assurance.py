"""High-assurance replay grammar layered over the generic execution audit.

The base audit verifier proves hash continuity and operation-stage ordering. This
module tightens the *language* of valid frontier-runtime audit chains so run-level
records cannot be confused with operation-level security evidence.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .execution_audit import (
    AuditEventKind,
    ExecutionAuditCheckpoint,
    ExecutionAuditEntry,
    ExecutionReplayVerifier,
    GENESIS_HASH,
    ReplayIssue,
    ReplayIssueKind,
    ReplayReport,
)
from .types import stable_fingerprint


class FrontierExecutionReplayVerifier(ExecutionReplayVerifier):
    """Replay verifier with strict operation/run-level grammar and prefix proofs."""

    _OPERATION_KINDS = {
        AuditEventKind.INTENT_BOUND,
        AuditEventKind.DECISION_MADE,
        AuditEventKind.EXECUTION_DENIED,
        AuditEventKind.AUTHORIZATION_ISSUED,
        AuditEventKind.AUTHORIZATION_CONSUMED,
        AuditEventKind.TOOL_OBSERVED,
        AuditEventKind.EVIDENCE_INGESTED,
        AuditEventKind.TRANSITION_LEARNED,
        AuditEventKind.EXECUTION_FINALIZED,
        AuditEventKind.EXECUTION_FAILED,
    }
    _RUN_KINDS = {
        AuditEventKind.CHECKPOINT_BOUND,
        AuditEventKind.RUN_RESUMED,
    }
    _HEX_FIELDS = {
        AuditEventKind.INTENT_BOUND: (
            "intent_fingerprint",
            "request_fingerprint",
            "argument_fingerprint",
            "state_fingerprint",
            "model_fingerprint",
            "world_fingerprint",
            "profile_fingerprint",
        ),
        AuditEventKind.DECISION_MADE: (
            "decision_fingerprint",
            "policy_fingerprint",
            "world_fingerprint",
            "model_fingerprint",
        ),
        AuditEventKind.AUTHORIZATION_ISSUED: (
            "authorization_fingerprint",
            "token_fingerprint",
        ),
        AuditEventKind.AUTHORIZATION_CONSUMED: (
            "authorization_fingerprint",
            "permit_fingerprint",
        ),
        AuditEventKind.TOOL_OBSERVED: (
            "observation_fingerprint",
            "bound_execution_fingerprint",
        ),
        AuditEventKind.EVIDENCE_INGESTED: (
            "evidence_fingerprint",
            "observation_fingerprint",
        ),
        AuditEventKind.TRANSITION_LEARNED: ("model_fingerprint",),
        AuditEventKind.EXECUTION_FINALIZED: (
            "model_fingerprint",
            "evidence_fingerprint",
        ),
        AuditEventKind.CHECKPOINT_BOUND: (
            "checkpoint_fingerprint",
            "audit_head_before",
            "audit_checkpoint_before",
            "runtime_guard_policy",
            "transition_model_fingerprint",
            "transition_model_lineage_hash",
            "world_model_fingerprint",
        ),
        AuditEventKind.RUN_RESUMED: (
            "audit_head",
            "current_audit_head_before_resume",
        ),
    }

    def verify(
        self,
        entries: Sequence[ExecutionAuditEntry] | Iterable[ExecutionAuditEntry],
        *,
        expected_run_id: str | None = None,
        expected_checkpoint: ExecutionAuditCheckpoint | None = None,
        require_finalized_operations: bool = False,
    ) -> ReplayReport:
        items = tuple(entries)
        base = super().verify(
            items,
            expected_run_id=expected_run_id,
            expected_checkpoint=expected_checkpoint,
            require_finalized_operations=require_finalized_operations,
        )
        issues = list(base.issues)
        for entry in items:
            if entry.kind in self._OPERATION_KINDS and entry.operation_id is None:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.PROTOCOL_ORDER,
                        entry.sequence,
                        None,
                        f"{entry.kind.value} must be bound to an operation_id",
                    )
                )
            if entry.kind in self._RUN_KINDS and entry.operation_id is not None:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.PROTOCOL_ORDER,
                        entry.sequence,
                        entry.operation_id,
                        f"{entry.kind.value} is run-level and must not carry operation_id",
                    )
                )
            self._validate_hex_fields(entry, issues)
            if entry.kind is AuditEventKind.CHECKPOINT_BOUND:
                self._validate_checkpoint_binding(entry, issues)
            elif entry.kind is AuditEventKind.RUN_RESUMED:
                self._validate_resume_prefix(entry, items, issues)

        fingerprint = stable_fingerprint(
            {
                "base": base.fingerprint,
                "issues": [
                    (
                        issue.kind.value,
                        issue.sequence,
                        issue.operation_id,
                        issue.message,
                        issue.expected,
                        issue.actual,
                    )
                    for issue in issues
                ],
            }
        )
        return ReplayReport(
            run_id=base.run_id,
            valid=not issues,
            entries_checked=base.entries_checked,
            head_hash=base.head_hash,
            issues=tuple(issues),
            operations=base.operations,
            checkpoint=base.checkpoint,
            fingerprint=fingerprint,
        )

    def _validate_hex_fields(
        self,
        entry: ExecutionAuditEntry,
        issues: list[ReplayIssue],
    ) -> None:
        for field_name in self._HEX_FIELDS.get(entry.kind, ()):
            if field_name not in entry.payload:
                continue
            value = entry.payload.get(field_name)
            if not self._is_sha256(value):
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.REQUIRED_FIELD_MISSING,
                        entry.sequence,
                        entry.operation_id,
                        f"{entry.kind.value}.{field_name} must be a sha256 fingerprint",
                        "64 lowercase/uppercase hex characters",
                        value,
                    )
                )

    @classmethod
    def _validate_checkpoint_binding(
        cls,
        entry: ExecutionAuditEntry,
        issues: list[ReplayIssue],
    ) -> None:
        payload = entry.payload
        expected_events = entry.sequence - 1
        actual_events = payload.get("audit_events_before")
        if actual_events != expected_events:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.CHECKPOINT_MISMATCH,
                    entry.sequence,
                    None,
                    "checkpoint binding event count does not match chain position",
                    expected_events,
                    actual_events,
                )
            )
        actual_head = payload.get("audit_head_before")
        if actual_head != entry.previous_hash:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.CHECKPOINT_MISMATCH,
                    entry.sequence,
                    None,
                    "checkpoint binding audit_head_before does not match previous hash",
                    entry.previous_hash,
                    actual_head,
                )
            )

        version = payload.get("frontier_binding_version")
        if version is None:
            return
        if version != 2:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.CHECKPOINT_MISMATCH,
                    entry.sequence,
                    None,
                    "unsupported frontier checkpoint binding version",
                    2,
                    version,
                )
            )
            return
        required = (
            "runtime_guard_policy",
            "transition_model_fingerprint",
            "transition_model_lineage_count",
            "transition_model_lineage_hash",
            "world_model_fingerprint",
        )
        for field_name in required:
            if field_name not in payload:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.REQUIRED_FIELD_MISSING,
                        entry.sequence,
                        None,
                        f"frontier checkpoint binding is missing {field_name}",
                    )
                )
        lineage_count = payload.get("transition_model_lineage_count")
        if (
            isinstance(lineage_count, bool)
            or not isinstance(lineage_count, int)
            or lineage_count < 0
        ):
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.CHECKPOINT_MISMATCH,
                    entry.sequence,
                    None,
                    "frontier checkpoint model-lineage count must be non-negative integer",
                    None,
                    lineage_count,
                )
            )
        for field_name in (
            "runtime_guard_policy",
            "transition_model_fingerprint",
            "transition_model_lineage_hash",
            "world_model_fingerprint",
        ):
            value = payload.get(field_name)
            if value is not None and not cls._is_sha256(value):
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.REQUIRED_FIELD_MISSING,
                        entry.sequence,
                        None,
                        f"frontier checkpoint {field_name} must be sha256",
                        "64 hex characters",
                        value,
                    )
                )

    @staticmethod
    def _validate_resume_prefix(
        entry: ExecutionAuditEntry,
        items: Sequence[ExecutionAuditEntry],
        issues: list[ReplayIssue],
    ) -> None:
        payload = entry.payload
        count = payload.get("audit_events")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.CHECKPOINT_MISMATCH,
                    entry.sequence,
                    None,
                    "run_resumed.audit_events must be a non-negative integer",
                    None,
                    count,
                )
            )
            return
        if count >= entry.sequence:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.CHECKPOINT_MISMATCH,
                    entry.sequence,
                    None,
                    "run resume prefix points at current/future audit sequence",
                    f"< {entry.sequence}",
                    count,
                )
            )
            return
        expected_head = GENESIS_HASH if count == 0 else items[count - 1].event_hash
        actual_head = payload.get("audit_head")
        if actual_head != expected_head:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.CHECKPOINT_MISMATCH,
                    entry.sequence,
                    None,
                    "run resume audit head does not identify the declared prior prefix",
                    expected_head,
                    actual_head,
                )
            )
        current_before = payload.get("current_audit_head_before_resume")
        if current_before != entry.previous_hash:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.PREVIOUS_HASH_MISMATCH,
                    entry.sequence,
                    None,
                    "run resume current_audit_head_before_resume does not match chain head",
                    entry.previous_hash,
                    current_before,
                )
            )
        events_before = payload.get("current_audit_events_before_resume")
        if events_before != entry.sequence - 1:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.SEQUENCE_GAP,
                    entry.sequence,
                    None,
                    "run resume current event count does not match chain position",
                    entry.sequence - 1,
                    events_before,
                )
            )

    @staticmethod
    def _is_sha256(value: object) -> bool:
        if not isinstance(value, str) or len(value) != 64:
            return False
        return all(ch in "0123456789abcdefABCDEF" for ch in value)