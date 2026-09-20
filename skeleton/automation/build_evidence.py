"""Immutable evidence objects for autonomous feature builds."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping

from .build_contracts import ArchitecturePlan, BuildBudget, BuildCandidate, BuildReview, CandidateFile
from .supervisor_runtime import canonical_json


@dataclass(frozen=True, slots=True)
class BuildPhaseEvidence:
    phase: str
    sequence: int
    input_fingerprint: str
    output_fingerprint: str
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "sequence": self.sequence,
            "input_fingerprint": self.input_fingerprint,
            "output_fingerprint": self.output_fingerprint,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class BuildEvidence:
    task_digest: str
    repository_head: str
    repository_index_fingerprint: str
    budget_fingerprint: str
    session_fingerprint: str
    architecture_fingerprint: str
    candidate_fingerprint: str
    file_manifest_fingerprint: str
    model_calls: int
    rounds: int
    phase_evidence: tuple[BuildPhaseEvidence, ...]
    review_count: int
    required_findings_remaining: int

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(canonical_json(self.as_dict())).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "task_digest": self.task_digest,
            "repository_head": self.repository_head,
            "repository_index_fingerprint": self.repository_index_fingerprint,
            "budget_fingerprint": self.budget_fingerprint,
            "session_fingerprint": self.session_fingerprint,
            "architecture_fingerprint": self.architecture_fingerprint,
            "candidate_fingerprint": self.candidate_fingerprint,
            "file_manifest_fingerprint": self.file_manifest_fingerprint,
            "model_calls": self.model_calls,
            "rounds": self.rounds,
            "phase_evidence": [item.as_dict() for item in self.phase_evidence],
            "review_count": self.review_count,
            "required_findings_remaining": self.required_findings_remaining,
        }

    def to_json(self) -> str:
        return json.dumps(
            {**self.as_dict(), "fingerprint": self.fingerprint},
            sort_keys=True,
            separators=(",", ":"),
        )


def fingerprint_files(files: Iterable[CandidateFile]) -> str:
    manifest = [
        item.as_dict(include_content=False)
        for item in sorted(files, key=lambda value: value.path)
    ]
    return hashlib.sha256(canonical_json(manifest)).hexdigest()


def fingerprint_mapping(value: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def phase_evidence(
    phase: str,
    sequence: int,
    *,
    input_value: Mapping[str, object],
    output_value: Mapping[str, object],
    notes: Iterable[str] = (),
) -> BuildPhaseEvidence:
    return BuildPhaseEvidence(
        phase=phase,
        sequence=sequence,
        input_fingerprint=fingerprint_mapping(input_value),
        output_fingerprint=fingerprint_mapping(output_value),
        notes=tuple(notes),
    )


def assemble_evidence(
    *,
    task_digest: str,
    repository_head: str,
    repository_index_fingerprint: str,
    budget: BuildBudget,
    session_fingerprint: str,
    architecture: ArchitecturePlan,
    candidate: BuildCandidate,
    phases: Iterable[BuildPhaseEvidence],
) -> BuildEvidence:
    reviews: tuple[BuildReview, ...] = candidate.reviews
    remaining = len(reviews[-1].required_findings) if reviews else 0
    return BuildEvidence(
        task_digest=task_digest,
        repository_head=repository_head,
        repository_index_fingerprint=repository_index_fingerprint,
        budget_fingerprint=budget.fingerprint,
        session_fingerprint=session_fingerprint,
        architecture_fingerprint=architecture.fingerprint,
        candidate_fingerprint=candidate.fingerprint,
        file_manifest_fingerprint=fingerprint_files(candidate.files),
        model_calls=candidate.model_calls,
        rounds=candidate.rounds,
        phase_evidence=tuple(phases),
        review_count=len(reviews),
        required_findings_remaining=remaining,
    )
