"""Fixed, original-only source fence without external training data or leakage."""
from __future__ import annotations
from dataclasses import dataclass
from .errors import refuse
from ..native_candidate.catalog import iter_examples, verify_exact, DOMAINS
from ..native_candidate.dedup import require_unique
from ..native_candidate.rights import verify_rights
from ..native_candidate.splits import partition
from ..native_candidate.split_proof import verify as verify_splits
from ..native_candidate.semantic_oracle import verify as verify_answer
from ..native_candidate.contamination import scan as benchmark_scan
from ..native_candidate.workload import build as training_lines


@dataclass(frozen=True, slots=True)
class GenesisSource:
    partitions: object
    training_lines: tuple[str, ...]
    source_sha256: str
    partitions_sha256: str
    rights_sha256: str
    curriculum_sha256: str
    benchmark_overlap_clear: bool
    original_answers_valid: bool

    def report(self) -> dict:
        return {
            "schema": "skeleton.native-genesis.source.v1",
            "source_sha256": self.source_sha256,
            "partitions_sha256": self.partitions_sha256,
            "rights_sha256": self.rights_sha256,
            "curriculum_sha256": self.curriculum_sha256,
            "training_lines": len(self.training_lines),
            "validation_examples": len(self.partitions.validation),
            "holdout_examples": len(self.partitions.holdout),
            "source_domains": len(DOMAINS),
            "benchmark_overlap_clear": self.benchmark_overlap_clear,
            "original_answers_valid": self.original_answers_valid,
            "near_duplicate_review_complete": False,
            "has_trained_weights": False,
            "release_qualified": False,
        }


def verify_source() -> GenesisSource:
    records = tuple(iter_examples())
    if not verify_exact(records) or len(records) != 576:
        refuse("source-inventory-incomplete")
    require_unique(records)
    rights = verify_rights(records)
    if rights.allowed_scope != "offline_native_candidate_training":
        refuse("rights-purpose")
    if not all(verify_answer(item) for item in records):
        refuse("original-answer-mismatch")
    parts = partition(records)
    verify_splits(parts)
    contamination = benchmark_scan(records)
    if not contamination.exact_clear:
        refuse("benchmark-contaminated-source")
    lines = training_lines(parts)
    if len(lines.lines) != 432:
        refuse("training-source-count")
    return GenesisSource(
        parts, lines.lines, rights.source_hash, parts.digest, rights.rights_digest,
        lines.curriculum_sha256, True, True,
    )
