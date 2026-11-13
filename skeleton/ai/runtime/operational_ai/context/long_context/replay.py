"""Fence replay against old policy/model and mismatched projections."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import ContextError

@dataclass(frozen=True,slots=True)
class ReplayFence:
    session_id:str
    model_digest:str
    tokenizer_digest:str
    policy_version:int
    projection_digest:str

    def agrees(self,current:'ReplayFence')->bool:
        return self==current


def require_replay(prior:ReplayFence,current:ReplayFence)->None:
    if not prior.agrees(current):
        raise ContextError('stale replay changes context, policy or model identity')
