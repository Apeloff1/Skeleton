"""Real completion-token cross-entropy from CPU native transformer logits."""
from __future__ import annotations
import math
from dataclasses import dataclass
from .token_windows import TargetWindow
from .canonical import digest,require_int
from .errors import reject


@dataclass(frozen=True,slots=True)
class MeasuredLoss:
    targets:int
    total_nats:float
    mean_nats:float
    loss_ppm:int
    perplexity:float
    windows_sha256:str

    def report(self)->dict:
        return {
            "schema":"skeleton.native-supervised.measured-loss.v1",
            "targets":self.targets,"total_nats":self.total_nats,
            "mean_nats":self.mean_nats,"loss_ppm":self.loss_ppm,
            "perplexity":self.perplexity,
            "windows_sha256":self.windows_sha256,
            "uses_actual_logits":True,"completion_only":True,
            "inference_quality_verified":False,
        }


def _target_nll(logits:list[float],target:int)->float:
    if type(logits) not in (tuple,list) or len(logits)<2:
        reject("loss-logits")
    if type(target) is not int or not 0<=target<len(logits):
        reject("loss-target-index")
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in logits):
        reject("loss-nonfinite-logits")
    highest=max(logits)
    exp_sum=sum(math.exp(value-highest) for value in logits)
    result=highest+math.log(exp_sum)-logits[target]
    if not math.isfinite(result) or result<0:
        reject("loss-invalid-nats")
    return max(0.0,result)


def measure_windows(model,windows:tuple[TargetWindow,...],*,max_targets:int=100000)->MeasuredLoss:
    require_int(max_targets,"loss-budget",1,1000000)
    if type(windows) is not tuple or not windows or len(windows)>max_targets:
        reject("loss-window-budget")
    if getattr(model,"_accel",None) is not None or getattr(model,"resident",False):
        reject("loss-cpu-only")
    total=0.0
    for item in windows:
        if type(item) is not TargetWindow:
            reject("loss-source-windows")
        logits=model._logits(list(item.context))
        total+=_target_nll(logits,item.target)
        if not math.isfinite(total):
            reject("loss-overflow")
    mean=total/len(windows)
    ppl=math.exp(min(700.0,mean))
    if not math.isfinite(ppl):
        reject("loss-perplexity")
    return MeasuredLoss(
        len(windows),total,mean,int(round(mean*1000000)),ppl,
        digest([item.record() for item in windows]),
    )
