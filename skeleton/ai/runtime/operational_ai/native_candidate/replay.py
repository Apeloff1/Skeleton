"""Deterministic reconstruction proof of candidate training plan and source."""
from __future__ import annotations
from .catalog import iter_examples, verify_exact
from .rights import verify_rights
from .splits import partition
from .plan import TrainingPlan
from .errors import deny


def verify_replay(plan: TrainingPlan, previous: dict) -> dict:
    if type(plan) is not TrainingPlan or type(previous) is not dict:
        deny("replay-contract")
    examples = tuple(iter_examples())
    if not verify_exact(examples):
        deny("replay-source")
    rights = verify_rights(examples)
    split = partition(examples)
    if previous.get("plan_sha256") != plan.digest:
        deny("replay-plan-drift")
    if previous.get("source_sha256") != rights.source_hash:
        deny("replay-source-drift")
    if previous.get("partition_sha256") != split.digest:
        deny("replay-partition-drift")
    return {
        "plan_sha256": plan.digest,
        "source_sha256": rights.source_hash,
        "partition_sha256": split.digest,
        "source_replay_verified": True,
        "gradient_replay_verified": False,
        "release_certified": False,
    }
