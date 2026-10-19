"""Source-bound 100-milestone assurance tracker with deterministic replay.

A milestone is a capability target, never an implicit completion claim.
Two independently identified host attestations and a matching source commit
are prerequisites for a recorded checkpoint. The tracker does not run CI or
prove that independently named attestations represent independent people.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .types import stable_fingerprint

_SHA1 = re.compile(r"^[a-f0-9]{40}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")

# Each acceptance target names an actual capability, not a synthetic pass.
_DOMAINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("context", (
        "scope-limited-negative-search", "pagination-and-partial-detection",
        "error-vs-absence-classification", "active-observation-integrity",
        "evidence-metadata-integrity", "goal-policy-preservation",
        "retained-note-continuity", "bounded-context-refill",
        "compaction-accounting", "context-page-replay",
    )),
    ("verifier", (
        "independent-integrity-review", "independent-scope-review",
        "mutated-goal-detection", "forged-result-detection",
        "forged-evidence-detection", "duplicate-source-detection",
        "scope-inflation-rejection", "global-absence-claim-rejection",
        "verifier-adversary", "verifier-checkpoint-replay",
    )),
    ("code", (
        "syntax-validation", "static-lint-review", "type-review",
        "import-resolution", "error-search-continuation",
        "authorized-repair", "post-repair-reverification",
        "modularity-review", "performance-evidence",
        "checker-evidence-independence",
    )),
    ("game", (
        "engine-integration", "source-and-asset-generation",
        "animation-state-integrity", "physics-consistency",
        "camera-and-frame-consistency", "controller-compatibility",
        "quest-and-state-continuity", "native-playthrough-evidence",
        "game-performance-evidence", "platform-export-evidence",
    )),
    ("measurement", (
        "baseline-source-identity", "equal-measurement-method",
        "measurement-unit-validation", "independent-sample-coverage",
        "finite-measurement-validation", "objective-thresholds",
        "regression-tolerances", "performance-variance-review",
        "comparative-scoring", "source-bound-measurement-replay",
    )),
    ("rights", (
        "complete-artifact-inventory", "canonical-paths",
        "original-work-provenance", "external-source-attribution",
        "licensed-material-conditions", "public-domain-evidence",
        "derivative-permission-review", "source-similarity-review",
        "unknown-rights-fail-closed", "copyright-scope-audit",
    )),
    ("creative", (
        "originality-review", "substantive-rewrite-review",
        "author-voice-continuity", "gdd-canon-integrity",
        "story-coherence", "character-arc-continuity",
        "dialogue-continuity", "narrative-and-mechanics-alignment",
        "independent-content-review", "copyright-before-rewrite-order",
    )),
    ("receipts", (
        "source-fingerprint", "working-context-serials",
        "scrutiny-pass-serials", "final-content-serials",
        "release-journal-serials", "append-only-hash-chain",
        "source-snapshot-continuity", "independent-replay",
        "tamper-mutation-probes", "content-free-audit-export",
    )),
    ("operations", (
        "durable-checkpoints", "exact-run-resume",
        "cancellation-handling", "crash-recovery",
        "bounded-budgets", "cross-run-isolation",
        "concurrency-leases", "idempotent-event-replay",
        "longform-runtime-tracing", "bounded-evidence-retention",
    )),
    ("release", (
        "exact-delivered-answer", "release-source-continuity",
        "required-criteria-enforcement", "independent-verdicts",
        "host-artifact-evidence", "exact-head-ci-checks",
        "first-install-evidence", "rollback-readiness",
        "merge-authorization", "production-release-admission",
    )),
)


class MilestoneEvidenceError(ValueError):
    """A milestone lacks valid evidence, sequence, or source continuity."""


@dataclass(frozen=True, slots=True)
class AssuranceMilestone:
    code: str
    domain: str
    capability: str
    prerequisite: str | None

    @property
    def title(self) -> str:
        return self.capability.replace("-", " ")


def _catalog() -> tuple[AssuranceMilestone, ...]:
    entries = []
    for domain_number, (domain, capabilities) in enumerate(_DOMAINS, 1):
        if len(capabilities) != 10 or len(set(capabilities)) != 10:
            raise MilestoneEvidenceError("every milestone domain must define 10 distinct capabilities")
        for rank, capability in enumerate(capabilities, 1):
            previous = f"M{(domain_number - 1) * 10 + rank - 1:03d}" if rank > 1 else None
            entries.append(AssuranceMilestone(
                code=f"M{(domain_number - 1) * 10 + rank:03d}",
                domain=domain, capability=capability,
                prerequisite=previous,
            ))
    return tuple(entries)


ASSURANCE_MILESTONES = _catalog()
MILESTONE_INDEX = {entry.code: entry for entry in ASSURANCE_MILESTONES}
assert len(ASSURANCE_MILESTONES) == len(MILESTONE_INDEX) == 100


@dataclass(frozen=True, slots=True)
class MilestoneAttestation:
    milestone_id: str
    source_commit: str
    artifact_digest: str
    scope: str
    primary_checker: str
    independent_checker: str
    primary_evidence: str
    independent_evidence: str
    verdict: str

    def __post_init__(self) -> None:
        if self.milestone_id not in MILESTONE_INDEX:
            raise MilestoneEvidenceError("unknown assurance milestone")
        if not isinstance(self.source_commit, str) or not _SHA1.fullmatch(self.source_commit):
            raise MilestoneEvidenceError("milestone evidence requires exact source commit")
        if not isinstance(self.artifact_digest, str) or not _SHA256.fullmatch(self.artifact_digest):
            raise MilestoneEvidenceError("milestone artifact requires a SHA-256 digest")
        if self.verdict not in {"pass", "blocked"}:
            raise MilestoneEvidenceError("milestone verdict must be pass or blocked")
        if not isinstance(self.scope, str) or not self.scope.strip() or len(self.scope) > 512:
            raise MilestoneEvidenceError("milestone scope must identify inspected evidence")
        if any(
            not isinstance(token, str) or not _TOKEN.fullmatch(token)
            for token in (self.primary_checker, self.independent_checker)
        ):
            raise MilestoneEvidenceError("milestone checker identity missing")
        if self.primary_checker == self.independent_checker:
            raise MilestoneEvidenceError("milestone checkers must have separate identities")
        if any(
            not isinstance(reference, str) or not reference.strip() or len(reference) > 4096
            for reference in (self.primary_evidence, self.independent_evidence)
        ) or self.primary_evidence == self.independent_evidence:
            raise MilestoneEvidenceError("independent scoped evidence references required")

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "milestone": self.milestone_id,
            "commit": self.source_commit,
            "artifact": self.artifact_digest,
            "scope": self.scope,
            "checkers": (self.primary_checker, self.independent_checker),
            "proofs": (self.primary_evidence, self.independent_evidence),
            "verdict": self.verdict,
        })


@dataclass(frozen=True, slots=True)
class MilestoneReceipt:
    sequence: int
    milestone_id: str
    attestation: MilestoneAttestation
    previous: str
    digest: str

    @classmethod
    def issue(
        cls, sequence: int, attestation: MilestoneAttestation, previous: str,
    ) -> "MilestoneReceipt":
        if type(sequence) is not int or sequence <= 0:
            raise MilestoneEvidenceError("invalid milestone sequence")
        if not _SHA256.fullmatch(previous):
            raise MilestoneEvidenceError("invalid previous milestone receipt")
        digest = stable_fingerprint({
            "sequence": sequence,
            "milestone": attestation.milestone_id,
            "attestation": attestation.fingerprint,
            "previous": previous,
        })
        return cls(sequence, attestation.milestone_id, attestation, previous, digest)


@dataclass(frozen=True, slots=True)
class MilestoneBoard:
    source_commit: str
    receipts: tuple[MilestoneReceipt, ...] = ()

    @classmethod
    def begin(cls, source_commit: str) -> "MilestoneBoard":
        if not isinstance(source_commit, str) or not _SHA1.fullmatch(source_commit):
            raise MilestoneEvidenceError("pin exact source commit before tracking")
        return cls(source_commit)

    @property
    def passing(self) -> frozenset[str]:
        return frozenset(
            receipt.milestone_id
            for receipt in self.receipts if receipt.attestation.verdict == "pass"
        )

    @property
    def blocked(self) -> frozenset[str]:
        return frozenset(
            receipt.milestone_id
            for receipt in self.receipts if receipt.attestation.verdict == "blocked"
        )

    @property
    def target_count(self) -> int:
        return len(ASSURANCE_MILESTONES)

    @property
    def completion_count(self) -> int:
        return len(self.passing)

    @property
    def completion_percent(self) -> float:
        return self.completion_count / self.target_count * 100

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "commit": self.source_commit,
            "receipts": [receipt.digest for receipt in self.receipts],
        })

    def register(self, attestation: MilestoneAttestation) -> "MilestoneBoard":
        verify_milestone_board(self)
        if not isinstance(attestation, MilestoneAttestation):
            raise MilestoneEvidenceError("milestone requires typed independent attestation")
        if attestation.source_commit != self.source_commit:
            raise MilestoneEvidenceError("milestone evidence belongs to another commit")
        existing = next(
            (item for item in self.receipts
             if item.milestone_id == attestation.milestone_id), None,
        )
        if existing is not None:
            if existing.attestation == attestation:
                return self  # Idempotent replay: no second receipt.
            raise MilestoneEvidenceError("milestone changed after its evidence checkpoint")
        prerequisite = MILESTONE_INDEX[attestation.milestone_id].prerequisite
        if (attestation.verdict == "pass" and prerequisite is not None
                and prerequisite not in self.passing):
            raise MilestoneEvidenceError("milestone prerequisite not verified")
        previous = self.receipts[-1].digest if self.receipts else "0" * 64
        added = MilestoneReceipt.issue(
            len(self.receipts) + 1, attestation, previous,
        )
        return MilestoneBoard(self.source_commit, self.receipts + (added,))

    def summary(self) -> dict[str, object]:
        """No stage is inferred complete from plan text or existence of code."""
        verify_milestone_board(self)
        return {
            "commit": self.source_commit,
            "target": self.target_count,
            "passed": self.completion_count,
            "blocked": len(self.blocked),
            "unverified": self.target_count - len(self.passing | self.blocked),
            "completion_percent": self.completion_percent,
            "receipt": self.fingerprint,
        }


def verify_milestone_board(board: MilestoneBoard) -> None:
    if not isinstance(board.source_commit, str) or not _SHA1.fullmatch(board.source_commit):
        raise MilestoneEvidenceError("milestone board lost source commit")
    previous = "0" * 64
    recorded: set[str] = set()
    passing: set[str] = set()
    for sequence, receipt in enumerate(board.receipts, 1):
        attestation = receipt.attestation
        if not isinstance(attestation, MilestoneAttestation):
            raise MilestoneEvidenceError("untyped milestone approval")
        attestation.__post_init__()  # Recheck unsafe replace() mutations.
        if (receipt.milestone_id in recorded
                or receipt.milestone_id != attestation.milestone_id):
            raise MilestoneEvidenceError("duplicate or relabeled milestone")
        if attestation.source_commit != board.source_commit:
            raise MilestoneEvidenceError("milestone attestation uses stale source")
        prerequisite = MILESTONE_INDEX[receipt.milestone_id].prerequisite
        if (attestation.verdict == "pass" and prerequisite is not None
                and prerequisite not in passing):
            raise MilestoneEvidenceError("unmet milestone prerequisite")
        expected = MilestoneReceipt.issue(sequence, attestation, previous)
        if receipt != expected:
            raise MilestoneEvidenceError("milestone receipt chain was modified")
        previous = receipt.digest
        recorded.add(receipt.milestone_id)
        if attestation.verdict == "pass":
            passing.add(receipt.milestone_id)


def restore_milestone_board(
    source_commit: str, receipts: Sequence[MilestoneReceipt],
) -> MilestoneBoard:
    """Replay a stored board without automatically trusting its pass claims."""
    board = MilestoneBoard(source_commit, tuple(receipts))
    verify_milestone_board(board)
    return board


def milestone_by_id(milestone_id: str) -> AssuranceMilestone:
    try:
        return MILESTONE_INDEX[milestone_id]
    except (KeyError, TypeError) as exc:
        raise MilestoneEvidenceError("unknown assurance milestone") from exc
