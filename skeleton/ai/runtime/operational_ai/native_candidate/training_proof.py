"""Match real training outputs against source plan, native model and lineage."""
from __future__ import annotations
from .candidate_receipt import CandidateReceipt
from .plan import TrainingPlan
from .trainer import CandidateTrainingResult
from .strict import bytes_sha
from .errors import deny


def inspect(result: CandidateTrainingResult, plan: TrainingPlan) -> CandidateReceipt:
    if type(result) is not CandidateTrainingResult or type(plan) is not TrainingPlan:
        deny("training-proof-types")
    if not result.candidate.production_authorized() is False:
        deny("candidate-serving-authorization")
    if result.candidate.status != "candidate":
        deny("candidate-status")
    if result.champion_digest != plan.expected_base_model_sha256:
        deny("candidate-champion")
    if result.optimizer_steps <= 0 or result.optimizer_steps > plan.max_optimizer_steps:
        deny("candidate-optimizer-budget")
    if result.lineage.manifest.config_digest != plan.digest:
        deny("candidate-plan-drift")
    if result.lineage.manifest.output_kind != "candidate-only":
        deny("candidate-promotion-attempt")
    return CandidateReceipt(
        plan.run_id, bytes_sha(result.checkpoint_json),
        result.candidate.weights_digest, result.lineage.manifest.digest,
        result.lineage.rights.rights_digest,
        result.lineage.rights.source_hash, result.lineage.partition_digest,
        result.optimizer_steps,
    )
