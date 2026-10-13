"""Final signed evidence bundle for one AI-directed shell execution."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Callable

from skeleton.shells.ai.signed_artifact import ArtifactSigner, SignedArtifact
from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
    EvidenceCorruption,
    EvidenceStateBackend,
)


@dataclass(frozen=True)
class AIExecutionEvidence:
    schema_version: int
    session_id: str
    intent_fingerprint: str
    proposal_fingerprint: str
    provenance_digest: str
    checkpoint_digest: str
    session_evidence_digest: str
    session_journal_digest: str
    audit_anchor_digest: str
    audit_chain_node_hash: str
    release_evidence_digest: str = ""
    sandbox_binding_digest: str = ""
    model_attestation_digest: str = ""
    execution_seal_id: str = ""
    quorum_approval_digest: str = ""
    runtime_trust_digest: str = ""
    authority_health_policy_digest: str = ""
    execution_attempt_id: str = ""
    execution_attempt_authority_digest: str = ""
    audit_witness_digest: str = ""
    audit_witness_sequence: int | None = None
    execution_attempt_state: str = ""
    completed_at: float = 0.0
    session_integrity_digest: str = ""
    session_journal_manifest_digest: str = ""
    root_protection_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported AI execution evidence schema")
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError("invalid execution evidence session_id")
        required = (
            "intent_fingerprint",
            "proposal_fingerprint",
            "provenance_digest",
            "checkpoint_digest",
            "session_evidence_digest",
            "session_journal_digest",
            "audit_anchor_digest",
            "audit_chain_node_hash",
        )
        for name in required:
            if len(getattr(self, name)) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        optional = (
            "release_evidence_digest",
            "sandbox_binding_digest",
            "model_attestation_digest",
            "quorum_approval_digest",
            "runtime_trust_digest",
            "authority_health_policy_digest",
            "execution_attempt_authority_digest",
            "audit_witness_digest",
            "session_integrity_digest",
            "session_journal_manifest_digest",
            "root_protection_digest",
        )
        for name in optional:
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        if len(self.execution_seal_id) > 128:
            raise ValueError("execution_seal_id too long")
        if len(self.execution_attempt_id) > 256:
            raise ValueError("execution_attempt_id too long")
        if bool(self.execution_attempt_id) != bool(
            self.execution_attempt_authority_digest
        ):
            raise ValueError(
                "execution attempt id and authority digest must be configured together"
            )
        if len(self.execution_attempt_state) > 64:
            raise ValueError("execution_attempt_state too long")
        if self.execution_attempt_state and not self.execution_attempt_id:
            raise ValueError(
                "execution attempt state requires execution attempt identity"
            )
        if self.audit_witness_sequence is not None and (
            isinstance(self.audit_witness_sequence, bool)
            or not isinstance(self.audit_witness_sequence, int)
            or self.audit_witness_sequence <= 0
        ):
            raise ValueError("audit_witness_sequence must be positive")
        if bool(self.audit_witness_digest) != (
            self.audit_witness_sequence is not None
        ):
            raise ValueError(
                "audit witness digest and sequence must be configured together"
            )
        if self.completed_at < 0:
            raise ValueError("completed_at may not be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "intent_fingerprint": self.intent_fingerprint,
            "proposal_fingerprint": self.proposal_fingerprint,
            "provenance_digest": self.provenance_digest,
            "checkpoint_digest": self.checkpoint_digest,
            "session_evidence_digest": self.session_evidence_digest,
            "session_journal_digest": self.session_journal_digest,
            "audit_anchor_digest": self.audit_anchor_digest,
            "audit_chain_node_hash": self.audit_chain_node_hash,
            "release_evidence_digest": self.release_evidence_digest,
            "sandbox_binding_digest": self.sandbox_binding_digest,
            "model_attestation_digest": self.model_attestation_digest,
            "execution_seal_id": self.execution_seal_id,
            "quorum_approval_digest": self.quorum_approval_digest,
            "runtime_trust_digest": self.runtime_trust_digest,
            "authority_health_policy_digest": (
                self.authority_health_policy_digest
            ),
            "execution_attempt_id": self.execution_attempt_id,
            "execution_attempt_authority_digest": (
                self.execution_attempt_authority_digest
            ),
            "audit_witness_digest": self.audit_witness_digest,
            "audit_witness_sequence": self.audit_witness_sequence,
            "execution_attempt_state": self.execution_attempt_state,
            "completed_at": self.completed_at,
            "session_integrity_digest": self.session_integrity_digest,
            "session_journal_manifest_digest": (
                self.session_journal_manifest_digest
            ),
            "root_protection_digest": self.root_protection_digest,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SignedAIExecutionEvidence:
    evidence: AIExecutionEvidence
    signature: SignedArtifact
    chain_node_hash: str

    def __post_init__(self) -> None:
        if len(self.chain_node_hash) != 64:
            raise ValueError("chain_node_hash must be SHA-256 hex")

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence": self.evidence.to_dict(),
            "evidence_digest": self.evidence.digest,
            "signature": self.signature.to_dict(),
            "chain_node_hash": self.chain_node_hash,
        }


class AIExecutionEvidenceBuilder:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._clock = clock

    def build(
        self,
        *,
        session_id: str,
        intent_fingerprint: str,
        proposal_fingerprint: str,
        provenance_digest: str,
        checkpoint_digest: str,
        session_evidence_digest: str,
        session_journal_digest: str,
        audit_anchor_digest: str,
        audit_chain_node_hash: str,
        release_evidence_digest: str = "",
        sandbox_binding_digest: str = "",
        model_attestation_digest: str = "",
        execution_seal_id: str = "",
        quorum_approval_digest: str = "",
        runtime_trust_digest: str = "",
        authority_health_policy_digest: str = "",
        execution_attempt_id: str = "",
        execution_attempt_authority_digest: str = "",
        audit_witness_digest: str = "",
        audit_witness_sequence: int | None = None,
        execution_attempt_state: str = "",
        session_integrity_digest: str = "",
        session_journal_manifest_digest: str = "",
        root_protection_digest: str = "",
    ) -> AIExecutionEvidence:
        return AIExecutionEvidence(
            1,
            session_id,
            intent_fingerprint,
            proposal_fingerprint,
            provenance_digest,
            checkpoint_digest,
            session_evidence_digest,
            session_journal_digest,
            audit_anchor_digest,
            audit_chain_node_hash,
            release_evidence_digest,
            sandbox_binding_digest,
            model_attestation_digest,
            execution_seal_id,
            quorum_approval_digest,
            runtime_trust_digest,
            authority_health_policy_digest,
            execution_attempt_id,
            execution_attempt_authority_digest,
            audit_witness_digest,
            audit_witness_sequence,
            execution_attempt_state,
            self._clock(),
            session_integrity_digest,
            session_journal_manifest_digest,
            root_protection_digest,
        )


class AIExecutionEvidenceStore:
    """Sign and append final execution evidence to a durable hash chain."""

    def __init__(
        self,
        backend: EvidenceStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-execution-evidence",
        max_items: int = 100_000,
    ) -> None:
        self.signer = signer
        self._chain = ContentAddressedEvidenceChain(
            backend,
            namespace=namespace,
            max_events=max_items,
        )

    def append(
        self,
        evidence: AIExecutionEvidence,
    ) -> SignedAIExecutionEvidence:
        signature = self.signer.sign(
            "ai-execution-evidence",
            evidence.digest,
            metadata={
                "session_id": evidence.session_id,
                "execution_seal_id": evidence.execution_seal_id,
            },
        )
        node = self._chain.append(
            "ai.execution.evidence",
            {
                "evidence": evidence.to_dict(),
                "signature": signature.to_dict(),
            },
        )
        return SignedAIExecutionEvidence(
            evidence,
            signature,
            node.node_hash,
        )

    def find_by_attempt_id(
        self,
        execution_attempt_id: str,
    ) -> SignedAIExecutionEvidence | None:
        if not execution_attempt_id or len(execution_attempt_id) > 256:
            raise ValueError("invalid execution_attempt_id")
        for item in self.snapshot():
            if item.evidence.execution_attempt_id == execution_attempt_id:
                return item
        return None

    def find_by_digest(
        self,
        evidence_digest: str,
    ) -> SignedAIExecutionEvidence | None:
        if len(evidence_digest) != 64:
            raise ValueError("evidence_digest must be SHA-256 hex")
        for item in self.snapshot():
            if item.evidence.digest == evidence_digest:
                return item
        return None

    def append_once(
        self,
        evidence: AIExecutionEvidence,
    ) -> SignedAIExecutionEvidence:
        if evidence.execution_attempt_id:
            existing = self.find_by_attempt_id(
                evidence.execution_attempt_id
            )
            if existing is not None:
                if existing.evidence.digest != evidence.digest:
                    raise RuntimeError(
                        "execution attempt already binds different final evidence"
                    )
                return existing
        else:
            existing = self.find_by_digest(evidence.digest)
            if existing is not None:
                return existing
        return self.append(evidence)

    @staticmethod
    def _evidence(raw: dict[str, object]) -> AIExecutionEvidence:
        return AIExecutionEvidence(
            int(raw["schema_version"]),
            str(raw["session_id"]),
            str(raw["intent_fingerprint"]),
            str(raw["proposal_fingerprint"]),
            str(raw["provenance_digest"]),
            str(raw["checkpoint_digest"]),
            str(raw["session_evidence_digest"]),
            str(raw["session_journal_digest"]),
            str(raw["audit_anchor_digest"]),
            str(raw["audit_chain_node_hash"]),
            str(raw.get("release_evidence_digest", "")),
            str(raw.get("sandbox_binding_digest", "")),
            str(raw.get("model_attestation_digest", "")),
            str(raw.get("execution_seal_id", "")),
            str(raw.get("quorum_approval_digest", "")),
            str(raw.get("runtime_trust_digest", "")),
            str(raw.get("authority_health_policy_digest", "")),
            str(raw.get("execution_attempt_id", "")),
            str(raw.get("execution_attempt_authority_digest", "")),
            str(raw.get("audit_witness_digest", "")),
            (
                None
                if raw.get("audit_witness_sequence") is None
                else int(raw["audit_witness_sequence"])
            ),
            str(raw.get("execution_attempt_state", "")),
            float(raw["completed_at"]),
            str(raw.get("session_integrity_digest", "")),
            str(raw.get("session_journal_manifest_digest", "")),
            str(raw.get("root_protection_digest", "")),
        )

    @staticmethod
    def _signature(raw: dict[str, object]) -> SignedArtifact:
        return SignedArtifact(
            str(raw["artifact_type"]),
            str(raw["artifact_digest"]),
            str(raw["key_id"]),
            float(raw["issued_at"]),
            dict(raw.get("metadata", {})),
            str(raw["signature"]),
        )

    def snapshot(self) -> tuple[SignedAIExecutionEvidence, ...]:
        result = []
        for node in self._chain.snapshot():
            raw_evidence = node.payload.get("evidence")
            raw_signature = node.payload.get("signature")
            if not isinstance(raw_evidence, dict) or not isinstance(raw_signature, dict):
                raise EvidenceCorruption("AI execution evidence payload is invalid")
            evidence = self._evidence(dict(raw_evidence))
            signature = self._signature(dict(raw_signature))
            result.append(
                SignedAIExecutionEvidence(
                    evidence,
                    signature,
                    node.node_hash,
                )
            )
        return tuple(result)

    def verify(self) -> bool:
        if not self._chain.verify():
            return False
        try:
            items = self.snapshot()
        except (EvidenceCorruption, ValueError, TypeError, KeyError):
            return False
        for item in items:
            if item.signature.artifact_type != "ai-execution-evidence":
                return False
            if item.signature.artifact_digest != item.evidence.digest:
                return False
            if (
                item.signature.metadata.get("session_id")
                != item.evidence.session_id
            ):
                return False
            if (
                item.signature.metadata.get("execution_seal_id", "")
                != item.evidence.execution_seal_id
            ):
                return False
            try:
                self.signer.verify(item.signature)
            except Exception:
                return False
        return True

    def root_hash(self) -> str:
        return self._chain.root_hash()
