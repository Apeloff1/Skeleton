"""Deterministic binding of high-assurance execution control surfaces."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.shells.ai.risk import RiskBand


@dataclass(frozen=True)
class AssuranceBinding:
    schema_version: int
    risk_band: RiskBand
    assurance_policy_digest: str
    plan_fingerprint: str
    release_evidence_digest: str = ""
    preconditions_digest: str = ""
    approval_id: str = ""
    quorum_digest: str = ""
    execution_backend_id: str = ""
    sandbox_binding_digest: str = ""
    runtime_trust_digest: str = ""
    execution_fence_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported assurance binding schema")
        object.__setattr__(self, "risk_band", RiskBand(self.risk_band))
        if len(self.assurance_policy_digest) != 64:
            raise ValueError("assurance policy digest must be SHA-256 hex")
        if len(self.plan_fingerprint) != 64:
            raise ValueError("plan fingerprint must be SHA-256 hex")
        for name in (
            "release_evidence_digest",
            "preconditions_digest",
            "quorum_digest",
            "sandbox_binding_digest",
            "runtime_trust_digest",
            "execution_fence_digest",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        if len(self.approval_id) > 128:
            raise ValueError("approval_id too long")
        if len(self.execution_backend_id) > 256:
            raise ValueError("execution_backend_id too long")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "risk_band": self.risk_band.value,
            "assurance_policy_digest": self.assurance_policy_digest,
            "plan_fingerprint": self.plan_fingerprint,
            "release_evidence_digest": self.release_evidence_digest,
            "preconditions_digest": self.preconditions_digest,
            "approval_id": self.approval_id,
            "quorum_digest": self.quorum_digest,
            "execution_backend_id": self.execution_backend_id,
            "sandbox_binding_digest": self.sandbox_binding_digest,
            "runtime_trust_digest": self.runtime_trust_digest,
            "execution_fence_digest": self.execution_fence_digest,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()
