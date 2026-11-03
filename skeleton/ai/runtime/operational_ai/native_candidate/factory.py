"""End-to-end native candidate factory from real model bytes to held candidate."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .candidate_receipt import CandidateReceipt
from .checkpoint_writer import publish
from .plan import TrainingPlan
from .preflight import admit, TrainingAdmission
from .trainer import CandidateTrainer
from .training_proof import inspect as inspect_training
from .process_fence import model_training_fence
from .strict import sha
from .errors import deny


@dataclass(frozen=True, slots=True)
class FactoryResult:
    candidate_receipt: CandidateReceipt
    publication: dict
    private_run_receipt: dict

    def public_record(self) -> dict:
        return {
            "schema": "skeleton.native-candidate.factory.v1",
            "candidate": self.candidate_receipt.record(),
            "publication": {
                "checkpoint_sha256": self.publication["checkpoint_sha256"],
                "bytes": self.publication["bytes"],
                "candidate_digest": self.publication["candidate_digest"],
                "kind": "candidate-only",
            },
            "candidate_only": True,
            "production_authorized": False,
            "quality_qualified": False,
            "release_certified": False,
        }


def qualify_preflight(champion: NativeLLMRuntime, plan: TrainingPlan) -> dict:
    proof = admit(champion, plan)
    return proof.record()


def train_native(
    champion: NativeLLMRuntime, plan: TrainingPlan,
    *, code_sha256: str, output_directory: Path, state_directory: Path,
) -> FactoryResult:
    sha(code_sha256, "code")
    if type(output_directory) is not Path or not output_directory.is_absolute():
        deny("output-root")
    if type(state_directory) is not Path or not state_directory.is_absolute():
        deny("state-root-required")
    with model_training_fence(state_directory, plan.expected_base_model_sha256):
        engine = CandidateTrainer(champion, plan, trainer_code_digest=code_sha256)
        result = engine.train()
        receipt = inspect_training(result, plan)
        publication = publish(result, output_directory)
    if publication["checkpoint_sha256"] != receipt.checkpoint_sha256:
        deny("publication-proof-mismatch")
    return FactoryResult(receipt, publication, result.public_record())
