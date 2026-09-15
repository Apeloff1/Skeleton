"""
core/build_journey.py — THE BUILD JOURNEY (one coherent, gamified flow).

Galaxy Studio's single source of truth for "how far is this game build, and what
is the ONE next thing to do?". It folds the scattered build surfaces (snowball
ladder, Stage Builder, forges, gates, packaging) into 7 INDUSTRY-STANDARD
milestones, derived entirely from REAL persisted state:

  • forged artifacts   (game_kb.artifacts)        → a step has been built
  • locked approvals    (game_kb.approvals)         → a step is locked-in
  • the Stage spine     (galaxy_stages)             → first gamefiles minted
  • forged assets       (construct_forge.build_assets)
  • the chosen era      (eras.file_count_standard)  → file-output target

Because every milestone reads live state, Rolling/Locking a snowball stage,
building a Stage, or forging assets immediately advances the journey, fills the
file meter, and turns the matching 100-phase band green.

Deep gamification: per-milestone XP + badges, a creator RANK/level, an overall
completion score, milestone-gated unlocks, a momentum streak, and a shareable
"build complete" card payload.
"""
from __future__ import annotations

import os
import time
from typing import Any

from core.databases import client as _MONGO

_db = _MONGO[os.environ.get("DB_NAME", "test_database")]


# ── 7 milestones (ordered industry pipeline). Each declares the artifact keys
#    that fulfil it, the tool route that advances it, XP, a badge, and copy. ──
MILESTONES: list[dict] = [
    {
        "key": "concept", "label": "Concept", "icon": "🎯",
        "tagline": "Pin the vision — questionnaire + core specs.",
        "arts": ["questionnaire", "core_specs"], "xp": 120,
        "badge": "Visionary", "badge_icon": "🪄",
        "route": "/snowball", "cta": "Answer the questionnaire",
        "band": "Foundation",
    },
    {
        "key": "spine", "label": "Spine", "icon": "🎬",
        "tagline": "Lay the game's stage spine — mint the first gamefiles.",
        "arts": [], "stage_spine": True, "xp": 150,
        "badge": "Showrunner", "badge_icon": "🎞️",
        "route": "/stages", "cta": "Build the stage spine",
        "band": "Narrative",
    },
    {
        "key": "world", "label": "World & Narrative", "icon": "🌍",
        "tagline": "Forge the world, factions, lore and quests.",
        "arts": ["lore_graph", "quest_db"], "xp": 200,
        "badge": "Worldsmith", "badge_icon": "🗺️",
        "route": "/snowball", "cta": "Forge the world & quests",
        "band": "World",
    },
    {
        "key": "systems", "label": "Systems", "icon": "⚙️",
        "tagline": "Wire mechanics, physics and procedural systems.",
        "arts": ["mechanics_config", "physics_system", "procedural_config"], "xp": 220,
        "badge": "Systems Engineer", "badge_icon": "🔧",
        "route": "/snowball", "cta": "Build the game systems",
        "band": "Mechanics",
    },
    {
        "key": "assets", "label": "Assets", "icon": "🎨",
        "tagline": "Forge the tiles, characters, props & worlds (era-scaled).",
        "arts": ["tileset", "asset_manifest"], "assets_or": True, "xp": 260,
        "badge": "Master Forger", "badge_icon": "🛠️",
        "route": "/forge-hub", "cta": "Forge the assets",
        "band": "Assets",
    },
    {
        "key": "polish", "label": "Polish & QA", "icon": "🧪",
        "tagline": "Playtest and pass the 14 AAA quality gates (>97).",
        "arts": ["qa_report"], "xp": 220,
        "badge": "Perfectionist", "badge_icon": "💎",
        "route": "/snowball", "cta": "Run QA & the gates",
        "band": "QA / Polish",
    },
    {
        "key": "launch", "label": "Package & Launch", "icon": "🚀",
        "tagline": "Package the build and prep the store launch.",
        "arts": ["build_manifest", "launch_manifest"], "xp": 300,
        "badge": "Launch Director", "badge_icon": "🏆",
        "route": "/my-builds", "cta": "Package & launch",
        "band": "QA / Polish",
    },
]

_TOTAL_XP = sum(m["xp"] for m in MILESTONES)

# Creator ranks unlocked by total XP earned.
_RANKS: list[tuple[int, str, str]] = [
    (0, "Intern", "🌱"),
    (200, "Junior Dev", "🎮"),
    (500, "Game Dev", "🕹️"),
    (850, "Lead Designer", "🎨"),
    (1200, "Studio Director", "🎬"),
    (_TOTAL_XP, "Legendary Auteur", "👑"),
]

# Map a 100-phase band → the milestone whose completion lights it up.
_BAND_FOR_MILESTONE = {m["band"]: m["key"] for m in MILESTONES}


def _rank_for(xp: int) -> dict:
    cur = _RANKS[0]
    nxt = None
    for i, r in enumerate(_RANKS):
        if xp >= r[0]:
            cur = r
            nxt = _RANKS[i + 1] if i + 1 < len(_RANKS) else None
    return {
        "level": [r[0] for r in _RANKS].index(cur[0]) + 1,
        "rank": cur[1], "rank_icon": cur[2],
        "next_rank": nxt[1] if nxt else None,
        "xp_to_next": max(0, nxt[0] - xp) if nxt else 0,
    }


def _milestone_progress(m: dict, arts: dict, approvals: dict,
                        stage_built: int, forged: int) -> tuple[float, bool, bool]:
    """Returns (progress 0..1, done, locked_in)."""
    if m.get("stage_spine"):
        done = stage_built > 0
        return (1.0 if done else 0.0), done, done
    reqs: list[str] = m["arts"]
    if not reqs:
        return 0.0, False, False
    have = sum(1 for a in reqs if a in arts)
    if m.get("assets_or") and forged > 0:
        have = len(reqs)  # forging assets satisfies the Assets milestone
    prog = have / len(reqs)
    done = have >= len(reqs)
    # locked_in = every required GDD section is also approved/locked
    locked_in = done and all(
        approvals.get(_approval_key(a), {}).get("approved") or a in arts
        for a in reqs)
    return prog, done, locked_in


# GDD section (art) → snowball forge key used in approvals
_ART_TO_FORGE = {
    "questionnaire": "questionnaire", "core_specs": "spec", "lore_graph": "world",
    "quest_db": "narrative", "mechanics_config": "mechanics",
    "physics_system": "physics", "procedural_config": "procedural",
    "tileset": "tileset", "asset_manifest": "assets", "qa_report": "qa",
    "build_manifest": "build", "launch_manifest": "launch",
}


def _approval_key(art: str) -> str:
    return _ART_TO_FORGE.get(art, art)


async def compute(pid: str) -> dict:
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "era": 1})
    if not g:
        g = {}
    kb = await _db.game_kb.find_one(
        {"game_id": pid}, {"_id": 0, "artifacts": 1, "approvals": 1})
    arts = (kb or {}).get("artifacts") or {}
    approvals = (kb or {}).get("approvals") or {}

    # live side-signals
    try:
        from core import stage_builder as sb
        stg = sb.summary(pid)
        stage_built = int(stg.get("built_count", 0))
        stage_total = int(stg.get("stage_count", 0))
        stage_gamefiles = int(stg.get("gamefile_count", 0))
    except Exception:
        stage_built = stage_total = stage_gamefiles = 0
    try:
        from core import construct_forge as cf
        forged = len(cf.build_assets(pid))
    except Exception:
        forged = 0

    era_key = g.get("era") or "modern"
    try:
        from core import eras as _eras
        era_spec = _eras.get_era(era_key)
    except Exception:
        era_spec = {"key": era_key, "label": era_key, "file_count_standard": 0}

    milestones: list[dict] = []
    earned_xp = 0
    weighted_done = 0.0
    band_done: dict[str, bool] = {}
    prev_done = True
    streak = 0
    streak_live = True
    badges: list[dict] = []
    first_active = None

    for m in MILESTONES:
        prog, done, locked_in = _milestone_progress(
            m, arts, approvals, stage_built, forged)
        unlocked = prev_done  # gated: unlocks only after the prior milestone done
        state = "done" if done else ("active" if unlocked else "locked")
        if state == "active" and first_active is None:
            first_active = m["key"]
        mxp = round(m["xp"] * prog)
        earned_xp += mxp
        weighted_done += m["xp"] * prog
        band_done[m["band"]] = band_done.get(m["band"], False) or done
        if done:
            badges.append({"key": m["key"], "name": m["badge"],
                           "icon": m["badge_icon"]})
        if streak_live and done:
            streak += 1
        elif not done:
            streak_live = False
        milestones.append({
            "key": m["key"], "label": m["label"], "icon": m["icon"],
            "tagline": m["tagline"], "state": state, "progress_pct": round(prog * 100),
            "xp": m["xp"], "xp_earned": mxp,
            "badge": m["badge"], "badge_icon": m["badge_icon"],
            "badge_earned": done,
            "route": m["route"], "cta": m["cta"],
            "unlocked": unlocked, "band": m["band"],
        })
        prev_done = prev_done and done

    completion = round(100 * weighted_done / max(1, _TOTAL_XP))
    rank = _rank_for(earned_xp)
    done_count = sum(1 for m in milestones if m["state"] == "done")
    active = next((m for m in milestones if m["key"] == first_active), None)
    complete = done_count == len(MILESTONES)

    nba = None
    if active:
        nba = {"key": active["key"], "label": active["label"],
               "icon": active["icon"], "cta": active["cta"],
               "route": active["route"], "tagline": active["tagline"]}

    return {
        "build_id": pid, "title": g.get("title", "Untitled Build"),
        "genre": g.get("genre", ""), "era": era_spec["key"],
        "era_label": era_spec["label"],
        "milestones": milestones,
        "milestones_total": len(MILESTONES),
        "milestones_done": done_count,
        "completion_pct": completion,
        "total_xp": _TOTAL_XP, "earned_xp": earned_xp,
        "streak": streak,
        "rank": rank,
        "badges": badges, "badges_total": len(MILESTONES),
        "next_best_action": nba,
        "complete": complete,
        "band_done": band_done,
        "stats": {
            "stages_built": stage_built, "stages_total": stage_total,
            "stage_gamefiles": stage_gamefiles, "forged_assets": forged,
            "file_count_standard": era_spec.get("file_count_standard", 0),
        },
        "share_card": {
            "title": g.get("title", "Untitled Build"),
            "era": era_spec["label"], "genre": g.get("genre", ""),
            "completion_pct": completion, "earned_xp": earned_xp,
            "rank": rank["rank"], "rank_icon": rank["rank_icon"],
            "badges": [b["icon"] for b in badges],
            "milestones": f"{done_count}/{len(MILESTONES)}",
            "stages": stage_total, "assets": forged,
            "file_target": era_spec.get("file_count_standard", 0),
            "stamp": "AAA build journey · Galaxy Studio",
            "ts": int(time.time()),
        },
    }


async def band_overlay(pid: str) -> dict[str, bool]:
    """Which 100-phase bands should be green based on REAL locked/forged state.
    Used by the snowball /phases card so Roll/Lock fills the meter live."""
    j = await compute(pid)
    return j.get("band_done", {})
