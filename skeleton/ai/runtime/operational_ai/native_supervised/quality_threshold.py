"""Candidate gate requires measured completion loss and no unverifiable boost."""
from __future__ import annotations
from dataclasses import dataclass
from .loss import MeasuredLoss
from .policy import SupervisedPolicy
from .errors import reject


@dataclass(frozen=True,slots=True)
class QualityDecision:
    initial_ppm:int
    candidate_ppm:int
    delta_ppm:int
    improved:bool
    within_ceiling:bool
    eligible_for_independent_probes:bool

    def report(self)->dict:
        return {
            **{key:getattr(self,key) for key in self.__dataclass_fields__},
            "actual_logits_measured":True,
            "heldout_accuracy_verified":False,
            "independent_authority_approved":False,
            "production_authorized":False,
        }


def judge(initial:MeasuredLoss,current:MeasuredLoss,policy:SupervisedPolicy)->QualityDecision:
    if type(initial) is not MeasuredLoss or type(current) is not MeasuredLoss:
        reject("quality-measurement-required")
    if type(policy) is not SupervisedPolicy or initial.targets!=current.targets:
        reject("quality-source-drift")
    if initial.windows_sha256!=current.windows_sha256:
        reject("quality-window-drift")
    delta=initial.loss_ppm-current.loss_ppm
    improved=delta>=policy.min_improvement_ppm and delta>0
    within=current.loss_ppm<=policy.max_validation_loss_ppm
    return QualityDecision(initial.loss_ppm,current.loss_ppm,
                           delta,improved,within,improved and within)
