"""Session-scoped Merkle proof bundles for finalized AI shell executions.

A generic Merkle proof only establishes that one chain leaf belongs to one
signed Merkle checkpoint.  This module binds those proofs to the recovery and
session evidence already used by finalization.

The bundle is evidence only.  It does not widen execution authority and does
not replace native hash-chain, archive, or durable recovery verification.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from skeleton.shells.ai.durable_merkle import (
    DurableMerkleAuthority,
    DurableMerkleChainKind,
    DurableMerkleError,
    DurableMerkleProof,
    SignedDurableMerkleCheckpoint,
)
from skeleton.shells.ai.recovery_checkpoint import (
    AIRecoveryCheckpoint,
)
from skeleton.shells.ai.session_evidence import (
    SessionExecutionEvidence,
)
from skeleton.shells.ai.session_integrity import (
    SessionEvidenceIntegrityReport,
)
from skeleton.shells.ai.session_journal import (
    SessionJournalEvidence,
)


def _digest(
    name: str,
    value: str,
) -> str:
    if len(value) != 64:
        raise ValueError(
            f"{name} must be SHA-256 hex"
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be SHA-256 hex"
        ) from exc
    return value.lower()


def _identity(
    name: str,
    value: str,
    maximum: int,
) -> str:
    if not value or len(value) > maximum:
        raise ValueError(
            f"invalid {name}"
        )
    return value


def _canonical_digest(
    value: object,
) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DurableSessionMerkleProofBundle:
    schema_version: int
    finalization_id: str
    session_id: str
    recovery_checkpoint_digest: str
    session_integrity_digest: str
    journal_checkpoint: SignedDurableMerkleCheckpoint
    journal_proofs: tuple[
        DurableMerkleProof,
        ...,
    ]
    receipt_chain_root: str
    receipt_checkpoint: (
        SignedDurableMerkleCheckpoint
        | None
    )
    receipt_proofs: tuple[
        DurableMerkleProof,
        ...,
    ]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported session Merkle bundle schema"
            )
        object.__setattr__(
            self,
            "finalization_id",
            _identity(
                "finalization_id",
                self.finalization_id,
                256,
            ),
        )
        object.__setattr__(
            self,
            "session_id",
            _identity(
                "session_id",
                self.session_id,
                160,
            ),
        )
        for name in (
            "recovery_checkpoint_digest",
            "session_integrity_digest",
            "receipt_chain_root",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        if not isinstance(
            self.journal_checkpoint,
            SignedDurableMerkleCheckpoint,
        ):
            raise TypeError(
                "journal_checkpoint must be SignedDurableMerkleCheckpoint"
            )
        if (
            self.journal_checkpoint
            .checkpoint.chain_kind
            is not DurableMerkleChainKind.JOURNAL
        ):
            raise ValueError(
                "journal checkpoint has wrong chain kind"
            )
        object.__setattr__(
            self,
            "journal_proofs",
            tuple(self.journal_proofs),
        )
        if not self.journal_proofs:
            raise ValueError(
                "session Merkle bundle requires journal proofs"
            )
        if not all(
            isinstance(
                proof,
                DurableMerkleProof,
            )
            for proof in self.journal_proofs
        ):
            raise TypeError(
                "journal_proofs must contain DurableMerkleProof"
            )
        if len(
            {
                proof.sequence
                for proof in self.journal_proofs
            }
        ) != len(self.journal_proofs):
            raise ValueError(
                "duplicate journal proof sequence"
            )
        for proof in self.journal_proofs:
            if (
                proof.chain_kind
                is not DurableMerkleChainKind.JOURNAL
            ):
                raise ValueError(
                    "journal proof has wrong chain kind"
                )
            if (
                proof.checkpoint_digest
                != self.journal_checkpoint.digest
            ):
                raise ValueError(
                    "journal proof checkpoint binding mismatch"
                )

        object.__setattr__(
            self,
            "receipt_proofs",
            tuple(self.receipt_proofs),
        )
        if self.receipt_checkpoint is None:
            if self.receipt_proofs:
                raise ValueError(
                    "receipt proofs require receipt checkpoint"
                )
        else:
            if not isinstance(
                self.receipt_checkpoint,
                SignedDurableMerkleCheckpoint,
            ):
                raise TypeError(
                    "receipt_checkpoint must be signed Merkle checkpoint"
                )
            if (
                self.receipt_checkpoint
                .checkpoint.chain_kind
                is not DurableMerkleChainKind.RECEIPTS
            ):
                raise ValueError(
                    "receipt checkpoint has wrong chain kind"
                )
            if (
                self.receipt_checkpoint
                .checkpoint.chain_root
                != self.receipt_chain_root
            ):
                raise ValueError(
                    "receipt checkpoint root differs from bundle root"
                )
            if len(
                {
                    proof.sequence
                    for proof in self.receipt_proofs
                }
            ) != len(self.receipt_proofs):
                raise ValueError(
                    "duplicate receipt proof sequence"
                )
            for proof in self.receipt_proofs:
                if (
                    proof.chain_kind
                    is not DurableMerkleChainKind.RECEIPTS
                ):
                    raise ValueError(
                        "receipt proof has wrong chain kind"
                    )
                if (
                    proof.checkpoint_digest
                    != self.receipt_checkpoint.digest
                ):
                    raise ValueError(
                        "receipt proof checkpoint binding mismatch"
                    )

    @property
    def journal_chain_root(self) -> str:
        return (
            self.journal_checkpoint
            .checkpoint.chain_root
        )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "finalization_id": (
                self.finalization_id
            ),
            "session_id": self.session_id,
            "recovery_checkpoint_digest": (
                self.recovery_checkpoint_digest
            ),
            "session_integrity_digest": (
                self.session_integrity_digest
            ),
            "journal_chain_root": (
                self.journal_chain_root
            ),
            "journal_checkpoint": (
                self.journal_checkpoint.to_dict()
            ),
            "journal_proofs": [
                proof.to_dict()
                for proof in self.journal_proofs
            ],
            "receipt_chain_root": (
                self.receipt_chain_root
            ),
            "receipt_checkpoint": (
                None
                if self.receipt_checkpoint is None
                else self.receipt_checkpoint.to_dict()
            ),
            "receipt_proofs": [
                proof.to_dict()
                for proof in self.receipt_proofs
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableSessionMerkleVerification:
    ok: bool
    identity_valid: bool
    recovery_binding_valid: bool
    integrity_binding_valid: bool
    journal_checkpoint_valid: bool
    journal_proofs_valid: bool
    receipt_checkpoint_valid: bool
    receipt_proofs_valid: bool
    journal_proof_count: int
    receipt_proof_count: int
    issues: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "ok",
            "identity_valid",
            "recovery_binding_valid",
            "integrity_binding_valid",
            "journal_checkpoint_valid",
            "journal_proofs_valid",
            "receipt_checkpoint_valid",
            "receipt_proofs_valid",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        for name in (
            "journal_proof_count",
            "receipt_proof_count",
        ):
            value = getattr(
                self,
                name,
            )
            if (
                isinstance(value, bool)
                or not isinstance(
                    value,
                    int,
                )
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        object.__setattr__(
            self,
            "issues",
            tuple(self.issues),
        )
        if any(
            not issue
            or len(issue) > 2048
            for issue in self.issues
        ):
            raise ValueError(
                "invalid session Merkle verification issue"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "identity_valid": (
                self.identity_valid
            ),
            "recovery_binding_valid": (
                self.recovery_binding_valid
            ),
            "integrity_binding_valid": (
                self.integrity_binding_valid
            ),
            "journal_checkpoint_valid": (
                self.journal_checkpoint_valid
            ),
            "journal_proofs_valid": (
                self.journal_proofs_valid
            ),
            "receipt_checkpoint_valid": (
                self.receipt_checkpoint_valid
            ),
            "receipt_proofs_valid": (
                self.receipt_proofs_valid
            ),
            "journal_proof_count": (
                self.journal_proof_count
            ),
            "receipt_proof_count": (
                self.receipt_proof_count
            ),
            "issues": list(self.issues),
        }


class DurableSessionMerkleError(
    RuntimeError
):
    pass


class DurableSessionMerkleAuthority:
    """Build and verify compact proof bundles for one finalized session."""

    def __init__(
        self,
        merkle: DurableMerkleAuthority,
        *,
        journal_chain_id: str = (
            "shell-ai-decision-journal"
        ),
        receipt_chain_id: str = (
            "shell-execution-receipts"
        ),
    ) -> None:
        if not isinstance(
            merkle,
            DurableMerkleAuthority,
        ):
            raise TypeError(
                "merkle must be DurableMerkleAuthority"
            )
        self.merkle = merkle
        self.journal_chain_id = _identity(
            "journal_chain_id",
            journal_chain_id,
            160,
        )
        self.receipt_chain_id = _identity(
            "receipt_chain_id",
            receipt_chain_id,
            160,
        )

    @staticmethod
    def _journal_expected(
        session_journal: SessionJournalEvidence,
    ) -> dict[int, str]:
        expected: dict[int, str] = {}
        for event in (
            session_journal.events
        ):
            if (
                event.global_sequence
                in expected
            ):
                raise DurableSessionMerkleError(
                    "duplicate journal sequence in session evidence"
                )
            expected[
                event.global_sequence
            ] = event.event_hash
        if not expected:
            raise DurableSessionMerkleError(
                "session journal contains no events"
            )
        return expected

    @staticmethod
    def _receipt_expected(
        integrity: SessionEvidenceIntegrityReport,
    ) -> dict[
        int,
        tuple[str, str],
    ]:
        expected: dict[
            int,
            tuple[str, str],
        ] = {}
        for inclusion in (
            integrity.receipt_inclusions
        ):
            if not inclusion.valid:
                raise DurableSessionMerkleError(
                    "cannot build Merkle bundle from invalid receipt inclusion"
                )
            if (
                inclusion.global_sequence
                is None
            ):
                raise DurableSessionMerkleError(
                    "receipt inclusion lacks global sequence"
                )
            sequence = (
                inclusion.global_sequence
            )
            value = (
                inclusion.receipt_id,
                inclusion.fingerprint,
            )
            if (
                sequence in expected
                and expected[sequence]
                != value
            ):
                raise DurableSessionMerkleError(
                    "conflicting receipt identity at same global sequence"
                )
            expected[sequence] = value
        return expected

    @staticmethod
    def _validate_common(
        *,
        finalization_id: str,
        session_id: str,
        recovery: AIRecoveryCheckpoint,
        integrity: SessionEvidenceIntegrityReport,
        session_journal: SessionJournalEvidence,
        session_evidence: SessionExecutionEvidence,
    ) -> None:
        _identity(
            "finalization_id",
            finalization_id,
            256,
        )
        _identity(
            "session_id",
            session_id,
            160,
        )
        if not isinstance(
            recovery,
            AIRecoveryCheckpoint,
        ):
            raise TypeError(
                "recovery must be AIRecoveryCheckpoint"
            )
        if not isinstance(
            integrity,
            SessionEvidenceIntegrityReport,
        ):
            raise TypeError(
                "integrity must be SessionEvidenceIntegrityReport"
            )
        if not isinstance(
            session_journal,
            SessionJournalEvidence,
        ):
            raise TypeError(
                "session_journal must be SessionJournalEvidence"
            )
        if not isinstance(
            session_evidence,
            SessionExecutionEvidence,
        ):
            raise TypeError(
                "session_evidence must be SessionExecutionEvidence"
            )
        identities = {
            session_id,
            recovery.session.session_id,
            integrity.session_id,
            session_journal.session_id,
            session_evidence.session_id,
        }
        if len(identities) != 1:
            raise DurableSessionMerkleError(
                "session identity mismatch across Merkle bundle inputs"
            )
        if not integrity.ok:
            raise DurableSessionMerkleError(
                "session integrity must be valid before Merkle proof build"
            )
        if (
            recovery.session_integrity_digest
            and recovery.session_integrity_digest
            != integrity.digest
        ):
            raise DurableSessionMerkleError(
                "recovery checkpoint integrity digest mismatch"
            )
        if (
            recovery.session_evidence_digest
            and recovery.session_evidence_digest
            != session_evidence.digest
        ):
            raise DurableSessionMerkleError(
                "recovery checkpoint session evidence digest mismatch"
            )
        if (
            recovery.session_journal_digest
            and recovery.session_journal_digest
            != session_journal.digest
        ):
            raise DurableSessionMerkleError(
                "recovery checkpoint session journal digest mismatch"
            )
        if (
            recovery.session.journal_root
            != integrity.journal_root
        ):
            raise DurableSessionMerkleError(
                "recovery journal root differs from integrity report"
            )
        if (
            recovery.session.receipt_root
            != integrity.receipt_root
        ):
            raise DurableSessionMerkleError(
                "recovery receipt root differs from integrity report"
            )

    def build(
        self,
        *,
        finalization_id: str,
        session_id: str,
        recovery: AIRecoveryCheckpoint,
        integrity: SessionEvidenceIntegrityReport,
        session_journal: SessionJournalEvidence,
        session_evidence: SessionExecutionEvidence,
        journal_chain,
        receipt_chain,
    ) -> DurableSessionMerkleProofBundle:
        self._validate_common(
            finalization_id=finalization_id,
            session_id=session_id,
            recovery=recovery,
            integrity=integrity,
            session_journal=session_journal,
            session_evidence=session_evidence,
        )
        journal_expected = (
            self._journal_expected(
                session_journal
            )
        )
        receipt_expected = (
            self._receipt_expected(
                integrity
            )
        )

        (
            journal_checkpoint,
            journal_leaves,
        ) = self.merkle.build(
            journal_chain,
            chain_id=self.journal_chain_id,
            chain_kind=(
                DurableMerkleChainKind.JOURNAL
            ),
            root_hash=(
                recovery.session.journal_root
            ),
        )
        journal_proofs = (
            self.merkle.proofs_for_sequences(
                journal_checkpoint,
                journal_leaves,
                journal_expected.keys(),
            )
        )
        if (
            journal_checkpoint
            .checkpoint.chain_root
            != recovery.session.journal_root
        ):
            raise DurableSessionMerkleError(
                "journal Merkle checkpoint root mismatch"
            )
        for proof in journal_proofs:
            expected_hash = (
                journal_expected[
                    proof.sequence
                ]
            )
            self.merkle.require_proof(
                journal_checkpoint,
                proof,
                expected_subject_id=(
                    expected_hash
                ),
                expected_payload_fingerprint=(
                    expected_hash
                ),
                chain=journal_chain,
            )

        receipt_checkpoint = None
        receipt_proofs: tuple[
            DurableMerkleProof,
            ...,
        ] = ()
        if receipt_expected:
            (
                receipt_checkpoint,
                receipt_leaves,
            ) = self.merkle.build(
                receipt_chain,
                chain_id=(
                    self.receipt_chain_id
                ),
                chain_kind=(
                    DurableMerkleChainKind.RECEIPTS
                ),
                root_hash=(
                    recovery.session.receipt_root
                ),
            )
            receipt_proofs = (
                self.merkle.proofs_for_sequences(
                    receipt_checkpoint,
                    receipt_leaves,
                    receipt_expected.keys(),
                )
            )
            for proof in receipt_proofs:
                (
                    expected_id,
                    expected_fingerprint,
                ) = receipt_expected[
                    proof.sequence
                ]
                self.merkle.require_proof(
                    receipt_checkpoint,
                    proof,
                    expected_subject_id=(
                        expected_id
                    ),
                    expected_payload_fingerprint=(
                        expected_fingerprint
                    ),
                    chain=receipt_chain,
                )

        return DurableSessionMerkleProofBundle(
            1,
            finalization_id,
            session_id,
            recovery.digest,
            integrity.digest,
            journal_checkpoint,
            journal_proofs,
            recovery.session.receipt_root,
            receipt_checkpoint,
            receipt_proofs,
        )

    @staticmethod
    def _journal_proof_map(
        bundle: DurableSessionMerkleProofBundle,
    ) -> Mapping[
        int,
        DurableMerkleProof,
    ]:
        return {
            proof.sequence: proof
            for proof in bundle.journal_proofs
        }

    @staticmethod
    def _receipt_proof_map(
        bundle: DurableSessionMerkleProofBundle,
    ) -> Mapping[
        int,
        DurableMerkleProof,
    ]:
        return {
            proof.sequence: proof
            for proof in bundle.receipt_proofs
        }

    def inspect(
        self,
        bundle: DurableSessionMerkleProofBundle,
        *,
        finalization_id: str,
        session_id: str,
        recovery: AIRecoveryCheckpoint,
        integrity: SessionEvidenceIntegrityReport,
        session_journal: SessionJournalEvidence,
        session_evidence: SessionExecutionEvidence,
        journal_chain=None,
        receipt_chain=None,
    ) -> DurableSessionMerkleVerification:
        issues: list[str] = []
        identity_valid = True
        recovery_valid = True
        integrity_valid = True
        journal_checkpoint_valid = True
        journal_proofs_valid = True
        receipt_checkpoint_valid = True
        receipt_proofs_valid = True

        try:
            self._validate_common(
                finalization_id=finalization_id,
                session_id=session_id,
                recovery=recovery,
                integrity=integrity,
                session_journal=session_journal,
                session_evidence=session_evidence,
            )
        except Exception as exc:
            issues.append(
                "session input validation failed: "
                f"{type(exc).__name__}"
            )
            integrity_valid = False

        if (
            bundle.finalization_id
            != finalization_id
            or bundle.session_id
            != session_id
        ):
            identity_valid = False
            issues.append(
                "Merkle bundle finalization/session identity mismatch"
            )

        if (
            bundle.recovery_checkpoint_digest
            != recovery.digest
            or bundle.journal_chain_root
            != recovery.session.journal_root
            or bundle.receipt_chain_root
            != recovery.session.receipt_root
        ):
            recovery_valid = False
            issues.append(
                "Merkle bundle recovery checkpoint binding mismatch"
            )

        if (
            bundle.session_integrity_digest
            != integrity.digest
        ):
            integrity_valid = False
            issues.append(
                "Merkle bundle session integrity binding mismatch"
            )

        journal_expected: dict[
            int,
            str,
        ] = {}
        try:
            journal_expected = (
                self._journal_expected(
                    session_journal
                )
            )
        except Exception as exc:
            journal_proofs_valid = False
            issues.append(
                "journal expectation construction failed: "
                f"{type(exc).__name__}"
            )

        journal_map = (
            self._journal_proof_map(
                bundle
            )
        )
        if (
            set(journal_map)
            != set(journal_expected)
        ):
            journal_proofs_valid = False
            issues.append(
                "journal Merkle proof sequence set mismatch"
            )

        if (
            bundle.journal_checkpoint
            .checkpoint.chain_root
            != recovery.session.journal_root
        ):
            journal_checkpoint_valid = False
            issues.append(
                "journal Merkle checkpoint historical root mismatch"
            )

        try:
            self.merkle.verify_checkpoint_signature(
                bundle.journal_checkpoint
            )
        except Exception as exc:
            journal_checkpoint_valid = False
            issues.append(
                "journal Merkle checkpoint signature failed: "
                f"{type(exc).__name__}"
            )

        if (
            journal_chain is not None
            and not self.merkle
            .verify_checkpoint_against_chain(
                bundle.journal_checkpoint,
                journal_chain,
            )
        ):
            journal_checkpoint_valid = False
            issues.append(
                "journal Merkle checkpoint no longer matches chain"
            )

        for sequence, expected_hash in (
            journal_expected.items()
        ):
            proof = journal_map.get(
                sequence
            )
            if proof is None:
                continue
            report = (
                self.merkle.inspect_proof(
                    bundle.journal_checkpoint,
                    proof,
                    expected_subject_id=(
                        expected_hash
                    ),
                    expected_payload_fingerprint=(
                        expected_hash
                    ),
                    chain=journal_chain,
                )
            )
            if not report.ok:
                journal_proofs_valid = False
                issues.append(
                    "journal Merkle proof failed "
                    f"for sequence {sequence}"
                )

        receipt_expected: dict[
            int,
            tuple[str, str],
        ] = {}
        try:
            receipt_expected = (
                self._receipt_expected(
                    integrity
                )
            )
        except Exception as exc:
            receipt_proofs_valid = False
            issues.append(
                "receipt expectation construction failed: "
                f"{type(exc).__name__}"
            )

        receipt_map = (
            self._receipt_proof_map(
                bundle
            )
        )
        if (
            set(receipt_map)
            != set(receipt_expected)
        ):
            receipt_proofs_valid = False
            issues.append(
                "receipt Merkle proof sequence set mismatch"
            )

        if receipt_expected:
            if bundle.receipt_checkpoint is None:
                receipt_checkpoint_valid = False
                receipt_proofs_valid = False
                issues.append(
                    "receipt Merkle checkpoint is missing"
                )
            else:
                if (
                    bundle.receipt_checkpoint
                    .checkpoint.chain_root
                    != recovery.session.receipt_root
                ):
                    receipt_checkpoint_valid = False
                    issues.append(
                        "receipt Merkle checkpoint historical root mismatch"
                    )
                try:
                    self.merkle.verify_checkpoint_signature(
                        bundle.receipt_checkpoint
                    )
                except Exception as exc:
                    receipt_checkpoint_valid = False
                    issues.append(
                        "receipt Merkle checkpoint signature failed: "
                        f"{type(exc).__name__}"
                    )
                if (
                    receipt_chain is not None
                    and not self.merkle
                    .verify_checkpoint_against_chain(
                        bundle.receipt_checkpoint,
                        receipt_chain,
                    )
                ):
                    receipt_checkpoint_valid = False
                    issues.append(
                        "receipt Merkle checkpoint no longer matches chain"
                    )

                for (
                    sequence,
                    (
                        expected_id,
                        expected_fingerprint,
                    ),
                ) in receipt_expected.items():
                    proof = receipt_map.get(
                        sequence
                    )
                    if proof is None:
                        continue
                    report = (
                        self.merkle.inspect_proof(
                            bundle.receipt_checkpoint,
                            proof,
                            expected_subject_id=(
                                expected_id
                            ),
                            expected_payload_fingerprint=(
                                expected_fingerprint
                            ),
                            chain=receipt_chain,
                        )
                    )
                    if not report.ok:
                        receipt_proofs_valid = False
                        issues.append(
                            "receipt Merkle proof failed "
                            f"for sequence {sequence}"
                        )
        else:
            if (
                bundle.receipt_checkpoint
                is not None
                or bundle.receipt_proofs
            ):
                receipt_checkpoint_valid = False
                receipt_proofs_valid = False
                issues.append(
                    "receipt Merkle evidence exists for session without receipts"
                )

        ok = (
            identity_valid
            and recovery_valid
            and integrity_valid
            and journal_checkpoint_valid
            and journal_proofs_valid
            and receipt_checkpoint_valid
            and receipt_proofs_valid
            and not issues
        )
        return DurableSessionMerkleVerification(
            ok,
            identity_valid,
            recovery_valid,
            integrity_valid,
            journal_checkpoint_valid,
            journal_proofs_valid,
            receipt_checkpoint_valid,
            receipt_proofs_valid,
            len(bundle.journal_proofs),
            len(bundle.receipt_proofs),
            tuple(issues),
        )

    def require(
        self,
        bundle: DurableSessionMerkleProofBundle,
        *,
        finalization_id: str,
        session_id: str,
        recovery: AIRecoveryCheckpoint,
        integrity: SessionEvidenceIntegrityReport,
        session_journal: SessionJournalEvidence,
        session_evidence: SessionExecutionEvidence,
        journal_chain=None,
        receipt_chain=None,
    ) -> DurableSessionMerkleVerification:
        report = self.inspect(
            bundle,
            finalization_id=finalization_id,
            session_id=session_id,
            recovery=recovery,
            integrity=integrity,
            session_journal=session_journal,
            session_evidence=session_evidence,
            journal_chain=journal_chain,
            receipt_chain=receipt_chain,
        )
        if not report.ok:
            detail = (
                report.issues[0]
                if report.issues
                else "session Merkle verification failed"
            )
            raise DurableSessionMerkleError(
                detail
            )
        return report
