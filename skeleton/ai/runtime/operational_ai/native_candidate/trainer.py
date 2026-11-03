"""Actual native TinyTransformer SGD over a cloned checkpoint, candidate-only.

The serving champion remains untouched; only the candidate clone is trained.
No weights are silently promoted or routed into the live serving process.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.training.flgb_training_runtime import (
    TrainingCheckpoint, CandidateWeights,
)
from .lineage import bind_lineage
from .preflight import admit
from .resource_preflight import estimate as estimate_resources
from .batch_receipt import BatchReceipt, verify_sequence
from .plan import TrainingPlan
from .strict import bytes_sha, digest, sha
from .errors import deny


@dataclass(frozen=True, slots=True)
class CandidateTrainingResult:
    candidate: CandidateWeights
    checkpoint_json: bytes
    checkpoint_record: TrainingCheckpoint
    initial_checkpoint_record: TrainingCheckpoint
    lineage: object
    admission: object
    elapsed_ms: int
    optimizer_steps: int
    batch_proof: dict
    resource_proof: dict
    champion_digest: str
    tokenizer_digest: str

    def public_record(self) -> dict:
        return {
            "schema": "skeleton.native-candidate.training-receipt.v1",
            "candidate_id": self.candidate.candidate_id,
            "candidate_digest": self.candidate.digest,
            "candidate_weights_digest": self.candidate.weights_digest,
            "candidate_checkpoint_sha256": bytes_sha(self.checkpoint_json),
            "checkpoint_bytes": len(self.checkpoint_json),
            "training_checkpoint_digest": self.checkpoint_record.digest,
            "initial_checkpoint_digest": self.initial_checkpoint_record.digest,
            "lineage": self.lineage.record(),
            "admission": self.admission.record(),
            "elapsed_ms": self.elapsed_ms,
            "optimizer_steps": self.optimizer_steps,
            "batch_proof": self.batch_proof,
            "resource_proof": self.resource_proof,
            "champion_digest": self.champion_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "output_kind": "candidate-only", "production_authorized": False,
            "real_gradient_executed": True, "release_certified": False,
        }


class CandidateTrainer:
    def __init__(self, champion: NativeLLMRuntime, plan: TrainingPlan,
                 *, trainer_code_digest: str):
        if type(champion) is not NativeLLMRuntime or type(plan) is not TrainingPlan:
            deny("trainer-native-contract")
        self.champion = champion
        self.plan = plan
        self.code_digest = sha(trainer_code_digest, "trainer-code")
        self._used = False

    def train(self) -> CandidateTrainingResult:
        if self._used:
            deny("trainer-single-use")
        self._used = True
        admission = admit(self.champion, self.plan)
        resource_proof = estimate_resources(self.champion, self.plan, admission)
        original = self.champion.model_digest
        snapshot = self.champion.checkpoint_json()
        # Restore is a deep model reconstruction; no gradient may mutate champion.
        candidate_runtime = NativeLLMRuntime.restore_json(snapshot)
        if candidate_runtime.model_digest != original:
            deny("candidate-clone-mismatch")
        lineage = bind_lineage(
            self.plan, admission.split, admission.rights,
            code_digest=self.code_digest,
            optimizer_steps=admission.tokens.optimizer_steps_estimate,
        )
        initial = TrainingCheckpoint(
            lineage.manifest.digest, 0, original,
            digest({"optimizer": "native-sgd", "steps": 0}),
            digest({"mode": "native-deterministic", "seed": 0}),
        )
        start = time.monotonic_ns()
        completed = 0
        batch_receipts = []
        try:
            lines = admission.workload.lines
            for offset in range(0, len(lines), self.plan.batch_lines):
                elapsed_ms = (time.monotonic_ns() - start) // 1000000
                if elapsed_ms >= self.plan.maximum_total_ms:
                    deny("training-wall-budget")
                batch = lines[offset:offset+self.plan.batch_lines]
                trained_steps = candidate_runtime.model.fit(
                    batch, lr=self.plan.learning_rate_ppm / 1000000,
                    schedule="cosine",
                )
                if type(trained_steps) is not int or trained_steps < 0:
                    deny("trainer-invalid-step-count")
                completed += trained_steps
                batch_receipts.append(BatchReceipt(
                    index=len(batch_receipts), first_line=offset, line_count=len(batch),
                    steps=trained_steps, cumulative_steps=completed,
                    elapsed_ms=(time.monotonic_ns()-start)//1000000,
                    source_sha256=digest(batch),
                ))
                if completed > self.plan.max_optimizer_steps:
                    deny("trainer-steps-overrun")
            if completed != admission.tokens.optimizer_steps_estimate:
                deny("trainer-step-mismatch")
            batch_proof = verify_sequence(tuple(batch_receipts), len(lines), completed)
            if (time.monotonic_ns() - start) // 1000000 > self.plan.maximum_total_ms:
                deny("training-wall-budget")
            trained = NativeLLMRuntime(candidate_runtime.model, limits=candidate_runtime.limits)
            if trained.model_digest == original:
                deny("trainer-unchanged-weights")
            self.champion.assert_model_unchanged()
            if self.champion.model_digest != original:
                deny("champion-mutated")
            encoded = trained.checkpoint_json().encode("utf-8")
            if len(encoded) > self.plan.maximum_checkpoint_bytes:
                deny("candidate-checkpoint-budget")
            if NativeLLMRuntime.restore_json(encoded.decode("utf-8")).model_digest != trained.model_digest:
                deny("candidate-restoration-mismatch")
            checkpoint = TrainingCheckpoint(
                lineage.manifest.digest, 1, trained.model_digest,
                digest({"optimizer": "native-sgd", "steps": completed,
                        "learning_rate_ppm": self.plan.learning_rate_ppm}),
                digest({"mode": "native-deterministic",
                        "batches": (len(lines) + self.plan.batch_lines - 1) // self.plan.batch_lines}),
                initial.digest,
            )
            candidate = CandidateWeights(
                candidate_id="original_" + self.plan.run_id,
                weights_digest=trained.model_digest,
                training_lineage_digest=checkpoint.digest,
                base_model_digest=original,
                status="candidate",
            )
            return CandidateTrainingResult(
                candidate, encoded, checkpoint, initial, lineage,
                admission, (time.monotonic_ns() - start) // 1000000,
                completed, batch_proof, resource_proof,
                original, trained.tokenizer.digest,
            )
        finally:
            # Model construction/gradient failures have no publication side effects.
            self.champion.assert_model_unchanged()
