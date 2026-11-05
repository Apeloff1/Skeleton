"""Actual held-out native inference against champion AND trained candidate."""
from __future__ import annotations
from dataclasses import dataclass

from .canonical import required_sha
from .checkpoint_store import read_verified
from .source import GenesisSource
from .errors import refuse
from ..native_candidate.validation import evaluate_model, ValidationReport
from ..native_candidate.candidate_comparison import compare, ModelComparison
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DualModelEvaluation:
    partition: str
    champion: ValidationReport
    candidate: ValidationReport
    comparison: ModelComparison
    source_sha256: str

    def report(self) -> dict:
        return {
            "schema": "skeleton.native-genesis.dual-evaluation.v1",
            "partition": self.partition,
            "source_sha256": self.source_sha256,
            "champion": self.champion.record(),
            "candidate": self.candidate.record(),
            "comparison": self.comparison.record(),
            "actual_native_evaluation": True,
            "independent_reviewer_signed": False,
            "automatic_promotion": False,
            "release_certified": False,
        }


def evaluate_pair(
    source: GenesisSource, *, champion_directory: Path,
    champion_checkpoint_sha256: str, champion_model_sha256: str,
    candidate_directory: Path, candidate_checkpoint_sha256: str,
    candidate_model_sha256: str, partition: str = "validation",
    max_new_tokens: int = 32,
) -> DualModelEvaluation:
    if type(source) is not GenesisSource or partition not in ("validation","holdout"):
        refuse("evaluation-source-or-partition")
    for name, value in (
        ("champion-checkpoint",champion_checkpoint_sha256),
        ("champion-model",champion_model_sha256),
        ("candidate-checkpoint",candidate_checkpoint_sha256),
        ("candidate-model",candidate_model_sha256),
    ):
        required_sha(value,name)
    if champion_model_sha256 == candidate_model_sha256:
        refuse("evaluation-no-weight-change")
    champion_bytes = read_verified(champion_directory,champion_checkpoint_sha256)
    candidate_bytes = read_verified(candidate_directory,candidate_checkpoint_sha256)
    ch = evaluate_model(
        champion_bytes,expected_model_sha256=champion_model_sha256,
        partitions=source.partitions,partition_name=partition,
        max_new_tokens=max_new_tokens,
    )
    ca = evaluate_model(
        candidate_bytes,expected_model_sha256=candidate_model_sha256,
        partitions=source.partitions,partition_name=partition,
        max_new_tokens=max_new_tokens,
    )
    if ch.source_partition_sha256 != source.partitions_sha256:
        refuse("evaluation-champion-source-mismatch")
    if ca.source_partition_sha256 != source.partitions_sha256:
        refuse("evaluation-candidate-source-mismatch")
    return DualModelEvaluation(partition,ch,ca,compare(ch,ca),source.source_sha256)
