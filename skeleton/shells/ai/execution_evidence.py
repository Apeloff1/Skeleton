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
    completed_at: float = 0.0

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
        )
        for name in optional:
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        if len(self.execution_seal_id) > 128:
            raise ValueError("execution_seal_id too long")
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
            "completed_at": self.completed_at,
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
            self._clock(),
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
            float(raw["completed_at"]),
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
