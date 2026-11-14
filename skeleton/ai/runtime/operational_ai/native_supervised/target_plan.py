"""Build full immutable completion-only update plan before mutating model."""
from __future__ import annotations
from dataclasses import dataclass
from .frames import paired_train,FramedPair
from .token_windows import TargetWindow,construct
from .canonical import digest
from .bootstrap import AlignedGenesis
from .errors import reject


@dataclass(frozen=True,slots=True)
class TargetPlan:
    windows:tuple[TargetWindow,...]
    example_count:int
    steps_per_epoch:int
    epochs:int
    total_optimizer_steps:int
    plan_sha256:str

    def summary(self)->dict:
        return {
            "schema":"skeleton.native-supervised.target-plan.v1",
            "examples":self.example_count,"targets_per_epoch":self.steps_per_epoch,
            "epochs":self.epochs,"total_optimizer_steps":self.total_optimizer_steps,
            "plan_sha256":self.plan_sha256,
            "prompt_tokens_used_as_loss_targets":0,
            "validation_targets_used_as_gradients":0,
            "holdout_targets_used_as_gradients":0,
        }


def prepare_targets(instance:AlignedGenesis)->TargetPlan:
    if type(instance) is not AlignedGenesis:
        reject("target-genesis")
    model=instance.runtime.model
    pairs=paired_train(instance.source.groups)
    all_windows=[]
    for pair in pairs:
        windows=construct(model,pair,max_context=instance.policy.context)
        all_windows.extend(windows)
        if len(all_windows)>instance.policy.max_optimizer_steps:
            reject("target-optimizer-budget")
    if not all_windows:
        reject("target-empty")
    count=len(all_windows)*instance.policy.epochs
    if count>instance.policy.max_optimizer_steps:
        reject("target-epoch-step-budget")
    return TargetPlan(
        tuple(all_windows),len(pairs),len(all_windows),
        instance.policy.epochs,count,digest({
            "model":instance.runtime.model_digest,
            "source":instance.source.corpus_sha256,
            "frames":[p.record() for p in pairs],
            "targets":[w.record() for w in all_windows],
            "epochs":instance.policy.epochs,
        }),
    )
