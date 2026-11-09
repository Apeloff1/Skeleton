"""Opt-in native production vocabulary growth without replacing pretrained weights.

Only the offline cloned TinyTransformer may be mutated. The live Jeeves cortex,
its BPE merge table, historical token IDs, and any separately saved model are
unchanged. The training gate explicitly opts into vocabulary expansion.
Torch-stack vocabulary growth requires a separate implementation; fail closed.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any, Sequence

from .jeeves_production_game_train import ProductionCheckpointError

MAX_NEW_TOKENS = 512
MAX_TOTAL_TOKENS = 4096
SCALE = 0.01


def planned_new_pieces(model: Any, documents: Sequence[str]) -> tuple[str, ...]:
    """Return missing persisted-BPE pieces in deterministic first-seen order."""
    if not hasattr(model, "bpe") or not hasattr(model.bpe, "encode_pieces"):
        raise ProductionCheckpointError("persisted BPE is required for native vocabulary growth")
    if not hasattr(model, "stoi"):
        raise ProductionCheckpointError("unsupported vocabulary architecture")
    discovered: dict[str, None] = {}
    for document in documents:
        if not isinstance(document, str) or not document.strip():
            raise ProductionCheckpointError("vocabulary corpus must contain nonempty text")
        for piece in model.bpe.encode_pieces(document):
            if piece not in model.stoi:
                if not isinstance(piece, str) or not piece.strip():
                    # Blank pieces have semantic significance (word separator),
                    # so do not use strip for regular acceptance.
                    if not isinstance(piece, str) or not piece:
                        raise ProductionCheckpointError("invalid BPE piece")
                discovered[piece] = None
                if len(discovered) > MAX_NEW_TOKENS:
                    raise ProductionCheckpointError("game vocabulary needs more than 512 new pieces")
    return tuple(discovered)


def expand_native_game_pieces(
    model: Any, documents: Sequence[str],
    *, expected_snapshot_digest: str,
) -> dict[str, Any]:
    """Extend an in-memory CLONE's embedding and output matrices.

    Appends stable, deterministic small-initialized rows; no trained row is
    discarded, rewritten, or re-indexed by this operation.
    """
    from skeleton.cortex.transformer import TinyTransformer

    if not isinstance(model, TinyTransformer):
        raise ProductionCheckpointError("vocabulary growth supports native TinyTransformer only")
    if not isinstance(expected_snapshot_digest, str) or len(expected_snapshot_digest) != 64:
        raise ProductionCheckpointError("parent snapshot digest required for vocabulary seed")
    if getattr(model, "_accel", None) is not None:
        raise ProductionCheckpointError("offline vocabulary growth requires nonresident native model")
    original_count = len(model.itos)
    before_stoi = dict(model.stoi)
    old_embedding = tuple(tuple(row) for row in model.E)
    old_output = tuple(tuple(row) for row in model.Wout)
    old_bias = tuple(model.bout)
    if len(model.E) != original_count or len(model.Wout) != original_count:
        raise ProductionCheckpointError("native vocabulary dimensions inconsistent")
    if len(model.bout) != original_count:
        raise ProductionCheckpointError("native output bias dimension inconsistent")
    new_pieces = planned_new_pieces(model, documents)
    if original_count + len(new_pieces) > MAX_TOTAL_TOKENS:
        raise ProductionCheckpointError("expanded game vocabulary exceeds 4096-token budget")
    if not new_pieces:
        return {
            "new_tokens": 0, "old_vocabulary_size": original_count,
            "new_vocabulary_size": original_count,
            "new_pieces_digest": hashlib.sha256(b"[]").hexdigest(),
            "pretrained_rows_preserved": True,
        }
    rng = random.Random(int(expected_snapshot_digest[:16], 16))
    for piece in new_pieces:
        index = len(model.itos)
        model.itos.append(piece)
        model.stoi[piece] = index
        model.E.append([rng.uniform(-SCALE, SCALE) for _ in range(model.dim)])
        if not model.tied:
            model.Wout.append([rng.uniform(-SCALE, SCALE) for _ in range(model.dim)])
        model.bout.append(0.0)
    if model.tied:
        model.Wout = model.E
    if any(model.stoi[token] != index for token, index in before_stoi.items()):
        raise ProductionCheckpointError("vocabulary growth reindexed an existing token")
    if tuple(tuple(row) for row in model.E[:original_count]) != old_embedding:
        raise ProductionCheckpointError("vocabulary growth changed pretrained embeddings")
    if tuple(tuple(row) for row in model.Wout[:original_count]) != old_output:
        raise ProductionCheckpointError("vocabulary growth changed pretrained output weights")
    if tuple(model.bout[:original_count]) != old_bias:
        raise ProductionCheckpointError("vocabulary growth changed pretrained biases")
    if len(model.Wout) != len(model.E) or len(model.bout) != len(model.E):
        raise ProductionCheckpointError("grown native vocabulary has incompatible tensor dimensions")
    digest = hashlib.sha256(json.dumps(
        list(new_pieces), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return {
        "new_tokens": len(new_pieces),
        "old_vocabulary_size": original_count,
        "new_vocabulary_size": len(model.itos),
        "new_pieces_digest": digest,
        "pretrained_rows_preserved": True,
        "existing_token_ids_preserved": True,
        "production_parent_mutated": False,
    }


__all__ = ["expand_native_game_pieces", "planned_new_pieces"]
