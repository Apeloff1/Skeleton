"""Prove SFT uses serving-framed prompts and response-only gradient targets."""
from __future__ import annotations
from .frames import FramedPair
from .token_windows import TargetWindow
from .canonical import digest
from .errors import reject


def prove(model,pair:FramedPair,windows:tuple[TargetWindow,...])->dict:
    if type(pair) is not FramedPair or not windows:
        reject("alignment-proof")
    prompt=tuple(model._ids(pair.prompt))
    completion=tuple(model._ids(pair.completion))
    if len(windows)!=len(completion):
        reject("alignment-target-count")
    if windows[0].context[-len(prompt):]!=prompt:
        reject("alignment-prompt-sequence")
    for index,item in enumerate(windows):
        if item.target!=completion[index] or item.ordinal!=index:
            reject("alignment-target-drift")
        if item.item_id!=pair.item_id:
            reject("alignment-source-drift")
    return {
        "source_id":pair.item_id,
        "prompt_tokens":len(prompt),"completion_tokens":len(completion),
        "supervised_targets":len(windows),
        "prompt_gradient_targets":0,
        "uses_native_chat_envelope":True,
        "context_digest":digest([x.record() for x in windows]),
    }
