"""Signed cross-store commit point for one finalized AI shell session.

Individual evidence stores can each be healthy while referring to different
epochs after a crash, operator mistake, or partial restore.  This module adds
one immutable signed commit record that binds the semantic finalization state
to the exact recovery checkpoint, session evidence, durable session-journal
manifest, session-integrity proof, audit anchor/witness, and final signed
execution evidence.

The commit is evidence authority only.  It never authorizes execution and does
not replace the underlying stores.  A missing commit after terminal evidence
is recoverable by reconstructing and re-publishing the same deterministic
record; a conflicting commit is a fail-closed manual-review condition.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalization,
    FinalizationPhase,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if len(value) != 64:
        raise ValueError(
            f"{name} must be a 64-character digest"
        )
    return value.lower()


def _identity(
    name: str,
    value: str,
    *,
    maximum: int,
    optional: bool = False,
) -> str:
    value = str(value)
    if optional and not value:
        return ""
    if not value or len(value) > maximum:
        raise ValueError(f"invalid {name}")
    return value


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def finalization_evidence_dict(
    finalization: AIExecutionFinalization,
) -> dict[str, object]:
    """Return only stable evidence bindings, excluding operational metadata."""
    if not isinstance(
        finalization,
        AIExecutionFinalization,
    ):
        raise TypeError(
            "finalization must be AIExecutionFinalization"
        )
    return {
        "schema_version": finalization.schema_version,
        "finalization_id": finalization.finalization_id,
        "session_id": finalization.session_id,
        "provenance_digest": (
            finalization.provenance_digest
        ),
        "phase": finalization.phase.value,
        "execution_attempt_id": (
            finalization.execution_attempt_id
        ),
        "execution_attempt_authority_digest": (
            finalization.execution_attempt_authority_digest
        ),
        "runtime_trust_digest": (
            finalization.runtime_trust_digest
        ),
        "release_evidence_digest": (
            finalization.release_evidence_digest
        ),
        "require_recovery_checkpoint": (
            finalization.require_recovery_checkpoint
        ),
        "require_witness": finalization.require_witness,
        "require_signed_evidence": (
            finalization.require_signed_evidence
        ),
        "session_evidence_digest": (
            finalization.session_evidence_digest
        ),
        "recovery_checkpoint_digest": (
            finalization.recovery_checkpoint_digest
        ),
        "audit_anchor_digest": (
            finalization.audit_anchor_digest
        ),
        "audit_chain_node_hash": (
            finalization.audit_chain_node_hash
        ),
        "audit_root": finalization.audit_root,
        "audit_witness_digest": (
            finalization.audit_witness_digest
        ),
        "audit_witness_sequence": (
            finalization.audit_witness_sequence
        ),
        "execution_evidence_digest": (
            finalization.execution_evidence_digest
        ),
        "execution_evidence_chain_node_hash": (
            finalization.execution_evidence_chain_node_hash
        ),
    }


def finalization_evidence_digest(
    finalization: AIExecutionFinalization,
) -> str:
    return _stable_digest(
        finalization_evidence_dict(
            finalization
        )
    )


@dataclass(frozen=True)
class DurableSessionCommitPolicy:
    require_complete_finalization: bool = True
    require_recovery_checkpoint: bool = True
    require_session_journal_manifest: bool = True
    require_audit_witness: bool = True
    require_signed_execution_evidence: bool = True
    require_root_protection: bool = False

    def __post_init__(self) -> None:
        for name in (
            "require_complete_finalization",
            "require_recovery_checkpoint",
            "require_session_journal_manifest",
            "require_audit_witness",
            "require_signed_execution_evidence",
            "require_root_protection",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict()
        )

    def to_dict(self) -> dict[str, bool]:
        return {
            "require_complete_finalization": (
                self.require_complete_finalization
            ),
            "require_recovery_checkpoint": (
                self.require_recovery_checkpoint
            ),
            "require_session_journal_manifest": (
                self.require_session_journal_manifest
            ),
            "require_audit_witness": (
                self.require_audit_witness
            ),
            "require_signed_execution_evidence": (
                self.require_signed_execution_evidence
            ),
            "require_root_protection": (
                self.require_root_protection
            ),
        }


@dataclass(frozen=True)
class DurableSessionCommit:
    schema_version: int
    commit_id: str
    finalization_id: str
    session_id: str
    execution_attempt_id: str
    provenance_digest: str
    finalization_evidence_digest: str
    recovery_checkpoint_digest: str
    session_evidence_digest: str
    session_journal_digest: str
    session_journal_manifest_digest: str
    session_integrity_digest: str
    journal_root: str
    receipt_root: str
    audit_anchor_digest: str
    audit_chain_node_hash: str
    audit_root: str
    audit_witness_digest: str
    audit_witness_sequence: int | None
    execution_evidence_digest: str
    execution_evidence_chain_node_hash: str
    runtime_trust_digest: str
    release_evidence_digest: str
    policy_digest: str
    finalization_revision: int
    recovery_revision: int | None
    session_evidence_revision: int
    session_journal_revision: int | None
    root_protection_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported durable session commit schema"
            )
        object.__setattr__(
            self,
            "commit_id",
            _digest("commit_id", self.commit_id),
        )
        object.__setattr__(
            self,
            "finalization_id",
            _identity(
                "finalization_id",
                self.finalization_id,
                maximum=256,
            ),
        )
        object.__setattr__(
            self,
            "session_id",
            _identity(
                "session_id",
                self.session_id,
                maximum=160,
            ),
        )
        object.__setattr__(
            self,
            "execution_attempt_id",
            _identity(
                "execution_attempt_id",
                self.execution_attempt_id,
                maximum=256,
                optional=True,
            ),
        )
        for name in (
            "provenance_digest",
            "finalization_evidence_digest",
            "session_evidence_digest",
            "session_journal_digest",
            "session_integrity_digest",
            "journal_root",
            "receipt_root",
            "audit_anchor_digest",
            "audit_chain_node_hash",
            "audit_root",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        for name in (
            "recovery_checkpoint_digest",
            "session_journal_manifest_digest",
            "audit_witness_digest",
            "execution_evidence_digest",
            "execution_evidence_chain_node_hash",
            "runtime_trust_digest",
            "release_evidence_digest",
            "root_protection_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                    optional=True,
                ),
            )
        if self.audit_witness_sequence is not None and (
            isinstance(
                self.audit_witness_sequence,
                bool,
            )
            or not isinstance(
                self.audit_witness_sequence,
                int,
            )
            or self.audit_witness_sequence <= 0
        ):
            raise ValueError(
                "audit_witness_sequence must be positive"
            )
        if bool(self.audit_witness_digest) != (
            self.audit_witness_sequence
            is not None
        ):
            raise ValueError(
                "audit witness digest and sequence must be paired"
            )
        for name in (
            "finalization_revision",
            "session_evidence_revision",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive"
                )
        for name in (
            "recovery_revision",
            "session_journal_revision",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive when present"
                )
        expected = self.derive_commit_id(
            self.finalization_id,
            self.finalization_evidence_digest,
            self.policy_digest,
        )
        if self.commit_id != expected:
            raise ValueError(
                "commit_id differs from stable commit identity"
            )

    @staticmethod
    def derive_commit_id(
        finalization_id: str,
        finalization_evidence_digest: str,
        policy_digest: str,
    ) -> str:
        finalization_id = _identity(
            "finalization_id",
            finalization_id,
            maximum=256,
        )
        finalization_evidence_digest = (
            _digest(
                "finalization_evidence_digest",
                finalization_evidence_digest,
            )
        )
        policy_digest = _digest(
            "policy_digest",
            policy_digest,
        )
        return _stable_digest(
            {
                "finalization_id": (
                    finalization_id
                ),
                "finalization_evidence_digest": (
                    finalization_evidence_digest
                ),
                "policy_digest": policy_digest,
            }
        )

    @property
    def authority_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "commit_id": self.commit_id,
            "finalization_id": self.finalization_id,
            "session_id": self.session_id,
            "execution_attempt_id": (
                self.execution_attempt_id
            ),
            "provenance_digest": (
                self.provenance_digest
            ),
            "finalization_evidence_digest": (
                self.finalization_evidence_digest
            ),
            "recovery_checkpoint_digest": (
                self.recovery_checkpoint_digest
            ),
            "session_evidence_digest": (
                self.session_evidence_digest
            ),
            "session_journal_digest": (
                self.session_journal_digest
            ),
            "session_journal_manifest_digest": (
                self.session_journal_manifest_digest
            ),
            "session_integrity_digest": (
                self.session_integrity_digest
            ),
            "journal_root": self.journal_root,
            "receipt_root": self.receipt_root,
            "audit_anchor_digest": (
                self.audit_anchor_digest
            ),
            "audit_chain_node_hash": (
                self.audit_chain_node_hash
            ),
            "audit_root": self.audit_root,
            "audit_witness_digest": (
                self.audit_witness_digest
            ),
            "audit_witness_sequence": (
                self.audit_witness_sequence
            ),
            "execution_evidence_digest": (
                self.execution_evidence_digest
            ),
            "execution_evidence_chain_node_hash": (
                self.execution_evidence_chain_node_hash
            ),
            "runtime_trust_digest": (
                self.runtime_trust_digest
            ),
            "release_evidence_digest": (
                self.release_evidence_digest
            ),
            "root_protection_digest": (
                self.root_protection_digest
            ),
            "policy_digest": self.policy_digest,
            "recovery_revision": self.recovery_revision,
            "session_evidence_revision": (
                self.session_evidence_revision
            ),
            "session_journal_revision": (
                self.session_journal_revision
            ),
        }

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.authority_dict
        )

    def to_dict(self) -> dict[str, object]:
        return {
            **self.authority_dict,
            "digest": self.digest,
            "finalization_revision": (
                self.finalization_revision
            ),
        }


@dataclass(frozen=True)
class SignedDurableSessionCommit:
    commit: DurableSessionCommit
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.commit,
            DurableSessionCommit,
        ):
            raise TypeError(
                "commit must be DurableSessionCommit"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )
        if (
            self.signature.artifact_type
            != "ai-durable-session-commit"
        ):
            raise ValueError(
                "invalid durable session commit artifact type"
            )
        if (
            self.signature.artifact_digest
            != self.commit.digest
        ):
            raise ValueError(
                "durable session commit signature digest mismatch"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "commit": self.commit.to_dict(),
            "commit_digest": self.commit.digest,
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class DurableSessionCommitHead:
    session_id: str
    finalization_id: str
    commit_id: str
    commit_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "session_id",
            _identity(
                "session_id",
                self.session_id,
                maximum=160,
            ),
        )
        object.__setattr__(
            self,
            "finalization_id",
            _identity(
                "finalization_id",
                self.finalization_id,
                maximum=256,
            ),
        )
        object.__setattr__(
            self,
            "commit_id",
            _digest(
                "commit_id",
                self.commit_id,
            ),
        )
        object.__setattr__(
            self,
            "commit_digest",
            _digest(
                "commit_digest",
                self.commit_digest,
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "session_id": self.session_id,
            "finalization_id": (
                self.finalization_id
            ),
            "commit_id": self.commit_id,
            "commit_digest": self.commit_digest,
        }


@dataclass(frozen=True)
class StoredDurableSessionCommit:
    revision: int
    signed: SignedDurableSessionCommit

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "session commit revision must be positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "signed": self.signed.to_dict(),
        }


@dataclass(frozen=True)
class DurableSessionCommitPublication:
    stored: StoredDurableSessionCommit
    head_revision: int
    head: DurableSessionCommitHead
    head_created: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.head_revision, bool)
            or not isinstance(
                self.head_revision,
                int,
            )
            or self.head_revision <= 0
        ):
            raise ValueError(
                "session commit head_revision must be positive"
            )
        if (
            self.stored.signed.commit.session_id
            != self.head.session_id
        ):
            raise ValueError(
                "session commit publication session mismatch"
            )
        if (
            self.stored.signed.commit.finalization_id
            != self.head.finalization_id
        ):
            raise ValueError(
                "session commit publication finalization mismatch"
            )
        if (
            self.stored.signed.commit.commit_id
            != self.head.commit_id
        ):
            raise ValueError(
                "session commit publication commit_id mismatch"
            )
        if (
            self.stored.signed.commit.digest
            != self.head.commit_digest
        ):
            raise ValueError(
                "session commit publication digest mismatch"
            )
        if not isinstance(
            self.head_created,
            bool,
        ):
            raise ValueError(
                "head_created must be bool"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored.to_dict(),
            "head_revision": self.head_revision,
            "head": self.head.to_dict(),
            "head_created": self.head_created,
        }


class DurableSessionCommitConflict(RuntimeError):
    pass


class DurableSessionCommitCorruption(RuntimeError):
    pass


class DurableSessionCommitBuilder:
    """Build deterministic session commits from finalized evidence objects."""

    def __init__(
        self,
        policy: DurableSessionCommitPolicy
        | None = None,
    ) -> None:
        self.policy = (
            policy
            or DurableSessionCommitPolicy()
        )

    def build(
        self,
        *,
        finalization: AIExecutionFinalization,
        finalization_revision: int,
        recovery_checkpoint_digest: str,
        recovery_revision: int | None,
        session_evidence_digest: str,
        session_evidence_revision: int,
        session_journal_digest: str,
        session_journal_manifest_digest: str = "",
        session_journal_revision: int | None = None,
        session_integrity_digest: str,
        journal_root: str,
        receipt_root: str,
        audit_anchor_digest: str,
        audit_chain_node_hash: str,
        audit_root: str,
        audit_witness_digest: str = "",
        audit_witness_sequence: int | None = None,
        execution_evidence_digest: str = "",
        execution_evidence_chain_node_hash: str = "",
        root_protection_digest: str = "",
    ) -> DurableSessionCommit:
        if not isinstance(
            finalization,
            AIExecutionFinalization,
        ):
            raise TypeError(
                "finalization must be AIExecutionFinalization"
            )
        if (
            self.policy.require_complete_finalization
            and finalization.phase
            is not FinalizationPhase.COMPLETE
        ):
            raise DurableSessionCommitConflict(
                "session commit requires complete finalization"
            )
        if (
            finalization.session_evidence_digest
            != session_evidence_digest
        ):
            raise DurableSessionCommitConflict(
                "session evidence differs from finalization"
            )
        if (
            finalization.recovery_checkpoint_digest
            != recovery_checkpoint_digest
        ):
            raise DurableSessionCommitConflict(
                "recovery checkpoint differs from finalization"
            )
        if (
            finalization.audit_anchor_digest
            != audit_anchor_digest
            or finalization.audit_chain_node_hash
            != audit_chain_node_hash
            or finalization.audit_root
            != audit_root
        ):
            raise DurableSessionCommitConflict(
                "audit anchor differs from finalization"
            )
        if (
            finalization.audit_witness_digest
            != audit_witness_digest
            or finalization.audit_witness_sequence
            != audit_witness_sequence
        ):
            raise DurableSessionCommitConflict(
                "audit witness differs from finalization"
            )
        if (
            finalization.execution_evidence_digest
            != execution_evidence_digest
            or finalization.execution_evidence_chain_node_hash
            != execution_evidence_chain_node_hash
        ):
            raise DurableSessionCommitConflict(
                "signed execution evidence differs from finalization"
            )

        if self.policy.require_recovery_checkpoint and (
            not recovery_checkpoint_digest
            or recovery_revision is None
        ):
            raise DurableSessionCommitConflict(
                "session commit requires durably stored recovery checkpoint"
            )
        if self.policy.require_session_journal_manifest and (
            not session_journal_manifest_digest
            or session_journal_revision is None
        ):
            raise DurableSessionCommitConflict(
                "session commit requires durable session-journal manifest"
            )
        if (
            self.policy.require_audit_witness
            and not audit_witness_digest
        ):
            raise DurableSessionCommitConflict(
                "session commit requires audit witness"
            )
        if (
            self.policy.require_signed_execution_evidence
            and not execution_evidence_digest
        ):
            raise DurableSessionCommitConflict(
                "session commit requires signed execution evidence"
            )
        if (
            self.policy.require_root_protection
            and not root_protection_digest
        ):
            raise DurableSessionCommitConflict(
                "session commit requires durable root protection"
            )
        if not session_journal_digest:
            raise DurableSessionCommitConflict(
                "session commit requires session journal digest"
            )
        if not session_integrity_digest:
            raise DurableSessionCommitConflict(
                "session commit requires session integrity digest"
            )
        if not journal_root or not receipt_root:
            raise DurableSessionCommitConflict(
                "session commit requires journal and receipt roots"
            )

        semantic_digest = (
            finalization_evidence_digest(
                finalization
            )
        )
        commit_id = (
            DurableSessionCommit.derive_commit_id(
                finalization.finalization_id,
                semantic_digest,
                self.policy.digest,
            )
        )
        return DurableSessionCommit(
            1,
            commit_id,
            finalization.finalization_id,
            finalization.session_id,
            finalization.execution_attempt_id,
            finalization.provenance_digest,
            semantic_digest,
            recovery_checkpoint_digest,
            session_evidence_digest,
            session_journal_digest,
            session_journal_manifest_digest,
            session_integrity_digest,
            journal_root,
            receipt_root,
            audit_anchor_digest,
            audit_chain_node_hash,
            audit_root,
            audit_witness_digest,
            audit_witness_sequence,
            execution_evidence_digest,
            execution_evidence_chain_node_hash,
            finalization.runtime_trust_digest,
            finalization.release_evidence_digest,
            self.policy.digest,
            finalization_revision,
            recovery_revision,
            session_evidence_revision,
            session_journal_revision,
            root_protection_digest,
        )


class DurableSessionCommitStore:
    """Immutable signed commit records plus one immutable head per session."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-durable-session-commit",
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid durable session commit namespace"
            )
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        self.backend = backend
        self.signer = signer
        self.namespace = namespace

    @staticmethod
    def _commit_key(
        finalization_id: str,
    ) -> str:
        finalization_id = _identity(
            "finalization_id",
            finalization_id,
            maximum=256,
        )
        return "commit:" + hashlib.sha256(
            finalization_id.encode()
        ).hexdigest()

    @staticmethod
    def _head_key(
        session_id: str,
    ) -> str:
        session_id = _identity(
            "session_id",
            session_id,
            maximum=160,
        )
        return "head:" + hashlib.sha256(
            session_id.encode()
        ).hexdigest()

    def _verify_signature(
        self,
        item: SignedDurableSessionCommit,
    ) -> None:
        try:
            self.signer.verify(
                item.signature
            )
        except ArtifactSignatureError as exc:
            raise DurableSessionCommitCorruption(
                "durable session commit signature verification failed"
            ) from exc
        if (
            item.signature.artifact_digest
            != item.commit.digest
        ):
            raise DurableSessionCommitCorruption(
                "durable session commit signed digest mismatch"
            )

    def get(
        self,
        finalization_id: str,
    ) -> StoredDurableSessionCommit | None:
        record = self.backend.get(
            self.namespace,
            self._commit_key(
                finalization_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            SignedDurableSessionCommit,
        ):
            raise DurableSessionCommitCorruption(
                "session commit backend value type mismatch"
            )
        self._verify_signature(
            record.value
        )
        if (
            record.value.commit.finalization_id
            != finalization_id
        ):
            raise DurableSessionCommitCorruption(
                "session commit finalization/key mismatch"
            )
        return StoredDurableSessionCommit(
            record.revision,
            record.value,
        )

    def head(
        self,
        session_id: str,
    ) -> tuple[
        int,
        DurableSessionCommitHead,
    ] | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(
                session_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableSessionCommitHead,
        ):
            raise DurableSessionCommitCorruption(
                "session commit head backend value type mismatch"
            )
        if (
            record.value.session_id
            != session_id
        ):
            raise DurableSessionCommitCorruption(
                "session commit head session/key mismatch"
            )
        return record.revision, record.value

    @staticmethod
    def _head_for(
        item: SignedDurableSessionCommit,
    ) -> DurableSessionCommitHead:
        return DurableSessionCommitHead(
            item.commit.session_id,
            item.commit.finalization_id,
            item.commit.commit_id,
            item.commit.digest,
        )

    def _sign(
        self,
        commit: DurableSessionCommit,
    ) -> SignedDurableSessionCommit:
        signature = self.signer.sign(
            "ai-durable-session-commit",
            commit.digest,
            metadata={
                "session_id": (
                    commit.session_id
                ),
                "finalization_id": (
                    commit.finalization_id
                ),
                "commit_id": commit.commit_id,
            },
        )
        return SignedDurableSessionCommit(
            commit,
            signature,
        )

    def _store_commit(
        self,
        signed: SignedDurableSessionCommit,
    ) -> StoredDurableSessionCommit:
        key = self._commit_key(
            signed.commit.finalization_id
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is not None:
            if not isinstance(
                existing.value,
                SignedDurableSessionCommit,
            ):
                raise DurableSessionCommitCorruption(
                    "session commit backend value type mismatch"
                )
            self._verify_signature(
                existing.value
            )
            if (
                existing.value.commit.digest
                != signed.commit.digest
            ):
                raise DurableSessionCommitConflict(
                    "finalization already binds different session commit"
                )
            return StoredDurableSessionCommit(
                existing.revision,
                existing.value,
            )
        try:
            record = self.backend.put_if_absent(
                self.namespace,
                key,
                signed,
            )
            return StoredDurableSessionCommit(
                record.revision,
                signed,
            )
        except DistributedStateConflict:
            winner = self.backend.get(
                self.namespace,
                key,
            )
            if (
                winner is None
                or not isinstance(
                    winner.value,
                    SignedDurableSessionCommit,
                )
            ):
                raise
            self._verify_signature(
                winner.value
            )
            if (
                winner.value.commit.digest
                != signed.commit.digest
            ):
                raise DurableSessionCommitConflict(
                    "concurrent session commit differs"
                )
            return StoredDurableSessionCommit(
                winner.revision,
                winner.value,
            )

    def _publish_head(
        self,
        stored: StoredDurableSessionCommit,
    ) -> tuple[
        int,
        DurableSessionCommitHead,
        bool,
    ]:
        desired = self._head_for(
            stored.signed
        )
        key = self._head_key(
            desired.session_id
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is not None:
            if not isinstance(
                existing.value,
                DurableSessionCommitHead,
            ):
                raise DurableSessionCommitCorruption(
                    "session commit head backend value type mismatch"
                )
            if existing.value != desired:
                raise DurableSessionCommitConflict(
                    "session already binds a different durable commit"
                )
            return (
                existing.revision,
                existing.value,
                False,
            )
        try:
            record = self.backend.put_if_absent(
                self.namespace,
                key,
                desired,
            )
            return (
                record.revision,
                desired,
                True,
            )
        except DistributedStateConflict:
            winner = self.backend.get(
                self.namespace,
                key,
            )
            if (
                winner is None
                or not isinstance(
                    winner.value,
                    DurableSessionCommitHead,
                )
            ):
                raise
            if winner.value != desired:
                raise DurableSessionCommitConflict(
                    "concurrent session head binds different durable commit"
                )
            return (
                winner.revision,
                winner.value,
                False,
            )

    def publish(
        self,
        commit: DurableSessionCommit,
    ) -> DurableSessionCommitPublication:
        if not isinstance(
            commit,
            DurableSessionCommit,
        ):
            raise TypeError(
                "commit must be DurableSessionCommit"
            )
        existing = self.get(
            commit.finalization_id
        )
        if existing is None:
            signed = self._sign(
                commit
            )
            stored = self._store_commit(
                signed
            )
        else:
            if (
                existing.signed.commit.digest
                != commit.digest
            ):
                raise DurableSessionCommitConflict(
                    "finalization already binds different session commit"
                )
            stored = existing

        (
            head_revision,
            head,
            head_created,
        ) = self._publish_head(stored)
        return DurableSessionCommitPublication(
            stored,
            head_revision,
            head,
            head_created,
        )

    def require(
        self,
        finalization_id: str,
        *,
        commit_digest: str = "",
    ) -> StoredDurableSessionCommit:
        stored = self.get(
            finalization_id
        )
        if stored is None:
            raise DurableSessionCommitConflict(
                "durable session commit is missing"
            )
        if commit_digest:
            commit_digest = _digest(
                "commit_digest",
                commit_digest,
            )
            if (
                stored.signed.commit.digest
                != commit_digest
            ):
                raise DurableSessionCommitConflict(
                    "durable session commit digest mismatch"
                )
        head = self.head(
            stored.signed.commit.session_id
        )
        if head is None:
            raise DurableSessionCommitCorruption(
                "durable session commit head is missing"
            )
        _, current = head
        expected = self._head_for(
            stored.signed
        )
        if current != expected:
            raise DurableSessionCommitCorruption(
                "durable session commit head differs from record"
            )
        return stored

    def require_session(
        self,
        session_id: str,
    ) -> StoredDurableSessionCommit:
        head = self.head(session_id)
        if head is None:
            raise DurableSessionCommitConflict(
                "durable session commit head is missing"
            )
        _, value = head
        stored = self.get(
            value.finalization_id
        )
        if stored is None:
            raise DurableSessionCommitCorruption(
                "session commit head references missing record"
            )
        if self._head_for(stored.signed) != value:
            raise DurableSessionCommitCorruption(
                "session commit head does not match record"
            )
        return stored

    def repair_head(
        self,
        finalization_id: str,
    ) -> DurableSessionCommitPublication:
        stored = self.get(
            finalization_id
        )
        if stored is None:
            raise DurableSessionCommitConflict(
                "cannot repair head without commit record"
            )
        (
            head_revision,
            head,
            head_created,
        ) = self._publish_head(
            stored
        )
        return DurableSessionCommitPublication(
            stored,
            head_revision,
            head,
            head_created,
        )

    def verify(
        self,
        finalization_id: str,
    ) -> bool:
        try:
            self.require(
                finalization_id
            )
        except (
            DurableSessionCommitConflict,
            DurableSessionCommitCorruption,
            ValueError,
        ):
            return False
        return True
