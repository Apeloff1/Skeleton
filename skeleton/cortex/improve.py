"""Improve — "like Elden Ring" raises the house, not a copy of the game.

Aspects that move: neo/rms ppl, steps, genos G, era dialect, mix heads.
Aspects that must not move: third-party prose, secrets, assets.
Order-of-magnitude is the trajectory target. Laws gate every write.
"""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.cortex.antiplag import distill_dialect, guard
from skeleton.cortex.laws import LawError, check
from skeleton.cortex.refs import lookup, record_provenance

MAX_IMPROVE_ROUNDS = 256
MAX_IMPROVE_STIMULUS_CHARS = 32_768

ASPECTS = {
    "soulslike": (
        "soulslike ttk elite dread bonfire rest extraction heat",
        "plan tensor hp dps stagger posture",
        "walk fog gate elite pack trash mix",
    ),
    "roguelike": (
        "roguelike lattice mix trash elite boss seed",
        "plan tensor ttk heat run reset",
        "shop relic floor climb",
    ),
    "metroidvania": (
        "metroidvania backtrack map lock key",
        "plan tensor exploration pack ability gate",
        "room graph traversal",
    ),
    "extraction_now": (
        "extraction_now ttk elite dread extract extract",
        "plan tensor loot heat zone timer",
        "squad wipe extract window",
    ),
    "cozy": (
        "cozy harvest era crop season",
        "plan tensor day cycle gift",
        "town route rest",
    ),
    "cozy_wholesome": (
        "cozy harvest era crop season",
        "plan tensor day cycle gift",
        "town route rest",
    ),
    "boomer_shooter": (
        "boomer_shooter movement gun poetry ttk trash speed",
        "plan tensor arena strafe rocket armor pickup",
        "mix trash=6 elite=1 boss=0 slack=0.82",
    ),
    "arcade_golden_age": (
        "arcade_golden_age score attack ttk trash wave",
        "plan tensor coin multiplier high score",
        "mix trash=2 elite=0 boss=0 slack=0.88",
    ),
    "horror_survival": (
        "horror_survival dread scarcity heat vent ammo",
        "plan tensor safe room stalker elite tension",
        "walk collapse extract late lock door bound",
    ),
    "immersive_sim": (
        "immersive_sim systemic emergent vent hack stealth",
        "plan tensor physics simulation stackable verbs",
        "room graph traversal multi solution",
    ),
    "crpg": (
        "crpg party initiative turn tactical dice check",
        "plan tensor build dialogue branch companion",
        "mix trash=4 elite=2 boss=0 slack=0.74",
    ),
    "tactics_grid": (
        "tactics_grid elevation flanking cover action points",
        "plan tensor squad turn order overwatch",
        "mix trash=5 elite=2 boss=0 slack=0.76",
    ),
    "fighting_game": (
        "fighting_game frame data hitconfirm neutral rollback",
        "plan tensorspacing punish cancel meter",
        "HP = DPS x TTK mix trash=0 elite=1 boss=1",
    ),
    "bullet_heaven": (
        "bullet_heaven swarm synergy evolutionxp magnet",
        "plan tensor horde density cooldown scaling",
        "mix trash=8 elite=2 boss=0 slack=0.79",
    ),
    "deckbuilder": (
        "deckbuilder draw mana exhaust relic synergy",
        "plan tensor turn energy curve boss act",
        "shop relic floor climb",
    ),
    "city_builder": (
        "city_builder logistics road zoning throughput grid",
        "plan tensor supply chain bottleneck happiness",
        "era feel spatial gestalt layout",
    ),
    "grand_strategy": (
        "grand_strategy diplomacy attrition supply front",
        "plan tensor map theatre economy tick",
        "era feel spatial gestalt layout",
    ),
}

GAME_ADJACENT_ASPECTS = {
    "netcode_rollback": (
        "rollback netcode determinism input delay state snapshot",
        "plan tensor tick prediction reconciliation",
    ),
    "procedural_generation": (
        "wave function collapse room graph seed biome lattice",
        "plan tensor constraint solver dungeon layout",
    ),
    "shader_pipeline": (
        "shader framegraph pbr lighting roughness shadow cascade",
        "plan tensor gpu drawcall batch occlusion",
    ),
    "physics_simulation": (
        "rigidbody ragdoll collision broadphase solver constraint",
        "plan tensor impulse velocity verlet tick",
    ),
    "ai_director_pacing": (
        "ai director stress peak relax horde pacing curve",
        "plan tensor ttk heat vent spawn budget",
    ),
    "spatial_audio": (
        "spatial audio occlusion reverb footstep threat cue",
        "plan tensor attenuation doppler mix bus",
    ),
    "economy_telemetry": (
        "economy sink faucet drop rate retention telemetry",
        "plan tensor loot bias progression curve",
    ),
}


def gaming_and_adjacent_corpus() -> List[str]:
    """Curated gaming and game-adjacent dialect corpus for beneficial weight priors."""
    out: List[str] = []
    for rows in ASPECTS.values():
        out.extend(rows)
    for rows in GAME_ADJACENT_ASPECTS.values():
        out.extend(rows)
    seen = set()
    dedup: List[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup


def apply_gaming_priors(neo, *, rounds: int = 2) -> Dict[str, Any]:
    """Find and apply beneficial gaming & game-adjacent weights across cortex & MoE."""
    from skeleton.cortex.curriculum import CORE_PAIRS, WALK_PAIRS

    rounds = max(1, min(16, int(rounds)))
    corpus = gaming_and_adjacent_corpus()
    core_texts = [a for a, _ in CORE_PAIRS] + [a for a, _ in WALK_PAIRS]
    focus_texts = core_texts + corpus[:12]

    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    before_steps = int(getattr(xf, "steps", 0) or 0)

    if xf is not None and hasattr(xf, "specialized_calibrate"):
        xf.specialized_calibrate(
            focus_texts,
            epochs=rounds,
            lr=0.04,
            weight_decay=1e-4,
            holdout=core_texts,
        )
    elif xf is not None and hasattr(xf, "fit"):
        for _ in range(rounds):
            xf.fit(focus_texts, lr=0.04, schedule="cosine")

    if rms is not None and hasattr(rms, "specialized_calibrate"):
        rms.specialized_calibrate(
            focus_texts,
            epochs=max(1, rounds // 2),
            lr=0.035,
            weight_decay=1e-4,
            holdout=core_texts,
        )
    elif rms is not None and hasattr(rms, "fit"):
        rms.fit(focus_texts, lr=0.035, schedule="cosine")

    for slot, port in (getattr(neo, "slots", {}) or {}).items():
        if port is not None and hasattr(port, "fit"):
            for text in core_texts[:6]:
                port.fit(text)

    moe = getattr(neo, "moe", None)
    moe_updates = 0
    if moe is not None and hasattr(neo, "_stream"):
        gaming_mix_priors = [
            (
                "HP = DPS x TTK ; observed mix trash=6 elite=2 boss=0 slack=0.70 soulslike",
                (6.0, 2.0, 0.0),
                "heat",
                (0.75, 0.65, 0.85, 0.80),
            ),
            (
                "HP = DPS x TTK ; observed mix trash=4 elite=1 boss=0 slack=0.80 extraction now",
                (4.0, 1.0, 0.0),
                "loot",
                (0.55, 0.78, 0.82, 0.72),
            ),
            (
                "HP = DPS x TTK ; observed mix trash=2 elite=0 boss=0 slack=0.88 arcade golden age",
                (2.0, 0.0, 0.0),
                "combat",
                (0.25, 0.90, 0.78, 0.60),
            ),
            ("soulslike extraction ttk elite dread", (6.0, 2.0, 0.0), "heat", (0.75, 0.65, 0.85, 0.80)),
            ("cozy wholesome intimacy grind farm", (1.0, 0.0, 0.0), "balanced", (0.90, 0.95, 0.88, 0.90)),
            ("boomer shooter movement gun poetry ttk", (6.0, 1.0, 0.0), "combat", (0.30, 0.82, 0.80, 0.65)),
            ("horror survival dread heat scarcity", (3.0, 2.0, 0.0), "heat", (0.80, 0.60, 0.86, 0.85)),
        ]
        for _ in range(max(4, rounds * 4)):
            for stim, mix_target, bias_target, pacing_target in gaming_mix_priors:
                h = neo._stream(stim)
                if "left" in moe.experts:
                    moe.experts["left"].head.step(h, mix_target, lr=0.14)
                    if getattr(moe.experts["left"], "aux", None) is not None:
                        moe.experts["left"].aux.step(h, pacing_target, lr=0.12)
                if "right" in moe.experts:
                    moe.experts["right"].head.step(h, bias_target, lr=0.10)
                if "midbrain" in moe.experts:
                    moe.experts["midbrain"].head.step(h, (0.65, 0.55, 0.55), lr=0.08)
                if "pfc" in moe.experts:
                    moe.experts["pfc"].head.step(h, 0.0, lr=0.08)
                    if getattr(moe.experts["pfc"], "aux", None) is not None:
                        moe.experts["pfc"].aux.step(h, (1.0, 1.0 if bias_target in {"heat", "loot"} else 0.0), lr=0.10)
                moe_updates += 1

    after_steps = int(getattr(xf, "steps", 0) or 0)
    return {
        "applied": 1,
        "gaming_domains": len(ASPECTS),
        "adjacent_domains": len(GAME_ADJACENT_ASPECTS),
        "corpus_size": len(corpus),
        "neo_steps_delta": after_steps - before_steps,
        "moe_updates": moe_updates,
    }


def _bounded_rounds(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError("rounds must be an integer")
    try:
        rounds = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("rounds must be an integer") from exc
    rounds = max(1, rounds)
    if rounds > MAX_IMPROVE_ROUNDS:
        raise ValueError(f"rounds exceeds safety budget ({MAX_IMPROVE_ROUNDS})")
    return rounds


def _aspects(era: str, title: str) -> List[str]:
    pack = list(ASPECTS.get(era, ASPECTS["soulslike"]))
    pack.append(distill_dialect(title, era))
    return pack


def improve(neo, stimulus: str, *, rounds: int = 16) -> Dict[str, Any]:
    if not isinstance(stimulus, str):
        raise ValueError("stimulus must be a string")
    if len(stimulus) > MAX_IMPROVE_STIMULUS_CHARS:
        raise ValueError(f"stimulus exceeds safety budget ({MAX_IMPROVE_STIMULUS_CHARS} chars)")
    rounds = _bounded_rounds(rounds)

    stim = stimulus or ""
    ref = lookup(stim)
    if ref is None:
        parts = stim.split(None, 1)
        if len(parts) == 2 and parts[0].casefold() == "like":
            ref = lookup(parts[1].strip())
    if ref is None:
        return {"improved": 0, "reason": "no-reference", "law": "cite-do-not-copy"}

    era = str(ref.get("era") or "soulslike")
    title = str(ref.get("title") or "")
    texts = _aspects(era, title)
    for t in texts:
        try:
            guard(t, title)
        except LawError as exc:
            return {"improved": 0, "reason": "law-violation", "law": exc.law}

    check({"kind": "improve", "dialect": texts[0], "title": title, "era": era})

    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    before = {
        "G": float(getattr(getattr(neo, "genos_engine", None), "G", 1.0) or 1.0),
        "neo_steps": int(getattr(xf, "steps", 0) or 0),
        "rms_steps": int(getattr(rms, "steps", 0) or 0),
    }
    if xf is not None:
        for _ in range(max(4, rounds)):
            xf.fit(texts, lr=0.05, schedule="cosine")
    if rms is not None:
        for _ in range(max(2, rounds // 2)):
            rms.fit(texts, lr=0.05, schedule="cosine")
    for slot, port in (getattr(neo, "slots", {}) or {}).items():
        xf_s = getattr(port, "transformer", None)
        if xf_s is not None and hasattr(xf_s, "fit"):
            xf_s.fit(texts[:2], lr=0.04, schedule="cosine")

    pulses = []
    if hasattr(neo, "genos"):
        for _ in range(8):
            pulses.append(neo.genos(" ".join(texts)[:180]))

    record_provenance({**ref, "dialect": texts[-1]}, action="improve")
    after_g = float(getattr(getattr(neo, "genos_engine", None), "G", before["G"]) or before["G"])
    ratio = after_g / max(before["G"], 1e-9)
    card = check({
        "kind": "improve",
        "improved": 1,
        "title": title,
        "era": era,
        "url": ref.get("url"),
        "citation": ref.get("citation"),
        "stored_prose": 0,
        "law": "ok",
        "rounds": rounds,
        "G0": round(before["G"], 6),
        "G": round(after_g, 6),
        "ratio": round(ratio, 4),
        "target": 10.0,
        "neo_steps": int(getattr(xf, "steps", 0) or 0) - before["neo_steps"],
        "rms_steps": int(getattr(rms, "steps", 0) or 0) - before["rms_steps"],
        "epsilon": float(getattr(getattr(neo, "genos_engine", None), "epsilon", 0) or 0),
        "dialect": texts[-1],
    })
    return card
