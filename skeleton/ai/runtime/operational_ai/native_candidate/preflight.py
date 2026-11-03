"""Independent candidate-training admission before expensive native gradients."""
from __future__ import annotations
from dataclasses import dataclass

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .catalog import iter_examples, verify_exact
from .contamination import scan, require_clear_exact
from .dedup import require_unique
from .plan import TrainingPlan
from .rights import verify_rights
from .split_proof import verify as verify_splits
from .splits import partition
from .token_admission import inspect_lines
from .workload import build
from .errors import deny
from .semantic_oracle import verify as verify_source_truth


@dataclass(frozen=True, slots=True)
class TrainingAdmission:
    split: object
    rights: object
    workload: object
    tokens: object
    contamination: object
    unique: dict
    split_proof: dict

    def record(self) -> dict:
        return {
            "split": self.split.record(),
            "rights": self.rights.record(),
            "workload": self.workload.record(),
            "tokenizer": self.tokens.record(),
            "contamination": self.contamination.record(),
            "duplicates": self.unique,
            "split_proof": self.split_proof,
            "candidate_only": True, "rights_scope": "offline_native_candidate_training",
            "quality_qualified": False, "release_certified": False,
        }


def admit(champion: NativeLLMRuntime, plan: TrainingPlan) -> TrainingAdmission:
    if type(champion) is not NativeLLMRuntime:
        deny("native-champion-required")
    if type(plan) is not TrainingPlan:
        deny("training-plan")
    champion.assert_model_unchanged()
    if champion.model_digest != plan.expected_base_model_sha256:
        deny("champion-identity-drift")
    if champion.tokenizer.digest != plan.expected_tokenizer_sha256:
        deny("champion-tokenizer-drift")
    examples = tuple(iter_examples())
    if not verify_exact(examples):
        deny("source-catalog-mismatch")
    if not all(verify_source_truth(item) for item in examples):
        deny("original-source-answer-mismatch")
    unique = require_unique(examples)
    rights = verify_rights(examples)
    parts = partition(examples)
    split_proof = verify_splits(parts)
    contamination = scan(examples)
    require_clear_exact(contamination)
    workload = build(parts)
    if any(len(line.encode("utf-8")) > plan.max_line_bytes
           for line in workload.lines):
        deny("training-line-over-budget")
    token_proof = inspect_lines(champion.model, workload.lines,
                                maximum_steps=plan.max_optimizer_steps,
                                min_known_ppm=plan.min_known_token_fraction_ppm)
    return TrainingAdmission(parts, rights, workload, token_proof,
                             contamination, unique, split_proof)
