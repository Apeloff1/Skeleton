"""Fail-closed reconciliation for deferred effects with externally observed outcomes.

Reconciliation never dispatches a handler. It may only terminalize an existing
durable started record when an independently authenticated provider attests to
the exact operation identity and outcome material.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Callable, Mapping
from .contracts import canonical_json, sha256_json
from .executor import ExecutionReceipt, FailureReceipt
from .journal import DeferredExecutionJournal, DeferredJournalConflict

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()

def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value

@dataclass(frozen=True, slots=True)
class ProviderOutcomeEvidence:
    operation_id: str
    invocation_fingerprint: str
    handler_identity: str
    provider_identity: str
    outcome: str
    outcome_digest: str
    evidence_nonce: str
    signature: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _text(self.operation_id, "operation_id"))
        object.__setattr__(self, "handler_identity", _text(self.handler_identity, "handler_identity"))
        object.__setattr__(self, "provider_identity", _text(self.provider_identity, "provider_identity"))
        object.__setattr__(self, "evidence_nonce", _text(self.evidence_nonce, "evidence_nonce"))
        if self.outcome not in {"succeeded", "failed"}:
            raise ValueError("outcome must be succeeded or failed")
        for name in ("invocation_fingerprint", "outcome_digest", "signature"):
            object.__setattr__(self, name, _digest(getattr(self, name), name))

    def signed_material(self) -> dict[str, str]:
        return {
            "operation_id": self.operation_id,
            "invocation_fingerprint": self.invocation_fingerprint,
            "handler_identity": self.handler_identity,
            "provider_identity": self.provider_identity,
            "outcome": self.outcome,
            "outcome_digest": self.outcome_digest,
            "evidence_nonce": self.evidence_nonce,
        }

    @property
    def evidence_digest(self) -> str:
        return sha256_json({**self.signed_material(), "signature": self.signature})

@dataclass(frozen=True, slots=True)
class ReconciliationReceipt:
    operation_id: str
    journal_record_digest: str
    evidence_digest: str
    provider_identity: str
    outcome: str
    terminal_record_digest: str

    @property
    def digest(self) -> str:
        return sha256_json({
            "schema_version": 1,
            "operation_id": self.operation_id,
            "journal_record_digest": self.journal_record_digest,
            "evidence_digest": self.evidence_digest,
            "provider_identity": self.provider_identity,
            "outcome": self.outcome,
            "terminal_record_digest": self.terminal_record_digest,
        })

class DeferredOutcomeReconciler:
    """Resolve unknown durable outcomes without replaying their effects."""

    def __init__(self, journal: DeferredExecutionJournal, *, verify_signature: Callable[[str, Mapping[str, str], str], bool]) -> None:
        if not callable(verify_signature):
            raise TypeError("verify_signature must be callable")
        self.journal = journal
        self.verify_signature = verify_signature

    def reconcile(self, evidence: ProviderOutcomeEvidence, *, result: Any | None = None, error_type: str | None = None) -> ReconciliationReceipt:
        if not isinstance(evidence, ProviderOutcomeEvidence):
            raise TypeError("evidence must be ProviderOutcomeEvidence")
        record = self.journal.load(evidence.operation_id)
        if record is None:
            raise DeferredJournalConflict("reconciliation requires an existing journal record")
        if record.state != "started":
            raise DeferredJournalConflict("reconciliation requires unresolved started state")
        if record.fingerprint != evidence.invocation_fingerprint:
            raise DeferredJournalConflict("provider evidence invocation fingerprint mismatch")
        if record.handler_identity != evidence.handler_identity:
            raise DeferredJournalConflict("provider evidence handler identity mismatch")
        if not self.verify_signature(evidence.provider_identity, evidence.signed_material(), evidence.signature):
            raise PermissionError("provider outcome evidence signature rejected")

        invocation = record.invocation
        common = {
            "operation_id": evidence.operation_id,
            "volume_id": invocation["volume_id"],
            "spec_digest": invocation["spec_digest"],
            "authority_digest": invocation["authority_digest"],
            "payload_digest": invocation["payload_digest"],
            "handler_identity": record.handler_identity,
            "attempt": 1,
            "cost_units": invocation["cost_units"],
            "latency_ms": invocation["latency_ms"],
        }
        if evidence.outcome == "succeeded":
            if result is None:
                raise ValueError("successful reconciliation requires result")
            encoded = canonical_json(result)
            actual = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            if actual != evidence.outcome_digest:
                raise DeferredJournalConflict("provider success result digest mismatch")
            receipt = ExecutionReceipt(**common, result_digest=actual)
            terminal = {
                "receipt": receipt.as_dict(),
                "receipt_digest": receipt.digest,
                "result": json.loads(encoded),
                "reconciliation": {"provider_identity": evidence.provider_identity, "evidence_digest": evidence.evidence_digest},
            }
        else:
            if result is not None:
                raise ValueError("failed reconciliation must not include result")
            error_type = _text(error_type, "error_type")
            receipt = FailureReceipt(**common, error_type=error_type, error_digest=evidence.outcome_digest)
            terminal = {
                "receipt": receipt.as_dict(),
                "receipt_digest": receipt.digest,
                "reconciliation": {"provider_identity": evidence.provider_identity, "evidence_digest": evidence.evidence_digest},
            }

        terminal_record = self.journal.record_terminal(
            operation_id=evidence.operation_id,
            fingerprint=evidence.invocation_fingerprint,
            state=evidence.outcome,
            terminal=terminal,
        )
        return ReconciliationReceipt(
            operation_id=evidence.operation_id,
            journal_record_digest=record.record_digest,
            evidence_digest=evidence.evidence_digest,
            provider_identity=evidence.provider_identity,
            outcome=evidence.outcome,
            terminal_record_digest=terminal_record.record_digest,
        )

__all__ = ["DeferredOutcomeReconciler", "ProviderOutcomeEvidence", "ReconciliationReceipt"]
