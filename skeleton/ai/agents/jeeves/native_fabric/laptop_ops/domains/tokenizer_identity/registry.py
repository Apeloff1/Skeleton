"""Tokenization and model-source identity coherence before native operation."""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    installed_tokenizer,
    model_pairing,
    tokenizer_config,
    vocabulary_size,
    special_tokens,
    source_revision,
    tokenizer_owner,
    last_inspection,
)
DOMAIN = "tokenizer_identity"
STAGES = ("installed_tokenizer", "model_pairing", "tokenizer_config", "vocabulary_size", "special_tokens", "source_revision", "tokenizer_owner", "last_inspection",)
STAGE_TYPES = (("installed_tokenizer", "sha_equal"), ("model_pairing", "sha_equal"), ("tokenizer_config", "sha_equal"), ("vocabulary_size", "bounded"), ("special_tokens", "true"), ("source_revision", "monotonic"), ("tokenizer_owner", "same_owner"), ("last_inspection", "fresh"),)
HANDLERS = (installed_tokenizer, model_pairing, tokenizer_config, vocabulary_size, special_tokens, source_revision, tokenizer_owner, last_inspection,)

def evaluate(evidence: object):
    """Reject every omitted stage and mismatched tokenizer/model source digest."""
    if type(evidence) is not dict or set(evidence) != set(STAGES):
        raise LaptopGateHold("missing or extra tokenizer source safeguard")
    stages = tuple(module.check(evidence[stage])
                   for stage, module in zip(STAGES, HANDLERS))
    if len(stages) != 8:
        raise LaptopGateHold("tokenizer source registry incomplete")
    if all(item.accepted for item in stages) and evidence["installed_tokenizer"]["observed_sha256"] != evidence["model_pairing"]["observed_sha256"]:
        raise LaptopGateHold("tokenizer and installed model pairing disagree")
    return stages

def contracts() -> tuple[dict[str, object], ...]:
    return tuple(module.contract() for module in HANDLERS)
