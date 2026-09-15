"""
core/stage_builder.py — THE STAGE PAGE (beginning of the build process).

A build is laid out as an ORDERED list of game STAGES (levels / scenes /
encounters / cinematics). The creator picks from a large, hand-authored
catalogue of DISTINCT stage TYPES (boss, mini-boss, enhanced-mob, interlude,
introduction, prelude, cutscene, theatric, drama-scene, …) and assembles the
spine of the game.

Each stage type is GENUINE and distinct: it carries its own pacing role,
combat flag, intensity, difficulty band, a real description, AND the set of
text→gamefile generators it spawns. Building a stage CREATES THE FIRST
GAMEFILES for the build (quest/enemy/cutscene/etc.) via core.text_gamefile,
which are in turn crosswired to the SAME 14-gate refinement engine.

Storage: galaxy_stages (one doc per {build_id, stage id}, ordered by `seq`).
Degrades to an in-memory mirror so a stage layout is never lost on a DB blip.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

MAX_STAGES = 100_000  # hard ceiling per build (user-mandated scale)
STAGES_COL = "galaxy_stages"

_MEM: dict[str, list[dict]] = {}  # build_id -> [stage docs]


def _db():
    from core.databases import get_sync_db
    return get_sync_db()


# ── CATEGORIES ───────────────────────────────────────────────────────────────
CATEGORIES: list[dict] = [
    {"key": "core",        "label": "Core / Structural", "icon": "🧱"},
    {"key": "combat",      "label": "Combat & Challenge", "icon": "⚔️"},
    {"key": "story",       "label": "Story & Narrative",  "icon": "📖"},
    {"key": "exploration", "label": "Exploration & Environment", "icon": "🗺️"},
    {"key": "cinematic",   "label": "Cinematic & Presentation",  "icon": "🎬"},
    {"key": "meta",        "label": "Specialized & Meta", "icon": "🧪"},
]

# Text→gamefile generator keys (must match core.text_gamefile.GENERATORS)
_Q, _D, _I, _E, _L, _LO, _AB, _CUT, _ECO, _ACH = (
    "quest_from_text", "dialogue_from_text", "item_from_text",
    "enemy_from_text", "level_from_text", "lore_from_text",
    "ability_from_text", "cutscene_from_text", "economy_from_text",
    "achievement_from_text",
)


def _st(key, label, icon, category, role, combat, intensity, difficulty,
        summary, gens) -> dict:
    return {"key": key, "label": label, "icon": icon, "category": category,
            "role": role, "combat": combat, "intensity": intensity,
            "difficulty": difficulty, "summary": summary, "gens": gens}


# ── THE STAGE TYPE CATALOGUE (hand-authored, every entry distinct) ───────────
STAGE_TYPES: list[dict] = [
    # ── Core / Structural ────────────────────────────────────────────────────
    _st("stage", "Stage", "🟦", "core", "playable", True, 45, "normal",
        "A standard playable stage — the default building block of the game spine. "
        "Mixed traversal and light combat sized to the current difficulty band.",
        [_L, _Q, _E]),
    _st("introduction", "Introduction", "🚪", "core", "onboarding", False, 20, "trivial",
        "The very first stage players touch: establishes tone, the playable verb, "
        "and the central promise of the game in a safe, low-stakes setting.",
        [_CUT, _D, _LO]),
    _st("prelude", "Prelude", "🌅", "core", "setup", False, 25, "easy",
        "A short scene-setting stage BEFORE the inciting incident — quiet world, "
        "ordinary life, the calm that the coming conflict will shatter.",
        [_LO, _D, _Q]),
    _st("interlude", "Interlude", "🍃", "core", "breather", False, 18, "trivial",
        "A pacing breather between intense beats: hub respite, gear up, talk to "
        "NPCs, let tension decompress before the next escalation.",
        [_D, _ECO, _LO]),
    _st("midpoint", "Midpoint Twist", "🔀", "core", "pivot", True, 70, "hard",
        "The act-two pivot: a revelation or reversal that re-frames the goal and "
        "raises the stakes. The mid-game everything-changes stage.",
        [_CUT, _Q, _E]),

    # ── Combat & Challenge ───────────────────────────────────────────────────
    _st("boss", "Boss Stage", "👑", "combat", "boss", True, 95, "hard",
        "A major multi-phase boss encounter: distinct phases, telegraphed attacks, "
        "an arena gimmick, and a signature reward. Caps a chapter or act.",
        [_E, _AB, _CUT, _I]),
    _st("mini_boss", "Mini-Boss Stage", "🛡️", "combat", "miniboss", True, 78, "hard",
        "A mid-tier elite gatekeeper — tougher than a mob, simpler than a boss. "
        "One or two mechanics players must read and counter to pass.",
        [_E, _AB, _I]),
    _st("enhanced_mob", "Enhanced Mob Stage", "💢", "combat", "combat", True, 62, "normal",
        "Standard enemies upgraded with affixes and modifiers (shielded, enraged, "
        "splitting). Teaches players to respect telegraphs before the boss.",
        [_E, _I, _Q]),
    _st("elite_mob", "Elite Mob Stage", "🔱", "combat", "combat", True, 68, "hard",
        "Rare elite variants with boosted stats and unique modifiers worth real "
        "loot — a step up from enhanced mobs, a step below a mini-boss.",
        [_E, _I, _ACH]),
    _st("raid_boss", "Raid Boss Stage", "🐲", "combat", "boss", True, 100, "extreme",
        "An end-game, massive, multi-phase battle designed for prepared parties. "
        "Mechanics stack across phases; failure resets the encounter.",
        [_E, _AB, _CUT, _ACH]),
    _st("survival_wave", "Survival Wave Stage", "🌊", "combat", "combat", True, 80, "hard",
        "A timed horde-survival challenge: endless escalating spawns, the goal is "
        "to outlast the clock with shrinking safe ground.",
        [_E, _ACH, _ECO]),
    _st("time_trial", "Time Trial Stage", "⏱️", "combat", "challenge", True, 72, "hard",
        "A speed-run gauntlet measured against a strict countdown — optimise the "
        "route, chain kills, beat the clock for tiered rewards.",
        [_L, _ACH, _Q]),
    _st("gauntlet", "Gauntlet Stage", "⛓️", "combat", "combat", True, 85, "hard",
        "Back-to-back fights with NO healing between rounds. Resource management "
        "across the whole run is the real test.",
        [_E, _AB, _ECO]),
    _st("skirmish", "Skirmish Stage", "🥊", "combat", "combat", True, 40, "easy",
        "A quick, low-stakes battle for testing builds or fast grinding. Short, "
        "repeatable, generous on respawns.",
        [_E, _ECO]),
    _st("ambush", "Ambush Stage", "🎯", "combat", "combat", True, 66, "normal",
        "A surprise encounter where player positioning starts compromised — react, "
        "reposition, and turn the trap around.",
        [_E, _CUT, _Q]),
    _st("nemesis", "Nemesis Stage", "🎭", "combat", "boss", True, 88, "hard",
        "A recurring rival that ADAPTS to the player's playstyle across the game, "
        "remembering past defeats and escalating each rematch.",
        [_E, _D, _CUT, _AB]),
    _st("horde", "Horde Stage", "🐜", "combat", "combat", True, 55, "normal",
        "Massive numbers of low-health, easily-defeated enemies — a power-fantasy "
        "crowd-clear that rewards AOE and momentum.",
        [_E, _ACH]),
    _st("colosseum", "Colosseum Stage", "🏟️", "combat", "combat", True, 82, "hard",
        "An arena of gladiatorial waves with a roaring crowd, escalating champions, "
        "and between-round shop choices.",
        [_E, _ECO, _ACH]),
    _st("boss_rush", "Boss Rush Stage", "💀", "combat", "boss", True, 97, "extreme",
        "A consecutive marathon refighting every boss already defeated — endurance, "
        "memory, and resource discipline under one health bar.",
        [_E, _AB, _ACH]),
    _st("nightmare_variant", "Nightmare Variant", "😈", "combat", "challenge", True, 92, "extreme",
        "A modified version of an existing stage cranked to extreme difficulty: new "
        "modifiers, harsher checkpoints, exclusive prestige rewards.",
        [_E, _ACH, _I]),

    # ── Story & Narrative ────────────────────────────────────────────────────
    _st("storyline", "Storyline Stage", "📚", "story", "narrative", False, 50, "normal",
        "A core narrative stage that advances the main plot — playable beats woven "
        "with dialogue and consequence, moving the throughline forward.",
        [_Q, _D, _LO]),
    _st("side_quest", "Side-Quest Stage", "🧭", "story", "narrative", True, 42, "normal",
        "An optional narrative path that expands world-building and rewards the "
        "curious without gating main progression.",
        [_Q, _D, _I]),
    _st("climax", "Climax Stage", "🌋", "story", "narrative", True, 98, "extreme",
        "The definitive narrative peak of a chapter or act — maximum stakes, the "
        "confrontation everything has built toward.",
        [_CUT, _Q, _E, _AB]),
    _st("cliffhanger", "Cliffhanger Stage", "🪂", "story", "narrative", False, 75, "hard",
        "A dramatic narrative cutoff engineered to build suspense — ends mid-reveal "
        "to pull the player into the next chapter.",
        [_CUT, _D]),
    _st("epilogue", "Epilogue Stage", "🌇", "story", "narrative", False, 22, "easy",
        "A wrap-up scene showing the aftermath of the main story — closure, "
        "reflection, and hooks for what comes next.",
        [_CUT, _D, _LO]),
    _st("flashback", "Flashback Stage", "⏪", "story", "narrative", True, 48, "normal",
        "A playable segment set in the past that reveals lore and recontextualises "
        "the present — often with altered abilities or a different character.",
        [_LO, _Q, _D]),
    _st("flashforward", "Flashforward Stage", "⏩", "story", "narrative", False, 60, "normal",
        "A cryptic peek into future events or an alternate timeline — foreshadows "
        "consequences and seeds dread or hope.",
        [_LO, _CUT]),
    _st("character_origin", "Character Origin Stage", "🌱", "story", "narrative", True, 46, "normal",
        "A dedicated stage exploring a specific companion's backstory — playable "
        "memory that deepens attachment and unlocks bonds.",
        [_D, _LO, _Q]),
    _st("dialogue_scene", "Dialogue Scene", "🗨️", "story", "narrative", False, 30, "trivial",
        "A choice-heavy interactive conversation with no active combat — branching "
        "lines, relationship shifts, and consequence flags.",
        [_D, _LO]),
    _st("lore_log", "Lore Log Stage", "📓", "story", "narrative", False, 15, "trivial",
        "A collectible text/audio world-building entry for enthusiasts — codex "
        "fragments that reward exploration without blocking play.",
        [_LO, _ACH]),
    _st("parallel_storyline", "Parallel Storyline", "🪢", "story", "narrative", True, 58, "normal",
        "A stage showing what another faction or character is doing concurrently — "
        "splits perspective and widens the world.",
        [_Q, _D, _LO]),
    _st("choice_matrix", "Choice Matrix Stage", "🕸️", "story", "narrative", False, 52, "normal",
        "A visual web of how prior choices branched the story — lets players see "
        "and steer their narrative consequences.",
        [_D, _ACH, _Q]),
    _st("memorial", "Memorial Stage", "🕯️", "story", "narrative", False, 28, "easy",
        "A somber narrative node dedicated to fallen characters — quiet, reflective, "
        "emotionally weighty.",
        [_LO, _D]),

    # ── Exploration & Environment ────────────────────────────────────────────
    _st("secret_chamber", "Secret Chamber", "🗝️", "exploration", "exploration", False, 38, "normal",
        "A hidden stage containing rare loot or easter eggs — rewards players who "
        "probe the seams of the level.",
        [_L, _I, _ACH]),
    _st("puzzle_room", "Puzzle Room", "🧩", "exploration", "puzzle", False, 35, "normal",
        "A non-combat stage built entirely on logic and mechanics — observe, "
        "deduce, manipulate, and unlock the way forward.",
        [_L, _Q]),
    _st("labyrinth", "Labyrinth Stage", "🌀", "exploration", "exploration", True, 56, "hard",
        "A complex maze where navigation IS the obstacle — disorienting layout, "
        "landmarks, and the threat of getting lost.",
        [_L, _E, _Q]),
    _st("gauntlet_chase", "Gauntlet Chase", "🏃", "exploration", "chase", True, 84, "hard",
        "An escape-style stage where players must outrun a relentless hazard — "
        "momentum, reaction, and no time to breathe.",
        [_L, _CUT, _E]),
    _st("outpost", "Outpost Stage", "🏕️", "exploration", "hub", False, 26, "easy",
        "A hub area that bridges two hostile regions — resupply, accept quests, and "
        "stage the next push.",
        [_ECO, _D, _Q]),
    _st("stronghold", "Stronghold Stage", "🏯", "exploration", "siege", True, 86, "hard",
        "A heavily fortified map requiring a systematic siege — layered defenses, "
        "objectives, and a commanding final chamber.",
        [_L, _E, _Q, _ACH]),
    _st("ruin_exploration", "Ruin Exploration", "🏛️", "exploration", "exploration", True, 50, "normal",
        "A dungeon-crawler map focused on traps and archaeology — read the room, "
        "disarm hazards, and recover ancient treasure.",
        [_L, _I, _LO]),
    _st("sanctuary", "Sanctuary Stage", "⛲", "exploration", "rest", False, 16, "trivial",
        "A peaceful, hidden environment for resting and upgrading — save, craft, and "
        "regroup in safety.",
        [_ECO, _LO]),
    _st("waypoint", "Waypoint Stage", "📍", "exploration", "transition", False, 12, "trivial",
        "A short transitional node used to unlock fast-travel — small, functional, "
        "a connective tissue between regions.",
        [_LO, _ACH]),
    _st("anomalous_zone", "Anomalous Zone", "🌌", "exploration", "exploration", True, 74, "hard",
        "A reality-bending stage with altered physics or strange gravity — the rules "
        "change and mastery means adapting fast.",
        [_L, _AB, _E]),

    # ── Cinematic & Presentation ─────────────────────────────────────────────
    _st("cinematic", "Cinematic Stage", "🎞️", "cinematic", "cinematic", False, 30, "trivial",
        "A directed, camera-led sequence advancing the story — high-production "
        "spectacle the player watches and feels.",
        [_CUT, _D]),
    _st("cutscene", "Cutscene", "🎬", "cinematic", "cinematic", False, 28, "trivial",
        "A scripted scene between gameplay beats — delivers plot, character, and "
        "stakes with controlled framing.",
        [_CUT, _D]),
    _st("theatric", "Theatric Stage", "🎭", "cinematic", "cinematic", False, 34, "easy",
        "A staged, performance-style scene with dramatic blocking and lighting — "
        "operatic presentation of a pivotal moment.",
        [_CUT, _D, _LO]),
    _st("drama_scene", "Drama Scene", "💔", "cinematic", "cinematic", False, 40, "easy",
        "An emotionally charged character scene — conflict, vulnerability, and "
        "consequence carried by performance and dialogue.",
        [_D, _CUT]),
    _st("monologue", "Monologue Scene", "🗣️", "cinematic", "cinematic", False, 36, "easy",
        "A dramatic solo speech by the villain or protagonist — a defining "
        "statement of motive, dread, or resolve.",
        [_D, _LO]),
    _st("montage", "Montage Cinematic", "🎵", "cinematic", "cinematic", False, 32, "easy",
        "A fast-paced visual sequence showing training or time passing — compresses "
        "growth into a stylised beat.",
        [_CUT, _LO]),
    _st("post_credits", "Post-Credits Scene", "🎟️", "cinematic", "cinematic", False, 44, "easy",
        "A secret cinematic that plays after the credits — a teaser, a twist, or a "
        "promise of more to come.",
        [_CUT, _LO]),
    _st("opening_sequence", "Opening Sequence", "🏷️", "cinematic", "cinematic", False, 24, "trivial",
        "The stylised, cinematic title sequence of the game or act — sets identity, "
        "mood, and the franchise signature.",
        [_CUT, _LO]),
    _st("lore_animatic", "Lore Animatic", "📺", "cinematic", "cinematic", False, 26, "trivial",
        "A stylised, sketched animatic explaining ancient history — economical "
        "world-building with strong art direction.",
        [_LO, _CUT]),
    _st("qte", "Quick-Time Event", "🕹️", "cinematic", "cinematic", True, 64, "normal",
        "A cinematic scene requiring fast button inputs — keeps the player's hands "
        "on the action during set-pieces.",
        [_CUT, _AB]),
    _st("pov_switch", "POV Switch Scene", "👁️", "cinematic", "cinematic", False, 38, "easy",
        "A scene viewed entirely through another character's eyes — shifts empathy "
        "and reveals hidden information.",
        [_D, _CUT, _LO]),
    _st("panorama", "Panorama Scene", "🏔️", "cinematic", "cinematic", False, 20, "trivial",
        "A sweeping, camera-only establishing shot of a massive new area — awe, "
        "scale, and a sense of place.",
        [_LO, _CUT]),
    _st("prophecy_cinematic", "Prophecy Cinematic", "🔮", "cinematic", "cinematic", False, 54, "normal",
        "A cryptic, dreamlike vision predicting future events — seeds mystery and "
        "rewards players who connect the clues.",
        [_LO, _CUT]),
    _st("narrative_voiceover", "Narrative Voiceover", "📻", "cinematic", "cinematic", False, 22, "trivial",
        "A scene driven by an omniscient or third-person narrator — frames the "
        "moment and bridges gameplay with story.",
        [_LO, _D]),

    # ── Specialized & Meta ───────────────────────────────────────────────────
    _st("tutorial", "Tutorial Stage", "🎓", "meta", "onboarding", False, 18, "trivial",
        "A safe sandbox teaching basic mechanics — guided, forgiving, and built to "
        "make the core loop click.",
        [_Q, _D, _ACH]),
    _st("training_grounds", "Training Grounds", "🏋️", "meta", "practice", True, 30, "easy",
        "A repeatable zone to test damage numbers and combos — dummies, toggles, and "
        "instant resets for mastery.",
        [_E, _AB]),
    _st("bonus_level", "Bonus Level", "🎁", "meta", "bonus", True, 50, "normal",
        "A whimsical, non-canon stage purely for extra currency or fun — a playful "
        "palate-cleanser off the main path.",
        [_ECO, _ACH, _I]),
    _st("infinite_descent", "Infinite Descent", "🕳️", "meta", "endless", True, 90, "extreme",
        "A rogue-lite mode that gets harder the deeper you go — procedural floors, "
        "escalating risk, and run-defining choices.",
        [_E, _I, _ECO, _ACH]),
    _st("mirage", "Mirage Stage", "🌫️", "meta", "challenge", True, 70, "hard",
        "An illusionary stage where enemies aren't what they seem — perception is "
        "the puzzle and trust is the trap.",
        [_E, _Q, _AB]),
    _st("sandbox", "Sandbox Mode", "🧰", "meta", "sandbox", True, 35, "easy",
        "A stage giving full control over spawns and tools — experiment, stress-test, "
        "and author emergent scenarios.",
        [_E, _I, _ECO]),
]

_BY_KEY = {s["key"]: s for s in STAGE_TYPES}


def catalog() -> dict:
    """Grouped, hand-authored stage-type catalogue for the Stage Page palette."""
    by_cat: dict[str, list[dict]] = {c["key"]: [] for c in CATEGORIES}
    for s in STAGE_TYPES:
        by_cat.setdefault(s["category"], []).append(s)
    groups = [{"category": c["key"], "label": c["label"], "icon": c["icon"],
               "count": len(by_cat.get(c["key"], [])), "types": by_cat.get(c["key"], [])}
              for c in CATEGORIES]
    return {"total_types": len(STAGE_TYPES), "max_stages": MAX_STAGES,
            "categories": [{"key": c["key"], "label": c["label"], "icon": c["icon"]}
                           for c in CATEGORIES],
            "groups": groups}


def get_type(type_key: str) -> dict | None:
    return _BY_KEY.get(type_key)


# ── persistence helpers ──────────────────────────────────────────────────────
def _mem(build_id: str) -> list[dict]:
    return _MEM.setdefault(build_id, [])


def _load(build_id: str) -> list[dict]:
    try:
        rows = list(_db()[STAGES_COL].find({"build_id": build_id}, {"_id": 0})
                    .sort("seq", 1))
        if rows:
            _MEM[build_id] = rows
            return rows
    except Exception:
        pass
    return sorted(_mem(build_id), key=lambda d: d.get("seq", 0))


def _persist(stage: dict) -> None:
    try:
        _db()[STAGES_COL].replace_one(
            {"_id": f"{stage['build_id']}:{stage['id']}"},
            {"_id": f"{stage['build_id']}:{stage['id']}", **stage}, upsert=True)
    except Exception:
        pass


def list_stages(build_id: str) -> dict:
    rows = _load(build_id)
    return {"build_id": build_id, "count": len(rows), "max_stages": MAX_STAGES,
            "remaining": max(0, MAX_STAGES - len(rows)), "stages": rows}


def add_stage(build_id: str, type_key: str, title: str = "",
              note: str = "") -> dict:
    if not build_id:
        return {"error": "missing_build_id"}
    t = get_type(type_key)
    if not t:
        return {"error": "unknown_stage_type", "type": type_key}
    rows = _load(build_id)
    if len(rows) >= MAX_STAGES:
        return {"error": "max_stages_reached", "max_stages": MAX_STAGES}
    seq = (max((r.get("seq", 0) for r in rows), default=0) + 1)
    sid = f"stg_{seq}_{uuid.uuid4().hex[:8]}"
    type_count = sum(1 for r in rows if r.get("type") == type_key) + 1
    stage = {
        "id": sid, "build_id": build_id, "seq": seq, "type": type_key,
        "label": t["label"], "icon": t["icon"], "category": t["category"],
        "role": t["role"], "combat": t["combat"], "intensity": t["intensity"],
        "difficulty": t["difficulty"], "summary": t["summary"], "gens": t["gens"],
        "title": (title or "").strip() or f"{t['label']} {type_count}",
        "note": (note or "").strip(),
        "built": False, "gamefile_ids": [], "gamefile_count": 0,
        "created": time.time(),
    }
    _mem(build_id).append(stage)
    _persist(stage)
    try:
        from core import build_ledger as bl
        bl.log(build_id, "stage_added",
               {"id": sid, "type": type_key, "label": t["label"], "seq": seq})
    except Exception:
        pass
    return stage


def update_stage(build_id: str, stage_id: str, title: str | None = None,
                 note: str | None = None) -> dict:
    rows = _load(build_id)
    stage = next((r for r in rows if r.get("id") == stage_id), None)
    if not stage:
        return {"error": "not_found"}
    if title is not None:
        stage["title"] = title.strip() or stage["title"]
    if note is not None:
        stage["note"] = note.strip()
    _persist(stage)
    return stage


def delete_stage(build_id: str, stage_id: str) -> dict:
    rows = _load(build_id)
    keep = [r for r in rows if r.get("id") != stage_id]
    if len(keep) == len(rows):
        return {"error": "not_found"}
    # re-sequence so seq stays dense
    for i, r in enumerate(keep, start=1):
        r["seq"] = i
        _persist(r)
    _MEM[build_id] = keep
    try:
        _db()[STAGES_COL].delete_one({"_id": f"{build_id}:{stage_id}"})
    except Exception:
        pass
    return {"deleted": True, "count": len(keep)}


def reorder(build_id: str, order: list[str]) -> dict:
    rows = _load(build_id)
    pos = {sid: i for i, sid in enumerate(order)}
    rows.sort(key=lambda r: pos.get(r.get("id"), 10 ** 9))
    for i, r in enumerate(rows, start=1):
        r["seq"] = i
        _persist(r)
    _MEM[build_id] = rows
    return {"ok": True, "count": len(rows)}


def build_stage(build_id: str, stage_id: str, enrich: bool = False,
                contexts: dict | None = None) -> dict:
    """CREATE THE FIRST GAMEFILES for this stage.

    Runs the stage's text→gamefile generators over the stage's title/note/summary
    so each stage seeds real, gate-ready gamefiles. This is the beginning of the
    build process.
    """
    rows = _load(build_id)
    stage = next((r for r in rows if r.get("id") == stage_id), None)
    if not stage:
        return {"error": "not_found"}
    from core import text_gamefile as tgf
    seed_text = " ".join(
        x for x in [stage.get("title", ""), stage.get("note", ""),
                    stage.get("summary", "")] if x).strip() or stage["label"]
    created = []
    for gen_key in stage.get("gens", []):
        gf = tgf.generate(gen_key, build_id, seed_text, enrich=enrich,
                          contexts=contexts)
        if gf and not gf.get("error"):
            created.append({"id": gf["id"], "system": gf["system"],
                            "type": gf["type"], "label": gf["label"]})
    stage["built"] = True
    stage["gamefile_ids"] = [c["id"] for c in created]
    stage["gamefile_count"] = len(created)
    stage["built_at"] = time.time()
    _persist(stage)
    try:
        from core import build_ledger as bl
        bl.log(build_id, "stage_built",
               {"id": stage_id, "type": stage["type"],
                "gamefiles": len(created), "enrich": enrich})
    except Exception:
        pass
    return {"ok": True, "stage_id": stage_id, "built": True,
            "gamefile_count": len(created), "gamefiles": created}


def summary(build_id: str) -> dict:
    rows = _load(build_id)
    built = [r for r in rows if r.get("built")]
    total_gf = sum(r.get("gamefile_count", 0) for r in rows)
    by_cat: dict[str, int] = {}
    for r in rows:
        by_cat[r.get("category", "core")] = by_cat.get(r.get("category", "core"), 0) + 1
    return {"build_id": build_id, "stage_count": len(rows),
            "built_count": len(built), "gamefile_count": total_gf,
            "max_stages": MAX_STAGES, "by_category": by_cat}
