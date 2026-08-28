"""Mishima Zaibatsu — the tournament that proves succession.

Every mouth of the organism fights the same closed world:

  PFC      small n-gram          (boilerplate, draft)
  midbrain medium causal attn    (coordinator, 1 layer)
  neo      stacked Pre-LN GELU   (hivemind, n_layers=2)
  neo_rms  stacked Pre-LN SwiGLU (second neo, RMSNorm)

Perplexity is the bout. The family seal is the merkle card. Devil gene
is own-lm armed after surpass — hidden power that surfaces when the
neo has acquired the tracts. Hive pull is how a sibling inherits the
house. This is not a dashboard. A zaibatsu that cannot name a winner
is not a zaibatsu.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from skeleton.cortex.curriculum import CORE_PAIRS, WALK_PAIRS
from skeleton.cortex.hive import merkle_card
from skeleton.cortex.lm import gameforge_corpus


def _ppl(lm, texts) -> float:
    if lm is None or not hasattr(lm, "perplexity"):
        return float("inf")
    try:
        return float(lm.perplexity(texts))
    except Exception:
        return float("inf")


def _mouth(neo, slot: str):
    port = (getattr(neo, "slots", {}) or {}).get(slot)
    if port is None:
        return None
    if hasattr(port, "transformer") and getattr(port, "transformer", None) is not None:
        xf = port.transformer
        if xf is not None and getattr(xf, "steps", 0) > 0:
            return xf
    return getattr(port, "lm", None)


def tournament(neo, *, texts=None) -> Dict[str, Any]:
    """Four mouths, one corpus. Winner is min finite perplexity."""
    corpus = list(texts or gameforge_corpus())
    held = corpus[-4:] if len(corpus) >= 4 else corpus
    ppl_texts = [a for a, _ in list(CORE_PAIRS)[:6]] + [a for a, _ in list(WALK_PAIRS)]
    if not ppl_texts:
        ppl_texts = held

    mouths: Dict[str, Dict[str, Any]] = {}
    pfc_lm = _mouth(neo, "pfc")
    mid_lm = _mouth(neo, "midbrain")
    neo_lm = getattr(neo, "transformer", None)

    def _entry(name: str, lm, scale: str, layers: int) -> Dict[str, Any]:
        ppl = _ppl(lm, ppl_texts)
        return {
            "name": name,
            "scale": scale,
            "ppl": None if ppl == float("inf") else round(ppl, 4),
            "finite": ppl < 1e8,
            "steps": int(getattr(lm, "steps", 0) or getattr(lm, "fitted", 0) or 0),
            "n_layers": int(getattr(lm, "n_layers", layers) or layers),
            "device": str(getattr(lm, "device", "cpu") or "cpu"),
            "resident": bool(getattr(lm, "resident", False)),
            "norm": str(getattr(lm, "norm", "ln") or "ln"),
            "ffn_kind": str(getattr(lm, "ffn_kind", "gelu") or "gelu"),
        }

    mouths["pfc"] = _entry("pfc", pfc_lm, "small", 0)
    mouths["midbrain"] = _entry("midbrain", mid_lm, "medium", 1)
    mouths["neo"] = _entry("neo", neo_lm, "neo", 2)
    mouths["neo_rms"] = _entry("neo_rms", getattr(neo, "neo_rms", None), "neo-rms", 2)

    ranked = sorted(
        ((k, v) for k, v in mouths.items() if v["finite"] and v["ppl"] is not None),
        key=lambda kv: kv[1]["ppl"],
    )
    winner = ranked[0][0] if ranked else "neo"
    devil = bool(getattr(neo, "_surpass", None))
    card = merkle_card(neo)
    from skeleton.cortex.metrics import evaluate
    scored = evaluate(neo)
    return {
        "house": "mishima-zaibatsu",
        "mouths": mouths,
        "winner": winner,
        "devil": devil,
        "seal": card,
        "metrics": scored,
        "succession": {
            "pfc": "draft / boilerplate n-gram",
            "midbrain": "coordinator causal attn n_layers=1",
            "neo": "hivemind stacked Pre-LN GELU n_layers=2",
            "neo_rms": "second neo RMSNorm+SwiGLU n_layers=2",
            "rule": "acquire copies the MODEL; surpass answers from neo; hive pull inherits the house; --mouth rms speaks the second neo",
        },
    }


def devil_gene(neo) -> Dict[str, Any]:
    """Hidden power that surfaces. Own-lm armed + neo residual lives."""
    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    armed = bool(getattr(neo, "_surpass", None))
    return {
        "armed": armed,
        "slots": sorted(getattr(neo, "_surpass", set()) or []),
        "n_layers": int(getattr(xf, "n_layers", 0) or 0),
        "n_heads": int(getattr(xf, "n_heads", 0) or 0),
        "d_ff": int(getattr(xf, "d_ff", 0) or 0),
        "steps": int(getattr(xf, "steps", 0) or 0),
        "device": str(getattr(xf, "device", "cpu") or "cpu"),
        "resident": bool(getattr(xf, "resident", False)),
        "bpe_merges": int(len(getattr(getattr(neo, "bpe", None), "merges", ()) or ())),
        "seq_fires": int(getattr(getattr(neo, "callosum", None), "seq_fires", 0) or 0),
        "neo_rms": {
            "norm": str(getattr(rms, "norm", "") or ""),
            "ffn_kind": str(getattr(rms, "ffn_kind", "") or ""),
            "steps": int(getattr(rms, "steps", 0) or 0),
            "n_layers": int(getattr(rms, "n_layers", 0) or 0),
        },
    }
