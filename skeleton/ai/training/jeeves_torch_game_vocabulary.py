"""Opt-in Torch-stack vocabulary expansion on a cloned Jeeves speaking model.

Vocabulary growth preserves the trained token IDs, embedding rows, output
projection rows, positional embeddings and all TransformerEncoder layers.
Only newly introduced token rows are initialized. The zero-momentum SGD
optimizer is re-bound after parameter replacement so new rows learn.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Sequence

from .jeeves_production_game_train import ProductionCheckpointError

MAX_NEW_TOKENS = 1024
MAX_TOTAL_TOKENS = 8192
SCALE = 0.01


def planned_new_words(model: Any, documents: Sequence[str]) -> tuple[str, ...]:
    from skeleton.cortex.torch_lm import TorchTransformer
    from skeleton.cortex.port import tokens

    if not isinstance(model, TorchTransformer):
        raise ProductionCheckpointError("Torch vocabulary growth requires TorchTransformer")
    new: dict[str, None] = {}
    for text in documents:
        if not isinstance(text, str) or not text.strip():
            raise ProductionCheckpointError("game vocabulary examples must be nonempty strings")
        for word in tokens(text):
            if not word or not isinstance(word, str):
                raise ProductionCheckpointError("invalid game corpus token")
            if word not in model.stoi:
                new[word] = None
                if len(new) > MAX_NEW_TOKENS:
                    raise ProductionCheckpointError("Torch game vocabulary needs over 1024 new tokens")
    return tuple(new)


def expand_torch_game_words(
    model: Any, documents: Sequence[str], *,
    expected_snapshot_digest: str,
) -> dict[str, Any]:
    from skeleton.cortex.torch_lm import TorchTransformer

    if not isinstance(model, TorchTransformer):
        raise ProductionCheckpointError("Torch vocabulary expansion supports only TorchTransformer")
    if (not isinstance(expected_snapshot_digest, str) or
            len(expected_snapshot_digest) != 64 or
            any(c not in "0123456789abcdef" for c in expected_snapshot_digest)):
        raise ProductionCheckpointError("valid parent snapshot digest required for new token seed")
    added = planned_new_words(model, documents)
    original_vocab = len(model.itos)
    if original_vocab + len(added) > MAX_TOTAL_TOKENS:
        raise ProductionCheckpointError("Torch game vocabulary exceeds 8192 tokens")
    if not added:
        return {
            "new_tokens": 0, "old_vocabulary_size": original_vocab,
            "new_vocabulary_size": original_vocab,
            "existing_token_ids_preserved": True,
            "pretrained_rows_preserved": True,
        }
    torch = model.torch
    net = model.net
    old_e = net.E.weight.detach().clone()
    old_w = net.out.weight.detach().clone()
    old_b = net.out.bias.detach().clone()
    other_state = {
        key: value.detach().clone()
        for key, value in net.state_dict().items()
        if key not in ("E.weight", "out.weight", "out.bias")
    }
    if old_e.shape[0] != original_vocab or old_w.shape[0] != original_vocab or old_b.shape[0] != original_vocab:
        raise ProductionCheckpointError("Torch parent vocabulary and tensors disagree")
    dimension = old_e.shape[1]
    generator = torch.Generator(device="cpu")
    generator.manual_seed(int(expected_snapshot_digest[:16], 16))
    new_e = torch.nn.Embedding(original_vocab + len(added), dimension).to(model.device_obj)
    new_out = torch.nn.Linear(dimension, original_vocab + len(added)).to(model.device_obj)
    with torch.no_grad():
        new_e.weight[:original_vocab].copy_(old_e)
        new_out.weight[:original_vocab].copy_(old_w)
        new_out.bias[:original_vocab].copy_(old_b)
        generated_e = (
            torch.randn(len(added), dimension, generator=generator, dtype=old_e.dtype) * SCALE
        ).to(model.device_obj)
        generated_w = (
            torch.randn(len(added), dimension, generator=generator, dtype=old_w.dtype) * SCALE
        ).to(model.device_obj)
        new_e.weight[original_vocab:].copy_(generated_e)
        new_out.weight[original_vocab:].copy_(generated_w)
        new_out.bias[original_vocab:].zero_()

    net.E = new_e
    net.out = new_out
    for word in added:
        model.stoi[word] = len(model.itos)
        model.itos.append(word)
    model._opt = torch.optim.SGD(net.parameters(), lr=0.06)

    with torch.no_grad():
        if (not torch.equal(net.E.weight[:original_vocab], old_e)
                or not torch.equal(net.out.weight[:original_vocab], old_w)
                or not torch.equal(net.out.bias[:original_vocab], old_b)):
            raise ProductionCheckpointError("Torch vocabulary growth changed existing trained output rows")
        if any(not torch.equal(net.state_dict()[name], value)
               for name, value in other_state.items()):
            raise ProductionCheckpointError("Torch vocabulary growth modified pretrained attention layers")
    digest = hashlib.sha256(json.dumps(
        list(added), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return {
        "new_tokens": len(added),
        "old_vocabulary_size": original_vocab,
        "new_vocabulary_size": len(model.itos),
        "new_tokens_sha256": digest,
        "pretrained_rows_preserved": True,
        "existing_token_ids_preserved": True,
        "production_parent_mutated": False,
        "optimizer_rebound_to_expanded_rows": True,
    }


__all__ = ["planned_new_words", "expand_torch_game_words"]
