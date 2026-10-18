"""Fine-tune inference and the local transformer on the focused game corpus.

Legal, coding, proofreading, syntax, errors, crash, and lint lessons are
weighted above the rest. The byte network continues from its saved weights.
The transformer is a separate candidate. Neither one promotes a serving
checkpoint, and holdout lines are not training text.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from skeleton.cortex.port import tokens as word_tokens
from skeleton.cortex.transformer import TinyTransformer

from skeleton.ai.runtime.inference.game_adaptive_ratchet import train_budget
from skeleton.ai.runtime.inference.game_corpus_stream import (
    TRACKS,
    CorpusStream,
    focus_weights,
    holdout_documents,
    track_holdouts,
)

SCHEMA = "skeleton.game_focus_finetune.v1"
FOCUS_BYTES = 8 * 1024 * 1024


def _mean_logprob(model: TinyTransformer, texts: list[str]) -> float:
    if not texts:
        raise ValueError("logprob texts are empty")
    return sum(model.logprob(text) for text in texts) / len(texts)


def finetune_transformer(
    *,
    max_documents: int = 36,
    learning_rate: float = 0.02,
    checkpoint_dir: Path | str = Path(".skeleton/game-focus-finetune"),
) -> dict[str, Any]:
    """Fit a small local transformer on fresh focus lines and keep it only if holdout logprob rises."""
    if isinstance(max_documents, bool) or not isinstance(max_documents, int) or max_documents < 2:
        raise ValueError("max_documents must be an int >= 2")
    if not isinstance(learning_rate, (int, float)) or isinstance(learning_rate, bool) or not 0.0 < float(learning_rate) <= 1.0:
        raise ValueError("learning_rate must be in (0, 1]")
    root = Path(checkpoint_dir)
    root.mkdir(parents=True, exist_ok=True)
    stream = CorpusStream(weights=focus_weights())
    reserved = set(holdout_documents())
    documents: list[str] = []
    seen: set[str] = set()
    while len(documents) < max_documents:
        _domain, text = stream.next_document()
        if text in reserved or text in seen:
            continue
        seen.add(text)
        documents.append(text)
    held = [text for rows in track_holdouts().values() for text in rows]
    vocab = sorted({token for text in documents for token in word_tokens(text)})
    model = TinyTransformer(vocab=vocab, dim=8, ctx=8, seed=11, n_layers=1, d_ff=0)
    before = _mean_logprob(model, held)
    if not math.isfinite(before):
        raise RuntimeError("transformer holdout logprob is not finite")
    steps = model.fit(documents, lr=float(learning_rate), schedule="cosine")
    after = _mean_logprob(model, held)
    if not math.isfinite(after):
        raise RuntimeError("transformer holdout logprob is not finite")
    kept = after > before
    snapshot_path = root / "transformer.json"
    if kept:
        tmp = snapshot_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(model.snapshot(), separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, snapshot_path)
    receipt = {
        "schema": SCHEMA,
        "kind": "transformer",
        "documents": len(documents),
        "steps": steps,
        "learning_rate": float(learning_rate),
        "holdout_logprob_before": before,
        "holdout_logprob_after": after,
        "kept": kept,
        "promotion": False,
        "service_checkpoint_touched": False,
        "byte_loss_is_gameplay_quality": False,
        "review_domains": list(TRACKS["review"]),
    }
    (root / "transformer-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def finetune_inference(
    *,
    additional_bytes: int = FOCUS_BYTES,
    peak_lr: float = 3e-5,
    chunk_docs: int = 24,
    slack: float = 2e-4,
    checkpoint_dir: Path | str = Path(".skeleton/game-corpus-199"),
    ledger_path: Path | str | None = Path("skeleton/ai/runtime/inference/game_corpus_cycles.json"),
    log: Any = None,
) -> dict[str, Any]:
    """Continue the saved byte network with legal, coding, and review lessons weighted up."""
    return train_budget(
        additional_bytes=additional_bytes,
        peak_lr=peak_lr,
        chunk_docs=chunk_docs,
        min_scale=1.0,
        slack=slack,
        stream_weights=focus_weights(),
        checkpoint_dir=checkpoint_dir,
        ledger_path=ledger_path,
        log=log,
    )


def main() -> None:
    import sys

    transformer = finetune_transformer()
    inference = finetune_inference(log=sys.stdout)
    print(json.dumps({"transformer": transformer, "inference": inference}, indent=2), flush=True)


if __name__ == "__main__":
    main()
