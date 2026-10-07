"""Decision provenance envelopes for AI-assisted shell execution."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True)
class AIDecisionProvenance:
    intent_fingerprint: str
    proposal_fingerprint: str
    tool_catalog_digest: str
    effect_digest: str
    policy_fingerprint: str
    schema_digest: str
    model_id: str
    risk_score: int
    approval_id: str = ""
    receipt_root: str = ""
    execution_backend_id: str = ""
    session_evidence_digest: str = ""
    sandbox_binding_digest: str = ""
    release_evidence_digest: str = ""
    runtime_trust_digest: str = ""
    authority_health_policy_digest: str = ""

    def __post_init__(self) -> None:
        for name in (
            "intent_fingerprint",
            "proposal_fingerprint",
            "tool_catalog_digest",
            "effect_digest",
            "policy_fingerprint",
            "schema_digest",
        ):
            value = getattr(self, name)
            if len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        if not 0 <= self.risk_score <= 100:
            raise ValueError("risk_score out of range")
        if len(self.model_id) > 256 or len(self.approval_id) > 128:
            raise ValueError("provenance identity field too long")
        if self.receipt_root and len(self.receipt_root) != 64:
            raise ValueError("receipt_root must be SHA-256 hex")
        if len(self.execution_backend_id) > 256:
            raise ValueError("execution_backend_id too long")
        for name in (
            "session_evidence_digest",
            "sandbox_binding_digest",
            "release_evidence_digest",
            "runtime_trust_digest",
            "authority_health_policy_digest",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")

    def to_dict(self) -> dict[str, object]:
        data = {
            "intent_fingerprint": self.intent_fingerprint,
            "proposal_fingerprint": self.proposal_fingerprint,
            "tool_catalog_digest": self.tool_catalog_digest,
            "effect_digest": self.effect_digest,
            "policy_fingerprint": self.policy_fingerprint,
            "schema_digest": self.schema_digest,
            "model_id": self.model_id,
            "risk_score": self.risk_score,
            "approval_id": self.approval_id,
            "receipt_root": self.receipt_root,
        }
        if self.execution_backend_id:
            data["execution_backend_id"] = self.execution_backend_id
        if self.session_evidence_digest:
            data["session_evidence_digest"] = self.session_evidence_digest
        if self.sandbox_binding_digest:
            data["sandbox_binding_digest"] = self.sandbox_binding_digest
        if self.release_evidence_digest:
            data["release_evidence_digest"] = self.release_evidence_digest
        if self.runtime_trust_digest:
            data["runtime_trust_digest"] = self.runtime_trust_digest
        if self.authority_health_policy_digest:
            data["authority_health_policy_digest"] = (
                self.authority_health_policy_digest
            )
        return data

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()
