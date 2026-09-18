"""Signed durable audit anchors for AI shell execution evidence."""

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
class AIAuditAnchor:
    schema_version: int
    session_id: str
    checkpoint_digest: str
    provenance_digest: str
    journal_root: str
    receipt_root: str
    session_evidence_digest: str
    release_evidence_digest: str = ""
    sandbox_binding_digest: str = ""
    runtime_trust_digest: str = ""
    authority_health_policy_digest: str = ""
    execution_attempt_id: str = ""
    execution_attempt_authority_digest: str = ""
    finalization_id: str = ""
    observed_at: float = 0.0

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported AI audit anchor schema")
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError("invalid AI audit anchor session_id")
        for name in (
            "checkpoint_digest",
            "provenance_digest",
            "journal_root",
            "receipt_root",
            "session_evidence_digest",
        ):
            if len(getattr(self, name)) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        for name in (
            "release_evidence_digest",
            "sandbox_binding_digest",
            "runtime_trust_digest",
            "authority_health_policy_digest",
            "execution_attempt_authority_digest",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        if len(self.execution_attempt_id) > 256:
            raise ValueError("execution_attempt_id too long")
        if bool(self.execution_attempt_id) != bool(
            self.execution_attempt_authority_digest
        ):
            raise ValueError(
                "execution attempt id and authority digest must be configured together"
            )
        if len(self.finalization_id) > 256:
            raise ValueError("finalization_id too long")
        if self.observed_at < 0:
            raise ValueError("audit anchor observed_at may not be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "checkpoint_digest": self.checkpoint_digest,
            "provenance_digest": self.provenance_digest,
            "journal_root": self.journal_root,
            "receipt_root": self.receipt_root,
            "session_evidence_digest": self.session_evidence_digest,
            "release_evidence_digest": self.release_evidence_digest,
            "sandbox_binding_digest": self.sandbox_binding_digest,
            "runtime_trust_digest": self.runtime_trust_digest,
            "authority_health_policy_digest": (
                self.authority_health_policy_digest
            ),
            "execution_attempt_id": self.execution_attempt_id,
            "execution_attempt_authority_digest": (
                self.execution_attempt_authority_digest
            ),
            "finalization_id": self.finalization_id,
            "observed_at": self.observed_at,
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
class SignedAIAuditAnchor:
    anchor: AIAuditAnchor
    signature: SignedArtifact
    chain_node_hash: str

    def __post_init__(self) -> None:
        if len(self.chain_node_hash) != 64:
            raise ValueError("chain_node_hash must be SHA-256 hex")

    def to_dict(self) -> dict[str, object]:
        return {
            "anchor": self.anchor.to_dict(),
            "anchor_digest": self.anchor.digest,
            "signature": self.signature.to_dict(),
            "chain_node_hash": self.chain_node_hash,
        }


class AIAuditAnchorStore:
    """Append signed evidence anchors to a durable content-addressed chain."""

    def __init__(
        self,
        backend: EvidenceStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-audit-anchor",
        max_anchors: int = 100_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.signer = signer
        self._clock = clock
        self._chain = ContentAddressedEvidenceChain(
            backend,
            namespace=namespace,
            max_events=max_anchors,
        )

    def append(
        self,
        *,
        session_id: str,
        checkpoint_digest: str,
        provenance_digest: str,
        journal_root: str,
        receipt_root: str,
        session_evidence_digest: str,
        release_evidence_digest: str = "",
        sandbox_binding_digest: str = "",
        runtime_trust_digest: str = "",
        authority_health_policy_digest: str = "",
        execution_attempt_id: str = "",
        execution_attempt_authority_digest: str = "",
        finalization_id: str = "",
    ) -> SignedAIAuditAnchor:
        anchor = AIAuditAnchor(
            1,
            session_id,
            checkpoint_digest,
            provenance_digest,
            journal_root,
            receipt_root,
            session_evidence_digest,
            release_evidence_digest,
            sandbox_binding_digest,
            runtime_trust_digest,
            authority_health_policy_digest,
            execution_attempt_id,
            execution_attempt_authority_digest,
            finalization_id,
            self._clock(),
        )
        signature = self.signer.sign(
            "ai-audit-anchor",
            anchor.digest,
            metadata={"session_id": session_id},
        )
        node = self._chain.append(
            "ai.audit.anchor",
            {
                "anchor": anchor.to_dict(),
                "signature": signature.to_dict(),
            },
        )
        return SignedAIAuditAnchor(
            anchor,
            signature,
            node.node_hash,
        )

    def find_by_finalization_id(
        self,
        finalization_id: str,
    ) -> SignedAIAuditAnchor | None:
        if not finalization_id or len(finalization_id) > 256:
            raise ValueError("invalid finalization_id")
        for item in self.snapshot():
            if item.anchor.finalization_id == finalization_id:
                return item
        return None

    def append_once(
        self,
        *,
        finalization_id: str,
        session_id: str,
        checkpoint_digest: str,
        provenance_digest: str,
        journal_root: str,
        receipt_root: str,
        session_evidence_digest: str,
        release_evidence_digest: str = "",
        sandbox_binding_digest: str = "",
        runtime_trust_digest: str = "",
        authority_health_policy_digest: str = "",
        execution_attempt_id: str = "",
        execution_attempt_authority_digest: str = "",
    ) -> SignedAIAuditAnchor:
        if not finalization_id or len(finalization_id) > 256:
            raise ValueError("invalid finalization_id")
        existing = self.find_by_finalization_id(finalization_id)
        if existing is not None:
            anchor = existing.anchor
            expected = {
                "session_id": session_id,
                "checkpoint_digest": checkpoint_digest,
                "provenance_digest": provenance_digest,
                "journal_root": journal_root,
                "receipt_root": receipt_root,
                "session_evidence_digest": session_evidence_digest,
                "release_evidence_digest": release_evidence_digest,
                "sandbox_binding_digest": sandbox_binding_digest,
                "runtime_trust_digest": runtime_trust_digest,
                "authority_health_policy_digest": authority_health_policy_digest,
                "execution_attempt_id": execution_attempt_id,
                "execution_attempt_authority_digest": (
                    execution_attempt_authority_digest
                ),
            }
            for name, value in expected.items():
                if getattr(anchor, name) != value:
                    raise RuntimeError(
                        f"finalization_id already binds different audit anchor {name}"
                    )
            return existing
        return self.append(
            session_id=session_id,
            checkpoint_digest=checkpoint_digest,
            provenance_digest=provenance_digest,
            journal_root=journal_root,
            receipt_root=receipt_root,
            session_evidence_digest=session_evidence_digest,
            release_evidence_digest=release_evidence_digest,
            sandbox_binding_digest=sandbox_binding_digest,
            runtime_trust_digest=runtime_trust_digest,
            authority_health_policy_digest=authority_health_policy_digest,
            execution_attempt_id=execution_attempt_id,
            execution_attempt_authority_digest=(
                execution_attempt_authority_digest
            ),
            finalization_id=finalization_id,
        )

    @staticmethod
    def _anchor(raw: dict[str, object]) -> AIAuditAnchor:
        return AIAuditAnchor(
            int(raw["schema_version"]),
            str(raw["session_id"]),
            str(raw["checkpoint_digest"]),
            str(raw["provenance_digest"]),
            str(raw["journal_root"]),
            str(raw["receipt_root"]),
            str(raw["session_evidence_digest"]),
            str(raw.get("release_evidence_digest", "")),
            str(raw.get("sandbox_binding_digest", "")),
            str(raw.get("runtime_trust_digest", "")),
            str(raw.get("authority_health_policy_digest", "")),
            str(raw.get("execution_attempt_id", "")),
            str(raw.get("execution_attempt_authority_digest", "")),
            str(raw.get("finalization_id", "")),
            float(raw["observed_at"]),
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

    def snapshot(self) -> tuple[SignedAIAuditAnchor, ...]:
        result = []
        for node in self._chain.snapshot():
            raw_anchor = node.payload.get("anchor")
            raw_signature = node.payload.get("signature")
            if not isinstance(raw_anchor, dict) or not isinstance(raw_signature, dict):
                raise EvidenceCorruption("AI audit anchor payload is invalid")
            anchor = self._anchor(dict(raw_anchor))
            signature = self._signature(dict(raw_signature))
            result.append(
                SignedAIAuditAnchor(
                    anchor,
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
            if item.signature.artifact_type != "ai-audit-anchor":
                return False
            if item.signature.artifact_digest != item.anchor.digest:
                return False
            try:
                self.signer.verify(item.signature)
            except Exception:
                return False
        return True

    def root_hash(self) -> str:
        return self._chain.root_hash()
