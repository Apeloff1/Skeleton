"""Explicit registered model selection without provider fallback or trust escalation."""
from __future__ import annotations
from dataclasses import dataclass
from .graph import WorkflowError

@dataclass(frozen=True,slots=True)
class ModelCandidate:
    model_id:str
    model_sha:str
    tokenizer_sha:str
    context_tokens:int
    active:bool
    allows_private:bool
    cost_units:int


def select_model(candidates:tuple[ModelCandidate,...],*,minimum_tokens:int,
                 private:bool=True,preferred:str|None=None)->ModelCandidate:
    if type(minimum_tokens) is not int or minimum_tokens<1:raise WorkflowError('invalid model context target')
    options=[x for x in candidates if x.active and x.context_tokens>=minimum_tokens
             and (not private or x.allows_private)]
    if preferred:
        matched=[x for x in options if x.model_id==preferred]
        if len(matched)!=1:raise WorkflowError('requested model not explicitly admitted')
        return matched[0]
    if not options:raise WorkflowError('no approved local model; no remote fallback')
    options.sort(key=lambda x:(x.cost_units,-x.context_tokens,x.model_id))
    return options[0]
