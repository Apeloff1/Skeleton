"""Validation and holdout target windows use same chat-framing, never SGD."""
from __future__ import annotations
from dataclasses import dataclass
from .frames import frame
from .token_windows import construct,TargetWindow
from .source import SourceScope
from .canonical import digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class HeldoutWindows:
    partition:str
    windows:tuple[TargetWindow,...]
    cases:int
    partition_sha256:str

    def report(self)->dict:
        return {
            "partition":self.partition,
            "cases":self.cases,"target_tokens":len(self.windows),
            "partition_sha256":self.partition_sha256,
            "optimizer_updates":0,
        }


def build(model,source:SourceScope,*,partition:str)->HeldoutWindows:
    if type(source) is not SourceScope:
        reject("heldout-source")
    if partition not in ("validation","holdout"):
        reject("heldout-train-forbidden")
    data=getattr(source.groups,partition)
    if len(data)!=72:
        reject("heldout-partition-incomplete")
    windows=[]
    for example in data:
        pair=frame(example)
        windows.extend(construct(model,pair,max_context=model.ctx))
    if not windows or len(windows)>100000:
        reject("heldout-target-count")
    return HeldoutWindows(partition,tuple(windows),len(data),
                          digest({"source":source.partition_sha256,
                                  "split":partition,
                                  "ids":[x.item_id for x in data]}))
