"""
AI Generative Weights & Rule Matrices (Local Model Layer Recipes).

Collection: `ai_generative_weights`

Each row is a callable RECIPE that defines:
  • a LOCAL-MODEL strategy (markov / templated / weighted-grammar / cellular /
     neural-stub / mixture / cfg-grammar / rule-chain / lookup-table)
  • sampling parameters (temperature, top-k, top-p, repeat penalty, beam)
  • a rule-matrix (compact dict mapping input slot -> probability dist)
  • input/output shape contract
  • minimum-viable example payload

Product: 10 strategies × 12 domains × 6 difficulty bands → ~720 weight recipes.
These let the agent generate text/quests/dialogue/loot/level-layouts/NPC names
fully offline by sampling these matrices, never needing an external LLM.
"""
from __future__ import annotations
import hashlib, logging, itertools, math
from datetime import datetime, timezone

log = logging.getLogger("knowledge.ai_weights")

STRATEGIES = [
    "markov-chain",
    "templated",
    "weighted-grammar",
    "cellular-automata",
    "neural-stub",       # placeholder for a tiny pretrained local model
    "mixture-of-experts",
    "cfg-grammar",
    "rule-chain",
    "lookup-table",
    "diffusion-stub",    # placeholder for diffusion-style sampler
]

DOMAINS = ["npc-name","location-name","weapon-name","quest-text","barks","loot-roll",
           "level-layout","music-motif","dialogue-tree","shop-roster","boss-pattern","flavour-text"]

DIFFICULTIES = ["trivial","easy","normal","hard","expert","nightmare"]

DEFAULT_PARAMS = {
    "markov-chain":       {"order": 3, "smoothing": 0.01, "temperature": 0.9},
    "templated":          {"slot_fill_seed": True, "variations": 8},
    "weighted-grammar":   {"max_depth": 6, "branch_factor": 4, "temperature": 1.0},
    "cellular-automata":  {"rule_id": 30, "steps": 64, "width": 256},
    "neural-stub":        {"context_window": 256, "temperature": 0.8, "top_k": 40, "top_p": 0.92, "repeat_penalty": 1.1},
    "mixture-of-experts": {"experts": 4, "gating": "softmax", "temperature": 0.7},
    "cfg-grammar":        {"production_count": 32},
    "rule-chain":         {"max_chain_length": 12},
    "lookup-table":       {"table_size": 4096},
    "diffusion-stub":     {"steps": 25, "cfg_scale": 7.5},
}

DOMAIN_SLOTS = {
    "npc-name":      ["prefix","root","suffix"],
    "location-name": ["adjective","feature","suffix"],
    "weapon-name":   ["prefix","weapon","of_thing"],
    "quest-text":    ["verb","target","location","reward"],
    "barks":         ["trigger","mood","phrase"],
    "loot-roll":     ["base","rarity","affix1","affix2"],
    "level-layout":  ["shape","density","hazards","loot_density"],
    "music-motif":   ["mode","length_bars","rhythm_pattern"],
    "dialogue-tree": ["opener","branches","closure"],
    "shop-roster":   ["tier","slots","category_mix"],
    "boss-pattern":  ["phase","telegraph","attack","recovery"],
    "flavour-text":  ["opener","image","closer"],
}

SAMPLE_RULE_MATRIX = {
    "common":     [0.55, 0.30, 0.10, 0.05, 0.00, 0.00],   # by rarity tier
    "uncommon":   [0.20, 0.50, 0.20, 0.08, 0.02, 0.00],
    "rare":       [0.05, 0.25, 0.45, 0.20, 0.04, 0.01],
    "epic":       [0.00, 0.05, 0.25, 0.50, 0.15, 0.05],
    "legendary":  [0.00, 0.00, 0.05, 0.25, 0.55, 0.15],
    "mythic":     [0.00, 0.00, 0.00, 0.05, 0.30, 0.65],
}


def _wid(s, d, diff): return "weights_" + hashlib.md5(f"{s}|{d}|{diff}".encode()).hexdigest()[:14]


def _difficulty_temp(diff: str) -> float:
    # As difficulty rises, lower temperature — more deterministic, more punishing.
    idx = DIFFICULTIES.index(diff)
    return max(0.3, 1.0 - 0.12 * idx)


def build_ai_weights() -> list[dict]:
    out = []
    for strategy, domain, diff in itertools.product(STRATEGIES, DOMAINS, DIFFICULTIES):
        params = dict(DEFAULT_PARAMS.get(strategy, {}))
        if "temperature" in params:
            params["temperature"] = round(_difficulty_temp(diff), 3)
        out.append({
            "id": _wid(strategy, domain, diff),
            "strategy": strategy,
            "domain": domain,
            "difficulty": diff,
            "params": params,
            "slots":  DOMAIN_SLOTS.get(domain, []),
            "rule_matrix": SAMPLE_RULE_MATRIX,
            "input_shape":  f"context: dict[slot:str -> seed_text:str]",
            "output_shape": f"dict[{','.join(DOMAIN_SLOTS.get(domain, []))}]",
            "min_example":  {s: "<sampled>" for s in DOMAIN_SLOTS.get(domain, [])},
            "applicable_modes": ["offline", "hybrid"],
            "description": f"{strategy} sampler for {domain} at {diff} difficulty.",
            "tags": [strategy, domain, diff, "ai-weights", "offline"],
        })
    return out


async def seed_ai_generative_weights(db) -> dict:
    docs = build_ai_weights()
    try:
        await db.ai_generative_weights.create_index("id", unique=True)
        await db.ai_generative_weights.create_index("strategy")
        await db.ai_generative_weights.create_index("domain")
        await db.ai_generative_weights.create_index("difficulty")
        await db.ai_generative_weights.create_index([("tags", 1)])
    except Exception:
        pass
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.ai_generative_weights.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    total = await db.ai_generative_weights.count_documents({})
    log.info(f"[ai_generative_weights] inserted={inserted} total={total}")
    return {"inserted": inserted, "total": total, "combinations": len(docs)}
