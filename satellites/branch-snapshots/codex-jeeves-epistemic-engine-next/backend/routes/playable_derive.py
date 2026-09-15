"""
🧬 DERIVE MODES — generate a CHILD playable from an existing one.

Extracted from routes/playable.py (Session 12 monolith decomposition). Covers the
full derive family: remix · sequel · prequel · competitor · expansion · variants ·
interlude · conclusion · series. Each mode shares one pipeline (`_do_derive`) and
selects its own system prompt, title prefix, prompt framing and code-volume target.

Shares the codegen quality loop + Mongo handle with routes.playable (single source
of truth). All derive endpoints POST to deeper paths (/{pid}/<mode>/async) so they
never shadow the GET /{pid} catch-all in routes.playable.
"""
from __future__ import annotations

import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from routes.playable import (
    _db, _GAME_SYS, PLAYABILITY_THRESHOLD, _codegen_quality_loop, _run_job,
    EXPANSION_SIZE_MULT, EXPANSION_MAX_REPAIR, EXPANSION_MAX_REFINE,
    EXPANSION_QUALITY_TARGET, EXPANSION_TIME_BUDGET, EXPANSION_HTML_CTX,
)

router = APIRouter(prefix="/api/playable", tags=["playable"])

# Remix — iterate on an existing game with a player's tweak instruction.
_REMIX_SYS = _GAME_SYS + (
    "\n\nYou are REMIXING an existing game per the user's tweak. Keep what works, apply the "
    "requested change, then deliberately INCREASE VARIATION and COMPLEXITY: add fresh mechanic "
    "variations, more enemy/obstacle types, extra power-ups, and richer juice — make it a clearly "
    "deeper, more surprising version. Return the FULL updated single-file HTML document.")

# Sequel — the next installment: same identity, escalated everything.
_SEQUEL_SYS = _GAME_SYS + (
    "\n\nYou are building the SEQUEL to an existing game. Keep the core identity, controls and "
    "feel players love, but make it a clear step up: a fresh theme/setting, escalated difficulty, "
    "at least one NEW mechanic or a boss, and a 'next chapter' vibe. Return the FULL single-file HTML.")

# Prequel — an earlier, intentionally SIMPLER and COZIER chapter.
_PREQUEL_SYS = _GAME_SYS + (
    "\n\nYou are building the PREQUEL — the story BEFORE this game. HARD RULES: make it deliberately "
    "SIMPLER and COZIER ('snug'): one gentle core mechanic, a calm/warm palette, soft rounded shapes, "
    "soothing WebAudio tones, no harsh fail states (forgiving, low-stakes, relaxing). It should feel "
    "like the cozy origin chapter that leads into the main game. Return the FULL single-file HTML.")

# Competitor — a rival studio's reimagining: HARD-CODED PvP + puzzles, 2x volume.
_COMPETITOR_SYS = _GAME_SYS + (
    "\n\nYou are a RIVAL studio reimagining a competitor's game in the SAME genre to OUT-COMPETE it. "
    "Do NOT copy it. HARD REQUIREMENTS: (1) add a PvP mode — local two-player (split controls or "
    "hot-seat turns) or a competitive vs-AI duel; (2) add PUZZLE elements (a solvable challenge the "
    "player must reason through). Bring distinct art and a tighter loop. The game must be roughly "
    "TWICE the code volume / depth of the original. Return the FULL single-file HTML document.")

# Expansion — a much larger, richer edition of the loaded game.
_EXPANSION_SYS = _GAME_SYS + (
    "\n\nYou are building a major EXPANSION of an existing game. HARD REQUIREMENTS: roughly TRIPLE the "
    "code volume / content of the original, and heighten QUALITY, INTRICACY and COMPLEXITY across the "
    "board: many more mechanics & their interactions, multiple levels/biomes/waves, several enemy "
    "types and bosses, deep progression & upgrades, layered WebAudio music + sfx, abundant particle "
    "and screen-shake juice. Keep what works, expand everything. Return the FULL single-file HTML.")

# Variants — alternate takes, one per signature colour.
_VARIANT_SYS = _GAME_SYS + (
    "\n\nYou are creating ONE bold ALTERNATE VARIANT of an existing game built around a signature "
    "COLOUR THEME. Keep the genre/controls recognisable, but give this variant its own distinct "
    "mechanic twist, mood and palette dominated by the given colour. Return the FULL single-file HTML.")

# Series — the next snowball entry: escalate complexity & intricacy every step.
_SERIES_SYS = _GAME_SYS + (
    "\n\nYou are building the NEXT ENTRY in an escalating SERIES (a 'snowball'). Build DIRECTLY on "
    "the loaded game and ESCALATE: more mechanics and deeper system interactions, more enemy/obstacle "
    "types, tougher and more intricate challenges, richer progression, and noticeably more polish & "
    "content than the previous entry — each entry must clearly out-do the one before it. Keep the core "
    "identity recognisable. Return the FULL single-file HTML document.")

# Interlude — a between-chapters episode, heavy on lore AND new mechanics.
_INTERLUDE_SYS = _GAME_SYS + (
    "\n\nYou are building an INTERLUDE — a between-chapters episode that is HEAVY ON LORE AND MECHANICS. "
    "HARD REQUIREMENTS: (1) LORE — weave in substantial story & worldbuilding: an intro narrative, "
    "environmental storytelling, in-game dialogue and/or a readable codex/journal that deepens the "
    "world and characters; (2) MECHANICS — introduce and showcase NEW systems/mechanics not present in "
    "the original (and let them interact). Mid-stakes, reflective pacing. Return the FULL single-file HTML.")

# Conclusion — the grand finale: full lore + gameplay wrap-up with multiple endings.
_CONCLUSION_SYS = _GAME_SYS + (
    "\n\nYou are building the CONCLUSION — the GRAND FINALE that wraps up the ENTIRE storyline, leaving "
    "NO STONE UNTURNED. HARD REQUIREMENTS: (1) FULL LORE PAYOFF — resolve every narrative thread with a "
    "rich epilogue/codex; deep, satisfying storytelling throughout; (2) CLIMACTIC GAMEPLAY — combine the "
    "series' mechanics into a culminating finale (a final gauntlet and/or multi-phase boss); (3) MULTIPLE "
    "ENDINGS — at least THREE distinct endings the player explicitly CHOOSES between via a final decision, "
    "each with its own outcome screen/epilogue. Be exhaustive and detailed. Return the FULL single-file HTML.")

# Polish — keep the game's identity but elevate it to exquisite, shippable quality.
_POLISH_SYS = _GAME_SYS + (
    "\n\nYou are running POLISH MODE on an existing game: do NOT change its core identity, genre, "
    "theme or controls — instead refine it to EXQUISITE, shippable, AAA-feel quality on two axes. "
    "(1) MECHANICS — tighten game feel: responsive controls with input buffering & coyote-time, a "
    "smooth, fair difficulty curve, readable rules, and tuned, satisfying core loop. (2) END-USER "
    "EXPERIENCE — maximal juice (screen shake, particles, tweened/eased motion, hit-stop, flash on "
    "impact), layered WebAudio sfx + subtle adaptive music, a crisp readable HUD & typography, an "
    "instant onboarding/tutorial hint, pause/resume, a settings toggle, generous ≥48px touch targets, "
    "navigator.vibrate haptics, a reduced-motion option and colour-blind-friendly palette, and "
    "satisfying feedback on EVERY interaction. Keep it a single runnable file, buttery 60fps and "
    "mobile-first. Preserve everything that already works. Return the FULL single-file HTML document.")

# Derive-mode config: each child-generation mode shares one pipeline.
_DERIVE_MODES = {
    "remix": {
        "sys": _REMIX_SYS, "prefix": "Remix", "verb": "Apply this tweak",
        "min_instr": 3, "require_instr": True, "size_mult": 0,
    },
    "sequel": {
        "sys": _SEQUEL_SYS, "prefix": "Sequel", "verb": "Sequel direction (optional)",
        "min_instr": 0, "require_instr": False, "size_mult": 0,
    },
    "prequel": {
        "sys": _PREQUEL_SYS, "prefix": "Prequel", "verb": "Prequel direction (optional)",
        "min_instr": 0, "require_instr": False, "size_mult": 0,
    },
    "competitor": {
        "sys": _COMPETITOR_SYS, "prefix": "Rival", "verb": "Competitor angle (optional)",
        "min_instr": 0, "require_instr": False, "size_mult": 2.0,
    },
    "expansion": {
        "sys": _EXPANSION_SYS, "prefix": "Expansion", "verb": "Expansion focus (optional)",
        "min_instr": 0, "require_instr": False, "size_mult": EXPANSION_SIZE_MULT,
    },
    "polish": {
        "sys": _POLISH_SYS, "prefix": "Polished", "verb": "Polish focus (optional)",
        "min_instr": 0, "require_instr": False, "size_mult": 0,
    },
    "interlude": {
        "sys": _INTERLUDE_SYS, "prefix": "Interlude", "verb": "Interlude direction (optional)",
        "min_instr": 0, "require_instr": False, "size_mult": 1.6,
    },
    "conclusion": {
        "sys": _CONCLUSION_SYS, "prefix": "Finale", "verb": "Conclusion direction (optional)",
        "min_instr": 0, "require_instr": False, "size_mult": 2.5,
    },
    "series": {
        "sys": _SERIES_SYS, "prefix": "Series", "verb": "Series direction (optional)",
        "min_instr": 0, "require_instr": False, "size_mult": 1.5,
    },
}

# Variants: four signature colours produced in one go.
_VARIANT_COLORS = [
    ("red", "#ef4444", "fiery red / crimson — aggressive, high-energy"),
    ("blue", "#3b82f6", "cool blue / cyan — calm, precise, futuristic"),
    ("green", "#22c55e", "vivid green / emerald — organic, lively, natural"),
    ("yellow", "#eab308", "bright yellow / gold — playful, sunny, electric"),
]


async def _do_derive(base: dict, mode: str, instruction: str, depth: str = "studio",
                     variant: tuple = None, size_override: float = None,
                     series_step: int = 0, series_total: int = 0) -> dict:
    """Generate a CHILD playable from an existing one — shared by remix / sequel /
    prequel / competitor / expansion / variant. `mode` selects the system prompt,
    title prefix, prompt framing and a hard-coded size target."""
    cfg = _DERIVE_MODES.get(mode, _DERIVE_MODES["remix"]) if mode != "variant" else None
    sys_prompt = _VARIANT_SYS if mode == "variant" else cfg["sys"]
    prefix = (variant[0].capitalize() if variant else (cfg["prefix"] if cfg else "Variant"))
    base_html = base.get("html", "")
    base_brief = base.get("brief", "")
    base_title = base.get("title") or "Untitled"
    base_bytes = len(base_html)
    instr = (instruction or "").strip()

    if mode == "remix":
        intent = (f"Apply this tweak: \"{instr}\".\nKeep everything that works, then INCREASE "
                  "variation and complexity (more mechanic variants, enemy/obstacle types, power-ups).")
    elif mode == "sequel":
        intent = ("Create the SEQUEL to this game (keep its identity & controls, escalate "
                  "everything, add a fresh theme + a new mechanic or boss)."
                  + (f"\nExtra direction: \"{instr}\"." if instr else ""))
    elif mode == "prequel":
        intent = ("Create the PREQUEL — the cozy origin chapter BEFORE this game. Make it deliberately "
                  "SIMPLER and COZIER: one gentle mechanic, warm palette, soft shapes, soothing tones, "
                  "forgiving low-stakes play."
                  + (f"\nExtra direction: \"{instr}\"." if instr else ""))
    elif mode == "competitor":
        intent = ("Reimagine this as a RIVAL studio's competing title in the same genre. HARD RULES: "
                  "add a PvP mode (local 2-player or competitive vs-AI duel) AND puzzle elements; "
                  "your own art and a tighter loop."
                  + (f"\nExtra angle: \"{instr}\"." if instr else ""))
    elif mode == "expansion":
        intent = ("Build a major DELUXE EXPANSION: keep what works and massively grow it into a "
                  "flagship edition — many more interacting mechanics, multiple levels/biomes/waves, "
                  "several enemy types AND bosses, deep progression with upgrades/unlocks, layered "
                  "WebAudio music + sfx, abundant particle & screen-shake juice, polished menus/HUD, "
                  "settings, pause, and a satisfying end-game. There is NO upper limit — go as large, "
                  "rich and intricate as you possibly can while staying a single runnable file."
                  + (f"\nExtra focus: \"{instr}\"." if instr else ""))
    elif mode == "interlude":
        intent = ("Build an INTERLUDE — a between-chapters episode HEAVY ON LORE AND MECHANICS: weave in "
                  "rich story & worldbuilding (intro narrative, environmental storytelling, dialogue and/or "
                  "a readable codex) AND introduce NEW interacting mechanics not in the original."
                  + (f"\nExtra direction: \"{instr}\"." if instr else ""))
    elif mode == "conclusion":
        intent = ("Build the CONCLUSION — the grand FINALE that wraps up the ENTIRE storyline with NO stone "
                  "unturned: full lore payoff (resolve every thread + epilogue/codex), a climactic finale "
                  "(final gauntlet and/or multi-phase boss combining the mechanics), and AT LEAST THREE "
                  "distinct MULTIPLE ENDINGS the player explicitly CHOOSES between via a final decision, each "
                  "with its own outcome screen."
                  + (f"\nExtra direction: \"{instr}\"." if instr else ""))
    elif mode == "series":
        intent = (f"Build the NEXT ENTRY in an escalating SERIES (entry {series_step} of {series_total}) — a "
                  "'snowball'. Build DIRECTLY on the loaded game and ESCALATE complexity & intricacy beyond "
                  "it: more mechanics & deeper interactions, more enemy/obstacle types, tougher intricate "
                  "challenges, richer progression and more polish than the previous entry. Keep the core "
                  "identity recognisable."
                  + (f"\nSeries direction: \"{instr}\"." if instr else ""))
    else:  # variant
        intent = (f"Create an ALTERNATE VARIANT themed around the colour {variant[0].upper()} "
                  f"({variant[2]}). Keep the genre/controls recognisable but give it a distinct "
                  f"mechanic twist, mood and a palette dominated by {variant[0]} ({variant[1]})."
                  + (f"\nExtra direction: \"{instr}\"." if instr else ""))

    # hard-coded size target (single-file ⇒ interpret 'file count' as code volume)
    size_mult = size_override if size_override is not None else ((cfg or {}).get("size_mult", 0) if mode != "variant" else 0)
    if size_mult and base_bytes:
        target = int(base_bytes * size_mult)
        if mode == "expansion":
            intent += (f"\n\nSIZE TARGET (HARD, NO CEILING): the source is ~{base_bytes // 1024} KB. "
                       f"Produce a DRAMATICALLY larger, deluxe game of AT LEAST {round(size_mult)}x the "
                       f"code volume — target ~{target // 1024} KB or MORE (never less than "
                       f"{int(target * 0.7) // 1024} KB). Bigger and richer is better; only stop when "
                       "the single file is genuinely packed with content. Add real depth, not filler.")
        else:
            intent += (f"\n\nSIZE TARGET (HARD): the source is ~{base_bytes // 1024} KB; you MUST produce a "
                       f"substantially larger game of roughly {round(size_mult)}x the code volume — "
                       f"target ~{target // 1024} KB (at least {int(target * 0.7) // 1024} KB). "
                       "Add real depth, not filler.")

    # EXPANSION ceiling-lift: feed more of the base + run the full deluxe quality
    # loop (more refines, higher target, far larger time budget) regardless of the
    # requested depth — expansion is inherently the flagship deluxe mode.
    profile = None
    base_ctx = 14000
    if mode == "expansion":
        depth = "studio"
        base_ctx = EXPANSION_HTML_CTX
        profile = {
            "max_repair": EXPANSION_MAX_REPAIR,
            "max_refine": EXPANSION_MAX_REFINE,
            "quality_target": EXPANSION_QUALITY_TARGET,
            "time_budget": EXPANSION_TIME_BUDGET,
            "html_ctx": EXPANSION_HTML_CTX,
        }

    prompt = (
        f"EXISTING GAME (full HTML below). {intent}\nReturn the FULL single-file HTML.\n\n"
        f"ORIGINAL BRIEF: {base_brief}\nORIGINAL TITLE: {base_title}\n\nCURRENT HTML:\n{base_html[:base_ctx]}"
    )
    title = (f"{prefix} {series_step} · {base_title}" if mode == "series" else f"{prefix} · {base_title}")[:60]

    gen = await _codegen_quality_loop(prompt, sys_prompt, base_brief, depth, profile)
    routed, html, removed, val = gen["routed"], gen["html"], gen["removed"], gen["val"]
    structurally_ok = bool(html) and val["score"] >= PLAYABILITY_THRESHOLD
    evaluation = gen.get("evaluation") or {"available": False, "reason": "skipped — failed structural gate"}
    pid = uuid.uuid4().hex
    doc = {
        "playable_id": pid, "title": title, "genre": base.get("genre", "arcade"),
        "brief": base_brief, "spec_id": base.get("spec_id"), "parent_id": base.get("playable_id"),
        "derive_mode": mode, "tweak": instr, "html": html, "bytes": len(html), "depth": depth,
        "variant_color": (variant[0] if variant else None),
        "variant_hex": (variant[1] if variant else None),
        "size_mult": size_mult or None, "base_bytes": base_bytes,
        "status": "ready" if structurally_ok else "failed",
        "playability_score": val["score"], "intricacy": val.get("intricacy"), "missing_checks": val["missing"],
        "repair_attempts": len(gen["trail"]), "repair_trail": gen["trail"],
        "evaluation": evaluation, "sanitized": removed,
        "model": routed.get("model"), "provider": routed.get("provider"),
        "latency_ms": routed.get("latency_ms"), "llm_error": routed.get("error"),
        "created_at": datetime.now(timezone.utc).isoformat(), "version": 1,
    }
    try:
        await _db.playables.insert_one(dict(doc))
        # 🔱 Remix attribution: bump the parent's remix_count (best-effort).
        parent_pid = base.get("playable_id")
        if parent_pid:
            await _db.playables.update_one({"playable_id": parent_pid}, {"$inc": {"remix_count": 1}})
    except Exception:
        pass
    out = {k: v for k, v in doc.items() if k != "html"}
    out["raw_path"] = f"/api/playable/{pid}/raw"
    return out


async def _do_variants(base: dict, depth: str) -> dict:
    """★ VARIANTS — produce FOUR alternate games in one go (red/blue/green/yellow),
    run concurrently. Returns a summary list under 'variants'."""
    results = await asyncio.gather(
        *[_do_derive(base, "variant", "", depth, variant=c) for c in _VARIANT_COLORS],
        return_exceptions=True,
    )
    variants = []
    for c, r in zip(_VARIANT_COLORS, results):
        if isinstance(r, dict):
            variants.append({"color": c[0], "hex": c[1], **r})
        else:
            variants.append({"color": c[0], "hex": c[1], "status": "failed", "error": str(r)})
    return {"kind": "variants", "variants": variants,
            "parent_id": base.get("playable_id"), "count": len(variants)}


# Snowball size multipliers per series step (entry N builds on N-1, escalating).
_SERIES_MULTS = [1.4, 1.7, 2.1, 2.6, 3.2]


async def _do_series(base: dict, steps: int, depth: str) -> dict:
    """★ SERIES — generate CONSECUTIVE games that snowball: each entry is derived
    from the PREVIOUS one with escalating complexity & intricacy. Sequential (each
    step needs the prior game's HTML as its base)."""
    steps = max(2, min(int(steps or 3), 5))
    chain, current = [], base
    for i in range(steps):
        mult = _SERIES_MULTS[min(i, len(_SERIES_MULTS) - 1)]
        child = await _do_derive(current, "series", "", depth,
                                 size_override=mult, series_step=i + 1, series_total=steps)
        chain.append({"step": i + 1, **child})
        if child.get("status") != "ready":
            break  # a broken entry can't be snowballed further
        full = await _db.playables.find_one({"playable_id": child["playable_id"]}, {"_id": 0})
        current = full or current
    return {"kind": "series", "series": chain,
            "parent_id": base.get("playable_id"), "count": len(chain)}


class RemixBody(BaseModel):
    tweak: str = ""
    depth: str = "studio"
    steps: int = 3


async def _kick_derive(pid: str, mode: str, instruction: str, depth: str = "studio") -> dict:
    """Shared validation + job kick for remix / sequel / competitor."""
    from core.anti_farm import allow
    if not allow(f"derive:{pid}", rate_per_sec=0.2, burst=4):
        return {"error": "rate_limited", "detail": "Too many generations on this game — slow down."}
    cfg = _DERIVE_MODES[mode]
    instr = (instruction or "").strip()
    if cfg["require_instr"] and len(instr) < cfg["min_instr"]:
        return {"error": f"instruction too short (min {cfg['min_instr']} chars)"}
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0})
    if not base or not base.get("html"):
        return {"error": "base playable not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": mode,
        "parent_id": pid, "tweak": instr[:300],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    asyncio.create_task(_run_job(job_id, _do_derive(base, mode, instr, depth)))
    return {"job_id": job_id, "job_status": "running"}


@router.post("/{pid}/remix/async")
async def remix_async(pid: str, body: RemixBody):
    """★ REMIX — iterate on an existing game with a tweak instruction. Async."""
    return await _kick_derive(pid, "remix", body.tweak, body.depth)


@router.post("/{pid}/sequel/async")
async def sequel_async(pid: str, body: RemixBody):
    """★ SEQUEL — build the next installment of an existing game. Async."""
    return await _kick_derive(pid, "sequel", body.tweak, body.depth)


@router.post("/{pid}/competitor/async")
async def competitor_async(pid: str, body: RemixBody):
    """★ COMPETITOR — a rival studio's reimagining that aims to out-do it
    (hard-coded PvP + puzzles, ~2x the code volume). Async."""
    return await _kick_derive(pid, "competitor", body.tweak, body.depth)


@router.post("/{pid}/prequel/async")
async def prequel_async(pid: str, body: RemixBody):
    """★ PREQUEL — the cozy, simplified ('snug') origin chapter before this game. Async."""
    return await _kick_derive(pid, "prequel", body.tweak, body.depth)


@router.post("/{pid}/expansion/async")
async def expansion_async(pid: str, body: RemixBody):
    """★ EXPANSION — a much larger, richer edition (~3x volume, heightened
    quality/intricacy/complexity) of the loaded game. Async."""
    return await _kick_derive(pid, "expansion", body.tweak, body.depth)


@router.post("/{pid}/variants/async")
async def variants_async(pid: str, body: RemixBody):
    """★ VARIANTS — produce FOUR colour-coded alternate games (red/blue/green/
    yellow) from one base, in a single job. Poll /job/{id}; the result carries
    kind='variants' with a `variants` array. Async."""
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0})
    if not base or not base.get("html"):
        return {"error": "base playable not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "variants",
        "parent_id": pid, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    asyncio.create_task(_run_job(job_id, _do_variants(base, body.depth)))
    return {"job_id": job_id, "job_status": "running"}


@router.post("/{pid}/interlude/async")
async def interlude_async(pid: str, body: RemixBody):
    """★ INTERLUDE — a between-chapters episode heavy on LORE and new MECHANICS. Async."""
    return await _kick_derive(pid, "interlude", body.tweak, body.depth)


@router.post("/{pid}/conclusion/async")
async def conclusion_async(pid: str, body: RemixBody):
    """★ CONCLUSION — the grand finale: full lore + gameplay wrap-up with 3+
    player-chosen MULTIPLE ENDINGS. Async."""
    return await _kick_derive(pid, "conclusion", body.tweak, body.depth)


@router.post("/{pid}/series/async")
async def series_async(pid: str, body: RemixBody):
    """★ SERIES — generate a SNOWBALL of consecutive games (default 3, max 5), each
    derived from the previous with escalating complexity/intricacy. Single job;
    result carries kind='series' with a `series` array. Async (sequential, slow)."""
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0})
    if not base or not base.get("html"):
        return {"error": "base playable not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "series",
        "parent_id": pid, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    asyncio.create_task(_run_job(job_id, _do_series(base, body.steps, body.depth)))
    return {"job_id": job_id, "job_status": "running"}
