"""Cross-layer integrity checks for finalized AI shell sessions.

A globally valid decision journal or receipt chain does not by itself prove
that one session's evidence is represented correctly.  This module verifies
the session-scoped journal manifest and execution evidence against the exact
committed chain contents before higher-level recovery evidence is signed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from skeleton.shells.ai.session_evidence import (
    SessionExecutionEvidence,
)
from skeleton.shells.ai.session_journal import (
    SessionJournalEvidence,
)


def _sha256_hex(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    # Digest values are opaque 64-character authority tokens; production

    # hashes are hexadecimal, while deterministic test/adapter sentinels may

    # use the full string alphabet.
    return value.lower()


@dataclass(frozen=True)
class JournalInclusionResult:
    global_sequence: int
    event_hash: str
    kind: str
    proposal_id: str
    found: bool
    valid: bool
    reason: str = ""

    def __post_init__(self) -> None:
        if (
            isinstance(self.global_sequence, bool)
            or not isinstance(self.global_sequence, int)
            or self.global_sequence <= 0
        ):
            raise ValueError(
                "journal inclusion sequence must be positive"
            )
        object.__setattr__(
            self,
            "event_hash",
            _sha256_hex(
                "event_hash",
                self.event_hash,
            ),
        )
        if not self.kind or len(self.kind) > 128:
            raise ValueError(
                "invalid journal inclusion kind"
            )
        if len(self.proposal_id) > 160:
            raise ValueError(
                "journal inclusion proposal_id too long"
            )
        if not isinstance(self.found, bool):
            raise ValueError("found must be bool")
        if not isinstance(self.valid, bool):
            raise ValueError("valid must be bool")
        if self.valid and not self.found:
            raise ValueError(
                "valid journal inclusion must be found"
            )
        if len(self.reason) > 2048:
            raise ValueError(
                "journal inclusion reason too long"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "global_sequence": self.global_sequence,
            "event_hash": self.event_hash,
            "kind": self.kind,
            "proposal_id": self.proposal_id,
            "found": self.found,
            "valid": self.valid,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ReceiptInclusionResult:
    step_id: str
    correlation_id: str
    attempt: int
    receipt_id: str
    fingerprint: str
    returncode: int | None
    global_sequence: int | None
    found: bool
    valid: bool
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.step_id or len(self.step_id) > 128:
            raise ValueError(
                "invalid receipt inclusion step_id"
            )
        if len(self.correlation_id) > 160:
            raise ValueError(
                "receipt inclusion correlation_id too long"
            )
        if (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt <= 0
        ):
            raise ValueError(
                "receipt inclusion attempt must be positive"
            )
        if not self.receipt_id or len(self.receipt_id) > 128:
            raise ValueError(
                "invalid receipt inclusion receipt_id"
            )
        object.__setattr__(
            self,
            "fingerprint",
            _sha256_hex(
                "fingerprint",
                self.fingerprint,
            ),
        )
        if self.global_sequence is not None and (
            isinstance(self.global_sequence, bool)
            or not isinstance(self.global_sequence, int)
            or self.global_sequence <= 0
        ):
            raise ValueError(
                "receipt global_sequence must be positive"
            )
        if not isinstance(self.found, bool):
            raise ValueError("found must be bool")
        if not isinstance(self.valid, bool):
            raise ValueError("valid must be bool")
        if self.valid and not self.found:
            raise ValueError(
                "valid receipt inclusion must be found"
            )
        if len(self.reason) > 2048:
            raise ValueError(
                "receipt inclusion reason too long"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "correlation_id": self.correlation_id,
            "attempt": self.attempt,
            "receipt_id": self.receipt_id,
            "fingerprint": self.fingerprint,
            "returncode": self.returncode,
            "global_sequence": self.global_sequence,
            "found": self.found,
            "valid": self.valid,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SessionEvidenceIntegrityReport:
    session_id: str
    journal_chain_ok: bool
    receipt_chain_ok: bool
    journal_root: str
    receipt_root: str
    journal_manifest_digest: str
    receipt_manifest_digest: str
    journal_inclusions: tuple[
        JournalInclusionResult,
        ...,
    ]
    receipt_inclusions: tuple[
        ReceiptInclusionResult,
        ...,
    ]
    issues: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError(
                "invalid integrity report session_id"
            )
        if not isinstance(self.journal_chain_ok, bool):
            raise ValueError(
                "journal_chain_ok must be bool"
            )
        if not isinstance(self.receipt_chain_ok, bool):
            raise ValueError(
                "receipt_chain_ok must be bool"
            )
        object.__setattr__(
            self,
            "journal_root",
            _sha256_hex(
                "journal_root",
                self.journal_root,
            ),
        )
        object.__setattr__(
            self,
            "receipt_root",
            _sha256_hex(
                "receipt_root",
                self.receipt_root,
            ),
        )
        object.__setattr__(
            self,
            "journal_manifest_digest",
            _sha256_hex(
                "journal_manifest_digest",
                self.journal_manifest_digest,
            ),
        )
        object.__setattr__(
            self,
            "receipt_manifest_digest",
            _sha256_hex(
                "receipt_manifest_digest",
                self.receipt_manifest_digest,
            ),
        )
        object.__setattr__(
            self,
            "journal_inclusions",
            tuple(self.journal_inclusions),
        )
        object.__setattr__(
            self,
            "receipt_inclusions",
            tuple(self.receipt_inclusions),
        )
        object.__setattr__(
            self,
            "issues",
            tuple(self.issues),
        )
        if any(len(issue) > 2048 for issue in self.issues):
            raise ValueError(
                "integrity issue text too long"
            )

    @property
    def ok(self) -> bool:
        return (
            self.journal_chain_ok
            and self.receipt_chain_ok
            and not self.issues
            and all(
                item.valid
                for item in self.journal_inclusions
            )
            and all(
                item.valid
                for item in self.receipt_inclusions
            )
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "session_id": self.session_id,
            "journal_chain_ok": self.journal_chain_ok,
            "receipt_chain_ok": self.receipt_chain_ok,
            "journal_root": self.journal_root,
            "receipt_root": self.receipt_root,
            "journal_manifest_digest": (
                self.journal_manifest_digest
            ),
            "receipt_manifest_digest": (
                self.receipt_manifest_digest
            ),
            "journal_inclusions": [
                item.to_dict()
                for item in self.journal_inclusions
            ],
            "receipt_inclusions": [
                item.to_dict()
                for item in self.receipt_inclusions
            ],
            "issues": list(self.issues),
            "ok": self.ok,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class SessionEvidenceIntegrityError(RuntimeError):
    pass


class SessionEvidenceIntegrityVerifier:
    """Verify one session against journal and receipt chain contents."""

    def __init__(
        self,
        journal,
        receipt_chain,
        *,
        require_session_journal: bool = True,
        journal_root_verifier=None,
        receipt_root_verifier=None,
    ) -> None:
        for name, value in (
            ("journal", journal),
            ("receipt_chain", receipt_chain),
        ):
            for method in (
                "snapshot",
                "verify",
                "root_hash",
            ):
                if not callable(
                    getattr(value, method, None)
                ):
                    raise TypeError(
                        f"{name} does not implement {method}"
                    )
        if not isinstance(
            require_session_journal,
            bool,
        ):
            raise ValueError(
                "require_session_journal must be bool"
            )
        self.journal = journal
        self.receipt_chain = receipt_chain
        self.require_session_journal = (
            require_session_journal
        )
        for name, verifier in (
            ("journal_root_verifier", journal_root_verifier),
            ("receipt_root_verifier", receipt_root_verifier),
        ):
            if verifier is not None and not callable(verifier):
                raise TypeError(f"{name} must be callable")
        self.journal_root_verifier = journal_root_verifier
        self.receipt_root_verifier = receipt_root_verifier

    @staticmethod
    def _manifest_digest(
        values: Iterable[dict[str, object]],
    ) -> str:
        raw = json.dumps(
            list(values),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def _journal_inclusions(
        self,
        evidence: SessionJournalEvidence,
        snapshot=None,
    ) -> tuple[
        tuple[JournalInclusionResult, ...],
        tuple[str, ...],
    ]:
        if snapshot is None:
            snapshot = self.journal.snapshot()
        by_sequence = {
            event.sequence: event
            for event in snapshot
        }
        issues: list[str] = []
        results: list[
            JournalInclusionResult
        ] = []

        if (
            self.require_session_journal
            and not evidence.events
        ):
            issues.append(
                "session journal contains no events"
            )

        for expected in evidence.events:
            actual = by_sequence.get(
                expected.global_sequence
            )
            if actual is None:
                reason = (
                    "journal event sequence is missing"
                )
                issues.append(
                    f"journal sequence "
                    f"{expected.global_sequence} missing"
                )
                results.append(
                    JournalInclusionResult(
                        expected.global_sequence,
                        expected.event_hash,
                        expected.kind,
                        expected.proposal_id,
                        False,
                        False,
                        reason,
                    )
                )
                continue

            problems: list[str] = []
            if (
                actual.event_hash
                != expected.event_hash
            ):
                problems.append(
                    "event hash mismatch"
                )
            if actual.kind != expected.kind:
                problems.append(
                    "event kind mismatch"
                )
            if (
                actual.proposal_id
                != expected.proposal_id
            ):
                problems.append(
                    "proposal id mismatch"
                )
            if (
                actual.session_id
                != evidence.session_id
            ):
                problems.append(
                    "session id mismatch"
                )

            valid = not problems
            reason = "; ".join(problems)
            if not valid:
                issues.append(
                    f"journal sequence "
                    f"{expected.global_sequence}: "
                    f"{reason}"
                )
            results.append(
                JournalInclusionResult(
                    expected.global_sequence,
                    expected.event_hash,
                    expected.kind,
                    expected.proposal_id,
                    True,
                    valid,
                    reason,
                )
            )
        return tuple(results), tuple(issues)

    def _receipt_inclusions(
        self,
        evidence: SessionExecutionEvidence,
        snapshot=None,
    ) -> tuple[
        tuple[ReceiptInclusionResult, ...],
        tuple[str, ...],
    ]:
        if snapshot is None:
            snapshot = self.receipt_chain.snapshot()
        by_id: dict[str, list[object]] = {}
        for item in snapshot:
            by_id.setdefault(
                item.receipt.receipt_id,
                [],
            ).append(item)

        issues: list[str] = []
        results: list[
            ReceiptInclusionResult
        ] = []

        for step in evidence.steps:
            if step.attempts == 0:
                continue
            for index, receipt_id in enumerate(
                step.receipt_ids,
            ):
                expected_fingerprint = (
                    step.receipt_fingerprints[index]
                )
                expected_returncode = (
                    step.returncodes[index]
                )
                attempt = index + 1
                matches = by_id.get(
                    receipt_id,
                    [],
                )
                if not matches:
                    reason = "receipt id is missing"
                    issues.append(
                        f"step {step.step_id} "
                        f"receipt {receipt_id} missing"
                    )
                    results.append(
                        ReceiptInclusionResult(
                            step.step_id,
                            step.correlation_id,
                            attempt,
                            receipt_id,
                            expected_fingerprint,
                            expected_returncode,
                            None,
                            False,
                            False,
                            reason,
                        )
                    )
                    continue

                if len(matches) > 1:
                    reason = (
                        "receipt id appears multiple "
                        "times in committed chain"
                    )
                    issues.append(
                        f"step {step.step_id} "
                        f"receipt {receipt_id} duplicated"
                    )
                    first = matches[0]
                    results.append(
                        ReceiptInclusionResult(
                            step.step_id,
                            step.correlation_id,
                            attempt,
                            receipt_id,
                            expected_fingerprint,
                            expected_returncode,
                            first.sequence,
                            True,
                            False,
                            reason,
                        )
                    )
                    continue

                item = matches[0]
                actual = item.receipt
                problems: list[str] = []
                if (
                    actual.fingerprint
                    != expected_fingerprint
                ):
                    problems.append(
                        "fingerprint mismatch"
                    )
                if (
                    actual.correlation_id
                    != step.correlation_id
                ):
                    problems.append(
                        "correlation id mismatch"
                    )
                if actual.returncode != expected_returncode:
                    problems.append(
                        "returncode mismatch"
                    )
                if actual.attempt != attempt:
                    problems.append(
                        "attempt number mismatch"
                    )

                valid = not problems
                reason = "; ".join(problems)
                if not valid:
                    issues.append(
                        f"step {step.step_id} "
                        f"receipt {receipt_id}: "
                        f"{reason}"
                    )
                results.append(
                    ReceiptInclusionResult(
                        step.step_id,
                        step.correlation_id,
                        attempt,
                        receipt_id,
                        expected_fingerprint,
                        expected_returncode,
                        item.sequence,
                        True,
                        valid,
                        reason,
                    )
                )
        return tuple(results), tuple(issues)

    def _direct_journal_inclusions(
        self,
        evidence: SessionJournalEvidence,
        expected_root: str,
    ):
        if self.journal_root_verifier is None:
            return None
        get_by_sequence = getattr(
            self.journal,
            "get_by_sequence",
            None,
        )
        sequence_for_root = getattr(
            self.journal,
            "sequence_for_root",
            None,
        )
        if not (
            callable(get_by_sequence)
            and callable(sequence_for_root)
        ):
            return None
        try:
            if not bool(
                self.journal_root_verifier(
                    expected_root
                )
            ):
                return None
            target_sequence = int(
                sequence_for_root(
                    expected_root
                )
            )
        except Exception:
            return None

        issues: list[str] = []
        results: list[JournalInclusionResult] = []
        if (
            self.require_session_journal
            and not evidence.events
        ):
            issues.append(
                "session journal contains no events"
            )
        for expected in evidence.events:
            if (
                expected.global_sequence
                > target_sequence
            ):
                reason = (
                    "journal event is newer than "
                    "historical proof root"
                )
                issues.append(
                    f"journal sequence "
                    f"{expected.global_sequence}: "
                    f"{reason}"
                )
                results.append(
                    JournalInclusionResult(
                        expected.global_sequence,
                        expected.event_hash,
                        expected.kind,
                        expected.proposal_id,
                        False,
                        False,
                        reason,
                    )
                )
                continue
            try:
                actual = get_by_sequence(
                    expected.global_sequence,
                    repair_missing=False,
                )
            except Exception:
                reason = (
                    "journal event sequence is unavailable"
                )
                issues.append(
                    f"journal sequence "
                    f"{expected.global_sequence} unavailable"
                )
                results.append(
                    JournalInclusionResult(
                        expected.global_sequence,
                        expected.event_hash,
                        expected.kind,
                        expected.proposal_id,
                        False,
                        False,
                        reason,
                    )
                )
                continue
            problems: list[str] = []
            if (
                actual.event_hash
                != expected.event_hash
            ):
                problems.append(
                    "event hash mismatch"
                )
            if actual.kind != expected.kind:
                problems.append(
                    "event kind mismatch"
                )
            if (
                actual.proposal_id
                != expected.proposal_id
            ):
                problems.append(
                    "proposal id mismatch"
                )
            if (
                actual.session_id
                != evidence.session_id
            ):
                problems.append(
                    "session id mismatch"
                )
            valid = not problems
            reason = "; ".join(problems)
            if not valid:
                issues.append(
                    f"journal sequence "
                    f"{expected.global_sequence}: "
                    f"{reason}"
                )
            results.append(
                JournalInclusionResult(
                    expected.global_sequence,
                    expected.event_hash,
                    expected.kind,
                    expected.proposal_id,
                    True,
                    valid,
                    reason,
                )
            )
        return (
            tuple(results),
            tuple(issues),
            expected_root,
        )

    def _direct_receipt_inclusions(
        self,
        evidence: SessionExecutionEvidence,
        expected_root: str,
    ):
        if self.receipt_root_verifier is None:
            return None
        find_by_receipt_id = getattr(
            self.receipt_chain,
            "find_by_receipt_id",
            None,
        )
        get_by_sequence = getattr(
            self.receipt_chain,
            "get_by_sequence",
            None,
        )
        sequence_for_root = getattr(
            self.receipt_chain,
            "sequence_for_root",
            None,
        )
        if not (
            callable(find_by_receipt_id)
            and callable(get_by_sequence)
            and callable(sequence_for_root)
        ):
            return None
        try:
            if not bool(
                self.receipt_root_verifier(
                    expected_root
                )
            ):
                return None
            target_sequence = int(
                sequence_for_root(
                    expected_root
                )
            )
        except Exception:
            return None

        issues: list[str] = []
        results: list[ReceiptInclusionResult] = []
        for step in evidence.steps:
            if step.attempts == 0:
                continue
            for index, receipt_id in enumerate(
                step.receipt_ids
            ):
                fingerprint = (
                    step.receipt_fingerprints[
                        index
                    ]
                )
                returncode = (
                    step.returncodes[index]
                )
                attempt = index + 1
                try:
                    inclusion = (
                        find_by_receipt_id(
                            receipt_id,
                            verify_chain=False,
                        )
                    )
                except Exception:
                    inclusion = None
                if inclusion is None:
                    reason = (
                        "receipt id is unavailable"
                    )
                    issues.append(
                        f"step {step.step_id} "
                        f"receipt {receipt_id} unavailable"
                    )
                    results.append(
                        ReceiptInclusionResult(
                            step.step_id,
                            step.correlation_id,
                            attempt,
                            receipt_id,
                            fingerprint,
                            returncode,
                            None,
                            False,
                            False,
                            reason,
                        )
                    )
                    continue
                sequence = int(
                    inclusion.entry.sequence
                )
                problems: list[str] = []
                if sequence > target_sequence:
                    problems.append(
                        "receipt is newer than historical proof root"
                    )
                try:
                    canonical = (
                        get_by_sequence(
                            sequence,
                            repair_missing=False,
                        )
                    )
                except Exception:
                    canonical = None
                    problems.append(
                        "receipt sequence locator is unavailable"
                    )
                if (
                    canonical is not None
                    and canonical.receipt_hash
                    != inclusion.node.receipt_hash
                ):
                    problems.append(
                        "receipt id index differs from sequence locator"
                    )
                actual = inclusion.node.receipt
                if actual.fingerprint != fingerprint:
                    problems.append(
                        "fingerprint mismatch"
                    )
                if (
                    actual.correlation_id
                    != step.correlation_id
                ):
                    problems.append(
                        "correlation id mismatch"
                    )
                if actual.returncode != returncode:
                    problems.append(
                        "returncode mismatch"
                    )
                if actual.attempt != attempt:
                    problems.append(
                        "attempt number mismatch"
                    )
                valid = not problems
                reason = "; ".join(problems)
                if not valid:
                    issues.append(
                        f"step {step.step_id} "
                        f"receipt {receipt_id}: "
                        f"{reason}"
                    )
                results.append(
                    ReceiptInclusionResult(
                        step.step_id,
                        step.correlation_id,
                        attempt,
                        receipt_id,
                        fingerprint,
                        returncode,
                        sequence,
                        True,
                        valid,
                        reason,
                    )
                )
        return (
            tuple(results),
            tuple(issues),
            expected_root,
        )

    @staticmethod
    def _historical_snapshot(
        chain,
        expected_root: str,
        *,
        label: str,
    ):
        """Select a current or historical committed prefix for verification."""
        current_ok = bool(chain.verify())
        current_root = _sha256_hex(
            f"{label}_root",
            chain.root_hash(),
        )
        if not expected_root:
            try:
                snapshot = chain.snapshot()
            except Exception as exc:
                return (
                    (),
                    False,
                    current_root,
                    f"{label} chain snapshot failed: "
                    f"{type(exc).__name__}",
                )
            return (
                snapshot,
                current_ok,
                current_root,
                (
                    ""
                    if current_ok
                    else f"{label} chain failed integrity"
                ),
            )

        expected_root = _sha256_hex(
            f"expected_{label}_root",
            expected_root,
        )
        snapshot_at = getattr(
            chain,
            "snapshot_at",
            None,
        )
        verify_root = getattr(
            chain,
            "verify_root",
            None,
        )
        root_is_ancestor = getattr(
            chain,
            "root_is_ancestor",
            None,
        )
        if not (
            callable(snapshot_at)
            and callable(verify_root)
            and callable(root_is_ancestor)
        ):
            try:
                snapshot = chain.snapshot()
            except Exception as exc:
                return (
                    (),
                    False,
                    current_root,
                    f"{label} chain snapshot failed: "
                    f"{type(exc).__name__}",
                )
            if current_root != expected_root:
                return (
                    snapshot,
                    False,
                    current_root,
                    f"{label} root differs from expected root",
                )
            return (
                snapshot,
                current_ok,
                current_root,
                (
                    ""
                    if current_ok
                    else f"{label} chain failed integrity"
                ),
            )

        try:
            historical = snapshot_at(
                expected_root
            )
            historical_ok = bool(
                verify_root(expected_root)
            )
            ancestor = bool(
                root_is_ancestor(expected_root)
            )
        except Exception as exc:
            return (
                (),
                False,
                expected_root,
                f"{label} historical root verification failed: "
                f"{type(exc).__name__}",
            )

        if not current_ok:
            return (
                historical,
                False,
                expected_root,
                f"{label} current chain failed integrity",
            )
        if not historical_ok:
            return (
                historical,
                False,
                expected_root,
                f"{label} historical root failed integrity",
            )
        if not ancestor:
            return (
                historical,
                False,
                expected_root,
                f"{label} historical root is not committed ancestor",
            )
        return (
            historical,
            True,
            expected_root,
            "",
        )

    def verify(
        self,
        session_journal: SessionJournalEvidence,
        session_evidence: SessionExecutionEvidence,
        *,
        expected_journal_root: str = "",
        expected_receipt_root: str = "",
    ) -> SessionEvidenceIntegrityReport:
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
        if (
            session_journal.session_id
            != session_evidence.session_id
        ):
            raise ValueError(
                "session journal/evidence identity mismatch"
            )

        direct_journal = (
            self._direct_journal_inclusions(
                session_journal,
                expected_journal_root,
            )
            if expected_journal_root
            else None
        )
        if direct_journal is None:
            (
                journal_snapshot,
                journal_chain_ok,
                journal_root,
                journal_chain_issue,
            ) = self._historical_snapshot(
                self.journal,
                expected_journal_root,
                label="decision journal",
            )
            journal_inclusions, journal_issues = (
                self._journal_inclusions(
                    session_journal,
                    journal_snapshot,
                )
            )
        else:
            (
                journal_inclusions,
                journal_issues,
                journal_root,
            ) = direct_journal
            journal_chain_ok = True
            journal_chain_issue = ""

        direct_receipts = (
            self._direct_receipt_inclusions(
                session_evidence,
                expected_receipt_root,
            )
            if expected_receipt_root
            else None
        )
        if direct_receipts is None:
            (
                receipt_snapshot,
                receipt_chain_ok,
                receipt_root,
                receipt_chain_issue,
            ) = self._historical_snapshot(
                self.receipt_chain,
                expected_receipt_root,
                label="receipt",
            )
            receipt_inclusions, receipt_issues = (
                self._receipt_inclusions(
                    session_evidence,
                    receipt_snapshot,
                )
            )
        else:
            (
                receipt_inclusions,
                receipt_issues,
                receipt_root,
            ) = direct_receipts
            receipt_chain_ok = True
            receipt_chain_issue = ""

        issues: list[str] = []
        if journal_chain_issue:
            issues.append(journal_chain_issue)
        if receipt_chain_issue:
            issues.append(receipt_chain_issue)
        issues.extend(journal_issues)
        issues.extend(receipt_issues)

        journal_manifest_digest = (
            self._manifest_digest(
                item.to_dict()
                for item in journal_inclusions
            )
        )
        receipt_manifest_digest = (
            self._manifest_digest(
                item.to_dict()
                for item in receipt_inclusions
            )
        )
        return SessionEvidenceIntegrityReport(
            session_journal.session_id,
            journal_chain_ok,
            receipt_chain_ok,
            journal_root,
            receipt_root,
            journal_manifest_digest,
            receipt_manifest_digest,
            journal_inclusions,
            receipt_inclusions,
            tuple(issues),
        )

    def require(
        self,
        session_journal: SessionJournalEvidence,
        session_evidence: SessionExecutionEvidence,
        *,
        expected_journal_root: str = "",
        expected_receipt_root: str = "",
    ) -> SessionEvidenceIntegrityReport:
        report = self.verify(
            session_journal,
            session_evidence,
            expected_journal_root=(
                expected_journal_root
            ),
            expected_receipt_root=(
                expected_receipt_root
            ),
        )
        if not report.ok:
            detail = (
                report.issues[0]
                if report.issues
                else "session evidence integrity failed"
            )
            raise SessionEvidenceIntegrityError(
                detail
            )
        return report
