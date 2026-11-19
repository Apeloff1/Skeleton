"""One pretraining pass for Jeeves, after full use at peak fidelity.

Live weights, shadow weights, adaptive weights, and reactive weights each
have to have been used. Operational fidelity has to clear the same 0.94
peak used by the studio gate, with finite weights on both mouths.
The architecture has to be the current cutting-edge stack: the 2020
runtime epoch (large-scale pretraining, attention, mixture-of-experts)
plus the RMSNorm and SwiGLU mouth. A passing confirmation authorizes
exactly one cosine pretraining pass. A second call does not train again.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List

PEAK_OPERATIONAL_FIDELITY = 0.94
PEAK_PERPLEXITY = 40.0
CUTTING_EDGE_CAPABILITIES = (
    "large_scale_pretraining",
    "transformer_attention",
    "mixture_of_experts",
)


def _digest(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _shadow_trials(neo) -> int:
    total = 0
    for stats in getattr(neo, "shadow", {}).values():
        if isinstance(stats, dict):
            total += int(stats.get("trials") or 0)
    return total


def _finite_mouth(model) -> bool:
    check = getattr(model, "validate_finite_weights", None)
    if not callable(check):
        return model is not None
    report = check()
    return bool(isinstance(report, dict) and report.get("healthy") is True)


def usage_report(neo) -> Dict[str, Any]:
    """Whether each weight bank has actually been used."""
    weights = neo.weight_inventory()["weights"]
    adaptive = neo.dynamic_weights.adaptive
    reactive = neo.dynamic_weights.reactive
    banks = {
        "weights": int(weights["steps"]) > 0 and int(weights["fitted"]) > 0,
        "shadow_weights": _shadow_trials(neo) > 0,
        "adaptive_weights": int(adaptive.steps) > 0,
        "reactive_weights": int(reactive.writes) > 0 and int(getattr(neo, "_dynamic_decodes", 0)) > 0,
    }
    missing = [name for name, used in banks.items() if not used]
    return {
        "full": not missing,
        "banks": banks,
        "missing": missing,
        "shadow_trials": _shadow_trials(neo),
        "dynamic_decodes": int(getattr(neo, "_dynamic_decodes", 0)),
    }


def fidelity_report(neo) -> Dict[str, Any]:
    """Peak operational fidelity from the live evaluation beats."""
    from skeleton.cortex.metrics import evaluate

    measured = evaluate(neo)
    beats = dict(measured.get("beats") or {})
    hit = sum(1 for value in beats.values() if value)
    total = len(beats)
    ratio = (hit / total) if total else 0.0
    perplexity = measured.get("ppl")
    try:
        perplexity_value = float(perplexity)
    except (TypeError, ValueError):
        perplexity_value = math.inf
    perplexity_ok = math.isfinite(perplexity_value) and perplexity_value < PEAK_PERPLEXITY
    export_ok = _finite_mouth(getattr(neo, "transformer", None))
    rms_ok = _finite_mouth(getattr(neo, "neo_rms", None))
    score = ratio if perplexity_ok and export_ok and rms_ok else min(ratio, 0.9)
    return {
        "score": round(score, 4),
        "peak": score >= PEAK_OPERATIONAL_FIDELITY and perplexity_ok and export_ok and rms_ok,
        "threshold": PEAK_OPERATIONAL_FIDELITY,
        "perplexity": None if not math.isfinite(perplexity_value) else round(perplexity_value, 4),
        "perplexity_ok": perplexity_ok,
        "export_ok": export_ok,
        "ai_ok": rms_ok and getattr(neo, "dynamic_weights", None) is not None,
        "beats": beats,
        "beats_hit": hit,
        "beats_total": total,
    }


def cutting_edge_report(neo) -> Dict[str, Any]:
    """Current-epoch pretraining stack, not a forecast decade."""
    from skeleton.ai.model_runtime.runtime_epochs import EpochStatus, RuntimeEpochRegistry

    registry = RuntimeEpochRegistry()
    current = [epoch for epoch in registry.through_decade(2020) if epoch.status is EpochStatus.CURRENT]
    capabilities = set(registry.inherited_capabilities(2020))
    missing = [name for name in CUTTING_EDGE_CAPABILITIES if name not in capabilities]
    rms = getattr(neo, "neo_rms", None)
    rms_norm = str(getattr(rms, "norm", "") or "")
    ffn_kind = str(getattr(rms, "ffn_kind", "") or "")
    speaking = getattr(neo, "transformer", None)
    heads = int(getattr(speaking, "n_heads", 0) or 0)
    layers = int(getattr(speaking, "n_layers", 0) or 0)
    banks_match = (
        getattr(neo, "dynamic_weights", None) is not None
        and int(neo.dynamic_weights.dim) == int(getattr(speaking, "dim", -1) or -1)
    )
    checks = {
        "current_epoch": len(current) == 1 and current[0].decade == 2020,
        "capabilities": not missing,
        "rms_norm": rms_norm == "rms",
        "swiglu": ffn_kind == "swiglu",
        "multi_head": heads >= 2 and layers >= 2,
        "dynamic_banks": banks_match,
    }
    return {
        "cutting_edge": all(checks.values()),
        "checks": checks,
        "missing_capabilities": missing,
        "epoch": 2020,
    }


def confirm_weight_pretrain(neo) -> Dict[str, Any]:
    """Confirm full use, peak fidelity, and the cutting-edge stack."""
    usage = usage_report(neo)
    fidelity = fidelity_report(neo)
    cutting = cutting_edge_report(neo)
    reasons: List[str] = []
    if not usage["full"]:
        reasons.append("usage_incomplete")
    if not fidelity["peak"]:
        reasons.append("fidelity_below_peak")
    if not cutting["cutting_edge"]:
        reasons.append("not_cutting_edge")
    body = {
        "kind": "jeeves-weight-pretrain-confirmation",
        "authorized": not reasons,
        "reasons": reasons,
        "usage": usage,
        "fidelity": fidelity,
        "cutting_edge": cutting,
        "already_pretrained": getattr(neo, "_weight_pretrain_receipt", None) is not None,
    }
    body["digest"] = _digest({
        "authorized": body["authorized"],
        "reasons": reasons,
        "fidelity": fidelity["score"],
        "missing": usage["missing"],
    })
    return body


def _corpus() -> List[str]:
    from skeleton.cortex.curriculum import CORE_PAIRS, WALK_PAIRS

    return [train for train, _held in list(CORE_PAIRS) + list(WALK_PAIRS) if train]


def pretrain_weights_once(neo) -> Dict[str, Any]:
    """Pretrain live and adaptive weights once the confirmation passes.

    Reactive weights stay a fast bank: this pass does not merge them into
    the transformer. Shadow weights are not promoted.
    """
    confirmation = confirm_weight_pretrain(neo)
    if getattr(neo, "_weight_pretrain_receipt", None) is not None:
        return {
            "kind": "jeeves-weight-pretrain",
            "pretrained": False,
            "once": True,
            "reason": "already_pretrained",
            "confirmation": confirmation,
            "shadow_weights_promoted": False,
        }
    if not confirmation["authorized"]:
        return {
            "kind": "jeeves-weight-pretrain",
            "pretrained": False,
            "once": True,
            "reason": confirmation["reasons"][0],
            "confirmation": confirmation,
            "shadow_weights_promoted": False,
        }

    speaking = neo.transformer
    rms = getattr(neo, "neo_rms", None)
    texts = _corpus()
    before_steps = int(getattr(speaking, "steps", 0) or 0)
    before_fitted = int(getattr(speaking, "fitted", 0) or 0)
    before_adaptive = int(neo.dynamic_weights.adaptive.steps)
    before_shadow = _shadow_trials(neo)
    speaking.fit(texts, lr=0.04, schedule="cosine")
    if rms is not None and hasattr(rms, "fit"):
        rms.fit(texts, lr=0.04, schedule="cosine")
    adaptive_pairs = 0
    for text in texts:
        stepped = neo.step_dynamic_weights(text)
        adaptive_pairs += int(stepped.get("pairs") or 0)
    after_steps = int(getattr(speaking, "steps", 0) or 0)
    receipt = {
        "kind": "jeeves-weight-pretrain-receipt",
        "passes": 1,
        "texts": len(texts),
        "adaptive_pairs": adaptive_pairs,
        "speaking_steps_before": before_steps,
        "speaking_steps_after": after_steps,
        "speaking_fitted_before": before_fitted,
        "speaking_fitted_after": int(getattr(speaking, "fitted", 0) or 0),
        "adaptive_steps_before": before_adaptive,
        "adaptive_steps_after": int(neo.dynamic_weights.adaptive.steps),
        "shadow_trials_before": before_shadow,
        "shadow_trials_after": _shadow_trials(neo),
        "fidelity": confirmation["fidelity"]["score"],
        "confirmation_digest": confirmation["digest"],
        "schedule": "cosine",
        "shadow_weights_promoted": False,
    }
    receipt["digest"] = _digest({key: value for key, value in receipt.items() if key != "digest"})
    neo._weight_pretrain_receipt = receipt
    return {
        "kind": "jeeves-weight-pretrain",
        "pretrained": True,
        "once": True,
        "reason": "pretrained",
        "receipt": receipt,
        "confirmation": confirmation,
        "shadow_weights_promoted": False,
        "weights_steps": after_steps,
        "adaptive_steps": receipt["adaptive_steps_after"],
    }


__all__ = [
    "CUTTING_EDGE_CAPABILITIES",
    "PEAK_OPERATIONAL_FIDELITY",
    "confirm_weight_pretrain",
    "cutting_edge_report",
    "fidelity_report",
    "pretrain_weights_once",
    "usage_report",
]
