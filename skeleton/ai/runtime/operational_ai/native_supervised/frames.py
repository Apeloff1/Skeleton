"""Train and serve on *identical* actual ChatTranscript prompt envelopes.

The previous generic LM corpus used 'Instruction/Response' whereas
NativeChatEngine uses role/byte-length framing. This module eliminates the
train/serve format mismatch; only completion tokens receive gradients.
"""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.ai.model_runtime.chat_protocol import ChatTranscript,ChatMessage
from ..native_candidate.records import TrainingExample
from .canonical import digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class FramedPair:
    item_id:str
    domain:str
    prompt:str
    completion:str
    prompt_sha256:str
    completion_sha256:str

    def record(self)->dict:
        return {
            "item_id":self.item_id,"domain":self.domain,
            "prompt_sha256":self.prompt_sha256,
            "completion_sha256":self.completion_sha256,
        }


def frame(example:TrainingExample)->FramedPair:
    if type(example) is not TrainingExample:
        reject("frame-source-record")
    raw=ChatTranscript((ChatMessage("user",example.prompt),)).format_prompt()
    independently=ChatTranscript.parse([
        {"role":"user","content":example.prompt},
    ]).format_prompt()
    if raw!=independently or not raw.endswith("[message role=assistant name= bytes=?]\n"):
        reject("chat-framing-drift")
    if "\x00" in raw or len(raw.encode("utf-8"))>8192:
        reject("chat-frame-budget")
    return FramedPair(
        example.item_id,example.domain,raw,example.completion,
        digest({"prompt":raw}),digest({"completion":example.completion}),
    )


def paired_train(groups)->tuple[FramedPair,...]:
    from ..native_candidate.splits import Partition
    if type(groups) is not Partition or len(groups.train)!=432:
        reject("train-only-partition")
    from ..native_candidate.curriculum import interleave
    pairs=tuple(frame(item) for item in interleave(groups.train))
    if len(pairs)!=432 or len({p.item_id for p in pairs})!=432:
        reject("train-pairs-incomplete")
    held={item.item_id for item in groups.validation+groups.holdout}
    if any(item.item_id in held for item in pairs):
        reject("heldout-leakage")
    return pairs
