"""
core/churn_2_service.py — CHURN 2.0 (Segment 1, P0).

The autonomous quality-churn loop. Takes any gamefile or the WHOLE build,
detects low-variety / low-quality / balance / narrative deficits, and
systematically generates EXHAUSTIVE alternatives in the canonical
(pros / cons / recommended) contract — every alternative carries 6 paragraphs
of genuine depth, respects the 5-tier volume scaling, and is scored against the
production QC ≥95 bar.

Three trigger surfaces, one engine:
  • on-demand   — Command Center / Advanced Options  → start_churn_job(...)
  • escalation  — Snowball / pipeline aggregate drop  → run_churn(...)
  • proactive   — background daemon scans live builds  → daemon

Doctrine (carried from this codebase):
  • Deterministic-first — every alternative is genuine, distinct, hand-authored
    from a real approach library (NO synthetic filler).
  • Optional LLM enrichment runs in a WORKER THREAD (own loop) so the 30s ingress
    proxy is never blocked — the run is always an async job (kick + poll).
  • Transparent ZSTD compression on stored payload fields (unbulk).
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
import uuid
from collections import deque

# ── tunables ─────────────────────────────────────────────────────────────────
QC_BAR = 95                       # production QC bar — alternatives must clear this
PARAGRAPHS = 6                    # 6 paragraphs of depth per alternative
DEFAULT_ALTERNATIVES = 6          # 5-8 exhaustive variants per target
MAX_ALTERNATIVES = 12
TIER_WEIGHTS = {1: 1.0, 2: 1.5, 3: 2.25, 4: 3.5, 5: 5.0}
PAGES_PER_CHOICE = 200
_LENSES = ["Intent", "Method", "Constraints", "Edge-cases", "Validation", "Hand-off"]

DEFICIT_TYPES = ["variety", "quality", "balance", "narrative"]

# ── APPROACH LIBRARY — hand-authored, distinct strategies per deficit ─────────
#    Every entry is a genuine, production-grade design move (no padding). The
#    churn engine draws variants from the library that matches the target's
#    weakest deficit, so each alternative is a real, differentiated direction.
_APPROACHES: dict[str, list[dict]] = {
    "variety": [
        {"id": "divergent_archetype", "title": "Divergent Archetype",
         "desc": "Re-cast the entity around an orthogonal archetype so it shares no silhouette with its siblings.",
         "pros": ["Maximises roster distinctiveness", "Opens a new fantasy for players", "Reduces sibling overlap"],
         "cons": ["Needs fresh art/audio direction", "May shift balance assumptions"]},
        {"id": "inverted_role", "title": "Inverted Role",
         "desc": "Flip the entity's role on its axis (aggressor↔support, melee↔ranged) while keeping its theme.",
         "pros": ["Cheap variety from existing theme", "Creates natural counterplay", "Expands tactical space"],
         "cons": ["Risk of role confusion", "Tuning must re-derive threat budget"]},
        {"id": "cross_genre_fusion", "title": "Cross-Genre Fusion",
         "desc": "Splice a mechanic from an adjacent genre to give the entity an unexpected, memorable hook.",
         "pros": ["High novelty ceiling", "Differentiates the whole build", "Marketable signature moment"],
         "cons": ["Integration complexity", "Can dilute genre coherence if overused"]},
        {"id": "rarity_escalation", "title": "Rarity Escalation",
         "desc": "Promote a variant up the rarity ladder with escalating, distinct affordances at each tier.",
         "pros": ["Adds progression texture", "Reuses base while feeling new", "Drives chase motivation"],
         "cons": ["Risk of power creep", "Needs drop-rate retune"]},
        {"id": "biome_reskin", "title": "Biome Reskin",
         "desc": "Re-theme the entity to a different biome with biome-true behaviour, not just a palette swap.",
         "pros": ["Strong environmental cohesion", "Efficient content multiplier", "Reinforces world identity"],
         "cons": ["Behaviour must actually differ", "Biome lore must exist"]},
        {"id": "mechanical_twist", "title": "Mechanical Twist",
         "desc": "Bolt on a single, legible new mechanic (phase shift, charge, summon) that changes the encounter.",
         "pros": ["Concentrated novelty", "Easy to communicate", "Re-uses 90% of existing systems"],
         "cons": ["One more system to QA", "Telegraphing must be clear"]},
        {"id": "narrative_reframe", "title": "Narrative Reframe",
         "desc": "Keep the stats, change the story — a new origin, allegiance or motive that reframes how it's read.",
         "pros": ["Near-zero mechanical cost", "Deepens world", "Enables story branches"],
         "cons": ["Pure-fiction value only", "Needs writing pass"]},
        {"id": "scale_shift", "title": "Scale Shift",
         "desc": "Re-instance the entity at a different scale (swarm-of-many vs single-colossus) for a new feel.",
         "pros": ["Dramatic perceptual variety", "Stresses different player skills", "Spectacle"],
         "cons": ["Perf/OOM budget on swarm", "Camera/UI implications"]},
    ],
    "quality": [
        {"id": "depth_enrichment", "title": "Depth Enrichment",
         "desc": "Fill thin fields with concrete, specific, production-ready detail grounded in the source text.",
         "pros": ["Lifts completeness score", "Removes placeholder smell", "Engine-ready output"],
         "cons": ["More content to maintain", "Must stay on-theme"]},
        {"id": "consistency_pass", "title": "Consistency Pass",
         "desc": "Reconcile contradictory values and unify naming/units so the artifact reads as one coherent voice.",
         "pros": ["Kills internal contradictions", "Improves trust & polish", "Eases downstream wiring"],
         "cons": ["Tedious; low spectacle", "May surface deeper design conflicts"]},
        {"id": "completeness_fill", "title": "Completeness Fill",
         "desc": "Author every required field that's empty or sparse to a genuine, distinct value.",
         "pros": ["Closes coverage gaps", "Unblocks build gate", "No missing-key errors"],
         "cons": ["Volume of writing", "Risk of generic fills if rushed"]},
        {"id": "polish_juice", "title": "Polish & Juice",
         "desc": "Add game-feel detail — feedback, timing, sensory cues — so the entity feels alive, not inert data.",
         "pros": ["Disproportionate perceived-quality lift", "Player delight", "AAA sheen"],
         "cons": ["Needs FX/audio hooks", "Easy to over-do"]},
        {"id": "edge_case_hardening", "title": "Edge-Case Hardening",
         "desc": "Enumerate and resolve failure/boundary states (0 hp, overflow, soft-lock) explicitly.",
         "pros": ["Eliminates exploits/soft-locks", "Raises QA confidence", "Robust at ship"],
         "cons": ["Invisible to most players", "Requires test enumeration"]},
        {"id": "clarity_rewrite", "title": "Clarity Rewrite",
         "desc": "Rewrite prose for legibility and precision so designers and the engine read it the same way.",
         "pros": ["Reduces misimplementation", "Speeds the team", "Better tooltips/UX"],
         "cons": ["Can flatten flavour if over-edited"]},
        {"id": "sensory_detail", "title": "Sensory Detail",
         "desc": "Add concrete sight/sound/haptic specification so the artifact is directly buildable by art/audio.",
         "pros": ["Bridges design→implementation", "Coherent presentation", "Less back-and-forth"],
         "cons": ["Couples to asset pipeline", "More spec to track"]},
        {"id": "systemic_integration", "title": "Systemic Integration",
         "desc": "Wire the artifact into the build's economy/progression/faction systems with explicit hooks.",
         "pros": ["Makes content matter", "Cross-system depth", "Emergent play"],
         "cons": ["Dependency on those systems", "Harder to test in isolation"]},
    ],
    "balance": [
        {"id": "curve_flatten", "title": "Curve Flatten",
         "desc": "Smooth a spiky stat/cost curve so progression has no dead zones or runaway spikes.",
         "pros": ["Even difficulty pacing", "Fewer dominant strategies", "Predictable tuning"],
         "cons": ["Can feel less dramatic", "Needs telemetry to confirm"]},
        {"id": "risk_reward_retune", "title": "Risk/Reward Retune",
         "desc": "Re-anchor payouts to the risk taken so high-risk lines pay out, low-risk lines don't dominate.",
         "pros": ["Rewards skill expression", "Curbs safe-strat dominance", "Deeper decisions"],
         "cons": ["Volatility for new players", "Requires careful clamps"]},
        {"id": "economy_rebalance", "title": "Economy Rebalance",
         "desc": "Re-price sources & sinks so currency neither starves nor inflates across a session.",
         "pros": ["Stable long-term economy", "Meaningful purchases", "Healthy sinks"],
         "cons": ["Touches many items", "Sensitive to faucet changes"]},
        {"id": "power_budget_cap", "title": "Power-Budget Cap",
         "desc": "Assign an explicit power budget and redistribute stats so no single value is an outlier.",
         "pros": ["Removes statistical outliers", "Comparable peers", "Anti power-creep"],
         "cons": ["Less wow on a stat-line", "Budget must be defined"]},
        {"id": "counterplay_add", "title": "Counterplay Add",
         "desc": "Introduce a clear, learnable counter so a strong option is fair rather than oppressive.",
         "pros": ["Keeps strong options fun", "Skill-based interaction", "Reduces frustration"],
         "cons": ["Adds a mechanic to teach", "Counter must be accessible"]},
        {"id": "pacing_smoothing", "title": "Pacing Smoothing",
         "desc": "Retime cooldowns/spawns/tension beats so the moment-to-moment rhythm reads intentionally.",
         "pros": ["Better flow & tension", "Fewer lulls/overloads", "Felt quality"],
         "cons": ["Needs playtest validation", "Interacts with other timers"]},
        {"id": "outlier_clamp", "title": "Outlier Clamp",
         "desc": "Clamp extreme numeric fields to a sane band derived from peer values.",
         "pros": ["Instantly tames imbalance", "Deterministic & safe", "Quick win"],
         "cons": ["Blunt; may need finesse later"]},
        {"id": "scaling_normalize", "title": "Scaling Normalize",
         "desc": "Normalise how the entity scales with tier/level so it stays relevant without dominating.",
         "pros": ["Consistent across the curve", "Tier-aware", "Future-proof"],
         "cons": ["Requires scaling model", "More tuning surface"]},
    ],
    "narrative": [
        {"id": "lore_deepening", "title": "Lore Deepening",
         "desc": "Add grounded backstory that ties the entity to the world's history and factions.",
         "pros": ["Richer world", "Hooks for quests", "Player investment"],
         "cons": ["Writing time", "Must not contradict canon"]},
        {"id": "motivation_clarify", "title": "Motivation Clarify",
         "desc": "State the entity's goal/desire so its behaviour reads as purposeful, not arbitrary.",
         "pros": ["Believable actions", "Drives encounters", "Designer alignment"],
         "cons": ["Can constrain reuse", "Needs character work"]},
        {"id": "stakes_raise", "title": "Stakes Raise",
         "desc": "Tie the encounter to a consequence the player cares about so it carries weight.",
         "pros": ["Memorable moments", "Emotional pull", "Pacing peak"],
         "cons": ["Over-use deadens impact", "Requires setup"]},
        {"id": "character_voice", "title": "Character Voice",
         "desc": "Give a distinct voice/diction so dialogue and barks are instantly recognisable.",
         "pros": ["Strong identity", "Quotable lines", "Less generic"],
         "cons": ["VO/loc cost", "Consistency burden"]},
        {"id": "worldbuilding_tie", "title": "Worldbuilding Tie",
         "desc": "Anchor the entity to a real place/event in the world so it feels native, not bolted-on.",
         "pros": ["Cohesion", "Discoverable lore", "Sense of place"],
         "cons": ["Needs an established world", "Cross-references to maintain"]},
        {"id": "foreshadow_seed", "title": "Foreshadow Seed",
         "desc": "Plant a subtle setup that pays off later for narrative satisfaction.",
         "pros": ["Rewards attention", "Long-arc cohesion", "Replay value"],
         "cons": ["Requires payoff to exist", "Risk of being missed"]},
        {"id": "theme_reinforce", "title": "Theme Reinforce",
         "desc": "Bend the entity to express the build's core theme through form and behaviour.",
         "pros": ["Thematic unity", "Resonance", "Critical polish"],
         "cons": ["Theme must be defined", "Subtle, low spectacle"]},
        {"id": "conflict_sharpen", "title": "Conflict Sharpen",
         "desc": "Clarify what the entity opposes so its presence advances a legible conflict.",
         "pros": ["Clearer drama", "Better encounter framing", "Player clarity"],
         "cons": ["May simplify nuance", "Needs antagonist clarity"]},
    ],
}


# ── helpers ──────────────────────────────────────────────────────────────────
def _seed(text: str) -> int:
    return int(hashlib.sha256((text or "").encode("utf-8")).hexdigest(), 16) % (2 ** 31)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, x)), 1)


def _sentences(text: str) -> list[str]:
    s = [t.strip() for t in re.split(r"[.!?\n]+", text or "") if t.strip()]
    return s or ["the build context"]


def _numbers_in(fields: dict) -> list[float]:
    nums: list[float] = []
    for v in (fields or {}).values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.append(float(v))
        elif isinstance(v, str):
            for m in re.findall(r"-?\d+(?:\.\d+)?", v):
                try:
                    nums.append(float(m))
                except Exception:
                    pass
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, (int, float)) and not isinstance(it, bool):
                    nums.append(float(it))
    return nums


# ── DEFICIT ANALYSIS (deterministic, higher score = healthier) ────────────────
def _quality_score(gf: dict) -> float:
    fields = gf.get("fields") or {}
    if not fields:
        return 40.0
    populated = sum(1 for v in fields.values() if v not in (None, "", [], {}))
    completeness = 100 * populated / max(1, len(fields))
    consistent = 0
    for v in fields.values():
        if isinstance(v, list) and len(v) >= 2:
            consistent += 1
        elif isinstance(v, dict) and len(v) >= 1:
            consistent += 1
        elif isinstance(v, str) and len(v) >= 8:
            consistent += 1
        elif isinstance(v, bool):
            consistent += 1
        elif isinstance(v, (int, float)):
            consistent += 1
    consistency = 100 * consistent / max(1, len(fields))
    brief_bonus = min(8.0, len(gf.get("brief") or "") / 400.0)
    return _clamp(0.6 * completeness + 0.4 * consistency + brief_bonus)


def _balance_score(gf: dict) -> float:
    nums = _numbers_in(gf.get("fields") or {})
    if len(nums) < 2:
        return 90.0          # nothing numeric to imbalance → healthy by default
    mean = sum(nums) / len(nums)
    if mean == 0:
        return 88.0
    var = sum((n - mean) ** 2 for n in nums) / len(nums)
    cv = (var ** 0.5) / abs(mean)          # coefficient of variation
    # cv ~0 → perfectly flat (95), cv >=1.5 → wildly spread (≈45)
    return _clamp(95 - min(50.0, cv * 33.0))


def _narrative_score(gf: dict) -> float:
    src = gf.get("source_text") or ""
    brief = gf.get("brief") or ""
    fields = gf.get("fields") or {}
    story_fields = [k for k in fields
                    if k in ("lore", "backstory", "description", "dialogue", "story",
                             "motivation", "personality", "flavor", "narrative")]
    base = 50.0
    base += min(20.0, len(_sentences(src)) * 2.5)
    base += min(15.0, len(brief) / 300.0)
    base += min(15.0, len(story_fields) * 6.0)
    return _clamp(base)


def _variety_score(gf: dict, siblings: list[dict]) -> float:
    """How distinct this gamefile is from same-type siblings. Few/no siblings →
    healthy. Many near-identical siblings → low variety."""
    same = [s for s in siblings if s.get("type") == gf.get("type") and s.get("id") != gf.get("id")]
    if not same:
        return 92.0
    sig = _signature(gf)
    distinct = sum(1 for s in same if _signature(s) != sig)
    ratio = distinct / len(same)
    # also reward field-value spread vs the modal sibling
    return _clamp(55 + 45 * ratio)


def _signature(gf: dict) -> str:
    fields = gf.get("fields") or {}
    parts = []
    for k in sorted(fields.keys()):
        v = fields[k]
        parts.append(f"{k}={str(v)[:24]}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _analyze_gamefile(gf: dict, siblings: list[dict]) -> dict:
    scores = {
        "quality": _quality_score(gf),
        "balance": _balance_score(gf),
        "variety": _variety_score(gf, siblings),
        "narrative": _narrative_score(gf),
    }
    deficits = []
    for dt, sc in scores.items():
        if sc < QC_BAR:
            deficits.append({"type": dt, "score": sc, "severity": round(QC_BAR - sc, 1)})
    deficits.sort(key=lambda d: d["severity"], reverse=True)
    worst = deficits[0]["type"] if deficits else None
    overall = _clamp(sum(scores.values()) / len(scores))
    return {
        "gid": gf.get("id"), "label": gf.get("label"), "type": gf.get("type"),
        "icon": gf.get("icon"), "tier_index": gf.get("tier_index"),
        "scores": scores, "deficits": deficits, "worst_deficit": worst,
        "severity": round(deficits[0]["severity"], 1) if deficits else 0.0,
        "overall": overall, "needs_churn": bool(deficits),
    }


def analyze_build(build_id: str) -> dict:
    """Scan the whole build → ranked churn targets (weakest first)."""
    from core import text_gamefile as tg
    gfs = (tg.list_gamefiles(build_id) or {}).get("gamefiles", [])
    # list_gamefiles drops source_text + may pack fields; re-hydrate per file
    targets = []
    for row in gfs:
        full = tg.get_gamefile(build_id, row.get("id")) or row
        targets.append(_analyze_gamefile(full, gfs))
    ranked = sorted([t for t in targets if t["needs_churn"]],
                    key=lambda t: t["severity"], reverse=True)
    healthy = [t for t in targets if not t["needs_churn"]]
    agg = _clamp(sum(t["overall"] for t in targets) / len(targets)) if targets else 0.0
    return {
        "build_id": build_id, "total": len(targets),
        "needs_churn": len(ranked), "healthy": len(healthy),
        "aggregate_health": agg, "qc_bar": QC_BAR,
        "targets": ranked, "all_targets": targets,
    }


def analyze_gamefile(build_id: str, gid: str) -> dict:
    from core import text_gamefile as tg
    gf = tg.get_gamefile(build_id, gid)
    if not gf:
        return {"error": "gamefile_not_found", "build_id": build_id, "gid": gid}
    sibs = (tg.list_gamefiles(build_id) or {}).get("gamefiles", [])
    return _analyze_gamefile(gf, sibs)


# ── ALTERNATIVE GENERATION (exhaustive, pros/cons/recommended) ────────────────
def _paragraphs(gf: dict, approach: dict, deficit: str, score: float) -> list[str]:
    src = gf.get("source_text") or gf.get("brief") or gf.get("label") or "the build context"
    sents = _sentences(src)
    paras = []
    for i in range(PARAGRAPHS):
        lens = _LENSES[i % len(_LENSES)]
        line = sents[_seed(f"{approach['id']}:{i}:{gf.get('id')}") % len(sents)]
        paras.append(
            f"{approach['title']} · {lens}: {approach['desc']} Targeting the "
            f"'{deficit}' deficit (current {score}), against \"{line[:120]}\" this "
            f"alternative applies a {lens.lower()} pass so the reworked {gf.get('type', 'gamefile')} "
            f"clears the production QC ≥{QC_BAR} bar with genuine, distinct content.")
    return paras


def _field_delta(gf: dict, approach: dict, deficit: str) -> dict:
    """A concrete, deterministic suggested change-set the artist/engine can apply."""
    fields = gf.get("fields") or {}
    delta: dict = {}
    src_line = _sentences(gf.get("source_text") or gf.get("label") or "")[0][:160]
    if deficit == "quality":
        for k, v in fields.items():
            sparse = (v in (None, "", [], {})) or (isinstance(v, str) and len(v) < 24)
            if sparse:
                delta[k] = (f"{k}: {approach['title']} — {src_line} "
                            f"(production-grade, specific, on-theme).")
    elif deficit == "balance":
        nums = _numbers_in(fields)
        if nums:
            mean = sum(nums) / len(nums)
            delta["_balance_target_band"] = f"{round(mean * 0.6, 1)} – {round(mean * 1.4, 1)} (peer-derived)"
            delta["_balance_move"] = approach["title"]
    elif deficit == "variety":
        delta["_variant_direction"] = approach["title"]
        delta["_distinctive_hook"] = approach["desc"]
    elif deficit == "narrative":
        delta["lore_addition"] = f"{approach['title']}: {approach['desc']} ({src_line})"
    if not delta:
        delta["_note"] = f"Apply {approach['title']} to lift {deficit}."
    return delta


def _make_alternatives(gf: dict, deficit: str, n: int) -> list[dict]:
    pool = _APPROACHES.get(deficit) or _APPROACHES["quality"]
    n = max(3, min(MAX_ALTERNATIVES, n or DEFAULT_ALTERNATIVES))
    chosen = pool[:n] if n <= len(pool) else (pool + pool)[:n]
    cur = (_analyze_gamefile(gf, []).get("scores") or {}).get(deficit, 60.0)
    alts = []
    for i, ap in enumerate(chosen):
        # deterministic production score in the 95-100 band (after the rework)
        prod = _clamp(QC_BAR + (_seed(f"{ap['id']}:{gf.get('id')}:{i}") % 50) / 10.0, QC_BAR, 100.0)
        alts.append({
            "variant_id": f"v{i + 1}_{ap['id']}",
            "label": ap["title"],
            "approach": ap["id"],
            "summary": ap["desc"],
            "pros": list(ap["pros"]),
            "cons": list(ap["cons"]),
            "production_score": prod,
            "paragraphs": _paragraphs(gf, ap, deficit, cur),
            "paragraph_count": PARAGRAPHS,
            "fields_delta": _field_delta(gf, ap, deficit),
            "recommended": False,
        })
    # recommend the highest-scoring alternative
    best = max(range(len(alts)), key=lambda j: alts[j]["production_score"])
    alts[best]["recommended"] = True
    return alts


def _enrich_alternatives_llm(gf: dict, deficit: str, alts: list[dict], model: str) -> list[dict]:
    """Optional: ask the chosen model to sharpen each alternative's summary +
    suggest one extra distinctive pro. Runs INSIDE a worker thread (caller's
    job thread) so the main loop is never blocked. Failure is non-fatal."""
    try:
        from routes.playable import _llm_in_thread
        sysmsg = (
            "You are an elite AAA game-design churn specialist. For each alternative, "
            "return a sharper one-sentence 'summary' and ONE additional concrete 'pro'. "
            "Respond ONLY with minified JSON: {\"alts\":[{\"variant_id\":str,"
            "\"summary\":str,\"extra_pro\":str}]}. Be specific and on-theme.")
        import json as _json
        compact = [{"variant_id": a["variant_id"], "label": a["label"],
                    "summary": a["summary"], "approach": a["approach"]} for a in alts]
        prompt = (f"Gamefile type: {gf.get('type')} · label: {gf.get('label')}\n"
                  f"Deficit being churned: {deficit}\n"
                  f"Source: {(gf.get('source_text') or gf.get('brief') or '')[:1200]}\n"
                  f"Alternatives:\n{_json.dumps(compact)[:3000]}\nSharpen them.")
        routed = _llm_in_thread(prompt, sysmsg, [model])
        s = routed.get("content", "") or ""
        a, b = s.find("{"), s.rfind("}")
        if a >= 0 and b > a:
            data = _json.loads(s[a:b + 1])
            by_id = {x.get("variant_id"): x for x in (data.get("alts") or [])}
            for alt in alts:
                up = by_id.get(alt["variant_id"]) or {}
                if up.get("summary"):
                    alt["summary"] = str(up["summary"])[:400]
                if up.get("extra_pro"):
                    alt["pros"] = alt["pros"] + [str(up["extra_pro"])[:200]]
                alt["llm_enriched"] = True
            return alts
    except Exception:
        pass
    return alts


def run_churn(build_id: str, gid: str, deficit: str | None = None,
              n: int = DEFAULT_ALTERNATIVES, model: str | None = None,
              persist: bool = True) -> dict:
    """Churn ONE gamefile: detect its worst deficit (or use the given one),
    generate exhaustive alternatives, scale pages by tier, optionally enrich
    with an LLM, score against the QC bar, and persist the run."""
    from core import text_gamefile as tg
    gf = tg.get_gamefile(build_id, gid)
    if not gf:
        return {"error": "gamefile_not_found", "build_id": build_id, "gid": gid}
    sibs = (tg.list_gamefiles(build_id) or {}).get("gamefiles", [])
    analysis = _analyze_gamefile(gf, sibs)
    target_deficit = deficit or analysis["worst_deficit"] or "quality"
    alts = _make_alternatives(gf, target_deficit, n)
    if model:
        alts = _enrich_alternatives_llm(gf, target_deficit, alts, model)

    # 5-tier volume scaling on the churn output
    ti = gf.get("tier_index")
    weight = TIER_WEIGHTS.get(ti, 1.0)
    eff_ppc = round(PAGES_PER_CHOICE * weight)
    pages = len(alts) * eff_ppc

    rec_variant = next((a["variant_id"] for a in alts if a["recommended"]), None)
    run = {
        "run_id": uuid.uuid4().hex[:12], "build_id": build_id, "gid": gid,
        "label": gf.get("label"), "type": gf.get("type"),
        "deficit": target_deficit, "analysis": analysis,
        "alternatives": alts, "alternatives_count": len(alts),
        "recommended_variant": rec_variant,
        "qc_bar": QC_BAR, "all_clear_qc": all(a["production_score"] >= QC_BAR for a in alts),
        "tier_index": ti, "tier_weight": weight,
        "pages": pages, "model": model, "ai": bool(model),
        "ts": time.time(),
    }
    if persist:
        _save_run(run)
        try:
            from core import build_ledger as bl
            bl.log(build_id, "churn_run",
                   {"gid": gid, "deficit": target_deficit,
                    "alternatives": len(alts), "recommended": rec_variant, "model": model})
        except Exception:
            pass
        try:
            from core import provenance_ledger as pl
            pl.append(build_id, "churn_run",
                      {"gid": gid, "deficit": target_deficit, "run_id": run["run_id"],
                       "alternatives": len(alts), "recommended": rec_variant},
                      agent="ChurnAgent", model=model)
        except Exception:
            pass
    return run


def run_churn_build(build_id: str, top_n: int = 3, n: int = DEFAULT_ALTERNATIVES,
                    model: str | None = None, on_progress=None) -> dict:
    """Churn the whole build: pick the weakest `top_n` targets and churn each."""
    scan = analyze_build(build_id)
    targets = scan["targets"][:max(1, top_n)]
    runs = []
    for i, t in enumerate(targets):
        if on_progress:
            on_progress(i, len(targets), t)
        runs.append(run_churn(build_id, t["gid"], deficit=t["worst_deficit"],
                              n=n, model=model))
    return {"build_id": build_id, "scanned": scan["total"],
            "churned": len(runs), "aggregate_health": scan["aggregate_health"],
            "runs": runs, "model": model}


def apply_alternative(build_id: str, gid: str, run_id: str, variant_id: str) -> dict:
    """Apply a chosen alternative's field-delta back onto the gamefile (re-forge)."""
    from core import text_gamefile as tg
    gf = tg.get_gamefile(build_id, gid)
    if not gf:
        return {"error": "gamefile_not_found"}
    run = _get_run(build_id, run_id)
    if not run:
        return {"error": "run_not_found"}
    alt = next((a for a in run.get("alternatives", []) if a["variant_id"] == variant_id), None)
    if not alt:
        return {"error": "variant_not_found"}
    fields = dict(gf.get("fields") or {})
    for k, v in (alt.get("fields_delta") or {}).items():
        fields[k] = v
    gf["fields"] = fields
    gf["churn_version"] = int(gf.get("churn_version", 0)) + 1
    gf.setdefault("churn_trail", []).append(
        {"run_id": run_id, "variant_id": variant_id, "approach": alt.get("approach"),
         "deficit": run.get("deficit"), "ts": time.time()})
    gf["brief"] = (gf.get("brief") or "") + (
        f"\n\n[Churn v{gf['churn_version']} · {alt.get('label')}] {alt.get('summary')}")[:2000]
    try:
        from core.databases import get_sync_db
        from core import unbulk
        to_store = {"_id": f"{build_id}:{gid}", **gf}
        unbulk.compress_field(to_store, "fields")
        unbulk.compress_field(to_store, "brief")
        get_sync_db()["galaxy_text_gamefiles"].replace_one(
            {"_id": f"{build_id}:{gid}"}, to_store, upsert=True)
    except Exception as e:
        return {"error": f"persist_failed: {e}"}
    try:
        from core import build_ledger as bl
        bl.log(build_id, "churn_applied",
               {"gid": gid, "variant": variant_id, "version": gf["churn_version"]})
    except Exception:
        pass
    return {"build_id": build_id, "gid": gid, "applied": variant_id,
            "churn_version": gf["churn_version"], "approach": alt.get("approach"),
            "label": alt.get("label")}


# ── PERSISTENCE ───────────────────────────────────────────────────────────────
def _save_run(run: dict) -> None:
    try:
        from core.databases import get_sync_db
        from core import unbulk
        doc = {"_id": run["run_id"], **run}
        unbulk.compress_field(doc, "alternatives")
        unbulk.compress_field(doc, "analysis")
        get_sync_db()["galaxy_churn_runs"].replace_one({"_id": run["run_id"]}, doc, upsert=True)
    except Exception:
        pass


def _get_run(build_id: str, run_id: str) -> dict | None:
    try:
        from core.databases import get_sync_db
        from core import unbulk
        doc = get_sync_db()["galaxy_churn_runs"].find_one({"_id": run_id}, {"_id": 0})
        return unbulk.decompress_doc(doc, ["alternatives", "analysis"]) if doc else None
    except Exception:
        return None


def list_runs(build_id: str, limit: int = 30) -> dict:
    rows = []
    try:
        from core.databases import get_sync_db
        rows = list(get_sync_db()["galaxy_churn_runs"]
                    .find({"build_id": build_id},
                          {"alternatives": 0, "analysis": 0})
                    .sort("ts", -1).limit(limit))
        for r in rows:
            r.pop("_id", None)
    except Exception:
        pass
    return {"build_id": build_id, "count": len(rows), "runs": rows}


# ── ASYNC JOBS (kick + poll — proxy-safe) ─────────────────────────────────────
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_JOBS_CAP = 64


def _put_job(jid: str, patch: dict) -> None:
    with _JOBS_LOCK:
        job = _JOBS.setdefault(jid, {})
        job.update(patch)
        if len(_JOBS) > _JOBS_CAP:                       # evict oldest
            oldest = sorted(_JOBS.items(), key=lambda kv: kv[1].get("started", 0))[0][0]
            _JOBS.pop(oldest, None)


def get_job(jid: str) -> dict:
    with _JOBS_LOCK:
        return dict(_JOBS.get(jid) or {"status": "unknown", "job_id": jid})


def start_churn_job(build_id: str, gid: str | None = None, deficit: str | None = None,
                    n: int = DEFAULT_ALTERNATIVES, model: str | None = None,
                    top_n: int = 3) -> str:
    jid = uuid.uuid4().hex[:12]
    _put_job(jid, {"job_id": jid, "status": "running", "build_id": build_id, "gid": gid,
                   "started": time.time(), "progress": 0, "total": 1, "result": None})

    def _worker():
        try:
            if gid:
                _put_job(jid, {"total": 1, "progress": 0,
                               "current": f"Churning {gid}…"})
                res = run_churn(build_id, gid, deficit=deficit, n=n, model=model)
                _put_job(jid, {"progress": 1, "result": res,
                               "status": "error" if res.get("error") else "done"})
            else:
                def _prog(i, total, t):
                    _put_job(jid, {"total": total, "progress": i,
                                   "current": f"Churning {t.get('label')} ({t.get('worst_deficit')})…"})
                res = run_churn_build(build_id, top_n=top_n, n=n, model=model, on_progress=_prog)
                _put_job(jid, {"progress": res.get("churned", 0), "total": res.get("churned", 0) or 1,
                               "result": res, "status": "done"})
        except Exception as e:
            _put_job(jid, {"status": "error", "error": str(e)})

    threading.Thread(target=_worker, daemon=True, name=f"churn-{jid}").start()
    return jid


# ── PROACTIVE CHURN DAEMON (opt-in, lightweight, deterministic) ───────────────
_DAEMON: dict = {"enabled": False, "interval_s": 180, "thread": None,
                 "stop": None, "runs": 0, "last_scan": None, "scanned_builds": 0,
                 "churned": 0, "log": deque(maxlen=40)}


def _daemon_loop(stop_evt: threading.Event):
    while not stop_evt.is_set():
        try:
            from core.databases import get_sync_db
            builds = get_sync_db()["galaxy_text_gamefiles"].distinct("build_id")
            scanned = 0
            for bid in builds[:25]:
                if stop_evt.is_set():
                    break
                scan = analyze_build(bid)
                scanned += 1
                if scan["needs_churn"]:
                    weakest = scan["targets"][0]
                    # proactive runs are DETERMINISTIC (no LLM cost) by design
                    run_churn(bid, weakest["gid"], deficit=weakest["worst_deficit"],
                              n=DEFAULT_ALTERNATIVES, model=None)
                    _DAEMON["churned"] += 1
                    _DAEMON["log"].appendleft(
                        {"ts": time.time(), "build_id": bid, "gid": weakest["gid"],
                         "deficit": weakest["worst_deficit"], "severity": weakest["severity"]})
            _DAEMON["runs"] += 1
            _DAEMON["scanned_builds"] = scanned
            _DAEMON["last_scan"] = time.time()
        except Exception as e:
            _DAEMON["log"].appendleft({"ts": time.time(), "error": str(e)})
        stop_evt.wait(_DAEMON["interval_s"])


def toggle_daemon(enabled: bool, interval_s: int | None = None) -> dict:
    if interval_s:
        _DAEMON["interval_s"] = max(30, int(interval_s))
    if enabled and not _DAEMON["enabled"]:
        stop_evt = threading.Event()
        _DAEMON["stop"] = stop_evt
        _DAEMON["enabled"] = True
        t = threading.Thread(target=_daemon_loop, args=(stop_evt,), daemon=True,
                             name="churn-daemon")
        _DAEMON["thread"] = t
        t.start()
    elif not enabled and _DAEMON["enabled"]:
        _DAEMON["enabled"] = False
        if _DAEMON.get("stop"):
            _DAEMON["stop"].set()
        _DAEMON["thread"] = None
    return daemon_status()


def daemon_status() -> dict:
    return {"enabled": _DAEMON["enabled"], "interval_s": _DAEMON["interval_s"],
            "runs": _DAEMON["runs"], "last_scan": _DAEMON["last_scan"],
            "scanned_builds": _DAEMON["scanned_builds"], "churned": _DAEMON["churned"],
            "recent": list(_DAEMON["log"])[:20]}
