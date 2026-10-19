"""Deterministic, fail-closed evidence journal for Jeeves delivery.

This module seals *existing* host attestations and checks their relationship.
It does not replace real checkers, execute code, grant rights, or claim that a
performance, copyright, or independent review happened without its evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .adversarial_verifier_review import AdversarialVerifierReviewer
from .code_delivery_quality import (
    QualityReleaseReceipt, QualityVerifierAdversary,
    required_checker_names, verify_quality_receipt,
)
from .final_delivery_reviews import (
    FinalReleaseReview, FinalReviewAdversary, required_final_kind,
    verify_final_release, quality_source_continuity_failure,
)
from .types import Goal, ToolObservation, stable_fingerprint
from .working_context_cycle import PreparedDelivery, verify_delivery


ANSWER_PATH = "delivery/jeeves_final_answer.md"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_STAGES_CONTEXT = (
    "context", "integrity", "scope", "verifier_adversary",
)
_STAGES_QUALITY = ("quality", "quality_adversary")
_STAGES_FINAL = (
    "comparative", "objective", "copyright", "creative_rewrite",
    "final_adversary",
)
_STAGES_HANDOFF = ("release",)
_ALLOWED_KINDS = {"code", "game", "creative", "non_code"}


class EvidenceJournalError(ValueError):
    """The given release evidence is incomplete, stale, or inconsistent."""


def _require_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise EvidenceJournalError(f"{name} requires a 64-digit SHA-256 fingerprint")
    return value


def _serial(number: int) -> str:
    if type(number) is not int or not 1 <= number <= 999_999_999:
        raise EvidenceJournalError("journal page counter out of supported range")
    digits = ""
    n = number
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    while n:
        n, rem = divmod(n, 36)
        digits = alphabet[rem] + digits
    return f"JEL-{digits.rjust(6, '0')}-P{number:09d}"


@dataclass(frozen=True, slots=True)
class EvidenceJournalEntry:
    sequence: int
    serial: str
    stage: str
    subject_digest: str
    evidence_ref: str
    previous_digest: str
    digest: str

    @classmethod
    def create(
        cls, sequence: int, stage: str, subject_digest: str,
        evidence_ref: str, previous_digest: str,
    ) -> "EvidenceJournalEntry":
        if not isinstance(stage, str) or not re.fullmatch(r"[a-z][a-z_]{2,40}", stage):
            raise EvidenceJournalError("invalid release evidence stage")
        _require_digest(subject_digest, "stage subject")
        _require_digest(previous_digest, "previous stage")
        if not isinstance(evidence_ref, str) or not evidence_ref.strip() or len(evidence_ref) > 4096:
            raise EvidenceJournalError("release stage requires a bounded evidence reference")
        serial = _serial(sequence)
        digest = stable_fingerprint({
            "sequence": sequence, "serial": serial, "stage": stage,
            "subject": subject_digest, "evidence": evidence_ref,
            "previous": previous_digest,
        })
        return cls(
            sequence, serial, stage, subject_digest,
            evidence_ref, previous_digest, digest,
        )


@dataclass(frozen=True, slots=True)
class ReleaseEvidenceJournal:
    run_id: str
    kind: str
    goal_digest: str
    answer_digest: str
    source_digest: str | None
    stages: tuple[EvidenceJournalEntry, ...]
    release_digest: str

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "run": self.run_id, "kind": self.kind,
            "goal": self.goal_digest, "answer": self.answer_digest,
            "source": self.source_digest,
            "stages": [stage.digest for stage in self.stages],
            "release": self.release_digest,
        })

    @property
    def milestone_count(self) -> int:
        return len(self.stages)

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(stage.stage for stage in self.stages)

    def exported_receipts(self) -> tuple[dict[str, object], ...]:
        """Content-free records suitable for a run log or host checkpoint."""
        return tuple({
            "sequence": entry.sequence,
            "serial": entry.serial,
            "stage": entry.stage,
            "subject_digest": entry.subject_digest,
            "evidence_ref": entry.evidence_ref,
            "previous_digest": entry.previous_digest,
            "digest": entry.digest,
        } for entry in self.stages)


def _expected_stages(kind: str) -> tuple[str, ...]:
    if kind not in _ALLOWED_KINDS:
        raise EvidenceJournalError("unsupported release kind")
    return (
        _STAGES_CONTEXT
        + (_STAGES_QUALITY if kind in {"code", "game"} else ())
        + (_STAGES_FINAL if kind in {"code", "game", "creative"} else ())
        + _STAGES_HANDOFF
    )


def verify_journal_chain(journal: ReleaseEvidenceJournal) -> None:
    """Verify serials, stage order, links and final content-free handoff."""
    if not isinstance(journal.run_id, str) or not journal.run_id.strip():
        raise EvidenceJournalError("missing release run identity")
    expected = _expected_stages(journal.kind)
    if journal.stage_names != expected:
        raise EvidenceJournalError("release stage ordering or coverage was altered")
    _require_digest(journal.goal_digest, "pinned user goal")
    _require_digest(journal.answer_digest, "exact final answer")
    if journal.kind in {"code", "game", "creative"}:
        _require_digest(journal.source_digest, "final reviewed sources")
    elif journal.source_digest is not None:
        raise EvidenceJournalError("unsupported unreviewed source digest")
    previous = "0" * 64
    for number, entry in enumerate(journal.stages, 1):
        expected_entry = EvidenceJournalEntry.create(
            number, expected[number - 1], entry.subject_digest,
            entry.evidence_ref, previous,
        )
        if entry != expected_entry:
            raise EvidenceJournalError("stage was reordered, forged or detached")
        previous = entry.digest
    if journal.release_digest != stable_fingerprint({
        "run": journal.run_id, "kind": journal.kind,
        "goal": journal.goal_digest, "answer": journal.answer_digest,
        "source": journal.source_digest, "last": previous,
    }):
        raise EvidenceJournalError("journal final handoff digest differs from its chain")


def _quality_extras(goal: Goal, quality: QualityReleaseReceipt) -> tuple[str, ...]:
    core = required_checker_names(quality.kind)
    extras = tuple(name for name in quality.standards if name not in core)
    requested = goal.metadata.get("additional_quality_requirements", ())
    if not isinstance(requested, (list, tuple)) or any(
        not isinstance(item, str) for item in requested
    ):
        raise EvidenceJournalError("invalid user quality requirements")
    if not set(requested).issubset(set(extras)):
        raise EvidenceJournalError("quality receipt omitted a user-mandated checker")
    return extras


def build_release_evidence_journal(
    run_id: str,
    goal: Goal,
    observations: Sequence[ToolObservation],
    prepared: PreparedDelivery,
    answer: str,
    *,
    quality: QualityReleaseReceipt | None = None,
    final: FinalReleaseReview | None = None,
    final_sources: Mapping[str, str] | None = None,
) -> ReleaseEvidenceJournal:
    """Recheck and seal a whole run against its exact authoritative evidence.

    No caller can supply a pre-approved pass token. The two original context
    verifiers, adversarial reviewer, quality verifier/adversary, copyright and
    creative reviewers, and final-review adversary are all checked again. This
    is an audit of attestations, not a substitute for the underlying host work.
    """
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", run_id):
        raise EvidenceJournalError("invalid run identifier")
    if not isinstance(answer, str):
        raise EvidenceJournalError("final answer must be actual text")
    required = required_final_kind(goal)
    kind = required or "non_code"
    if required in {"code", "game"} and quality is None:
        raise EvidenceJournalError("code/game delivery has no source quality receipt")
    if required in {"code", "game", "creative"} and final is None:
        raise EvidenceJournalError("authored work requires final copyright/rewrite receipt")
    if required is None and (quality is not None or final is not None):
        raise EvidenceJournalError("unrequested review domain cannot authorize delivery")

    v1, v2 = verify_delivery(prepared, goal, observations, answer=answer)
    reviewed_adversarial = AdversarialVerifierReviewer().review(
        prepared, goal, observations, answer=answer,
    )
    if not reviewed_adversarial.passed:
        raise EvidenceJournalError("independent context adversary did not pass")

    records: list[tuple[str, str, str]] = [
        ("context", prepared.fingerprint, "host:working-context-cycle"),
        ("integrity", v1, "host:integrity-verifier"),
        ("scope", v2, "host:scope-verifier"),
        ("verifier_adversary", reviewed_adversarial.digest,
         "host:adversarial-verifier-review"),
    ]
    audited_sources: dict[str, str] = {}
    quality_digest: str | None = None
    if quality is not None:
        if quality.kind != kind or not quality.releasable:
            raise EvidenceJournalError("quality receipt is blocked or has wrong domain")
        audited_sources = dict(quality.scrutiny.files)
        extras = _quality_extras(goal, quality)
        verify_quality_receipt(
            quality, files=audited_sources, kind=kind, required=extras,
        )
        quality_adversary = QualityVerifierAdversary().review(
            quality, files=audited_sources, kind=kind, required=extras,
        )
        quality_digest = quality.digest
        records.extend((
            ("quality", quality.digest, "host:source-quality-review"),
            ("quality_adversary", quality_adversary,
             "host:quality-verifier-adversary"),
        ))

    source_digest = None
    if final is not None:
        if final.kind != kind or not final.passed:
            raise EvidenceJournalError("final rights/creative review was blocked")
        if final_sources is None or ANSWER_PATH not in final_sources:
            raise EvidenceJournalError("final source inventory omitted exact answer")
        sources = dict(final_sources)
        if sources[ANSWER_PATH] != answer:
            raise EvidenceJournalError("final review did not inspect exact answer bytes")
        if quality is not None:
            continuity_error = quality_source_continuity_failure(
                sources, audited_sources, audited_sources,
            )
            if continuity_error:
                raise EvidenceJournalError(continuity_error)
        verify_final_release(
            final, sources, upstream_quality_digest=quality_digest,
        )
        final_adversary = FinalReviewAdversary.challenge(
            final, sources, upstream_quality_digest=quality_digest,
        )
        source_digest = final.source_digest
        comparative = stable_fingerprint([
            measurement.fingerprint for measurement in final.measurements
        ])
        objective = stable_fingerprint({
            "passing": [m.axis for m in final.measurements if m.objective_ok],
            "thresholds": [m.target_evidence for m in final.measurements],
        })
        records.extend((
            ("comparative", comparative, "host:measured-comparison"),
            ("objective", objective, "host:measured-quality-objectives"),
            ("copyright", final.copyright.fingerprint,
             final.copyright.evidence_ref),
            ("creative_rewrite", final.creative_rewrite.fingerprint,
             final.creative_rewrite.evidence_ref),
            ("final_adversary", final_adversary,
             "host:final-review-adversary"),
        ))
    records.append((
        "release", stable_fingerprint({
            "goal": prepared.goal_digest,
            "answer": stable_fingerprint(answer),
            "quality": quality_digest,
            "final": final.fingerprint if final else None,
        }), "host:release-handoff",
    ))
    if tuple(stage for stage, _, _ in records) != _expected_stages(kind):
        raise EvidenceJournalError("release stages were omitted or reordered")
    previous = "0" * 64
    entries = []
    for index, (stage, subject, evidence) in enumerate(records, 1):
        entry = EvidenceJournalEntry.create(
            index, stage, _require_digest(subject, stage), evidence, previous,
        )
        entries.append(entry)
        previous = entry.digest
    goal_digest = prepared.goal_digest
    answer_digest = stable_fingerprint(answer)
    release_digest = stable_fingerprint({
        "run": run_id, "kind": kind, "goal": goal_digest,
        "answer": answer_digest, "source": source_digest, "last": previous,
    })
    journal = ReleaseEvidenceJournal(
        run_id, kind, goal_digest, answer_digest, source_digest,
        tuple(entries), release_digest,
    )
    verify_journal_chain(journal)
    return journal


def verify_release_evidence_journal(
    journal: ReleaseEvidenceJournal,
    goal: Goal,
    observations: Sequence[ToolObservation],
    prepared: PreparedDelivery,
    answer: str,
    *,
    quality: QualityReleaseReceipt | None = None,
    final: FinalReleaseReview | None = None,
    final_sources: Mapping[str, str] | None = None,
) -> None:
    """Replay the full assurance process before trusting a restored checkpoint."""
    verify_journal_chain(journal)
    rebuilt = build_release_evidence_journal(
        journal.run_id, goal, observations, prepared, answer,
        quality=quality, final=final, final_sources=final_sources,
    )
    if journal != rebuilt:
        raise EvidenceJournalError("restored journal does not match live reviewed evidence")
