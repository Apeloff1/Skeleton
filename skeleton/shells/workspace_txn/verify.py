"""Independent verification helpers for transaction evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from skeleton.shells.provenance import canonical_json
from skeleton.shells.workspace_txn.backup import ContentAddressedBackupStore
from skeleton.shells.workspace_txn.journal import TransactionJournal
from skeleton.shells.workspace_txn.scanner import WorkspaceScanner
from skeleton.shells.workspace_txn.types import TransactionResult


@dataclass(frozen=True)
class VerificationFinding:
    code: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class TransactionVerification:
    transaction_id: str
    findings: tuple[VerificationFinding, ...]

    @property
    def ok(self) -> bool:
        return all(finding.ok for finding in self.findings)


class TransactionVerifier:
    def __init__(
        self,
        *,
        scanner: WorkspaceScanner,
        backup_store: ContentAddressedBackupStore,
        journal: TransactionJournal,
    ) -> None:
        self.scanner = scanner
        self.backup_store = backup_store
        self.journal = journal

    @staticmethod
    def _receipt_digest(result: TransactionResult) -> str:
        return hashlib.sha256(canonical_json(result.receipt.payload())).hexdigest()

    def verify(
        self,
        root: Path | str,
        result: TransactionResult,
    ) -> TransactionVerification:
        findings: list[VerificationFinding] = []
        findings.append(
            VerificationFinding(
                "receipt_digest",
                self._receipt_digest(result) == result.receipt.receipt_digest,
                "transaction receipt canonical digest",
            )
        )
        findings.append(
            VerificationFinding(
                "policy_binding",
                result.receipt.policy_digest == result.decision.policy_digest,
                "receipt policy digest binds evaluated policy",
            )
        )
        findings.append(
            VerificationFinding(
                "change_binding",
                result.receipt.change_set_digest == result.changes.digest,
                "receipt binds deterministic change set",
            )
        )
        if result.backup is not None:
            findings.append(
                VerificationFinding(
                    "backup_integrity",
                    self.backup_store.verify_manifest(result.backup),
                    "content-addressed backup manifest and blobs verify",
                )
            )
        findings.append(
            VerificationFinding(
                "journal_integrity",
                self.journal.verify(),
                "transaction journal hash chain verifies",
            )
        )
        events = self.journal.events(
            transaction_id=result.receipt.transaction_id
        )
        findings.append(
            VerificationFinding(
                "journal_presence",
                bool(events),
                "transaction has journal evidence",
            )
        )
        if result.reverted and result.rollback is not None:
            findings.append(
                VerificationFinding(
                    "rollback_verified",
                    result.rollback.verified,
                    "rollback scanner returned pre-mutation snapshot digest",
                )
            )
        return TransactionVerification(
            result.receipt.transaction_id,
            tuple(findings),
        )
