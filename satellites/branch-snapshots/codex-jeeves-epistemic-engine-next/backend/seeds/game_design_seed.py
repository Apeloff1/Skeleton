"""
Game design + balancing knowledge base.

Collections:
  • game_design_patterns    — well-known design patterns + when to apply
  • game_balance_curves     — common balance/progression curves with formulas
"""
from __future__ import annotations
import hashlib, logging, itertools
from datetime import datetime, timezone

log = logging.getLogger("knowledge.game_design")

DESIGN_PATTERNS = [
    ("feedback-loop-positive",   "Positive feedback loop — winning amplifies winning. Use sparingly."),
    ("feedback-loop-negative",   "Negative feedback loop — losing gets help. Smooths difficulty."),
    ("flow-zone",                "Skill vs. challenge balanced (Csikszentmihalyi flow)."),
    ("compulsion-loop",          "Anticipate → Action → Reward → Repeat."),
    ("asymmetric-balance",       "Different sides with equal win-rates via diversity."),
    ("intransitive-balance",     "Rock-paper-scissors triangle. No dominant choice."),
    ("diminishing-returns",      "Each additional unit of X gives less benefit."),
    ("investment-trap",          "Sunk-cost retention mechanic — design carefully."),
    ("daily-engagement",         "Daily ration of content + login bonus."),
    ("battle-pass",              "Time-limited progression track with free + premium lanes."),
    ("gacha-pity",               "Soft + hard pity timers to bound RNG misery."),
    ("power-budget",             "Total stats budget per item slot."),
    ("choice-architecture",      "Default option matters more than options provided."),
    ("emergent-narrative",       "Story emerges from system interaction, not script."),
    ("juice",                    "Audio-visual feedback amplifying small actions."),
    ("failure-recovery",         "Quick-restart loop in difficulty-spike games."),
    ("safe-experimentation",     "Designated zone to try mechanics without permanent loss."),
    ("environmental-storytelling","Story told through props, not text."),
    ("set-piece",                "Bespoke crafted moment in otherwise systemic game."),
    ("breadcrumb-pacing",        "Steady drip of rewards to maintain motivation."),
    ("meaningful-choice",        "Choice with permanent consequence."),
    ("mastery-curve",            "Skill ceiling slope; depth vs. accessibility."),
    ("social-proof",             "Show what other players are doing."),
    ("loss-aversion-shop",       "Time-limited cosmetics leverage loss aversion."),
    ("endgame-treadmill",        "Endgame loop after main story complete."),
]

GENRES = ["rpg","fps","moba","rts","arpg","survival","mmo","roguelike","platformer","horror","sim","sandbox","4x","fighter","racing","sports","puzzle","deck-builder","gacha","asymm"]


def _did(p, g): return "design_" + hashlib.md5(f"{p}|{g}".encode()).hexdigest()[:14]


def build_design_patterns():
    out = []
    for (p, desc), g in itertools.product(DESIGN_PATTERNS, GENRES):
        out.append({
            "id": _did(p, g),
            "pattern": p,
            "genre": g,
            "description": desc,
            "application": f"In a {g} game, the {p} pattern is typically realised via {GENRES[GENRES.index(g) % len(GENRES)]}-specific mechanic.",
            "tags": [p, g, "design-pattern"],
        })
    return out


CURVES = [
    ("linear",      "value = a * level + b",       {"a": 10, "b": 0}),
    ("exponential", "value = a * b^level",          {"a": 100, "b": 1.15}),
    ("quadratic",   "value = a * level^2 + b*level + c", {"a": 5, "b": 10, "c": 0}),
    ("logarithmic", "value = a * log(level+1) + b", {"a": 50, "b": 0}),
    ("diminishing", "value = cap - (cap - a) * (1-r)^level", {"cap": 100, "a": 10, "r": 0.1}),
    ("sigmoid",     "value = cap / (1 + e^(-k*(level - midpoint)))", {"cap": 100, "k": 0.4, "midpoint": 25}),
    ("power-budget-soft-cap", "value = level^0.85", {"exp": 0.85}),
]

USES = ["xp-to-level","damage-per-level","hp-per-level","economy-cost","loot-rarity-chance","enemy-spawn-rate","cooldown-reduction","crit-damage","healing","item-stack"]


def build_balance_curves():
    out = []
    for (curve, formula, params), use in itertools.product(CURVES, USES):
        out.append({
            "id": "curve_" + hashlib.md5(f"{curve}|{use}".encode()).hexdigest()[:14],
            "curve": curve,
            "use": use,
            "formula": formula,
            "default_params": params,
            "description": f"Apply {curve} curve to {use}. Tune params to taste.",
            "tags": [curve, use, "balance"],
        })
    return out


async def seed_game_design(db) -> dict:
    patterns = build_design_patterns()
    curves = build_balance_curves()
    try:
        await db.game_design_patterns.create_index("id", unique=True)
        await db.game_design_patterns.create_index("pattern")
        await db.game_design_patterns.create_index("genre")
        await db.game_balance_curves.create_index("id", unique=True)
        await db.game_balance_curves.create_index("curve")
        await db.game_balance_curves.create_index("use")
    except Exception:
        pass
    now = datetime.now(timezone.utc).isoformat()
    p_in = 0; c_in = 0
    for d in patterns:
        d["indexed_at"] = now
        try:
            r = await db.game_design_patterns.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            if r.upserted_id is not None: p_in += 1
        except Exception: pass
    for d in curves:
        d["indexed_at"] = now
        try:
            r = await db.game_balance_curves.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            if r.upserted_id is not None: c_in += 1
        except Exception: pass
    return {
        "design_patterns_inserted": p_in,
        "design_patterns_total": await db.game_design_patterns.count_documents({}),
        "balance_curves_inserted": c_in,
        "balance_curves_total": await db.game_balance_curves.count_documents({}),
    }
