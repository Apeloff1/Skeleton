"""Evidence bundle for model, policy, and autonomy releases."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.shells.ai.provider_attestation import ProviderAttestation
from skeleton.shells.ai.safety_case import SafetyCase


@dataclass(frozen=True)
class ReleaseEvidence:
    release_id: str
    code_revision: str
    policy_fingerprint: str
    tool_catalog_digest: str
    effect_digest: str
    eval_dataset_digest: str
    eval_run_digest: str
    provider_attestation_digest: str
    safety_case: SafetyCase
    workspace_manifest_digest: str = ""

    def __post_init__(self) -> None:
        if not self.release_id or len(self.release_id) > 160:
            raise ValueError("invalid release_id")
        if not self.code_revision or len(self.code_revision) > 256:
            raise ValueError("invalid code_revision")
        for name in (
            "policy_fingerprint",
            "tool_catalog_digest",
            "effect_digest",
            "eval_dataset_digest",
            "eval_run_digest",
            "provider_attestation_digest",
        ):
            if len(getattr(self, name)) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        if self.workspace_manifest_digest and len(self.workspace_manifest_digest) != 64:
            raise ValueError("workspace_manifest_digest must be SHA-256 hex")

    def to_dict(self) -> dict[str, object]:
        return {
            "release_id": self.release_id,
            "code_revision": self.code_revision,
            "policy_fingerprint": self.policy_fingerprint,
            "tool_catalog_digest": self.tool_catalog_digest,
            "effect_digest": self.effect_digest,
            "eval_dataset_digest": self.eval_dataset_digest,
            "eval_run_digest": self.eval_run_digest,
            "provider_attestation_digest": self.provider_attestation_digest,
            "workspace_manifest_digest": self.workspace_manifest_digest,
            "safety_case": self.safety_case.to_dict(),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def deployable(self) -> bool:
        return self.safety_case.deployable


class ReleaseEvidenceBuilder:
    def build(
        self,
        *,
        release_id: str,
        code_revision: str,
        policy_fingerprint: str,
        tool_catalog_digest: str,
        effect_digest: str,
        eval_dataset_digest: str,
        eval_run_payload: dict[str, object],
        provider_attestation: ProviderAttestation,
        safety_case: SafetyCase,
        workspace_manifest_digest: str = "",
    ) -> ReleaseEvidence:
        eval_raw = json.dumps(
            eval_run_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return ReleaseEvidence(
            release_id,
            code_revision,
            policy_fingerprint,
            tool_catalog_digest,
            effect_digest,
            eval_dataset_digest,
            hashlib.sha256(eval_raw).hexdigest(),
            provider_attestation.digest,
            safety_case,
            workspace_manifest_digest,
        )
