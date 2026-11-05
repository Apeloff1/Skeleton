"""Aggregate measured native SGD facts; never synthesize absent measurements."""
from __future__ import annotations
from dataclasses import dataclass
from .trainer import SupervisedResult
from .errors import reject


@dataclass(frozen=True,slots=True)
class Metrics:
    gradients:int
    epochs_completed:int
    initial_validation_ppm:int
    final_validation_ppm:int
    validation_improvement_ppm:int
    training_elapsed_ms:int
    candidate_checkpoint_bytes:int
    candidate_sha256:str

    def record(self)->dict:
        return {
            "schema":"skeleton.native-supervised.training-metrics.v1",
            **{k:getattr(self,k) for k in self.__dataclass_fields__},
            "real_measured_gradient_steps":True,
            "model_performance_certified":False,
            "hardware_qualified":False,
        }


def from_result(result:SupervisedResult)->Metrics:
    if type(result) is not SupervisedResult:
        reject("training-metrics-result")
    if result.actual_optimizer_steps<=0 or result.elapsed_ms<0:
        reject("training-metrics-unfinished")
    return Metrics(
        result.actual_optimizer_steps,len(result.epoch_results),
        result.initial_validation_loss.loss_ppm,
        result.best_validation_loss.loss_ppm,
        result.quality.delta_ppm,result.elapsed_ms,
        len(result.candidate_checkpoint),result.candidate_checkpoint_sha256,
    )
