"""Real CPU SGD updates on completion tokens only, with strict step receipts."""
from __future__ import annotations
from dataclasses import dataclass
from time import monotonic_ns
import math
from .token_windows import TargetWindow
from .canonical import digest,require_int
from .errors import reject
from .lr_schedule import learning_rate


@dataclass(frozen=True,slots=True)
class OptimizerReceipt:
    epoch:int
    batches:int
    steps:int
    elapsed_ms:int
    first_target_sha256:str
    last_target_sha256:str
    weights_changed:bool

    def record(self)->dict:
        return {key:getattr(self,key) for key in self.__dataclass_fields__}


def execute_epoch(
    model, windows:tuple[TargetWindow,...], *,
    epoch:int, total_epochs:int, global_step_start:int,
    total_steps:int, learning_rate_ppm:int, max_wall_ms:int,
    start_monotonic_ns:int, batch_size:int,
)->OptimizerReceipt:
    for name,value,low,high in (
        ("epoch",epoch,0,12),("epoch-count",total_epochs,1,12),
        ("global-step",global_step_start,0,1000000),
        ("total-steps",total_steps,1,1000000),
        ("wall-budget",max_wall_ms,1,36000000),
        ("batch",batch_size,1,64),
    ):
        require_int(value,name,low,high)
    if type(windows) is not tuple or not windows:
        reject("optimizer-empty-windows")
    if getattr(model,"resident",False) or getattr(model,"_accel",None) is not None:
        reject("optimizer-cpu-only")
    if not hasattr(model,"_sgd") or not hasattr(model,"steps"):
        reject("optimizer-native-model")
    if global_step_start+len(windows)>total_steps:
        reject("optimizer-step-bounds")
    before=model.steps
    checkpoint_first=digest(windows[0].record())
    checkpoint_last=digest(windows[-1].record())
    count=0
    for offset in range(0,len(windows),batch_size):
        elapsed=(monotonic_ns()-start_monotonic_ns)//1000000
        if elapsed>=max_wall_ms:
            reject("optimizer-wall-budget")
        for item in windows[offset:offset+batch_size]:
            rate=learning_rate(
                global_step_start+count,total_steps,learning_rate_ppm,
                floor_ppm=max(1,learning_rate_ppm//20),
            )
            loss=model._sgd(list(item.context),item.target,rate)
            if type(loss) not in (int,float) or not math.isfinite(loss):
                reject("optimizer-invalid-loss")
            count+=1
        if model.steps!=before+count:
            reject("optimizer-native-step-drift")
    return OptimizerReceipt(
        epoch,(len(windows)+batch_size-1)//batch_size,count,
        (monotonic_ns()-start_monotonic_ns)//1000000,
        checkpoint_first,checkpoint_last,model.steps>before,
    )
