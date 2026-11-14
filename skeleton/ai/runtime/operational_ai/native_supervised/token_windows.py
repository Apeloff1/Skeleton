"""Native completion-only SFT windows: no prompt-target gradient leakage."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.cortex.port import tokens
from .frames import FramedPair
from .canonical import digest,require_int
from .errors import reject


@dataclass(frozen=True,slots=True)
class TargetWindow:
    context:tuple[int,...]
    target:int
    item_id:str
    ordinal:int

    def record(self)->dict:
        return {
            "item_id":self.item_id,"ordinal":self.ordinal,
            "context_sha256":digest(self.context),
            "target":self.target,
        }


def construct(model, pair:FramedPair,*,max_context:int)->tuple[TargetWindow,...]:
    if type(pair) is not FramedPair:
        reject("window-pair-required")
    require_int(max_context,"window-context",32,4096)
    if not hasattr(model,"_ids") or not hasattr(model,"ctx") or not hasattr(model,"itos"):
        reject("window-real-native-model")
    if max_context>model.ctx:
        reject("window-context-greater-than-model")
    if not pair.completion.strip():
        reject("completion-empty")
    prompt_ids=tuple(model._ids(pair.prompt))
    target_ids=tuple(model._ids(pair.completion))
    if not prompt_ids or not target_ids:
        reject("window-empty-token")
    if len(prompt_ids)>max_context:
        reject("prompt-context-exceeds-claimed-budget")
    if any(type(t) is not int or not 0<=t<len(model.itos)
           for t in prompt_ids+target_ids):
        reject("token-outside-vocabulary")
    prefix=list(prompt_ids)
    windows=[]
    for ordinal,target in enumerate(target_ids):
        window=tuple(prefix[-max_context:])
        if not window:
            reject("target-without-context")
        windows.append(TargetWindow(window,target,pair.item_id,ordinal))
        prefix.append(target)
    if len(windows)!=len(target_ids):
        reject("target-window-loss")
    return tuple(windows)


def count_windows(windows:tuple[TargetWindow,...])->int:
    if type(windows) is not tuple or not windows:
        reject("training-window-list")
    if len(windows)>100000:
        reject("training-target-ceiling")
    return len(windows)
