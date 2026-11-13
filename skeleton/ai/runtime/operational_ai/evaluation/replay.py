"""Observe deterministic replay without mutating the incumbent model."""
from __future__ import annotations
from ..authority.canonical import ContractViolation,digest
from ..authority.budgets import Limits
from ..model.gateway import ModelGateway


def compare(gateway:ModelGateway,messages:list[dict[str,str]],limits:Limits,
            *,seed:int=0)->dict:
    first=gateway.complete(messages,limits,seed=seed)
    second=gateway.complete(messages,limits,seed=seed)
    same=first.generation.output_digest==second.generation.output_digest
    return {"state":"replay-consistent" if same else "replay-drift",
            "model_digest":gateway.backend.model_digest,
            "tokenizer_digest":gateway.backend.tokenizer_digest,
            "first_output_sha256":first.generation.output_digest,
            "second_output_sha256":second.generation.output_digest,
            "seed":seed,"automated_promotion_authorized":False}
