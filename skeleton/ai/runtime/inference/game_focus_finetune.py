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

import torch

from skeleton.cortex.port import tokens as word_tokens
from skeleton.cortex.transformer import TinyTransformer

from skeleton.ai.runtime.inference.game_adaptive_ratchet import (
    ByteRNN,
    _pin,
    expand_byte_rnn,
    network_digest,
    train_budget,
)
from skeleton.ai.runtime.inference.game_corpus_stream import (
    TRACKS,
    CorpusStream,
    focus_weights,
    holdout_documents,
    track_holdouts,
)

SCHEMA = "skeleton.game_focus_finetune.v1"
ENTERPRISE_SCHEMA = "skeleton.game_finetune_enterprise.v1"
FOCUS_BYTES = 8 * 1024 * 1024
HALF_BYTES = 32 * 1024 * 1024
# Official NumpyRecurrentLM reload after the focus fine-tune. Half targets are these values / 2.
OFFICIAL_FOCUS_BASELINE = {
    "visual": 1.5055037017735209,
    "narrative": 1.4767407712552283,
    "systems": 1.51098586405026,
    "review": 1.5594443256757207,
    "practice": 1.5272560882968464,
}
ROLLBACK_DIGEST = "0e45ff72aaea58646e918e9a0442c3df30ee6912a060a663674c463531c1da75"

# Fourteen implementation levels. This record standardizes the fine-tune.
# It does not mark the repository enterprise-qualified.
_LEVELS = {
    "L00": "inference package owns the byte network and the local transformer candidate",
    "L01": "no new runtime root; NumpyRecurrentLM and TinyTransformer stay the owners",
    "L02": "half targets are half the measured baseline; holdout text is not a training target",
    "L03": "promotion stays false; a serving checkpoint is not replaced",
    "L04": "AdamW fine-tune from the saved weights; the gradient uses shared template bytes",
    "L05": "weights stay under the gitignored checkpoint directory",
    "L06": "original lessons only; no personal data and no commercial game text",
    "L07": "a rejected or non-finite step restores the weights",
    "L08": "official track losses, digest, accepts, and rejects are on the receipt",
    "L09": "byte budget, learning rate, hidden size, and seconds are recorded",
    "L10": "official NumpyRecurrentLM reload is the acceptance measurement",
    "L11": "rollback digest is the pre-finetune network; use it when the half is not met",
    "L12": "PAUSE saves and waits; a reject plateau keeps the best weights",
    "L13": "not an enterprise-qualified volume; the half target is explicit and unmet until measured",
}


def half_targets(baseline: dict[str, float]) -> dict[str, float]:
    if not baseline:
        raise ValueError("baseline tracks are empty")
    targets = {}
    for name, value in baseline.items():
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0:
            raise ValueError(f"baseline {name} is not a positive finite loss")
        targets[str(name)] = numeric / 2.0
    return targets


def enterprise_record(
    *,
    baseline: dict[str, float],
    official: dict[str, float],
    rollback_digest: str,
) -> dict[str, Any]:
    targets = half_targets(baseline)
    missing = set(targets) - set(official)
    if missing:
        raise ValueError(f"official tracks missing {sorted(missing)}")
    met = {name: float(official[name]) <= targets[name] for name in targets}
    return {
        "schema": ENTERPRISE_SCHEMA,
        "standardized": True,
        "enterprise_qualified": False,
        "owner": "skeleton.ai.runtime.inference",
        "runtime_root_added": False,
        "levels": dict(_LEVELS),
        "half_targets": targets,
        "half_met": met,
        "half_met_all": all(met.values()),
        "rollback_digest": rollback_digest,
        "rollback_trigger": "keep the rollback network when any track is above its half target",
        "promotion": False,
    }


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


def seed_expanded_checkpoint(
    source: Path | str,
    dest: Path | str,
    *,
    hidden: int,
) -> dict[str, Any]:
    """Write a widened copy of a saved network. The source checkpoint is the rollback.

    A destination that already has trained bytes is left in place so a restarted
    fine-tune continues instead of wiping the widened weights.
    """
    root = Path(dest)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "checkpoint.pt"
    if path.exists():
        existing = torch.load(path, map_location="cpu", weights_only=False)
        if int(existing.get("hidden", -1)) == hidden and int(existing.get("bytes_done", 0)) > 0:
            status_path = root / "status.json"
            cycle_complete = False
            if status_path.exists():
                status = json.loads(status_path.read_text(encoding="utf-8"))
                cycle_complete = isinstance(status, dict) and status.get("state") == "complete"
            return {
                "hidden": hidden,
                "bytes_done": int(existing["bytes_done"]),
                "goal": existing.get("goal"),
                "checkpoint": str(path),
                "seeded": False,
                "cycle_complete": cycle_complete,
            }
    loaded = torch.load(source, map_location="cpu", weights_only=False)
    current = int(loaded["hidden"])
    model = ByteRNN(current)
    model.load_state_dict(loaded["best_state"])
    _pin(model)
    wider = expand_byte_rnn(model, hidden)
    records = loaded.get("sam_records")
    ema = loaded.get("domain_ema")
    domain_ema = {}
    if isinstance(ema, dict):
        for name, value in ema.items():
            numeric = float(value)
            if math.isfinite(numeric):
                domain_ema[str(name)] = numeric
    payload = {
        "model": wider.state_dict(),
        "best_state": {key: value.detach().cpu().clone() for key, value in wider.state_dict().items()},
        "hidden": wider.hidden,
        "bytes_done": 0,
        "ratchet": {},
        "replay": [],
        "domain_ema": domain_ema,
        "sam_records": list(records) if isinstance(records, list) else [],
        "rollback_source": str(source),
    }
    tmp = path.with_suffix(".tmp")
    torch.save(payload, tmp)
    os.replace(tmp, path)
    return {"hidden": wider.hidden, "bytes_done": 0, "checkpoint": str(path), "seeded": True}


def _source_digest(source: Path | str) -> str:
    loaded = torch.load(source, map_location="cpu", weights_only=False)
    model = ByteRNN(int(loaded["hidden"]))
    model.load_state_dict(loaded["best_state"])
    _pin(model)
    return network_digest(model)


def finetune_toward_half(
    *,
    source: Path | str = Path(".skeleton/game-corpus-199/checkpoint.pt"),
    checkpoint_dir: Path | str = Path(".skeleton/game-corpus-half"),
    hidden: int = 256,
    budget_bytes: int = HALF_BYTES,
    peak_lr: float = 3e-5,
    baseline: dict[str, float] | None = None,
    rollback_digest: str,
    log: Any = None,
) -> dict[str, Any]:
    """Fine-tune a widened copy until the budget, the half targets, or a reject plateau."""
    if not isinstance(rollback_digest, str) or len(rollback_digest) < 16:
        raise ValueError("rollback_digest is required")
    if _source_digest(source) != rollback_digest:
        raise ValueError("source checkpoint does not match the rollback digest")
    if baseline is None:
        baseline = dict(OFFICIAL_FOCUS_BASELINE)
    seeded = seed_expanded_checkpoint(source, checkpoint_dir, hidden=hidden)
    targets = half_targets(baseline)
    train_kwargs: dict[str, Any] = {
        "peak_lr": peak_lr,
        "checkpoint_dir": checkpoint_dir,
        "hidden": hidden,
        "chunk_docs": 24,
        "min_scale": 1.0,
        "slack": 2e-4,
        "margin_cap": 1e-5,
        "stream_weights": focus_weights(),
        "continuation": True,
        "plateau_rejects": 256,
        "log_bytes": 1024 * 1024,
        "score_ceiling": targets,
        "loss_focus": "skeleton",
        "ledger_path": Path("skeleton/ai/runtime/inference/game_corpus_cycles.json"),
        "log": log,
    }
    saved_goal = seeded.get("goal")
    unfinished = (
        isinstance(saved_goal, int)
        and not isinstance(saved_goal, bool)
        and int(seeded["bytes_done"]) < saved_goal
        and not seeded.get("cycle_complete")
    )
    if seeded.get("seeded", True) or not unfinished:
        if seeded.get("seeded", True):
            train_kwargs["budget_bytes"] = budget_bytes
        else:
            train_kwargs["additional_bytes"] = budget_bytes
    else:
        train_kwargs["budget_bytes"] = saved_goal
    receipt = train_budget(**train_kwargs)
    receipt["enterprise"] = enterprise_record(
        baseline=baseline,
        official=receipt["official_tracks"],
        rollback_digest=rollback_digest,
    )
    root = Path(checkpoint_dir)
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    ledger = Path("skeleton/ai/runtime/inference/game_corpus_cycles.json")
    if ledger.exists():
        rows = json.loads(ledger.read_text(encoding="utf-8"))
        if isinstance(rows, list) and rows and rows[-1].get("model_digest") == receipt["model_digest"]:
            rows[-1]["enterprise"] = receipt["enterprise"]
            tmp = ledger.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, ledger)
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
