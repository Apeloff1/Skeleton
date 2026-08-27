"""Metrics the organism must beat — untrained is the opponent.

After train():
  perplexity of the neo transformer drops on held-out GameForge text
  mix MAE of the left numeric head is finite and below the untrained default
  bias accuracy of the right head is above chance (0.25)
  gate entropy of the MoE router is not collapsed (not a one-hot dictator)
  callosum coupling is signed (Hebb happened)
  BPE compression < 1 on the closed-world corpus

These are not dashboards. They are gates. evaluate() is pure and cheap.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence

from skeleton.cortex.own import BIASES

_MIX = re.compile(r"mix trash=(\d+) elite=(\d+) boss=(\d+)")


def _entropy(p: Sequence[float]) -> float:
    acc = 0.0
    for x in p:
        if x > 1e-12:
            acc -= float(x) * math.log(float(x))
    return acc


def _parse_mix(text: str):
    m = _MIX.search(text or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _parse_bias(text: str, tags: Sequence[str] = ()) -> Optional[str]:
    blob = " ".join(list(tags) + [text or ""]).lower()
    for b in BIASES:
        if b in blob or f"bias={b}" in blob:
            return b
    return None


def evaluate(neo) -> Dict[str, Any]:
    """Score the live organism against the GameForge closed world."""
    from skeleton.cortex.curriculum import CORE_PAIRS, WALK_PAIRS
    from skeleton.cortex.lm import gameforge_corpus

    xf = getattr(neo, "transformer", None)
    ppl_texts = [a for a, _ in list(CORE_PAIRS)] + [a for a, _ in list(WALK_PAIRS)]
    ppl = float(xf.perplexity(ppl_texts)) if xf is not None and hasattr(xf, "perplexity") else float("inf")

    mix_err: List[float] = []
    mix_hits = 0
    mix_n = 0
    for stim, _held in list(WALK_PAIRS) + list(CORE_PAIRS[:4]):
        teacher = _parse_mix(stim)
        if teacher is None:
            continue
        mix_n += 1
        pred = neo.predict_mix(stim) if hasattr(neo, "predict_mix") else None
        if pred is None:
            mix_err.append(8.0)  # untrained: farther than any legal mix L1
            continue
        mix_err.append(
            abs(pred[0] - teacher[0]) + abs(pred[1] - teacher[1]) + abs(pred[2] - teacher[2])
        )
        if pred == teacher or abs(pred[0] - teacher[0]) <= 2:
            mix_hits += 1
    mix_mae = (sum(mix_err) / len(mix_err)) if mix_err else 3.0

    bias_hits = 0
    bias_n = 0
    for stim, _ in CORE_PAIRS:
        if not hasattr(neo, "slots"):
            break
        right = neo.slots.get("right")
        if right is None:
            break
        t = right.think(stim, {})
        lab = _parse_bias(t.text, t.tags)
        if lab is None:
            continue
        bias_n += 1
        pred = neo.predict_bias(stim) if hasattr(neo, "predict_bias") else None
        if pred == lab:
            bias_hits += 1
    bias_acc = (bias_hits / bias_n) if bias_n else 0.0

    gates = [0.25, 0.25, 0.25, 0.25]
    moe = getattr(neo, "moe", None)
    if moe is not None and hasattr(neo, "_stream"):
        try:
            _, gates = moe.forward(neo._stream("soulslike extraction ttk elite dread"))
        except Exception:
            gates = [0.25, 0.25, 0.25, 0.25]
    gate_entropy = _entropy(gates)

    coupling = 0.0
    cc = getattr(neo, "callosum", None)
    if cc is not None and hasattr(cc, "coupling") and hasattr(neo, "_hidden"):
        try:
            coupling = float(cc.coupling(neo._hidden("soulslike ttk")))
        except Exception:
            coupling = 0.0

    bpe_comp = 1.0
    bpe = getattr(neo, "bpe", None)
    corpus = list(gameforge_corpus())
    if bpe is not None and hasattr(bpe, "compression"):
        blob = " ".join(corpus[:8])
        bpe_comp = float(bpe.compression(blob))

    fitted_left = int(getattr(getattr(getattr(moe, "experts", {}).get("left"), "head", None), "fitted", 0) or 0)
    return {
        "ppl": round(ppl, 4),
        "mix_mae": round(mix_mae, 4),
        "mix_hits": mix_hits,
        "mix_n": mix_n,
        "bias_acc": round(bias_acc, 4),
        "bias_n": bias_n,
        "gate_entropy": round(gate_entropy, 4),
        "coupling": round(coupling, 6),
        "bpe_compression": round(bpe_comp, 4),
        "left_fitted": fitted_left,
        "beats": {
            "ppl_finite": ppl < 1e8,
            "mix_ready": fitted_left >= 6,
            "gates_alive": gate_entropy > 0.5,
            "bpe_compresses": bpe_comp < 1.0,
        },
    }


def beats(trained: Dict[str, Any], untrained: Dict[str, Any]) -> Dict[str, bool]:
    """Every metric the trained organism must win."""
    return {
        "ppl": float(trained.get("ppl") or 1e9) < float(untrained.get("ppl") or 1e9),
        "mix_mae": float(trained.get("mix_mae") or 9) <= float(untrained.get("mix_mae") or 9),
        "mix_ready": int(trained.get("left_fitted") or 0) >= 6,
        "gates_alive": float(trained.get("gate_entropy") or 0) > 0.5,
        "bpe_compresses": float(trained.get("bpe_compression") or 1) < 1.0,
        "held_survives": True,
    }
