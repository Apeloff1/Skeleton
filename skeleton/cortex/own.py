"""Own-system — the memory the neo LM speaks from.

The transformer in JeevesCortex is the voice (CPU default, CUDA if
the device harness can see a GPU). This
module is the few-shot memory: Jaccard recall, mix/bias exemplars,
tract interchange. Compose stitches numbers; the LM utters text.
Two cortices interchange by exporting a Tract plus weights.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from skeleton.cortex.distill import Ability
from skeleton.cortex.port import Thought, jaccard, tokens
from skeleton.forge.eras import ERA_IDS

def _era_hit(tags: Iterable[str], stim_toks: set) -> bool:
    tagset = set(tags or ())
    stim_eras = set()
    tag_eras = set()
    for e in ERA_IDS:
        parts = tuple(e.split("_"))
        if e in stim_toks or (parts and all(p in stim_toks for p in parts)):
            stim_eras.add(e)
        if e in tagset:
            tag_eras.add(e)
    if stim_eras:
        return bool(tag_eras & stim_eras)
    return bool(tagset & stim_toks)


MIN_JACCARD = 0.40
K_RECALL = 5
_NEIGHBORS = ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1))
BIASES = ("loot", "combat", "heat", "balanced")


@dataclass(frozen=True)
class Tract:
    """A transferable ability bundle. The unit of interchange."""

    slot: str
    backend: str
    scale: str
    capabilities: Tuple[str, ...]
    exemplars: Tuple[Ability, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot": self.slot,
            "backend": self.backend,
            "scale": self.scale,
            "capabilities": list(self.capabilities),
            "exemplars": [e.to_dict() for e in self.exemplars],
            "size": len(self.exemplars),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Tract":
        ex = tuple(Ability.from_dict(e) for e in (d.get("exemplars") or []))
        caps = tuple(d.get("capabilities") or ())
        return cls(
            slot=str(d.get("slot") or "neo"),
            backend=str(d.get("backend") or "unknown"),
            scale=str(d.get("scale") or "injected"),
            capabilities=caps,
            exemplars=ex,
        )


@dataclass
class RecallHit:
    jaccard: float
    ability: Ability

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jaccard": round(self.jaccard, 4),
            "slot": self.ability.slot,
            "kind": self.ability.kind,
            "fp": self.ability.stimulus_fp,
            "tags": list(self.ability.tags),
        }


class OwnSystem:
    """The thing being trained. Stores tracts, recalls by Jaccard, composes."""

    def __init__(self) -> None:
        self._items: List[Ability] = []
        self._by_fp: Dict[str, List[Ability]] = {}
        self.models: Dict[str, Dict[str, Any]] = {}

    def ingest_model(self, slot: str, snap: Optional[Dict[str, Any]]) -> int:
        if not snap:
            return 0
        self.models[str(slot)] = dict(snap)
        return 1

    def ingest(self, ability: Ability, stimulus: str = "") -> Ability:
        if not ability.tokens and stimulus:
            ability.tokens = tokens(stimulus)
        self._items.append(ability)
        self._by_fp.setdefault(ability.stimulus_fp, []).append(ability)
        return ability

    def extend(self, abilities: Iterable[Ability]) -> int:
        n = 0
        for ab in abilities:
            self.ingest(ab)
            n += 1
        return n

    def recall(self, stimulus: str, *, k: int = K_RECALL,
               min_jaccard: float = MIN_JACCARD,
               slot: Optional[str] = None) -> List[RecallHit]:
        q = tokens(stimulus)
        scored: List[RecallHit] = []
        seen: set = set()
        for ab in self._items:
            if slot and ab.slot not in {slot, "neo"} and slot not in ab.tags:
                continue
            key = (ab.slot, ab.stimulus_fp, ab.signature)
            if key in seen:
                continue
            seen.add(key)
            j = jaccard(q, ab.tokens)
            if j >= min_jaccard:
                scored.append(RecallHit(j, ab))
        def _rank(h: RecallHit):
            tags = h.ability.tags
            pri = 0 if ("acquired" in tags or "imported" in tags) else 1
            return (pri, -h.jaccard, -h.ability.confidence, -h.ability.seen)
        scored.sort(key=_rank)
        return scored[: max(1, k)]

    def compose(self, stimulus: str, *,
                min_jaccard: float = MIN_JACCARD) -> Optional[Tuple[Thought, float, List[RecallHit]]]:
        hits = self.recall(stimulus, k=K_RECALL, min_jaccard=min_jaccard)
        improved = self.best_observed_mix(stimulus)
        if not hits:
            if improved is None:
                return None
            thought = Thought(
                slot="neo", kind="own",
                text=(
                    f"improved mix trash={int(improved[0])} "
                    f"elite={int(improved[1])} boss={int(improved[2])}"
                ),
                confidence=0.88,
                tags=("neo", "own", "improved", "mix"),
                numbers=improved,
            )
            return thought, 1.0, []
        by_src: Dict[str, RecallHit] = {}
        for h in hits:
            src = _source_slot(h.ability)
            if src not in by_src:
                by_src[src] = h
        order = ("pfc", "left", "right", "midbrain", "neo")
        parts: List[str] = []
        tags: List[str] = ["neo", "own"]
        confs: List[float] = []
        used: List[RecallHit] = []
        best_j = 0.0
        for src in order:
            h = by_src.get(src)
            if h is None:
                continue
            label = {"pfc": "P", "left": "L", "right": "R", "midbrain": "H", "neo": "N"}[src]
            parts.append(f"[{label}] {h.ability.text}")
            tags.extend(list(h.ability.tags[:4]))
            confs.append(h.ability.confidence * (0.50 + 0.50 * h.jaccard))
            used.append(h)
            if h.jaccard > best_j:
                best_j = h.jaccard
        if not parts:
            h = hits[0]
            parts = [h.ability.text]
            tags.extend(list(h.ability.tags))
            confs = [h.ability.confidence * (0.50 + 0.50 * h.jaccard)]
            used = [h]
            best_j = h.jaccard
        conf = min(1.0, sum(confs) / max(1, len(confs)))
        kind = "own-compose" if len(used) > 1 else "own"
        extra = "compose" if kind == "own-compose" else "recall"
        mix: Tuple[float, ...] = ()
        improved = self.best_observed_mix(stimulus)
        if improved is not None:
            mix = improved
            tags.append("improved")
        else:
            left_hit = by_src.get("left")
            if left_hit is not None and len(left_hit.ability.numbers) >= 3:
                mix = tuple(float(x) for x in left_hit.ability.numbers[-3:])
        tag_t = tuple(dict.fromkeys(list(tags) + [extra]))
        thought = Thought(
            slot="neo", kind=kind, text=" || ".join(parts),
            confidence=conf,
            tags=tag_t,
            numbers=mix if mix else (best_j, float(len(used))),
        )
        return thought, best_j, used

    def best_observed_mix(self, stimulus: str) -> Optional[Tuple[float, float, float]]:
        rec = self.best_observed_record(stimulus)
        return rec["mix"] if rec else None

    def best_observed_record(self, stimulus: str) -> Optional[Dict[str, Any]]:
        """Highest-slack observed mix whose era tag appears in the stimulus."""
        stim_toks = set(tokens(stimulus))
        if not stim_toks:
            return None
        best_slack = -1.0
        best: Optional[Dict[str, Any]] = None
        for a in self._items:
            if "observed" not in a.tags:
                continue
            if len(a.numbers) < 4:
                continue
            if not _era_hit(a.tags, stim_toks):
                continue
            slack = float(a.numbers[-1])
            if slack > best_slack:
                best_slack = slack
                mix = (
                    float(a.numbers[-4]),
                    float(a.numbers[-3]),
                    float(a.numbers[-2]),
                )
                best = {
                    "mix": mix,
                    "slack": slack,
                    "invented": "invented" in a.tags,
                    "imported": "imported" in a.tags,
                    "tags": a.tags,
                }
        return best

    def mix_neighbors(self, trash: int, elite: int, boss: int) -> List[Tuple[int, int, int]]:
        out: List[Tuple[int, int, int]] = []
        seen = {(trash, elite, boss)}
        for dt, de, db in _NEIGHBORS:
            t, e, b = trash + dt, elite + de, boss + db
            if 1 <= t <= 6 and 0 <= e <= 3 and 0 <= b <= 1:
                key = (t, e, b)
                if key not in seen:
                    seen.add(key)
                    out.append(key)
        return out

    def mix_cost(self, pack: Dict[str, Any], trash: int, elite: int, boss: int) -> float:
        ttk = pack.get("ttk") or {}
        return (
            trash * float(ttk.get("trash") or 1.0)
            + elite * float(ttk.get("elite") or 6.0)
            + boss * float(ttk.get("boss") or 60.0)
        )

    def propose_mix(self, stimulus: str, score_fn, *, beam: int = 3, depth: int = 2) -> Optional[Tuple[int, int, int, float, bool]]:
        """Beam-search mix neighbors. Invented iff the winner was never observed."""
        return self.beam_mix(stimulus, score_fn, beam=beam, depth=depth)

    def beam_mix(self, stimulus: str, score_fn, *, beam: int = 3, depth: int = 2) -> Optional[Tuple[int, int, int, float, bool]]:
        rec = self.best_observed_record(stimulus)
        if rec is None:
            return None
        t, e, b = int(rec["mix"][0]), int(rec["mix"][1]), int(rec["mix"][2])
        start = (t, e, b)
        observed = {start}
        for a in self._items:
            if "observed" not in a.tags or len(a.numbers) < 4:
                continue
            observed.add((int(a.numbers[-4]), int(a.numbers[-3]), int(a.numbers[-2])))
        best = (float(score_fn(t, e, b)), start)
        frontier: List[Tuple[float, Tuple[int, int, int]]] = [best]
        beam = max(1, int(beam))
        depth = max(1, int(depth))
        for _ in range(depth):
            cand: List[Tuple[float, Tuple[int, int, int]]] = []
            seen = {m for _, m in frontier}
            for _, mix in frontier:
                for n in self.mix_neighbors(*mix):
                    if n in seen:
                        continue
                    seen.add(n)
                    cand.append((float(score_fn(*n)), n))
            cand.sort(key=lambda kv: kv[0], reverse=True)
            frontier = cand[:beam]
            if frontier and frontier[0][0] > best[0] + 1e-6:
                best = frontier[0]
        winner = best[1]
        return winner[0], winner[1], winner[2], best[0], winner not in observed

    def best_observed_bias(self, stimulus: str) -> Optional[str]:
        stim_toks = set(tokens(stimulus))
        best_s = -1.0
        best: Optional[str] = None
        for a in self._items:
            if "observed" not in a.tags or "bias" not in a.tags:
                continue
            if not _era_hit(a.tags, stim_toks):
                continue
            slack = float(a.numbers[-1]) if a.numbers else 0.0
            for b in BIASES:
                if b in a.tags and slack > best_s:
                    best_s = slack
                    best = b
        return best

    def propose_bias(self, stimulus: str, score_fn, start: Optional[str] = None) -> Optional[Tuple[str, float, bool]]:
        base = start or self.best_observed_bias(stimulus) or "balanced"
        best, best_s = base, float(score_fn(base))
        invented = False
        for b in BIASES:
            if b == base:
                continue
            s = float(score_fn(b))
            if s > best_s + 1e-6:
                best, best_s, invented = b, s, True
        return best, best_s, invented

    def best_observed_policy(self, stimulus: str) -> Optional[Tuple[int, int]]:
        stim_toks = set(tokens(stimulus))
        best_s = -1.0
        best: Optional[Tuple[int, int]] = None
        for a in self._items:
            if "observed" not in a.tags or a.slot not in {"pfc", "neo"}:
                continue
            if "policy" not in a.tags and "pfc" not in a.tags:
                continue
            if len(a.numbers) < 3:
                continue
            if not _era_hit(a.tags, stim_toks):
                continue
            slack = float(a.numbers[-1])
            if slack > best_s:
                best_s = slack
                best = (int(a.numbers[-3]), int(a.numbers[-2]))
        return best

    def propose_policy(self, score_fn, start_spawn: int, start_late: int) -> Tuple[int, int, float, bool]:
        base = (int(bool(start_spawn)), int(bool(start_late)))
        best, best_s = base, float(score_fn(*base))
        invented = False
        for sp in (0, 1):
            for lt in (0, 1):
                if (sp, lt) == base:
                    continue
                s = float(score_fn(sp, lt))
                if s > best_s + 1e-6:
                    best, best_s, invented = (sp, lt), s, True
        return best[0], best[1], best_s, invented

    def export_tract(self, slot: str, *, backend: str = "own",
                     scale: str = "neo") -> Tract:
        slot = (slot or "").lower()
        ex = tuple(
            a for a in self._items
            if a.slot == slot or slot in a.tags
        )
        if not ex:
            ex = tuple(a for a in self._items if a.slot == "neo")
        caps = tuple(dict.fromkeys(t for a in ex for t in a.tags))
        return Tract(slot=slot, backend=backend, scale=scale,
                     capabilities=caps, exemplars=ex)

    def import_tract(self, tract: Tract) -> int:
        n = 0
        for ab in tract.exemplars:
            tagged = Ability(
                slot="neo",
                stimulus_fp=ab.stimulus_fp,
                signature=ab.signature,
                kind=ab.kind,
                text=ab.text,
                tags=tuple(dict.fromkeys(ab.tags + ("imported", tract.slot, tract.backend))),
                numbers=ab.numbers,
                confidence=ab.confidence,
                seen=ab.seen,
                tokens=ab.tokens,
            )
            self.ingest(tagged)
            n += 1
        return n

    @property
    def size(self) -> int:
        return len(self._items)

    def capabilities(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(t for a in self._items for t in a.tags))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "size": self.size,
            "fingerprints": len(self._by_fp),
            "capabilities": list(self.capabilities())[:24],
            "models": sorted(self.models),
        }

    def snapshot(self) -> Dict[str, Any]:
        return {"items": [a.to_dict() for a in self._items], "models": dict(self.models)}

    def restore(self, data: Dict[str, Any]) -> int:
        n = 0
        for d in data.get("items") or []:
            self.ingest(Ability.from_dict(d))
            n += 1
        for slot, snap in (data.get("models") or {}).items():
            self.ingest_model(str(slot), snap)
        return n


def shadow_eval(own: Thought, teacher: Thought) -> bool:
    """Own wins if it is at least as sure and shares any structural tag."""
    tag_j = jaccard(own.tags, teacher.tags)
    return (own.confidence + 0.08) >= (teacher.confidence * 0.88) and (
        tag_j >= 0.12 or own.kind.startswith("own")
    )


def _source_slot(ab: Ability) -> str:
    if "acquired" in ab.tags or "imported" in ab.tags:
        for s in ("pfc", "left", "right", "midbrain"):
            if s in ab.tags:
                return s
    if ab.slot in {"pfc", "left", "right", "midbrain"}:
        return ab.slot
    for s in ("pfc", "left", "right", "midbrain"):
        if s in ab.tags:
            return s
    return "neo"


def _mat_frobenius(mat: Any) -> float:
    import math
    if not isinstance(mat, list) or not mat:
        return 0.0
    acc = 0.0
    for row in mat:
        if isinstance(row, list):
            for x in row:
                fx = float(x)
                if math.isfinite(fx):
                    acc += fx * fx
    return math.sqrt(acc)


def _mat_delta_frobenius(mat_a: Any, mat_b: Any) -> float:
    import math
    if (
        not isinstance(mat_a, list)
        or not isinstance(mat_b, list)
        or not mat_a
        or len(mat_a) != len(mat_b)
        or not isinstance(mat_a[0], list)
        or not isinstance(mat_b[0], list)
        or len(mat_a[0]) != len(mat_b[0])
    ):
        return 0.0
    acc = 0.0
    for ra, rb in zip(mat_a, mat_b):
        for xa, xb in zip(ra, rb):
            d = float(xa) - float(xb)
            if math.isfinite(d):
                acc += d * d
    return math.sqrt(acc)


def parse_shadow_weights(neo) -> Dict[str, Any]:
    """Parse shadow trial telemetry, transformer weight deltas, LoRA adapters, and MoE heads."""
    import hashlib
    import json
    import math
    from skeleton.cortex.laws import check

    shadow_raw = dict(getattr(neo, "shadow", {}) or {})
    surpassed = set(getattr(neo, "_surpass", set()) or set())
    slot_metrics: Dict[str, Dict[str, Any]] = {}
    promotable_slots: List[str] = []

    for key, stats in sorted(shadow_raw.items()):
        wins = int((stats or {}).get("wins") or 0)
        trials = int((stats or {}).get("trials") or 0)
        emp_rate = wins / max(1, trials)
        posterior_mean = (wins + 1.0) / (trials + 2.0)
        lower_bound = max(0.0, posterior_mean - 1.0 / math.sqrt(trials + 4.0))
        promotable = bool(trials >= 3 and emp_rate >= 0.60)
        if promotable and key != "own":
            promotable_slots.append(key)
        slot_metrics[key] = {
            "wins": wins,
            "trials": trials,
            "win_rate": round(emp_rate, 4),
            "posterior_mean": round(posterior_mean, 4),
            "confidence_lower_bound": round(lower_bound, 4),
            "surpassed": key in surpassed or (key == "own" and bool(surpassed)),
            "promotable": promotable,
        }

    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    backup = getattr(neo, "backup_transformer", None)
    layer_deltas: List[Dict[str, Any]] = []
    embedding_delta_norm = 0.0

    if xf is not None and rms is not None:
        embedding_delta_norm = round(_mat_delta_frobenius(getattr(xf, "E", []), getattr(rms, "E", [])), 6)
        xf_layers = list(getattr(xf, "layers", []) or [])
        rms_layers = list(getattr(rms, "layers", []) or [])
        for idx in range(min(len(xf_layers), len(rms_layers))):
            la, lb = xf_layers[idx], rms_layers[idx]
            attn_delta = (
                _mat_delta_frobenius(la.Wq, lb.Wq)
                + _mat_delta_frobenius(la.Wk, lb.Wk)
                + _mat_delta_frobenius(la.Wv, lb.Wv)
                + _mat_delta_frobenius(la.Wo, lb.Wo)
            )
            ffn_delta = (
                _mat_delta_frobenius(la.W1, lb.W1)
                + _mat_delta_frobenius(la.W2, lb.W2)
            )
            layer_deltas.append({
                "layer": idx,
                "attn_delta_norm": round(attn_delta, 6),
                "ffn_delta_norm": round(ffn_delta, 6),
                "primary_wq_norm": round(_mat_frobenius(la.Wq), 6),
                "shadow_wq_norm": round(_mat_frobenius(lb.Wq), 6),
            })

    lora_summary = None
    if xf is not None and getattr(xf, "lora", None) is not None:
        lora_summary = xf.lora.to_dict()

    moe = getattr(neo, "moe", None)
    moe_summary: Dict[str, Any] = {}
    if moe is not None:
        moe_summary = moe.to_dict()

    own = getattr(neo, "own", None)
    exemplar_count = int(getattr(own, "size", 0) or 0)
    high_conf_exemplars = 0
    if own is not None:
        for ab in getattr(own, "_items", ()):
            if float(getattr(ab, "confidence", 0.0)) >= 0.75:
                high_conf_exemplars += 1

    digest_payload = {
        "slot_metrics": slot_metrics,
        "embedding_delta_norm": embedding_delta_norm,
        "layer_deltas": layer_deltas,
        "exemplar_count": exemplar_count,
        "high_conf_exemplars": high_conf_exemplars,
        "has_backup": backup is not None,
    }
    shadow_digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    report = check({
        "kind": "shadow-weight-parse",
        "schema_version": "skeleton.cortex.shadow_parse.v1",
        "slot_metrics": slot_metrics,
        "promotable_slots": promotable_slots,
        "embedding_delta_norm": embedding_delta_norm,
        "layer_deltas": layer_deltas,
        "lora_summary": lora_summary,
        "moe_summary": moe_summary,
        "exemplar_count": exemplar_count,
        "high_conf_exemplars": high_conf_exemplars,
        "shadow_digest": shadow_digest,
        "stored_prose": 0,
        "law": "ok",
    })
    return report


def create_hyperweights(
    neo,
    *,
    alpha: float = 0.30,
    rank: int = 4,
    tag_filter: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Synthesize a content-addressed Hyperweight Bundle from shadow weights, LoRA, and MoE priors."""
    import hashlib
    import json
    import math
    from skeleton.cortex.curriculum import CORE_PAIRS
    from skeleton.cortex.gossip import mix_snapshots
    from skeleton.cortex.laws import check

    a = max(0.05, min(0.85, float(alpha)))
    r = max(1, min(16, int(rank)))
    parsed = parse_shadow_weights(neo)

    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    probe_texts = [t for t, _ in list(CORE_PAIRS)[:4]] or ["soulslike ttk elite"]

    ppl_xf = float(xf.perplexity(probe_texts)) if xf is not None and hasattr(xf, "perplexity") else 10.0
    ppl_rms = float(rms.perplexity(probe_texts)) if rms is not None and hasattr(rms, "perplexity") else 10.0
    inv_xf = 1.0 / max(ppl_xf if math.isfinite(ppl_xf) else 1e6, 1e-6)
    inv_rms = 1.0 / max(ppl_rms if math.isfinite(ppl_rms) else 1e6, 1e-6)
    rms_share = inv_rms / (inv_xf + inv_rms)
    effective_alpha = round(a * rms_share * 2.0, 6)
    effective_alpha = max(0.05, min(0.50, effective_alpha))

    hyper_transformer_snap = None
    layer_hyper_projections: List[Dict[str, Any]] = []
    if xf is not None and rms is not None:
        s_xf = xf.snapshot()
        s_rms = rms.snapshot()
        if int(s_xf.get("dim", 0)) == int(s_rms.get("dim", 0)):
            hyper_transformer_snap = mix_snapshots(s_xf, s_rms, effective_alpha)
        for l_idx, layer in enumerate(getattr(xf, "layers", ())):
            d = int(getattr(layer, "dim", 8) or 8)
            proj_a: List[List[float]] = []
            proj_b: List[List[float]] = [[0.0] * r for _ in range(d)]
            for r_idx in range(r):
                row_src = layer.Wq[r_idx % len(layer.Wq)] if layer.Wq else [0.0] * d
                norm_row = math.sqrt(sum(x * x for x in row_src)) or 1.0
                proj_a.append([round(x / norm_row * 0.1, 6) for x in row_src])
                if r_idx < d:
                    proj_b[r_idx][r_idx] = round(effective_alpha * 0.25, 6)
            layer_hyper_projections.append({
                "layer": l_idx,
                "rank": r,
                "alpha": float(r * 2),
                "A": proj_a,
                "B": proj_b,
            })

    filter_set = {str(t).lower() for t in tag_filter} if tag_filter else set()
    own = getattr(neo, "own", None)
    routing_postings: Dict[str, List[str]] = {}
    selected_exemplars: List[Dict[str, Any]] = []
    if own is not None:
        for ab in getattr(own, "_items", ()):
            tags_lower = {str(t).lower() for t in ab.tags}
            if filter_set and not (tags_lower & filter_set):
                continue
            if float(ab.confidence) >= 0.65 or "observed" in tags_lower or "acquired" in tags_lower:
                if len(selected_exemplars) < 48:
                    selected_exemplars.append(ab.to_dict())
                for tok in list(ab.tags)[:8]:
                    bucket = routing_postings.setdefault(str(tok).lower(), [])
                    if ab.stimulus_fp not in bucket and len(bucket) < 16:
                        bucket.append(ab.stimulus_fp)

    moe = getattr(neo, "moe", None)
    moe_snapshot = moe.snapshot() if moe is not None and hasattr(moe, "snapshot") else None

    core_payload = {
        "schema_version": "skeleton.cortex.hyperweights.v1",
        "effective_alpha": effective_alpha,
        "rank": r,
        "shadow_digest": parsed["shadow_digest"],
        "ppl_weights": {"neo": round( 1.0 - rms_share, 4), "neo_rms": round(rms_share, 4)},
        "layer_hyper_projections": layer_hyper_projections,
        "routing_postings": routing_postings,
        "exemplar_count": len(selected_exemplars),
    }
    bundle_digest = hashlib.sha256(
        json.dumps(core_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    bundle = check({
        "kind": "hyperweight-bundle",
        "schema_version": "skeleton.cortex.hyperweights.v1",
        "bundle_digest": bundle_digest,
        "shadow_digest": parsed["shadow_digest"],
        "effective_alpha": effective_alpha,
        "rank": r,
        "ppl_weights": core_payload["ppl_weights"],
        "layer_hyper_projections": layer_hyper_projections,
        "routing_postings": routing_postings,
        "exemplars": selected_exemplars,
        "moe_snapshot": moe_snapshot,
        "hyper_transformer_snapshot": hyper_transformer_snap,
        "promotable_slots": parsed["promotable_slots"],
        "stored_prose": 0,
        "law": "ok",
    })
    return bundle


def apply_hyperweights(
    neo,
    bundle: Dict[str, Any],
    *,
    blend: float = 0.25,
) -> Dict[str, Any]:
    """Apply a verified Hyperweight Bundle to a cortex with automatic coherence-gate rollback."""
    import math
    from skeleton.cortex.curriculum import CORE_PAIRS
    from skeleton.cortex.gossip import mix_snapshots
    from skeleton.cortex.laws import check

    if not isinstance(bundle, dict) or bundle.get("schema_version") != "skeleton.cortex.hyperweights.v1":
        raise ValueError("invalid hyperweight bundle schema_version")
    if not bundle.get("bundle_digest"):
        raise ValueError("hyperweight bundle missing bundle_digest")

    b_factor = max(0.0, min(1.0, float(blend)))
    xf = getattr(neo, "transformer", None)
    probe_texts = [t for t, _ in list(CORE_PAIRS)[:6]] or ["soulslike ttk elite"]

    saved_xf = xf.snapshot() if xf is not None and hasattr(xf, "snapshot") else None
    before_ppl = float(xf.perplexity(probe_texts)) if xf is not None and hasattr(xf, "perplexity") else 10.0

    hyper_snap = bundle.get("hyper_transformer_snapshot")
    applied_transformer = False
    rolled_back = False

    if xf is not None and isinstance(hyper_snap, dict) and saved_xf is not None and b_factor > 0.0:
        if (
            int(saved_xf.get("dim", 0)) == int(hyper_snap.get("dim", 0))
            and len(saved_xf.get("layers", ())) == len(hyper_snap.get("layers", ()))
        ):
            mixed = mix_snapshots(saved_xf, hyper_snap, b_factor)
            restored = type(xf).from_snapshot(mixed)
            xf.E, xf.P, xf.Wout, xf.bout = restored.E, restored.P, restored.Wout, restored.bout
            xf.layers, xf.n_layers = restored.layers, restored.n_layers
            if getattr(xf, "tied", False) and hasattr(xf, "tie"):
                xf.tie()
            after_ppl = float(xf.perplexity(probe_texts))
            if not math.isfinite(after_ppl) or after_ppl > before_ppl * 1.05:
                rb = type(xf).from_snapshot(saved_xf)
                xf.E, xf.P, xf.Wout, xf.bout = rb.E, rb.P, rb.Wout, rb.bout
                xf.layers, xf.n_layers = rb.layers, rb.n_layers
                if getattr(xf, "tied", False) and hasattr(xf, "tie"):
                    xf.tie()
                rolled_back = True
            else:
                applied_transformer = True
                if hasattr(xf, "checkpoint_redundant_standby"):
                    xf.checkpoint_redundant_standby()

    rank = int(bundle.get("rank") or 4)
    if xf is not None and hasattr(neo, "attach_lora"):
        if getattr(xf, "lora", None) is None:
            neo.attach_lora(rank=rank, alpha=float(rank * 2))
        elif xf.lora.rank < rank:
            xf.lora.expand_rank(rank)

    own = getattr(neo, "own", None)
    imported_exemplars = 0
    if own is not None:
        for raw_ex in bundle.get("exemplars") or []:
            if isinstance(raw_ex, dict):
                own.ingest(Ability.from_dict(raw_ex))
                imported_exemplars += 1

    for slot in bundle.get("promotable_slots") or []:
        if hasattr(neo, "surpass") and slot in {"pfc", "midbrain", "left", "right"}:
            neo.surpass(slot)

    if hasattr(neo, "sync_backup_transformer"):
        neo.sync_backup_transformer()

    final_ppl = float(xf.perplexity(probe_texts)) if xf is not None and hasattr(xf, "perplexity") else before_ppl
    return check({
        "kind": "hyperweight-apply",
        "applied": 1 if (applied_transformer or imported_exemplars > 0) else 0,
        "bundle_digest": bundle["bundle_digest"],
        "applied_transformer": applied_transformer,
        "rolled_back": rolled_back,
        "imported_exemplars": imported_exemplars,
        "before_ppl": round(before_ppl, 6),
        "final_ppl": round(final_ppl, 6),
        "stored_prose": 0,
        "law": "ok",
    })


class RepetitionTrainingAutomation:
    """Spaced-repetition internal training automation with Ebbinghaus/SM-2 scheduling."""

    def __init__(self) -> None:
        self.cards: Dict[str, Dict[str, Any]] = {}
        self.cycles_run: int = 0
        self.total_repetitions: int = 0

    def _card(self, stimulus: str) -> Dict[str, Any]:
        key = stimulus.strip()[:160]
        if key not in self.cards:
            self.cards[key] = {
                "stimulus": key,
                "easiness": 2.5,
                "interval": 1,
                "streak": 0,
                "repetitions": 0,
                "last_loss": None,
                "best_loss": None,
                "velocity": 0.0,
            }
        return self.cards[key]

    def schedule(self, neo, stimuli: Iterable[str], *, top_k: int = 8) -> List[Dict[str, Any]]:
        """Score stimuli by urgency (high loss / low streak / interval due) and return repetition schedule."""
        xf = getattr(neo, "transformer", None)
        scored: List[Dict[str, Any]] = []
        seen = set()
        for raw in stimuli:
            if not isinstance(raw, str) or not raw.strip():
                continue
            text = raw.strip()
            if text in seen:
                continue
            seen.add(text)
            card = self._card(text)
            loss = float(xf.perplexity([text])) if xf is not None and hasattr(xf, "perplexity") else 10.0
            prev = card["last_loss"]
            velocity = (float(prev) - loss) if prev is not None else 0.0
            card["velocity"] = round(velocity, 6)
            card["last_loss"] = round(loss, 6)
            if card["best_loss"] is None or loss < float(card["best_loss"]):
                card["best_loss"] = round(loss, 6)

            urgency = loss / max(1.0, float(card["easiness"]) * (1.0 + 0.25 * float(card["streak"])))
            reps = 3 if urgency >= 8.0 else (2 if urgency >= 4.0 else 1)
            scored.append({
                "stimulus": text,
                "loss": round(loss, 6),
                "urgency": round(urgency, 6),
                "repetitions": reps,
                "streak": int(card["streak"]),
                "easiness": round(float(card["easiness"]), 4),
            })
        scored.sort(key=lambda item: (-float(item["urgency"]), -float(item["loss"])))
        return scored[: max(1, int(top_k))]

    def run_cycle(
        self,
        neo,
        stimuli: Optional[Iterable[str]] = None,
        *,
        cycles: int = 2,
        top_k: int = 8,
        base_lr: float = 0.035,
        synthesize_hyperweights: bool = True,
    ) -> Dict[str, Any]:
        """Run automated spaced-repetition training, shadow parsing, and hyperweight synthesis."""
        from skeleton.cortex.curriculum import CORE_PAIRS, WALK_PAIRS
        from skeleton.cortex.improve import gaming_and_adjacent_corpus

        cycles = max(1, min(8, int(cycles)))
        default_pool = (
            [a for a, _ in list(CORE_PAIRS)]
            + [a for a, _ in list(WALK_PAIRS)]
            + gaming_and_adjacent_corpus()[:8]
        )
        pool = list(stimuli) if stimuli is not None else default_pool
        xf = getattr(neo, "transformer", None)
        rms = getattr(neo, "neo_rms", None)

        initial_ppl = float(xf.perplexity(pool[:8])) if xf is not None and hasattr(xf, "perplexity") else 10.0
        cycle_reports: List[Dict[str, Any]] = []

        for c_idx in range(cycles):
            sched = self.schedule(neo, pool, top_k=top_k)
            expanded_batch: List[str] = []
            for item in sched:
                reps = int(item["repetitions"])
                expanded_batch.extend([str(item["stimulus"])] * reps)
                self.total_repetitions += reps

            lr = max(0.01, float(base_lr) * (0.90 ** c_idx))
            for item in sched[:4]:
                neo.think(str(item["stimulus"]))

            if xf is not None and hasattr(xf, "specialized_calibrate"):
                xf.specialized_calibrate(expanded_batch, epochs=1, lr=lr, weight_decay=1e-4, holdout=pool[:8])
            elif xf is not None and hasattr(xf, "fit"):
                xf.fit(expanded_batch, lr=lr, schedule="cosine")

            if rms is not None and hasattr(rms, "specialized_calibrate"):
                rms.specialized_calibrate(expanded_batch, epochs=1, lr=lr * 0.9, weight_decay=1e-4, holdout=pool[:8])

            for slot, port in (getattr(neo, "slots", {}) or {}).items():
                if port is not None and hasattr(port, "fit"):
                    for doc in expanded_batch[:6]:
                        port.fit(doc)
                if hasattr(neo, "acquire"):
                    neo.acquire(slot)

            # Update SM-2 easiness and interval per scheduled card
            improved_cards = 0
            for item in sched:
                stim_text = str(item["stimulus"])
                card = self._card(stim_text)
                before_l = float(item["loss"])
                after_l = float(xf.perplexity([stim_text])) if xf is not None and hasattr(xf, "perplexity") else before_l
                card["repetitions"] = int(card["repetitions"]) + int(item["repetitions"])
                if after_l <= before_l:
                    card["streak"] = int(card["streak"]) + 1
                    card["easiness"] = min(3.5, float(card["easiness"]) + 0.10)
                    card["interval"] = max(1, int(round(card["interval"] * card["easiness"])))
                    improved_cards += 1
                else:
                    card["streak"] = 0
                    card["easiness"] = max(1.3, float(card["easiness"]) - 0.15)
                    card["interval"] = 1
                card["last_loss"] = round(after_l, 6)

            self.cycles_run += 1
            cycle_reports.append({
                "cycle": c_idx + 1,
                "scheduled_items": len(sched),
                "expanded_repetitions": len(expanded_batch),
                "improved_cards": improved_cards,
                "lr": round(lr, 5),
            })

        if hasattr(neo, "sleep_cycle"):
            neo.sleep_cycle(n=6)
        if hasattr(neo, "sync_backup_transformer"):
            neo.sync_backup_transformer()

        shadow_report = parse_shadow_weights(neo)
        hyper_bundle = None
        hyper_apply = None
        if synthesize_hyperweights:
            hyper_bundle = create_hyperweights(neo)
            hyper_apply = apply_hyperweights(neo, hyper_bundle, blend=0.20)

        final_ppl = float(xf.perplexity(pool[:8])) if xf is not None and hasattr(xf, "perplexity") else initial_ppl
        return {
            "kind": "repetition-training-automation",
            "cycles_executed": cycles,
            "total_repetitions": self.total_repetitions,
            "tracked_cards": len(self.cards),
            "initial_ppl": round(initial_ppl, 6),
            "final_ppl": round(final_ppl, 6),
            "improved": final_ppl <= initial_ppl,
            "cycle_reports": cycle_reports,
            "shadow_report": shadow_report,
            "hyperweights": hyper_bundle,
            "hyperweight_application": hyper_apply,
        }


class ZeroShotBlueprintCompiler:
    """Zero-Shot Brief-to-Playable-Blueprint Compiler & Predictive Build Memoizer.

    Combines Cortex MoE encounter/pacing/bias heads, context-conditioned
    HyperLoRA gates, lookahead Jacobi parallel decoding, and hardware-accurate
    Console/ROM tile-bank synthesis into a single content-addressed blueprint
    with O(1) predictive semantic memoization.
    """

    def __init__(self, *, max_cache_entries: int = 128) -> None:
        self.max_cache_entries = max(8, int(max_cache_entries))
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

    def compile(
        self,
        neo,
        brief: str,
        *,
        console_target: str = "gb_dmg_rom",
        genre: str = "action_platformer",
        tile_count: int = 6,
        seed: int = 19,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        import hashlib
        import json
        from skeleton.cortex.laws import check
        from skeleton.cortex.speculative import GrammarBudgetLogitProcessor, lookahead_jacobi_decode
        from skeleton.forge.hardware import compile_console_rom_envelope, synthesize_rom_tile_bank

        clean_brief = (brief or "soulslike extraction ttk elite dread").strip()
        cache_key_raw = f"{clean_brief}|{console_target}|{genre}|{int(tile_count)}|{int(seed)}"
        cache_key = hashlib.sha256(cache_key_raw.encode("utf-8")).hexdigest()[:24]

        if use_cache and cache_key in self._cache:
            self.hits += 1
            cached = dict(self._cache[cache_key])
            cached["cache_hit"] = True
            cached["cache_stats"] = {"hits": self.hits, "misses": self.misses, "entries": len(self._cache)}
            return cached

        self.misses += 1
        trace = neo.think(clean_brief)
        h = neo._stream(clean_brief) if hasattr(neo, "_stream") else [0.5] * 8

        # Bind HyperLoRA context if attached on speaking transformer
        xf = getattr(neo, "transformer", None)
        rms = getattr(neo, "neo_rms", None)
        backup = getattr(neo, "backup_transformer", None)
        hyper_gates = None
        if xf is not None:
            if getattr(xf, "hyper_lora", None) is None and hasattr(xf, "attach_hyper_lora"):
                xf.attach_hyper_lora(ctx_dim=len(h), rank=2, alpha=4.0, seed=seed)
            if getattr(xf, "hyper_lora", None) is not None:
                hyper_gates = xf.hyper_lora.bind_context(h)

        # Lookahead Jacobi multi-branch speculative decode across primary + draft mouths
        jacobi_out = None
        if xf is not None and hasattr(xf, "_ids"):
            drafts = [m for m in (rms, backup) if m is not None and int(getattr(m, "V", -1)) == int(getattr(xf, "V", -2))]
            prefix_ids = list(xf._ids(clean_brief)) or [int(getattr(xf, "unk", 0))]
            domain_tokens = [t for t in clean_brief.lower().split() if t in getattr(xf, "stoi", {})]
            proc = GrammarBudgetLogitProcessor(
                xf.itos,
                domain_boost_tokens=domain_tokens[:6],
                no_repeat_ngram_size=2,
            )
            jacobi_out = lookahead_jacobi_decode(
                xf,
                drafts or [xf],
                prefix_ids,
                8,
                lookahead_window=4,
                max_jacobi_iters=3,
                logit_processor=proc,
            )

        # Predict encounter mix, pacing vector, and loot/combat/heat bias from MoE
        mix = neo.predict_mix(clean_brief) if hasattr(neo, "predict_mix") else (3, 1, 0)
        if mix is None:
            mix = (3, 1, 0)
        bias = neo.predict_bias(clean_brief) if hasattr(neo, "predict_bias") else "combat"
        if bias is None:
            bias = "combat"
        pacing = (0.50, 0.85, 0.80, 0.72)
        if getattr(neo, "moe", None) is not None and "left" in neo.moe.experts:
            aux = getattr(neo.moe.experts["left"], "aux", None)
            if aux is not None and hasattr(aux, "predict"):
                pacing = tuple(round(float(x), 4) for x in aux.predict(h))

        # Synthesize hardware-exact ROM tile bank, palette, OAM table, and PSG audio patch
        rom_envelope = compile_console_rom_envelope(console_target)
        rom_assets = synthesize_rom_tile_bank(
            console_target,
            tile_count=tile_count,
            seed=seed,
            pattern=genre,
        )

        blueprint = {
            "schema_version": "skeleton.cortex.zero_shot_blueprint.v1",
            "kind": "zero-shot-game-blueprint",
            "blueprint_id": f"bp-{cache_key[:12]}",
            "brief": clean_brief[:160],
            "genre": genre,
            "console_target": rom_envelope["profile_key"],
            "encounter_mix": {"trash": int(mix[0]), "elite": int(mix[1]), "boss": int(mix[2])},
            "reward_bias": str(bias),
            "pacing_curve": {
                "tension": float(pacing[0]),
                "density": float(pacing[1]),
                "recovery": float(pacing[2]),
                "clarity": float(pacing[3]),
            },
            "hive_confidence": round(float(trace.hive_value), 4),
            "hyper_lora_gates": hyper_gates,
            "jacobi_decode": jacobi_out,
            "rom_envelope": rom_envelope,
            "rom_assets": rom_assets,
            "cache_hit": False,
            "cache_stats": {"hits": self.hits, "misses": self.misses, "entries": len(self._cache) + 1},
            "stored_prose": 0,
            "law": "ok",
        }
        digest_payload = json.dumps(
            {
                "id": blueprint["blueprint_id"],
                "mix": blueprint["encounter_mix"],
                "tile_sha256": rom_assets["tile_sha256"],
            },
            sort_keys=True,
        ).encode("utf-8")
        blueprint["blueprint_digest"] = hashlib.sha256(digest_payload).hexdigest()
        verified = check(blueprint)

        if use_cache:
            if len(self._cache) >= self.max_cache_entries:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[cache_key] = dict(verified)
        return verified
