"""Weight gossip. α-mix two same-shape transformers. α=0 is a no-op."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from skeleton.cortex.hive import merkle_card


def _mix_vec(a: Sequence[float], b: Sequence[float], alpha: float) -> List[float]:
    if len(a) != len(b):
        return list(a)
    ia = 1.0 - alpha
    return [ia * x + alpha * y for x, y in zip(a, b)]


def _mix_mat(A: List[List[float]], B: List[List[float]], alpha: float) -> List[List[float]]:
    if not A or not B or len(A) != len(B) or len(A[0]) != len(B[0]):
        return [list(row) for row in A]
    return [_mix_vec(ra, rb, alpha) for ra, rb in zip(A, B)]


def mix_blocks(dst_blk: Dict[str, Any], src_blk: Dict[str, Any], alpha: float) -> Dict[str, Any]:
    out = dict(dst_blk)
    for key in ("Wq", "Wk", "Wv", "Wo", "W1", "Wu", "W2", "b1", "bu", "b2", "ln1_g", "ln1_b", "ln2_g", "ln2_b"):
        dv, sv = dst_blk.get(key), src_blk.get(key)
        if isinstance(dv, list) and dv and isinstance(dv[0], list):
            out[key] = _mix_mat(dv, sv or dv, alpha)
        elif isinstance(dv, list):
            out[key] = _mix_vec(dv, sv or dv, alpha)
    return out


def mix_snapshots(dst: Dict[str, Any], src: Dict[str, Any], alpha: float) -> Dict[str, Any]:
    a = max(0.0, min(1.0, float(alpha)))
    out = dict(dst)
    for key in ("E", "P", "Wout"):
        if isinstance(dst.get(key), list) and isinstance(src.get(key), list):
            out[key] = _mix_mat(dst[key], src[key], a)
    if isinstance(dst.get("bout"), list) and isinstance(src.get("bout"), list):
        out["bout"] = _mix_vec(dst["bout"], src["bout"], a)
    d_layers, s_layers = list(dst.get("layers") or []), list(src.get("layers") or [])
    if d_layers and s_layers and len(d_layers) == len(s_layers):
        out["layers"] = [mix_blocks(d, s, a) for d, s in zip(d_layers, s_layers)]
    return out


def gossip(dst_lm, src_lm, *, alpha: float = 0.5, keys: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    if dst_lm is None or src_lm is None:
        return {"gossiped": 0, "reason": "missing"}
    if int(getattr(dst_lm, "dim", 0) or 0) != int(getattr(src_lm, "dim", 0) or 0):
        return {"gossiped": 0, "reason": "dim-mismatch"}
    if int(getattr(dst_lm, "n_layers", 0) or 0) != int(getattr(src_lm, "n_layers", 0) or 0):
        return {"gossiped": 0, "reason": "depth-mismatch"}
    a = max(0.0, min(1.0, float(alpha)))
    if a == 0.0:
        return {"gossiped": 1, "alpha": 0.0, "n_layers": int(dst_lm.n_layers), "dim": int(dst_lm.dim),
                "keys": list(keys or ("E", "P", "Wout", "layers")), "reason": "alpha0"}
    restored = type(dst_lm).from_snapshot(mix_snapshots(dst_lm.snapshot(), src_lm.snapshot(), a))
    dst_lm.E, dst_lm.P, dst_lm.Wout, dst_lm.bout = restored.E, restored.P, restored.Wout, restored.bout
    dst_lm.layers, dst_lm.n_layers = restored.layers, restored.n_layers
    return {"gossiped": 1, "alpha": a, "n_layers": int(dst_lm.n_layers), "dim": int(dst_lm.dim),
            "keys": list(keys or ("E", "P", "Wout", "layers"))}


def gossip_cortices(dst, src, *, alpha: float = 0.5) -> Dict[str, Any]:
    before = merkle_card(dst)
    info = gossip(getattr(dst, "transformer", None), getattr(src, "transformer", None), alpha=alpha)
    rms = gossip(getattr(dst, "neo_rms", None), getattr(src, "neo_rms", None), alpha=alpha)
    after = merkle_card(dst)
    info["before_steps"] = before.get("transformer_steps")
    info["after_steps"] = after.get("transformer_steps")
    info["neo_rms"] = rms
    info["card"] = after
    return info


def absorb_mouth(dst_lm, src_lm, *, alpha: float = 0.2) -> Dict[str, Any]:
    """Copy a trained (possibly shallower) mouth into dst."""
    if dst_lm is None or src_lm is None:
        return {"absorbed": 0, "reason": "missing"}
    if int(getattr(dst_lm, "dim", 0) or 0) != int(getattr(src_lm, "dim", 0) or 0):
        return {"absorbed": 0, "reason": "dim-mismatch"}
    source_training = max(
        int(getattr(src_lm, "fitted", 0) or 0),
        int(getattr(src_lm, "steps", 0) or 0),
    )
    if source_training <= 0:
        return {"absorbed": 0, "reason": "source-unfitted"}
    a = max(0.0, min(1.0, float(alpha)))
    if a == 0.0:
        return {"absorbed": 1, "alpha": 0.0, "reason": "alpha0", "layers": 0}
    ds = dst_lm.snapshot()
    ss = src_lm.snapshot()
    mixed = mix_snapshots(ds, ss, a)
    d_layers, s_layers = list(ds.get("layers") or []), list(ss.get("layers") or [])
    n = min(len(d_layers), len(s_layers))
    if n and len(d_layers) != len(s_layers):
        layers = [mix_blocks(d_layers[i], s_layers[i], a) for i in range(n)] + d_layers[n:]
        mixed["layers"] = layers
    restored = type(dst_lm).from_snapshot(mixed)
    dst_lm.E, dst_lm.P, dst_lm.Wout, dst_lm.bout = restored.E, restored.P, restored.Wout, restored.bout
    dst_lm.layers, dst_lm.n_layers = restored.layers, restored.n_layers
    return {"absorbed": 1, "alpha": a, "layers": n,
            "dst_layers": int(dst_lm.n_layers), "src_layers": int(getattr(src_lm, "n_layers", 0) or 0)}


def gossip_mouths(neo, *, alpha: float = 0.25, direction: str = "rms-into-gelu") -> Dict[str, Any]:
    """Mix the two local mouths. Default: RMS/SwiGLU bleeds into the GELU primary."""
    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    if direction == "gelu-into-rms":
        info = gossip(rms, xf, alpha=alpha)
        info["direction"] = direction
        return info
    info = gossip(xf, rms, alpha=alpha)
    info["direction"] = "rms-into-gelu"
    return info


def adaptive_gossip(
    dst_lm,
    src_lm,
    corpus: Iterable[str],
    *,
    max_alpha: float = 0.5,
) -> Dict[str, Any]:
    """Perplexity-calibrated, coherence-gated weight gossip with automatic rollback."""
    import math

    if dst_lm is None or src_lm is None:
        return {"gossiped": 0, "reason": "missing"}
    if int(getattr(dst_lm, "dim", 0) or 0) != int(getattr(src_lm, "dim", 0) or 0):
        return {"gossiped": 0, "reason": "dim-mismatch"}
    if int(getattr(dst_lm, "n_layers", 0) or 0) != int(getattr(src_lm, "n_layers", 0) or 0):
        return {"gossiped": 0, "reason": "depth-mismatch"}
    texts = [t for t in corpus if isinstance(t, str) and t.strip()]
    if not texts:
        return {"gossiped": 0, "reason": "empty-corpus"}
    cap = max(0.0, min(1.0, float(max_alpha)))
    dst_before = float(dst_lm.perplexity(texts))
    src_ppl = float(src_lm.perplexity(texts))
    if not math.isfinite(dst_before) or not math.isfinite(src_ppl):
        return {"gossiped": 0, "reason": "nonfinite-ppl"}
    # Weight alpha proportional to src_lm's inverse-perplexity share.
    inv_dst = 1.0 / max(dst_before, 1e-9)
    inv_src = 1.0 / max(src_ppl, 1e-9)
    raw_share = inv_src / (inv_dst + inv_src)
    alpha = round(min(cap, max(0.05, raw_share * cap * 2.0)), 6) if cap > 0.0 else 0.0
    if alpha == 0.0:
        return {
            "gossiped": 0,
            "alpha": 0.0,
            "dst_ppl_before": round(dst_before, 6),
            "dst_ppl_after": round(dst_before, 6),
            "src_ppl": round(src_ppl, 6),
            "reason": "alpha0",
        }
    saved = dst_lm.snapshot()
    mixed = mix_snapshots(saved, src_lm.snapshot(), alpha)
    restored = type(dst_lm).from_snapshot(mixed)
    dst_lm.E, dst_lm.P, dst_lm.Wout, dst_lm.bout = restored.E, restored.P, restored.Wout, restored.bout
    dst_lm.layers, dst_lm.n_layers = restored.layers, restored.n_layers
    if getattr(dst_lm, "tied", False) and hasattr(dst_lm, "tie"):
        dst_lm.tie()
    dst_after = float(dst_lm.perplexity(texts))
    if not math.isfinite(dst_after) or dst_after > dst_before:
        rollback = type(dst_lm).from_snapshot(saved)
        dst_lm.E, dst_lm.P, dst_lm.Wout, dst_lm.bout = rollback.E, rollback.P, rollback.Wout, rollback.bout
        dst_lm.layers, dst_lm.n_layers = rollback.layers, rollback.n_layers
        if getattr(dst_lm, "tied", False) and hasattr(dst_lm, "tie"):
            dst_lm.tie()
        return {
            "gossiped": 0,
            "alpha": alpha,
            "dst_ppl_before": round(dst_before, 6),
            "dst_ppl_after": round(dst_before, 6),
            "candidate_ppl": round(dst_after, 6) if math.isfinite(dst_after) else None,
            "src_ppl": round(src_ppl, 6),
            "reason": "coherence-gate-rollback",
        }
    return {
        "gossiped": 1,
        "alpha": alpha,
        "dst_ppl_before": round(dst_before, 6),
        "dst_ppl_after": round(dst_after, 6),
        "src_ppl": round(src_ppl, 6),
        "reason": "improved",
    }


def cooperative_logits(
    models: Sequence[Any],
    ids: Sequence[int],
    *,
    weights: Optional[Sequence[float]] = None,
    caches: Optional[Sequence[Any]] = None,
) -> List[float]:
    """Fuse next-token distributions from multiple compatible models in log-prob space."""
    import math
    from skeleton.cortex.attn import softmax

    valid = [m for m in models if m is not None]
    if not valid:
        raise ValueError("cooperative_logits requires at least one model")
    vocab = int(getattr(valid[0], "V", 0) or 0)
    if vocab <= 0:
        raise ValueError("cooperative model must expose positive vocabulary size V")
    for m in valid[1:]:
        if int(getattr(m, "V", 0) or 0) != vocab:
            raise ValueError("all cooperative models must share vocabulary size V")
    if weights is None:
        w_norm = [1.0 / len(valid)] * len(valid)
    else:
        if len(weights) != len(valid):
            raise ValueError("weights length must match models length")
        raw_w = [max(0.0, float(w)) for w in weights]
        total_w = sum(raw_w)
        if total_w <= 0.0 or not math.isfinite(total_w):
            raise ValueError("weights must have a positive finite sum")
        w_norm = [w / total_w for w in raw_w]

    fused_probs = [0.0] * vocab
    for idx, model in enumerate(valid):
        ctx = int(getattr(model, "ctx", 6) or 6)
        window = [int(t) for t in ids][-ctx:] or [0]
        cache = caches[idx] if (caches is not None and idx < len(caches)) else None
        if cache is not None and hasattr(model, "_logits_window"):
            logits = list(model._logits_window(window, cache))
        else:
            logits = list(model._logits(window))
        probs = softmax(logits)
        weight = w_norm[idx]
        for v in range(vocab):
            fused_probs[v] += weight * probs[v]
    return [math.log(max(p, 1e-12)) for p in fused_probs]


def cooperative_decode(
    models: Sequence[Any],
    prefix: str,
    *,
    n: int = 12,
    seed: int = 0,
    weights: Optional[Sequence[float]] = None,
    temperature: float = 1.0,
    top_k: int = 0,
    top_p: float = 1.0,
    min_p: float = 0.0,
    use_cache: bool = True,
) -> str:
    """Cooperatively decode n tokens from a weighted ensemble of compatible models."""
    import random
    from skeleton.cortex.attn import sample_logits
    from skeleton.cortex.transformer import UNK, KVCache

    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    valid = [m for m in models if m is not None]
    if not valid:
        return ""
    primary = valid[0]
    for m in valid[1:]:
        if list(getattr(m, "itos", ())) != list(getattr(primary, "itos", ())):
            raise ValueError("cooperative models must share identical token vocabularies")
    ids = list(primary._ids(prefix or "")) or [int(getattr(primary, "unk", 0))]
    caches = [
        KVCache(int(m.n_layers), int(m.ctx))
        if (use_cache and hasattr(m, "_logits_window") and not getattr(m, "use_mod", False))
        else None
        for m in valid
    ]
    rng = random.Random(int(seed) & 0xFFFFFFFF)
    generated: List[int] = []
    for _ in range(n):
        logits = cooperative_logits(valid, ids, weights=weights, caches=caches)
        nxt = int(
            sample_logits(
                logits,
                rng,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                min_p=min_p,
            )
        )
        ids.append(nxt)
        generated.append(nxt)
    itos = list(getattr(primary, "itos", ()))
    return " ".join(itos[i] if 0 <= i < len(itos) else UNK for i in generated)


def redundant_consensus_decode(
    models: Sequence[Any],
    prefix: str,
    *,
    n: int = 12,
    seed: int = 0,
    weights: Optional[Sequence[float]] = None,
    temperature: float = 1.0,
    min_p: float = 0.05,
) -> Dict[str, Any]:
    """Quorum/consensus decoding across a redundant transformer ring with fault isolation.

    Filters out models with non-finite weights or mismatched vocabularies,
    computes per-step token distributions across all healthy members, tracks
    top-1 token agreement (quorum ratio), and dynamically downweights members
    whose step logits are high-entropy or non-finite.
    """
    import math
    import random
    from skeleton.cortex.attn import sample_logits, softmax
    from skeleton.cortex.transformer import UNK, KVCache

    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    candidates = [m for m in models if m is not None]
    if not candidates:
        return {"text": "", "healthy_models": 0, "quorum_agreement": 0.0, "degraded_models": 0}

    primary_itos = list(getattr(candidates[0], "itos", ()))
    healthy: List[Any] = []
    healthy_weights: List[float] = []
    degraded = 0
    for idx, m in enumerate(candidates):
        if list(getattr(m, "itos", ())) != primary_itos:
            degraded += 1
            continue
        if hasattr(m, "validate_finite_weights"):
            try:
                if not m.validate_finite_weights().get("healthy", False):
                    if hasattr(m, "restore_from_standby"):
                        m.restore_from_standby()
                    if not m.validate_finite_weights().get("healthy", False):
                        degraded += 1
                        continue
            except Exception:
                degraded += 1
                continue
        healthy.append(m)
        w = float(weights[idx]) if (weights is not None and idx < len(weights)) else 1.0
        healthy_weights.append(max(1e-6, w))

    if not healthy:
        raise RuntimeError("no healthy transformers available in redundant consensus ring")

    w_sum = sum(healthy_weights)
    base_weights = [w / w_sum for w in healthy_weights]
    lead = healthy[0]
    ids = list(lead._ids(prefix or "")) or [int(getattr(lead, "unk", 0))]
    caches = [
        KVCache(int(m.n_layers), int(m.ctx))
        if (hasattr(m, "_logits_window") and not getattr(m, "use_mod", False))
        else None
        for m in healthy
    ]
    vocab = int(getattr(lead, "V", len(primary_itos)))
    rng = random.Random(int(seed) & 0xFFFFFFFF)
    generated: List[int] = []
    agreements: List[float] = []
    step_failovers = 0

    for _ in range(n):
        step_probs: List[List[float]] = []
        step_w: List[float] = []
        top1_votes: Dict[int, int] = {}
        for m_idx, model in enumerate(healthy):
            ctx = int(getattr(model, "ctx", 6) or 6)
            window = [int(t) for t in ids][-ctx:] or [0]
            cache = caches[m_idx]
            try:
                logits = (
                    list(model._logits_window(window, cache))
                    if cache is not None
                    else list(model._logits(window))
                )
                if not all(math.isfinite(x) for x in logits):
                    step_failovers += 1
                    continue
                probs = softmax(logits)
                entropy = -sum(p * math.log(max(p, 1e-12)) for p in probs)
                conf_scale = 1.0 / (1.0 + max(0.0, entropy) * 0.25)
                step_probs.append(probs)
                step_w.append(base_weights[m_idx] * conf_scale)
                top_tok = max(range(vocab), key=lambda i: probs[i])
                top1_votes[top_tok] = top1_votes.get(top_tok, 0) + 1
            except Exception:
                step_failovers += 1
                continue

        if not step_probs:
            raise RuntimeError("all redundant transformers failed during step decode")

        sw_total = sum(step_w) or 1.0
        fused = [0.0] * vocab
        for probs, w in zip(step_probs, step_w):
            nw = w / sw_total
            for v in range(vocab):
                fused[v] += nw * probs[v]
        fused_logits = [math.log(max(p, 1e-12)) for p in fused]
        nxt = int(
            sample_logits(
                fused_logits,
                rng,
                temperature=temperature,
                min_p=min_p,
            )
        )
        ids.append(nxt)
        generated.append(nxt)
        max_vote = max(top1_votes.values()) if top1_votes else 1
        agreements.append(max_vote / max(1, len(step_probs)))

    text = " ".join(
        primary_itos[i] if 0 <= i < len(primary_itos) else UNK
        for i in generated
    )
    return {
        "text": text,
        "token_ids": generated,
        "healthy_models": len(healthy),
        "degraded_models": degraded,
        "step_failovers": step_failovers,
        "quorum_agreement": round(sum(agreements) / max(1, len(agreements)), 4),
    }


def slerp_vectors(a: Sequence[float], b: Sequence[float], t: float) -> List[float]:
    """Spherical linear interpolation (SLERP) between two parameter vectors."""
    import math

    if len(a) != len(b):
        return list(a)
    tau = max(0.0, min(1.0, float(t)))
    if tau == 0.0:
        return [float(x) for x in a]
    if tau == 1.0:
        return [float(y) for y in b]
    norm_a = math.sqrt(sum(float(x) * float(x) for x in a))
    norm_b = math.sqrt(sum(float(y) * float(y) for y in b))
    if norm_a < 1e-12 or norm_b < 1e-12:
        return _mix_vec(a, b, tau)
    dot_ab = sum(float(x) * float(y) for x, y in zip(a, b)) / (norm_a * norm_b)
    dot_ab = max(-1.0, min(1.0, dot_ab))
    omega = math.acos(dot_ab)
    sin_omega = math.sin(omega)
    if abs(sin_omega) < 1e-6:
        return _mix_vec(a, b, tau)
    w_a = math.sin((1.0 - tau) * omega) / sin_omega
    w_b = math.sin(tau * omega) / sin_omega
    target_norm = (1.0 - tau) * norm_a + tau * norm_b
    raw = [w_a * (float(x) / norm_a) + w_b * (float(y) / norm_b) for x, y in zip(a, b)]
    raw_norm = math.sqrt(sum(v * v for v in raw))
    if raw_norm < 1e-12:
        return _mix_vec(a, b, tau)
    scale_factor = target_norm / raw_norm
    return [v * scale_factor for v in raw]


def _ties_merge_vectors(
    base_vec: Sequence[float],
    donor_vecs: Sequence[Sequence[float]],
    weights: Sequence[float],
    *,
    density: float = 0.75,
    scaling_lambda: float = 0.85,
) -> tuple[List[float], Dict[str, int]]:
    """TIES-Merging (Trim, Elect Sign, Disjoint Merge) over parameter vectors."""
    n = len(base_vec)
    valid_donors = [d for d in donor_vecs if len(d) == n]
    if not valid_donors:
        return [float(x) for x in base_vec], {"trimmed": 0, "sign_conflicts": 0, "merged_coords": 0}
    deltas: List[List[float]] = []
    trimmed_count = 0
    keep_k = max(1, int(round(max(0.05, min(1.0, float(density))) * n)))
    for d in valid_donors:
        raw_delta = [float(d[i]) - float(base_vec[i]) for i in range(n)]
        ranked = sorted((abs(v) for v in raw_delta), reverse=True)
        threshold = ranked[min(keep_k - 1, len(ranked) - 1)] if ranked else 0.0
        trimmed: List[float] = []
        for v in raw_delta:
            if abs(v) >= threshold and abs(v) > 1e-12:
                trimmed.append(v)
            else:
                trimmed.append(0.0)
                trimmed_count += 1
        deltas.append(trimmed)

    out: List[float] = []
    sign_conflicts = 0
    merged_coords = 0
    for i in range(n):
        pos_mass = 0.0
        neg_mass = 0.0
        for m_idx, delta in enumerate(deltas):
            w = float(weights[m_idx]) if m_idx < len(weights) else 1.0
            val = delta[i] * w
            if val > 0.0:
                pos_mass += val
            elif val < 0.0:
                neg_mass += abs(val)
        if pos_mass > 0.0 and neg_mass > 0.0:
            sign_conflicts += 1
        elected_sign = 1.0 if pos_mass >= neg_mass else -1.0
        agree_sum = 0.0
        agree_w = 0.0
        for m_idx, delta in enumerate(deltas):
            val = delta[i]
            if val == 0.0:
                continue
            if (val > 0.0 and elected_sign > 0.0) or (val < 0.0 and elected_sign < 0.0):
                w = float(weights[m_idx]) if m_idx < len(weights) else 1.0
                agree_sum += val * w
                agree_w += w
        if agree_w > 0.0:
            merged_coords += 1
            merged_delta = (agree_sum / agree_w) * float(scaling_lambda)
        else:
            merged_delta = 0.0
        out.append(float(base_vec[i]) + merged_delta)
    return out, {
        "trimmed": trimmed_count,
        "sign_conflicts": sign_conflicts,
        "merged_coords": merged_coords,
    }


def task_vector_soup_merge(
    base_lm,
    specialist_lms: Sequence[Any],
    *,
    corpus: Optional[Iterable[str]] = None,
    density: float = 0.75,
    scaling_lambda: float = 0.85,
    slerp_blend: float = 0.25,
) -> Dict[str, Any]:
    """TIES-Merging + SLERP Model Soup over specialist transformers with perplexity ratchet."""
    import math

    if base_lm is None:
        return {"merged": 0, "reason": "missing-base"}
    dim = int(getattr(base_lm, "dim", 0) or 0)
    n_layers = int(getattr(base_lm, "n_layers", 0) or 0)
    donors = [
        m for m in (specialist_lms or ())
        if m is not None
        and int(getattr(m, "dim", 0) or 0) == dim
        and int(getattr(m, "n_layers", 0) or 0) == n_layers
    ]
    if not donors:
        return {"merged": 0, "reason": "no-compatible-donors"}

    probe = [t for t in (corpus or ()) if isinstance(t, str) and t.strip()]
    ppl_before = float(base_lm.perplexity(probe)) if probe and hasattr(base_lm, "perplexity") else None
    donor_weights: List[float] = []
    for m in donors:
        if probe and hasattr(m, "perplexity"):
            try:
                p = float(m.perplexity(probe))
                donor_weights.append(1.0 / max(p if math.isfinite(p) else 1e6, 1e-6))
            except Exception:
                donor_weights.append(1.0)
        else:
            donor_weights.append(max(1.0, float(getattr(m, "steps", 1) or 1)))
    w_sum = sum(donor_weights) or 1.0
    norm_weights = [w / w_sum for w in donor_weights]

    base_snap = base_lm.snapshot()
    donor_snaps = [m.snapshot() for m in donors]
    merged_snap = dict(base_snap)
    stats = {"trimmed": 0, "sign_conflicts": 0, "merged_coords": 0}

    def _merge_mat_ties_slerp(base_mat: List[List[float]], donor_mats: List[List[List[float]]]) -> List[List[float]]:
        if not base_mat or not base_mat[0]:
            return [list(r) for r in base_mat]
        rows, cols = len(base_mat), len(base_mat[0])
        flat_base = [x for r in base_mat for x in r]
        flat_donors = [
            [x for r in dm for x in r]
            for dm in donor_mats
            if len(dm) == rows and len(dm[0]) == cols
        ]
        if not flat_donors:
            return [list(r) for r in base_mat]
        ties_vec, st = _ties_merge_vectors(
            flat_base,
            flat_donors,
            norm_weights,
            density=density,
            scaling_lambda=scaling_lambda,
        )
        stats["trimmed"] += st["trimmed"]
        stats["sign_conflicts"] += st["sign_conflicts"]
        stats["merged_coords"] += st["merged_coords"]
        if slerp_blend > 0.0:
            ties_vec = slerp_vectors(flat_base, ties_vec, 1.0 - max(0.0, min(0.95, float(slerp_blend))) * 0.5)
        return [ties_vec[r * cols:(r + 1) * cols] for r in range(rows)]

    for key in ("E", "P", "Wout"):
        if isinstance(base_snap.get(key), list):
            d_mats = [ds.get(key) for ds in donor_snaps if isinstance(ds.get(key), list)]
            merged_snap[key] = _merge_mat_ties_slerp(base_snap[key], d_mats)

    if isinstance(base_snap.get("bout"), list):
        d_vecs = [ds.get("bout") for ds in donor_snaps if isinstance(ds.get("bout"), list)]
        bv, st = _ties_merge_vectors(
            base_snap["bout"],
            d_vecs,
            norm_weights,
            density=density,
            scaling_lambda=scaling_lambda,
        )
        stats["trimmed"] += st["trimmed"]
        stats["sign_conflicts"] += st["sign_conflicts"]
        stats["merged_coords"] += st["merged_coords"]
        merged_snap["bout"] = bv

    base_layers = list(base_snap.get("layers") or [])
    new_layers: List[Dict[str, Any]] = []
    for l_idx, b_blk in enumerate(base_layers):
        out_blk = dict(b_blk)
        d_blks = [
            (ds.get("layers") or [])[l_idx]
            for ds in donor_snaps
            if len(ds.get("layers") or []) > l_idx
        ]
        for key in ("Wq", "Wk", "Wv", "Wo", "W1", "Wu", "W2", "b1", "bu", "b2", "ln1_g", "ln1_b", "ln2_g", "ln2_b"):
            bv = b_blk.get(key)
            if isinstance(bv, list) and bv and isinstance(bv[0], list):
                d_mats = [db.get(key) for db in d_blks if isinstance(db.get(key), list)]
                out_blk[key] = _merge_mat_ties_slerp(bv, d_mats)
            elif isinstance(bv, list):
                d_vecs = [db.get(key) for db in d_blks if isinstance(db.get(key), list)]
                mv, st = _ties_merge_vectors(
                    bv,
                    d_vecs,
                    norm_weights,
                    density=density,
                    scaling_lambda=scaling_lambda,
                )
                stats["trimmed"] += st["trimmed"]
                stats["sign_conflicts"] += st["sign_conflicts"]
                stats["merged_coords"] += st["merged_coords"]
                out_blk[key] = mv
        new_layers.append(out_blk)
    merged_snap["layers"] = new_layers

    restored = type(base_lm).from_snapshot(merged_snap)
    base_lm.E, base_lm.P, base_lm.Wout, base_lm.bout = restored.E, restored.P, restored.Wout, restored.bout
    base_lm.layers, base_lm.n_layers = restored.layers, restored.n_layers
    if getattr(base_lm, "tied", False) and hasattr(base_lm, "tie"):
        base_lm.tie()

    ppl_after = float(base_lm.perplexity(probe)) if probe and hasattr(base_lm, "perplexity") else None
    rolled_back = False
    if ppl_before is not None and ppl_after is not None and (not math.isfinite(ppl_after) or ppl_after > ppl_before * 1.02):
        rb = type(base_lm).from_snapshot(base_snap)
        base_lm.E, base_lm.P, base_lm.Wout, base_lm.bout = rb.E, rb.P, rb.Wout, rb.bout
        base_lm.layers, base_lm.n_layers = rb.layers, rb.n_layers
        if getattr(base_lm, "tied", False) and hasattr(base_lm, "tie"):
            base_lm.tie()
        rolled_back = True
        ppl_after = ppl_before

    if hasattr(base_lm, "checkpoint_redundant_standby"):
        base_lm.checkpoint_redundant_standby()

    return {
        "kind": "ties-slerp-model-soup",
        "merged": 0 if rolled_back else 1,
        "rolled_back": rolled_back,
        "donor_count": len(donors),
        "donor_weights": [round(w, 4) for w in norm_weights],
        "density": round(float(density), 4),
        "scaling_lambda": round(float(scaling_lambda), 4),
        "ppl_before": round(ppl_before, 6) if ppl_before is not None else None,
        "ppl_after": round(ppl_after, 6) if ppl_after is not None else None,
        "stats": stats,
    }
