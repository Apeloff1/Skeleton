"""Check that no supervised target belonged to validation or holdout."""
from __future__ import annotations
from .target_plan import TargetPlan
from .source import SourceScope
from .errors import reject
from .canonical import digest


def prove(plan:TargetPlan,source:SourceScope)->dict:
    if type(plan) is not TargetPlan or type(source) is not SourceScope:
        reject("train-separation-contract")
    train={case.item_id for case in source.groups.train}
    validation={case.item_id for case in source.groups.validation}
    holdout={case.item_id for case in source.groups.holdout}
    if len(train)!=432 or len(validation)!=72 or len(holdout)!=72:
        reject("train-separation-count")
    if train&validation or train&holdout or validation&holdout:
        reject("train-separation-overlap")
    ids={case.item_id for case in plan.windows}
    if ids!=train:
        reject("train-plan-examples-drift")
    if len(plan.windows)!=plan.steps_per_epoch or plan.example_count!=432:
        reject("train-plan-steps")
    return {
        "train_cases":len(train),"validation_cases":len(validation),
        "holdout_cases":len(holdout),"supervised_windows":len(plan.windows),
        "source_scope_sha256":digest({"train":sorted(train),
                                      "validation":sorted(validation),
                                      "holdout":sorted(holdout)}),
        "train_only_gradient_targets":True,
        "holdout_gradient_targets":0,
    }
