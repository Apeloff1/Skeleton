"""
gameforge/jeeves/jeeves_self_training.py — Jeeves' OWN logic + self-training.

At launch Jeeves prefills its databases with game-specific logic (genres,
mechanics, pipeline doctrine, quality gates, monetization, room/seat/toolbox
awareness) + the master skill bank + its MasterMap capabilities, so it can
reason and act WITHOUT an external LLM. `recall()` gives deterministic lexical
retrieval over the seeded knowledge; `train_at_launch()` is idempotent.
"""
from __future__ import annotations

import glob
import json
import os
import time
from typing import Any

_GF = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../gameforge

# ── Prefilled game-specific logic Jeeves trains on ────────────────────────────
GAME_LOGIC: list[dict] = [
    {"topic": "genre:roguelike", "text": "Roguelike: procedural runs, permadeath, meta-progression, "
     "risk/reward loops. Core mechanics: run seed, item synergies, escalating difficulty, unlock currency."},
    {"topic": "genre:platformer", "text": "Platformer: tight jump physics, coyote-time, level gating, "
     "collectibles. Balance jump arc vs hazard spacing; add checkpoints and momentum."},
    {"topic": "genre:rpg", "text": "RPG: character progression, stats/skills, quests, dialogue trees, "
     "loot economy, faction reputation. Ground narrative in world lore for coherence."},
    {"topic": "genre:puzzle", "text": "Puzzle: one clean rule set, escalating complexity, no dead-ends, "
     "clear feedback. Difficulty curve = introduce, combine, subvert."},
    {"topic": "genre:shooter", "text": "Shooter: recoil/spread, hit feedback, enemy telegraphs, cover, "
     "ammo economy, power curve. Juice with screen-shake + particles."},
    {"topic": "pipeline", "text": "Studio pipeline: questionnaire -> snowball steps (concept, mechanics, "
     "world, assets, systems, polish, build) -> forges -> boardroom -> evaluation room -> vault + gamefiles -> deploy."},
    {"topic": "governance", "text": "Every artifact entering the Boardroom is sent to the Evaluation Room "
     "(Knowledge Nexus jury) FIRST, evaluated (accept/revise/reject), returned to the Boardroom, then "
     "persisted to Vault + gamefiles ONLY on ACCEPT."},
    {"topic": "quality_gate", "text": "Hard quality bar >=95. Score = min(overall, every factor: coherence, "
     "depth, originality, polish, consistency, completeness). Regenerate with auditor feedback until it passes."},
    {"topic": "monetization", "text": "Options: free, paid, IAP, battle-pass, cosmetics. Avoid pay-to-win; "
     "reward engagement; seasonal live-ops calendar drives retention."},
    {"topic": "rooms", "text": "1000 CNS rooms each hold a seat (role), a skill tree, a toolbox (repair "
     "coordinator), a bookshelf and a team rolodex. Agents read step logs and keep working."},
    {"topic": "toolbox", "text": "Each room's Toolbox gathers qualified agents to fix issues (security "
     "breach, corruption, damage, perf). Integrated with nav map, delegation and blockchain logs."},
    {"topic": "seats", "text": "Seat & role selector: 100 seats per category; roles carry specialty, skills, "
     "coder-style references, competency level and prompt template. Jeeves delegates by qualification."},
    {"topic": "fast_travel", "text": "Agents can fast-travel to an optimal midpoint between rooms to cut long "
     "traversals, then respawn to origin — nav-map + RAG synergy picks the midpoint."},
    {"topic": "deploy", "text": "Final build exports APK + EXE + Web/PWA. Vault files can be committed to Git "
     "and pushed to GitHub (push activates once a remote + token are configured)."},
]

# ── Coding knowledge (Jeeves self-trains on this too) ─────────────────────────
CODING_KNOWLEDGE: list[dict] = [
    {"topic": "code:solid", "text": "SOLID: Single-responsibility, Open/closed, Liskov substitution, "
     "Interface segregation, Dependency inversion — the backbone of maintainable OOP."},
    {"topic": "code:dry", "text": "DRY — don't repeat yourself. Extract shared logic once; duplication is a "
     "maintenance liability. Balance with avoiding premature abstraction (rule of three)."},
    {"topic": "code:yagni", "text": "YAGNI — you aren't gonna need it. Build only what the current task needs; "
     "don't design for hypothetical futures."},
    {"topic": "code:naming", "text": "Name for intent, not implementation. Functions are verbs, variables are "
     "nouns; avoid abbreviations; make the code read like prose."},
    {"topic": "code:functions", "text": "Small pure functions, single level of abstraction, few args (<=3), "
     "no side effects where avoidable. Early-return to reduce nesting."},
    {"topic": "code:errors", "text": "Validate at system boundaries (user input, external APIs). Trust internal "
     "invariants. Fail fast with clear messages; never swallow exceptions silently."},
    {"topic": "code:testing", "text": "Test pyramid: many unit, some integration, few E2E. Test behaviour not "
     "implementation. Red-green-refactor. Cover edge cases + failure paths."},
    {"topic": "code:perf", "text": "Measure before optimizing. Big-O first, then constants. Cache hot paths, "
     "avoid N+1 queries, batch IO, stream large data, use appropriate data structures."},
    {"topic": "code:concurrency", "text": "Prefer immutability + message passing over shared mutable state. "
     "Off-load blocking work to threads; keep the event loop free (async I/O)."},
    {"topic": "code:datastructures", "text": "Pick by access pattern: array (index), hashmap (lookup), heap "
     "(priority), tree/BST (ordered), graph (relations), ring buffer (streaming)."},
    {"topic": "code:algorithms", "text": "Know sort/search, two-pointer, sliding window, BFS/DFS, dynamic "
     "programming, greedy, union-find. Choose by constraints (n, memory, latency)."},
    {"topic": "code:git", "text": "Small atomic commits, imperative messages, feature branches, PR review, "
     "never commit secrets. Rebase to keep history linear when appropriate."},
    {"topic": "code:refactor", "text": "Refactor in safe steps behind tests: rename, extract, inline, move. "
     "Leave code cleaner than you found it — but only within the task's scope."},
    {"topic": "code:security", "text": "Never trust input; parameterize queries; hash passwords (bcrypt/argon2); "
     "least-privilege; secrets in env not code; validate + sanitize; rate-limit."},
    {"topic": "code:api", "text": "REST: nouns + verbs (GET/POST/PUT/DELETE), status codes, idempotency, "
     "versioning, pagination, consistent error envelopes. Document with OpenAPI."},
    {"topic": "code:react_native", "text": "RN/Expo: StyleSheet.create, no DOM, onPress not onClick, SafeArea "
     "insets, 44px touch targets, FlatList/FlashList for long lists, memoize heavy renders."},
    {"topic": "code:state", "text": "Lift state minimally; colocate; derive don't duplicate. Use context/zustand "
     "for cross-cutting; avoid prop-drilling; keep effects dependency-correct."},
    {"topic": "code:python", "text": "Pythonic: comprehensions, context managers, dataclasses, type hints, "
     "f-strings, EAFP over LBYL, generators for large iteration, stdlib first."},
    {"topic": "code:async", "text": "async def + await for I/O; never block the loop with CPU/LLM calls — use "
     "to_thread/executor. Gather for concurrency; guard with timeouts."},
    {"topic": "code:review", "text": "Review for correctness, readability, tests, security, and scope creep. "
     "Prefer many small reviewable diffs; explain the why in the description."},
]

# ── Game-design knowledge — highest quality, most-used, metric-driven ─────────
GAME_DESIGN_KNOWLEDGE: list[dict] = [
    {"topic": "gd:core_loop", "text": "Core loop = the 30-second action players repeat: act -> feedback -> "
     "reward -> upgrade. Make it satisfying in isolation before adding meta systems.",
     "metric": "session_length", "usage": "very_high"},
    {"topic": "gd:retention", "text": "Retention is king: target D1 40%+, D7 20%+, D30 10%+. Drive it with a "
     "strong FTUE, daily reasons to return, and a visible progression goal.",
     "metric": "retention", "usage": "very_high"},
    {"topic": "gd:ftue", "text": "First-Time User Experience: teach by doing in <60s, one concept at a time, "
     "early win within 2 minutes. Most churn happens in the first session.",
     "metric": "D1_retention", "usage": "very_high"},
    {"topic": "gd:flow", "text": "Flow channel: keep challenge slightly above skill. Too hard = anxiety, too "
     "easy = boredom. Ramp difficulty with the player's mastery curve.",
     "metric": "engagement", "usage": "high"},
    {"topic": "gd:juice", "text": "Game feel / juice: screen shake, particles, hit-stop, easing, sound on every "
     "action. Cheap to add, huge perceived-quality lift.",
     "metric": "review_score", "usage": "very_high"},
    {"topic": "gd:reward_schedule", "text": "Variable-ratio reward schedules (unpredictable rewards) maximize "
     "engagement; mix with fixed milestone rewards for a sense of steady progress.",
     "metric": "session_count", "usage": "high"},
    {"topic": "gd:progression", "text": "Layer progression: short (per-run), mid (unlocks), long (mastery/meta). "
     "Always show the next goal and the progress bar toward it.",
     "metric": "D30_retention", "usage": "very_high"},
    {"topic": "gd:onboarding_funnel", "text": "Track the onboarding funnel step-by-step; the biggest drop-off is "
     "your #1 fix. Instrument tutorial completion + first-win rate.",
     "metric": "conversion", "usage": "high"},
    {"topic": "gd:monetization", "text": "LTV = ARPDAU x lifetime days. Ethical models: cosmetics, battle-pass, "
     "value IAP. Avoid pay-to-win (kills retention + reviews).",
     "metric": "LTV", "usage": "high"},
    {"topic": "gd:difficulty_curve", "text": "Introduce -> combine -> subvert -> master. Add dynamic difficulty "
     "adjustment (DDA) to keep players in flow without feeling punished.",
     "metric": "completion_rate", "usage": "high"},
    {"topic": "gd:economy", "text": "Design sources vs sinks so currency neither inflates nor starves. Model "
     "the economy ledger before shipping; playtest for exploits.",
     "metric": "economy_health", "usage": "high"},
    {"topic": "gd:level_design", "text": "Teach mechanics in safe rooms before testing them under pressure. Guide "
     "the eye with light/color/composition. Pace tension with rest beats.",
     "metric": "completion_rate", "usage": "high"},
    {"topic": "gd:feedback", "text": "Every input needs immediate, legible feedback (visual + audio + haptic). "
     "Telegraph enemy actions; make cause->effect unmistakable.",
     "metric": "clarity", "usage": "very_high"},
    {"topic": "gd:narrative", "text": "Environmental storytelling + player agency beat cutscenes. Ground lore in "
     "the world's real systems; keep it consistent (canon graph).",
     "metric": "immersion", "usage": "medium"},
    {"topic": "gd:ui_ux", "text": "Game UI: information hierarchy, glanceable HUD, thumb-reachable controls, "
     "consistent iconography, readable at speed. Minimize modal interruptions.",
     "metric": "usability", "usage": "very_high"},
    {"topic": "gd:playtesting", "text": "Watch players, don't ask. Note where they hesitate, fail, or quit. The "
     "first 3 minutes decide most reviews. Iterate on observed friction.",
     "metric": "review_score", "usage": "high"},
    {"topic": "gd:accessibility", "text": "Colorblind-safe palettes, remappable controls, scalable text, subtitles, "
     "difficulty options. Widens audience + improves reviews.",
     "metric": "reach", "usage": "medium"},
    {"topic": "gd:session_design", "text": "Design for the target session length (mobile 3-7 min). Provide clean "
     "save/quit points and quick re-entry so short sessions feel complete.",
     "metric": "session_length", "usage": "high"},
    {"topic": "gd:hooks", "text": "Curiosity + collection + competition + completion are the strongest hooks. "
     "Combine 2-3; surface them early and reinforce with rewards.",
     "metric": "retention", "usage": "high"},
    {"topic": "gd:balance", "text": "No dominant strategy: every option should have a counter. Use power-budget "
     "math + simulation; nerf outliers gently, buff underdogs first.",
     "metric": "fairness", "usage": "high"},
]

# Target corpus size — seeds represent ~50% so self-training keeps growing it.
_SEED_COUNT = len(GAME_LOGIC) + len(CODING_KNOWLEDGE) + len(GAME_DESIGN_KNOWLEDGE)
TARGET_KNOWLEDGE = _SEED_COUNT * 2  # prefilled at ~50% capacity


def _all_knowledge() -> list[dict]:
    out = []
    for item in GAME_LOGIC:
        out.append({**item, "domain": "game_logic"})
    for item in CODING_KNOWLEDGE:
        out.append({**item, "domain": "coding"})
    for item in GAME_DESIGN_KNOWLEDGE:
        out.append({**item, "domain": "game_design"})
    return out


def _load_master_skills() -> list[str]:
    p = os.path.join(_GF, "datasets", "skill_dataset", "master_skill_bank.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            cats = json.load(f).get("skill_categories", {})
        out: list[str] = []
        for v in cats.values():
            out.extend(v)
        return out
    except Exception:  # noqa: BLE001
        return []


def _mastermap_capabilities() -> list[str]:
    files = glob.glob(os.path.join(_GF, "jeeves", "jeeves_mastermap_*.json"))
    files.sort(key=lambda p: len(os.path.basename(p)))
    if not files:
        return []
    try:
        with open(files[-1], "r", encoding="utf-8") as f:
            data = json.load(f)
        return data[next(iter(data))].get("new_components", [])
    except Exception:  # noqa: BLE001
        return []


def train_at_launch(db) -> dict:
    """Idempotent: seed jeeves_knowledge (game logic + coding + game design) +
    jeeves_skill_bank so Jeeves self-trains. Prefilled to ~50% of target capacity."""
    trained = {"knowledge": 0, "skills": 0, "capabilities": 0}
    try:
        kb = db["jeeves_knowledge"]
        for item in _all_knowledge():
            kb.update_one({"topic": item["topic"]},
                          {"$set": {**item, "trained_at": time.time()}}, upsert=True)
            trained["knowledge"] += 1
        skills = _load_master_skills()
        sb = db["jeeves_skill_bank"]
        for sk in skills:
            sb.update_one({"skill": sk}, {"$set": {"skill": sk, "source": "master_skill_bank"}}, upsert=True)
        trained["skills"] = len(skills)
        caps = _mastermap_capabilities()
        for c in caps:
            kb.update_one({"topic": f"capability:{c}"},
                          {"$set": {"topic": f"capability:{c}", "text": c, "kind": "mastermap",
                                    "domain": "mastermap"}}, upsert=True)
        trained["capabilities"] = len(caps)
        total = kb.count_documents({})
        fill_percent = min(100, round(total / TARGET_KNOWLEDGE * 100)) if TARGET_KNOWLEDGE else 100
        db["jeeves_status"].update_one(
            {"_id": "self_training"},
            {"$set": {"trained": True, "at": time.time(), "counts": trained,
                      "target": TARGET_KNOWLEDGE, "fill_percent": fill_percent,
                      "domains": ["game_logic", "coding", "game_design", "mastermap"]}}, upsert=True)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:160], "trained": trained}
    return {"ok": True, "trained": trained, "fill_percent": fill_percent, "target": TARGET_KNOWLEDGE}


def recall(db, query: str, k: int = 5) -> list[dict]:
    """Deterministic lexical retrieval over Jeeves' seeded knowledge."""
    import re
    q = set(w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2)
    scored: list[tuple[int, dict]] = []
    try:
        for doc in db["jeeves_knowledge"].find({}, {"_id": 0}):
            hay = (doc.get("topic", "") + " " + doc.get("text", "")).lower()
            score = sum(1 for w in q if w in hay)
            if score:
                scored.append((score, doc))
    except Exception:  # noqa: BLE001
        return []
    scored.sort(key=lambda t: t[0], reverse=True)
    return [d for _, d in scored[:k]]


def status(db) -> dict:
    try:
        st = db["jeeves_status"].find_one({"_id": "self_training"}, {"_id": 0}) or {}
        st["knowledge_count"] = db["jeeves_knowledge"].count_documents({})
        st["skill_count"] = db["jeeves_skill_bank"].count_documents({})
        st["by_domain"] = {
            d: db["jeeves_knowledge"].count_documents({"domain": d})
            for d in ("game_logic", "coding", "game_design", "mastermap", "acquired", "learned")
        }
        return st
    except Exception:  # noqa: BLE001
        return {"trained": False}
