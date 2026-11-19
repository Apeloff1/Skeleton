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


# One mass pass: many epochs, and many full-corpus SGD sweeps inside each epoch.
AAA_MASS_EPOCHS = 8
AAA_MASS_STEPS_PER_EPOCH = 4
AAA_SHADOW_TRIALS = 4

# Production lessons for a modern AAA vertical slice. Words outside the
# closed GameForge vocabulary are dropped at corpus build time.
_AAA_LESSONS = (
    "modern aaa ttk trash elite boss spectacle assisted mastery",
    "plan tensor world layout room graph bound stream",
    "combat ttk elite dread heat stagger posture boss",
    "cinematic camera spectacle era feel spatial gestalt",
    "animation locomotion walk run hops cores bound",
    "audio mix heat vent collapse score trash",
    "narrative quest compile recipe sim forge run",
    "systems loot bias heat extract late lock",
    "vertical slice walk collapse extract core bound",
    "lighting materials era feel cozy dread spectacle",
    "squad encounter mix trash elite boss slack",
    "player glass ttk elite boss assisted mastery",
    "soulslike extraction ttk elite dread rest forge",
    "hp dps ttk compile recipe sim extract collapse",
)


def _known_line(model, text: str) -> str:
    known = getattr(model, "stoi", {}) or {}
    words = [word for word in text.lower().split() if word in known]
    return " ".join(words)


def aaa_game_creation_corpus(model) -> List[str]:
    """AAA game-creation lines plus one sweep of every live vocabulary token."""
    lines = []
    seen = set()
    for lesson in _AAA_LESSONS:
        line = _known_line(model, lesson)
        if len(line.split()) >= 2 and line not in seen:
            seen.add(line)
            lines.append(line)
    itos = list(getattr(model, "itos", ()) or ())
    unk = str(getattr(model, "unk", 0))
    vocab_words = []
    for index, token in enumerate(itos):
        if not token or index == 0 and token in {"__unk__", unk}:
            continue
        if token == "__unk__":
            continue
        vocab_words.append(str(token))
    if len(vocab_words) >= 2:
        sweep = " ".join(vocab_words)
        if sweep not in seen:
            lines.append(sweep)
    if len(lines) < 2:
        raise ValueError("AAA game-creation corpus is empty")
    return lines


def _iter_cells(model) -> List[float]:
    cells: List[float] = []
    for matrix in (getattr(model, "E", []), getattr(model, "P", []), getattr(model, "Wout", [])):
        for row in matrix:
            cells.extend(float(value) for value in row)
    cells.extend(float(value) for value in getattr(model, "bout", []) or [])
    for layer in getattr(model, "layers", []) or []:
        matrices = [layer.Wq, layer.Wk, layer.Wv, layer.Wo, layer.W1, layer.W2]
        # GELU does not read the SwiGLU gate. RMSNorm does not read a bias.
        if getattr(layer, "ffn_kind", "") == "swiglu":
            matrices.append(layer.Wu)
        for matrix in matrices:
            for row in matrix:
                cells.extend(float(value) for value in row)
        vectors = [layer.b1, layer.b2, layer.ln1_g, layer.ln2_g]
        if getattr(layer, "ffn_kind", "") == "swiglu":
            vectors.append(layer.bu)
        if getattr(layer, "norm", "") != "rms":
            vectors.extend((layer.ln1_b, layer.ln2_b))
        for vector in vectors:
            cells.extend(float(value) for value in vector)
    return cells


def _inactive_cells(model) -> Dict[str, int]:
    rms_bias = 0
    gelu_gate = 0
    for layer in getattr(model, "layers", []) or []:
        if getattr(layer, "norm", "") == "rms":
            rms_bias += len(layer.ln1_b) + len(layer.ln2_b)
        if getattr(layer, "ffn_kind", "") != "swiglu":
            gelu_gate += len(layer.bu) + sum(len(row) for row in layer.Wu)
    return {"rms_bias": rms_bias, "gelu_gate": gelu_gate}


def _bank_fill(cells: List[float]) -> Dict[str, Any]:
    total = len(cells)
    nonzero = 0
    nonfinite = 0
    for value in cells:
        if not math.isfinite(value):
            nonfinite += 1
        elif value != 0.0:
            nonzero += 1
    return {
        "cells": total,
        "nonzero": nonzero,
        "zeros": total - nonzero - nonfinite,
        "nonfinite": nonfinite,
        "filled": total > 0 and nonzero == total and nonfinite == 0,
    }


def weight_fill_report(neo) -> Dict[str, Any]:
    """Occupancy of every active weight. Unused RMS biases are counted apart."""
    speaking = _bank_fill(_iter_cells(neo.transformer))
    rms_model = getattr(neo, "neo_rms", None)
    rms = _bank_fill(_iter_cells(rms_model)) if rms_model is not None else {
        "cells": 0, "nonzero": 0, "zeros": 0, "nonfinite": 0, "filled": False,
    }
    inactive = _inactive_cells(neo.transformer)
    if rms_model is not None:
        rms_inactive = _inactive_cells(rms_model)
        inactive["rms_bias"] += rms_inactive["rms_bias"]
        inactive["gelu_gate"] += rms_inactive["gelu_gate"]
    adaptive = neo.dynamic_weights.adaptive
    adaptive_cells: List[float] = []
    for matrix in (adaptive.A, adaptive.B):
        for row in matrix:
            adaptive_cells.extend(row)
    adaptive_cells.extend(adaptive.bias)
    adaptive_fill = _bank_fill(adaptive_cells)
    reactive_cells = [value for row in neo.dynamic_weights.reactive.M for value in row]
    reactive_fill = _bank_fill(reactive_cells)
    shadow_slots = {}
    shadow_filled = True
    for slot, stats in getattr(neo, "shadow", {}).items():
        trials = int((stats or {}).get("trials") or 0) if isinstance(stats, dict) else 0
        shadow_slots[str(slot)] = trials
        if trials < AAA_SHADOW_TRIALS:
            shadow_filled = False
    banks = {
        "weights": speaking,
        "rms_weights": rms,
        "adaptive_weights": adaptive_fill,
        "reactive_weights": reactive_fill,
    }
    return {
        "kind": "jeeves-weight-fill",
        "banks": banks,
        "shadow_trials": shadow_slots,
        "shadow_filled": shadow_filled,
        "inactive_cells": inactive,
        "filled": all(bank["filled"] for bank in banks.values()) and shadow_filled,
    }


def _dense_signal(rows: List[List[float]]) -> List[float]:
    if not rows:
        raise ValueError("no embedding rows")
    dim = len(rows[0])
    mixed = [0.0 for _ in range(dim)]
    for row in rows:
        for index, value in enumerate(row):
            mixed[index] += float(value)
    peak = max((abs(value) for value in mixed if value != 0.0), default=0.0)
    if peak == 0.0:
        raise ValueError("embedding table has no magnitude")
    for index, value in enumerate(mixed):
        if value == 0.0:
            mixed[index] = peak if index % 2 == 0 else -peak
    return mixed


def _rotate(values: List[float], shift: int) -> List[float]:
    width = len(values)
    offset = shift % width
    return values[offset:] + values[:offset]


def _fill_dynamic_banks(neo) -> int:
    """Drive adaptive and reactive cells with dense signals from live embeddings."""
    table = list(neo.transformer.E)
    signal = _dense_signal(table)
    dim = len(signal)
    writes = 0
    for shift in range(dim):
        hidden = _rotate(signal, shift)
        target = _rotate(signal, shift + 1)
        neo.dynamic_weights.observe(hidden, target)
        writes += 1
    return writes


def _fill_shadow_ledger(neo, texts: List[str]) -> int:
    from skeleton.cortex.port import SLOTS

    for slot in SLOTS:
        if slot not in neo._surpass:
            neo.surpass(slot)
    thinks = 0
    budget = max(AAA_SHADOW_TRIALS, len(texts))
    while thinks < budget:
        short = [
            slot for slot, stats in neo.shadow.items()
            if int((stats or {}).get("trials") or 0) < AAA_SHADOW_TRIALS
        ]
        if not short:
            break
        neo.think(texts[thinks % len(texts)])
        thinks += 1
    return thinks


def mass_pretrain_aaa_game_creation(neo) -> Dict[str, Any]:
    """Mass-pretrain every active weight bank on AAA game creation.

    Eight epochs each run four full SGD sweeps of the AAA lessons and the
    whole vocabulary, on the speaking transformer and the RMS mouth. Adaptive
    weights observe the lessons on every step. A closing pass fills any
    adaptive or reactive cell still empty. Shadow slots record real trials
    and are not promoted into the live weights.
    """
    confirmation = confirm_weight_pretrain(neo)
    if getattr(neo, "_weight_mass_pretrain_receipt", None) is not None:
        return {
            "kind": "jeeves-aaa-mass-pretrain",
            "pretrained": False,
            "once": True,
            "reason": "already_mass_pretrained",
            "confirmation": confirmation,
            "shadow_weights_promoted": False,
            "fill": weight_fill_report(neo),
        }
    if not confirmation["authorized"]:
        return {
            "kind": "jeeves-aaa-mass-pretrain",
            "pretrained": False,
            "once": True,
            "reason": confirmation["reasons"][0],
            "confirmation": confirmation,
            "shadow_weights_promoted": False,
            "fill": None,
        }

    from skeleton.cortex.attn import cosine_lr

    speaking = neo.transformer
    rms = getattr(neo, "neo_rms", None)
    texts = aaa_game_creation_corpus(speaking)
    lessons = [text for text in texts if text != texts[-1]] or list(texts)
    before_steps = int(getattr(speaking, "steps", 0) or 0)
    before_rms_steps = int(getattr(rms, "steps", 0) or 0)
    before_adaptive = int(neo.dynamic_weights.adaptive.steps)
    before_shadow = _shadow_trials(neo)
    sweeps = AAA_MASS_EPOCHS * AAA_MASS_STEPS_PER_EPOCH
    sweep = 0
    for _epoch in range(AAA_MASS_EPOCHS):
        for _step in range(AAA_MASS_STEPS_PER_EPOCH):
            lr = cosine_lr(sweep, sweeps, base=0.04, floor=0.008)
            speaking.fit(texts, lr=lr, schedule="const")
            if rms is not None and hasattr(rms, "fit"):
                rms.fit(texts, lr=lr, schedule="const")
            for text in lessons:
                neo.step_dynamic_weights(text)
            sweep += 1
    dynamic_writes = _fill_dynamic_banks(neo)
    shadow_thinks = _fill_shadow_ledger(neo, lessons)
    if hasattr(neo, "sync_backup_transformer"):
        neo.sync_backup_transformer()
    fill = weight_fill_report(neo)
    if not fill["filled"]:
        return {
            "kind": "jeeves-aaa-mass-pretrain",
            "pretrained": False,
            "once": True,
            "reason": "weights_not_filled",
            "confirmation": confirmation,
            "shadow_weights_promoted": False,
            "fill": fill,
        }
    after_steps = int(getattr(speaking, "steps", 0) or 0)
    after_rms_steps = int(getattr(rms, "steps", 0) or 0)
    step_delta = after_steps - before_steps
    if step_delta < sweeps:
        return {
            "kind": "jeeves-aaa-mass-pretrain",
            "pretrained": False,
            "once": True,
            "reason": "steps_short",
            "confirmation": confirmation,
            "shadow_weights_promoted": False,
            "fill": fill,
            "epochs": AAA_MASS_EPOCHS,
            "steps_per_epoch": AAA_MASS_STEPS_PER_EPOCH,
            "weights_steps": after_steps,
        }
    neo.massive_steps_completed = int(getattr(neo, "massive_steps_completed", 0) or 0) + step_delta
    receipt = {
        "kind": "jeeves-aaa-mass-pretrain-receipt",
        "passes": 1,
        "epochs": AAA_MASS_EPOCHS,
        "steps_per_epoch": AAA_MASS_STEPS_PER_EPOCH,
        "sweeps": sweeps,
        "texts": len(texts),
        "level": "aaa",
        "domain": "game_creation",
        "speaking_steps_before": before_steps,
        "speaking_steps_after": after_steps,
        "speaking_steps_delta": step_delta,
        "rms_steps_before": before_rms_steps,
        "rms_steps_after": after_rms_steps,
        "rms_steps_delta": after_rms_steps - before_rms_steps,
        "adaptive_steps_before": before_adaptive,
        "adaptive_steps_after": int(neo.dynamic_weights.adaptive.steps),
        "shadow_trials_before": before_shadow,
        "shadow_trials_after": _shadow_trials(neo),
        "dynamic_dense_writes": dynamic_writes,
        "shadow_thinks": shadow_thinks,
        "fill": {
            "weights": fill["banks"]["weights"]["cells"],
            "rms_weights": fill["banks"]["rms_weights"]["cells"],
            "adaptive_weights": fill["banks"]["adaptive_weights"]["cells"],
            "reactive_weights": fill["banks"]["reactive_weights"]["cells"],
            "shadow_trials": fill["shadow_trials"],
        },
        "inactive_cells": fill["inactive_cells"],
        "fidelity": confirmation["fidelity"]["score"],
        "confirmation_digest": confirmation["digest"],
        "schedule": "cosine",
        "shadow_weights_promoted": False,
    }
    receipt["digest"] = _digest({key: value for key, value in receipt.items() if key != "digest"})
    neo._weight_mass_pretrain_receipt = receipt
    return {
        "kind": "jeeves-aaa-mass-pretrain",
        "pretrained": True,
        "once": True,
        "reason": "mass_pretrained",
        "level": "aaa",
        "domain": "game_creation",
        "epochs": AAA_MASS_EPOCHS,
        "steps_per_epoch": AAA_MASS_STEPS_PER_EPOCH,
        "sweeps": sweeps,
        "receipt": receipt,
        "confirmation": confirmation,
        "shadow_weights_promoted": False,
        "fill": fill,
        "weights_steps": after_steps,
        "adaptive_steps": receipt["adaptive_steps_after"],
    }


__all__ = [
    "AAA_MASS_EPOCHS",
    "AAA_MASS_STEPS_PER_EPOCH",
    "AAA_SHADOW_TRIALS",
    "CUTTING_EDGE_CAPABILITIES",
    "PEAK_OPERATIONAL_FIDELITY",
    "aaa_game_creation_corpus",
    "confirm_weight_pretrain",
    "cutting_edge_report",
    "fidelity_report",
    "mass_pretrain_aaa_game_creation",
    "pretrain_weights_once",
    "usage_report",
    "weight_fill_report",
]
