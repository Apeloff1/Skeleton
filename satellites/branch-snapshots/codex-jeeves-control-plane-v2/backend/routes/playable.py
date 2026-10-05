"""
╔══════════════════════════════════════════════════════════════════════════╗
║  PHASE V.1 — REAL PLAYABLE EXPORT  (Playability & Physics)                 ║
║                                                                            ║
║  Closes the brief → spec → *playable* loop. Until now Galaxy Studio        ║
║  emitted FILES; this turns a brief (or a compiled design-spec) into an     ║
║  ACTUAL runnable game: a single, self-contained, mobile-touch HTML5 game   ║
║  that plays live in-app inside a WebView.                                   ║
║                                                                            ║
║  Flow:  brief / spec_id ──▶ Model Router (task='gameplay_code') ──▶ raw    ║
║  HTML ──▶ tolerant extract ──▶ ★ PLAYABILITY GATE (structural validation:  ║
║  canvas + game-loop + input + win/lose + offline self-containment) ──▶     ║
║  sanitize external <script src> ──▶ persist ──▶ served raw for the WebView.║
║                                                                            ║
║  ★ The gate refuses to ship a non-runnable artifact: if the LLM returns    ║
║  prose, a fragment, or a CDN-dependent page, status='failed' with the      ║
║  exact missing structural checks (so the UI can prompt a regenerate).      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import os
import threading
import base64
import re
import time
import json
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from core.databases import client as _SHARED_MONGO_CLIENT
from routes.llm_router import MODEL_CATALOG, ROUTING_POLICY, EMERGENT_LLM_KEY

router = APIRouter(prefix="/api/playable", tags=["playable"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]
PROJ = {"_id": 0}

PLAYABILITY_THRESHOLD = int(os.environ.get("PLAYABLE_MIN_SCORE", "70"))
# Provider-diverse codegen ensemble (mirrors the router's gameplay_code policy).
_GAME_ENSEMBLE = ROUTING_POLICY.get("gameplay_code", ["claude-sonnet-4-6", "gpt-5.4", "gemini-3.1-pro-preview"])
# Judge ensemble for the eval harness (reasoning-tilted; mirrors playtest_qa).
_JUDGE_ENSEMBLE = ROUTING_POLICY.get("playtest_qa", ["o3", "claude-sonnet-4-6", "gpt-5.4-mini"])
# I.5 — self-improving codegen: how many STRUCTURAL repair passes when the gate fails.
MAX_REPAIR = int(os.environ.get("PLAYABLE_MAX_REPAIR", "2"))
# Quality-driven refinement: total refine budget (structural + judge-driven quality passes).
# Each pass is an extra LLM round, so keep this modest (1 = one quality elevation pass).
MAX_REFINE = int(os.environ.get("PLAYABLE_MAX_REFINE", "1"))
# VII.1 — judge gate: minimum overall eval score to mark the build "shippable".
EVAL_SHIP_MIN = int(os.environ.get("PLAYABLE_EVAL_SHIP_MIN", "60"))
# Rigorous quality target: keep re-refining (within budget) until the judge's
# overall meets this bar. Higher ⇒ more intricate, more polished output.
QUALITY_TARGET = int(os.environ.get("PLAYABLE_QUALITY_TARGET", "85"))
# Adaptive latency guard: skip the (expensive) quality-refinement pass if the
# build has already consumed this many seconds — keeps total wall time bounded.
QUALITY_TIME_BUDGET = int(os.environ.get("PLAYABLE_QUALITY_TIME_BUDGET", "210"))

# ── EXPANSION "DELUXE" CEILING-LIFT ──────────────────────────────────────────
# Expansion is the flagship deluxe mode: bigger, richer, judge-elevated. Its
# generation alone runs minutes, so the normal QUALITY_TIME_BUDGET (210s) would
# expire BEFORE any quality-refinement pass — shipping un-elevated output. These
# overrides give expansion its own, far larger envelope so the full
# generate → repair → judge → refine loop actually runs to a high quality bar.
EXPANSION_SIZE_MULT = float(os.environ.get("PLAYABLE_EXPANSION_SIZE_MULT", "2.5"))
EXPANSION_MAX_REPAIR = int(os.environ.get("PLAYABLE_EXPANSION_MAX_REPAIR", "3"))
EXPANSION_MAX_REFINE = int(os.environ.get("PLAYABLE_EXPANSION_MAX_REFINE", "2"))
EXPANSION_QUALITY_TARGET = int(os.environ.get("PLAYABLE_EXPANSION_QUALITY_TARGET", "92"))
EXPANSION_TIME_BUDGET = int(os.environ.get("PLAYABLE_EXPANSION_TIME_BUDGET", "1200"))  # 20 min
EXPANSION_HTML_CTX = int(os.environ.get("PLAYABLE_EXPANSION_HTML_CTX", "28000"))

_GAME_SYS = """You are a WORLD-CLASS HTML5 game engineer and game designer. Build a COMPLETE, \
SELF-CONTAINED, SINGLE-FILE HTML5 game of EXCEPTIONAL depth and polish from the brief. \
Aim for maximal complexity and high intricacy — a game a studio would ship, not a toy demo.

HARD CONSTRAINTS (non-negotiable):
- Output ONLY one full HTML document, starting with <!DOCTYPE html>. No markdown fences, no prose.
- EVERYTHING inline: all CSS in <style>, all JS in <script>. NO external files, CDNs, <img src>, fonts, or network — it must run 100% offline.
- Render on a <canvas> sized responsively to the viewport (window.innerWidth/innerHeight; handle resize and devicePixelRatio for crisp visuals).
- A real requestAnimationFrame game loop with delta-time stepping (frame-rate independent).
- MOBILE-FIRST input: touchstart/touchmove/touchend or pointer events, big thumb-friendly zones; keyboard as a bonus. Prevent default scroll/zoom.
- A clear finite-state machine: MENU → PLAYING → PAUSED → GAME OVER/WIN, with tap-to-restart. On-screen HUD (score, lives/health, progress).

DEPTH & INTRICACY (strive for ALL of these):
- 2+ interacting mechanics (not just one), emergent combinations, and meaningful player decisions.
- A difficulty curve / progression: levels, waves, stages, or escalating speed/spawn — the game must evolve over time.
- Juice & game feel: particle effects, screen shake, easing/tweened motion, hit-flashes, combo/score popups.
- Procedural audio via the WebAudio API (AudioContext) — sfx for actions and a subtle musical/ambient layer (no audio files).
- Smart entities: simple AI/behaviours (chasing, dodging, patterns), spawn management, object pooling for performance.
- A coherent art direction: deliberate palette, gradients, glow/shadow, particles, readable typography drawn on canvas.
- Persist a high score to localStorage and surface it in the HUD.
- Robust: no console errors, clamp to device, handle edge cases, pause on blur/visibilitychange.

Make it genuinely fun, replayable, and impressive on a phone with one thumb. Favour richness over minimalism."""

# Fast lane — a leaner spec for quick iteration (smaller output ⇒ much faster).
_GAME_SYS_FAST = """You are an expert HTML5 game engineer. Build a COMPLETE, SELF-CONTAINED, \
SINGLE-FILE, mobile-touch HTML5 game from the brief — focused and quick to load.
HARD CONSTRAINTS:
- Output ONLY one full HTML document, starting with <!DOCTYPE html>. No markdown, no prose.
- EVERYTHING inline; NO external files/CDNs/network — runs 100% offline.
- A <canvas> sized to the viewport, a requestAnimationFrame loop, touch/pointer input.
- States: menu → playing → game over, with tap-to-restart; an on-screen score HUD; a win and a lose.
Keep it TIGHT: one strong core mechanic done well, a little juice (a few particles + simple WebAudio \
beeps), a clean palette, high-score in localStorage. Prefer something fun and runnable over sprawling \
features. Output ONLY the HTML document."""


from routes.playable_htmlutils import (  # HTML codegen utils (split out)
    _extract_html, _sanitize, _validate, _extract_json,
)


# Structural-repair system prompt: reuse the full game spec, then focus the model
# on fixing the failed playability checks and returning the COMPLETE document.
_REPAIR_SYS = _GAME_SYS + (
    "\n\nYOU ARE NOW IN REPAIR MODE. The previous attempt failed structural "
    "playability checks. Fix EVERY issue (missing canvas, game loop, input "
    "handling, state machine, offline-safety, etc.) and return the ENTIRE "
    "corrected HTML document — never a diff, never prose, never markdown fences."
)

# Judge-driven quality elevation: keep the game runnable while raising depth,
# polish and game-feel per the critique.
_QUALITY_SYS = _GAME_SYS + (
    "\n\nYOU ARE NOW IN QUALITY-ELEVATION MODE. The game already runs; raise its "
    "depth, intricacy, polish and game-feel per the judge's critique WITHOUT "
    "breaking it. Keep it fully offline and self-contained. Return the ENTIRE "
    "upgraded HTML document only — no prose, no markdown."
)

# Evaluation judge: scores the game and returns STRICT JSON only.
_JUDGE_SYS = (
    "You are a ruthless but fair senior game-QA judge. Play-read the supplied "
    "single-file HTML5 game and score it. Respond with STRICT MINIFIED JSON ONLY "
    "(no prose, no markdown) using EXACTLY these keys: "
    '{"playability":0-100,"coherence":0-100,"fun":0-100,"polish":0-100,'
    '"overall":0-100,"verdict":"ship|polish|reject","difficulty":"easy|medium|hard",'
    '"length":"short|medium|long","critique":"<=400 chars","top_fix":"<=300 chars"}. '
    "playability = does it actually run and is it controllable on a phone; coherence "
    "= does it match the brief and hold together; fun = engagement/replayability; "
    "polish = juice, art, audio, feel. Be strict: reserve overall >85 for genuinely "
    "great games."
)


async def _resolve_brief(brief: str, spec_id: str) -> tuple:
    """Turn either a raw brief or a stored design-spec into the build prompt +
    title/genre. Returns (prompt, title, genre)."""
    if spec_id:
        spec = await _db.design_specs.find_one({"spec_id": spec_id}, PROJ)
        if spec and spec.get("gdd"):
            g = spec["gdd"]
            mech = "; ".join(
                (m.get("name", "") if isinstance(m, dict) else str(m)) for m in (g.get("mechanics") or [])[:6]
            )
            prompt = (
                f"TITLE: {g.get('title', 'Untitled')}\n"
                f"GENRE: {g.get('genre', '')} / {g.get('subgenre', '')}\n"
                f"LOGLINE: {g.get('logline', '')}\n"
                f"CORE LOOP: {g.get('core_loop', '')}\n"
                f"KEY MECHANICS: {mech}\n"
                f"ART DIRECTION: {g.get('art_direction', '')}\n"
                "Build a playable mini-game that captures this core loop in one screen."
            )
            return prompt, g.get("title", "Untitled"), g.get("genre", "arcade")
    # raw brief path — derive a title heuristically
    b = (brief or "").strip()
    title = (b[:40].strip().rstrip(".") or "Untitled Game")
    return f"BRIEF: {b}\nBuild a playable mini-game that delivers this in one screen.", title, "arcade"


class GenerateBody(BaseModel):
    brief: str = ""
    spec_id: str = ""
    title: str = ""
    depth: str = "studio"
    creator_id: str = ""
    forged_from: str = ""
    derive_mode: str = ""


async def _llm_async(prompt: str, system: str, ensemble: list) -> dict:
    """Run a provider-diverse LLM ensemble (fallback) WITHOUT touching the
    main-loop Mongo client — safe to drive from a fresh loop inside a thread."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    if not EMERGENT_LLM_KEY:
        return {"content": "", "error": "EMERGENT_LLM_KEY not configured", "model": None, "provider": None}
    sid = f"playable-{uuid.uuid4().hex[:8]}"
    last_err = None
    for i, model in enumerate(ensemble):
        provider = MODEL_CATALOG.get(model, {}).get("provider", "openai")
        t0 = time.time()
        try:
            chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=sid,
                           system_message=system).with_model(provider, model)
            resp = await chat.send_message(UserMessage(text=prompt))
            content = resp.content if hasattr(resp, "content") else str(resp)
            return {"content": content, "model": model, "provider": provider,
                    "latency_ms": int((time.time() - t0) * 1000), "attempts": i + 1}
        except Exception as e:  # provider error → next in ensemble
            last_err = str(e)
    return {"content": "", "error": f"all models failed: {last_err}", "model": None, "provider": None}


# process-wide cap on concurrent LLM calls (smooths provider load + thread pool under bursts)
_LLM_SEM = threading.Semaphore(int(os.environ.get("LLM_MAX_CONCURRENCY", "3")))


def _llm_in_thread(prompt: str, system: str, ensemble: list) -> dict:
    """Blocking entrypoint executed in a worker thread (own event loop) so the
    underlying LLM call never freezes the server's main event loop.

    A process-wide semaphore caps concurrent LLM calls (default 3) so a burst of
    wire/polish jobs can't stampede the model providers or starve the thread pool.
    Threads simply wait their turn here — the event loop stays free."""
    with _LLM_SEM:
        return asyncio.run(_llm_async(prompt, system, ensemble))


async def _codegen_quality_loop(prompt: str, system: str, brief: str, depth: str = "studio",
                                profile: dict = None) -> dict:
    """★ RIGOROUS QUALITY PIPELINE (I.5 + VII.1 fused) — generate, then refine
    within a budget until the build is both STRUCTURALLY runnable and meets the
    judge's QUALITY_TARGET:
      1. structural repairs while the playability gate fails;
      2. judge-driven quality passes (using the judge's critique + top_fix) while
         the overall eval is below QUALITY_TARGET.
    Always keeps the BEST artifact (runnable first, then highest judged overall).
    Every LLM call is offloaded to a worker thread.

    `profile` (optional) lifts the per-mode ceiling — e.g. EXPANSION passes a far
    larger max_refine / quality_target / time_budget / html_ctx so its long,
    deluxe generation still receives full judge-driven elevation."""
    profile = profile or {}
    max_repair = int(profile.get("max_repair", MAX_REPAIR))
    base_refine = int(profile.get("max_refine", MAX_REFINE))
    quality_target = int(profile.get("quality_target", QUALITY_TARGET))
    time_budget = int(profile.get("time_budget", QUALITY_TIME_BUDGET))
    html_ctx = int(profile.get("html_ctx", 12000))
    repairs_left, refines_left = max_repair, (0 if depth == "fast" else base_refine)
    t_start = time.time()

    routed = await asyncio.to_thread(_llm_in_thread, prompt, system, _GAME_ENSEMBLE)
    html, removed = _sanitize(_extract_html(routed.get("content", "")))
    val = _validate(html)
    trail = [{"attempt": 1, "kind": "generate", "score": val["score"],
              "intricacy": val.get("intricacy"), "missing": val["missing"], "model": routed.get("model")}]
    best = {"routed": routed, "html": html, "removed": removed, "val": val, "evaluation": None}

    # ── phase 1: structural repairs (bounded by max_repair) ──
    while best["val"]["score"] < PLAYABILITY_THRESHOLD and repairs_left > 0:
        repairs_left -= 1
        repair_prompt = (
            f"ORIGINAL BRIEF/PROMPT:\n{prompt}\n\n"
            f"The previous attempt scored {best['val']['score']}/100 and FAILED these "
            f"checks: {', '.join(best['val']['missing']) or 'none'}.\n\n"
            f"PREVIOUS HTML (fix it, return the FULL corrected document):\n{best['html'][:html_ctx] or '(empty output)'}"
        )
        r2 = await asyncio.to_thread(_llm_in_thread, repair_prompt, _REPAIR_SYS, _GAME_ENSEMBLE)
        h2, rem2 = _sanitize(_extract_html(r2.get("content", "")))
        v2 = _validate(h2)
        trail.append({"attempt": len(trail) + 1, "kind": "structural_repair", "score": v2["score"],
                      "intricacy": v2.get("intricacy"), "missing": v2["missing"], "model": r2.get("model")})
        if v2["score"] > best["val"]["score"]:
            best = {"routed": r2, "html": h2, "removed": rem2, "val": v2, "evaluation": None}

    structurally_ok = bool(best["html"]) and best["val"]["score"] >= PLAYABILITY_THRESHOLD

    # ── phase 2: judge-driven quality refinement (bounded by max_refine) ──
    if structurally_ok:
        best["evaluation"] = await _judge_eval(best["html"], brief)
        while (refines_left > 0 and best["evaluation"].get("available")
               and best["evaluation"].get("overall", 0) < quality_target
               and (time.time() - t_start) < time_budget):
            refines_left -= 1
            ev = best["evaluation"]
            quality_prompt = (
                f"ORIGINAL BRIEF/PROMPT:\n{prompt}\n\n"
                f"A QA judge scored the current game {ev.get('overall')}/100 "
                f"(playability {ev.get('playability')}, coherence {ev.get('coherence')}, "
                f"fun {ev.get('fun')}, polish {ev.get('polish')}).\n"
                f"CRITIQUE: {ev.get('critique')}\nTOP FIX: {ev.get('top_fix')}\n"
                f"Also strengthen any missing depth: {', '.join(best['val']['missing']) or 'none'}.\n\n"
                f"CURRENT HTML (upgrade it, return the FULL document):\n{best['html'][:html_ctx]}"
            )
            r3 = await asyncio.to_thread(_llm_in_thread, quality_prompt, _QUALITY_SYS, _GAME_ENSEMBLE)
            h3, rem3 = _sanitize(_extract_html(r3.get("content", "")))
            v3 = _validate(h3)
            cand_ok = bool(h3) and v3["score"] >= PLAYABILITY_THRESHOLD
            ev3 = await _judge_eval(h3, brief) if cand_ok else {"available": False}
            trail.append({"attempt": len(trail) + 1, "kind": "quality_repair", "score": v3["score"],
                          "intricacy": v3.get("intricacy"), "eval_overall": ev3.get("overall"),
                          "model": r3.get("model")})
            # accept only if it stays runnable AND the judge likes it more
            if cand_ok and ev3.get("available") and ev3.get("overall", 0) > best["evaluation"].get("overall", 0):
                best = {"routed": r3, "html": h3, "removed": rem3, "val": v3, "evaluation": ev3}
    else:
        best["evaluation"] = {"available": False, "reason": "skipped — failed structural gate"}

    return {**best, "trail": trail}


async def _judge_eval(html: str, brief: str) -> dict:
    """★ VII.1 AUTOMATED EVAL HARNESS — a judge LLM scores the game on
    playability / coherence / fun / polish and returns a ship/polish/reject
    verdict. Offloaded to a worker thread; never raises."""
    if not html:
        return {"available": False, "reason": "no html to evaluate"}
    prompt = (f"BRIEF:\n{brief or '(none)'}\n\nGAME HTML (may be truncated):\n{html[:14000]}\n\nScore this game.")
    routed = await asyncio.to_thread(_llm_in_thread, prompt, _JUDGE_SYS, _JUDGE_ENSEMBLE)
    data = _extract_json(routed.get("content", ""))
    if not data:
        return {"available": False, "reason": routed.get("error") or "judge returned no JSON",
                "judge_model": routed.get("model")}

    def _clamp(v):
        try:
            return max(0, min(100, int(v)))
        except (TypeError, ValueError):
            return 0
    axes = {k: _clamp(data.get(k, 0)) for k in ("playability", "coherence", "fun", "polish")}
    overall = _clamp(data.get("overall", round(sum(axes.values()) / 4)))
    verdict = str(data.get("verdict", "")).lower()
    if verdict not in ("ship", "polish", "reject"):
        verdict = "ship" if overall >= EVAL_SHIP_MIN else "polish"
    difficulty = str(data.get("difficulty", "")).lower()
    if difficulty not in ("easy", "medium", "hard"):
        difficulty = "medium"
    length = str(data.get("length", "")).lower()
    if length not in ("short", "medium", "long"):
        length = "medium"
    return {
        "available": True, **axes, "overall": overall, "verdict": verdict,
        "difficulty": difficulty, "length": length,
        "critique": str(data.get("critique", ""))[:400],
        "top_fix": str(data.get("top_fix", ""))[:300],
        "judge_model": routed.get("model"),
        "shippable": overall >= EVAL_SHIP_MIN,
    }


async def _persist(prompt: str, title: str, genre: str, brief: str, spec_id: str,
                   parent_id: str, remix_of_brief: str, depth: str = "studio",
                   forged_from: str = "", derive_mode: str = "") -> dict:
    """Shared pipeline: rigorous quality loop (codegen → structural repair →
    judge-driven quality refinement) → persist. Used by fresh generation."""
    gen_system = _GAME_SYS_FAST if depth == "fast" else _GAME_SYS
    gen = await _codegen_quality_loop(prompt, gen_system, remix_of_brief or brief, depth)
    routed, html, removed, val = gen["routed"], gen["html"], gen["removed"], gen["val"]
    llm_error = routed.get("error")
    structurally_ok = bool(html) and val["score"] >= PLAYABILITY_THRESHOLD

    evaluation = gen.get("evaluation") or {"available": False, "reason": "skipped — failed structural gate"}
    status = "ready" if structurally_ok else "failed"

    pid = uuid.uuid4().hex
    doc = {
        "playable_id": pid,
        "title": title,
        "genre": genre,
        "brief": brief,
        "spec_id": spec_id or None,
        "parent_id": parent_id or None,
        "html": html,
        "bytes": len(html),
        "status": status,
        "playability_score": val["score"],
        "intricacy": val.get("intricacy"),
        "missing_checks": val["missing"],
        "repair_attempts": len(gen["trail"]),
        "repair_trail": gen["trail"],
        "evaluation": evaluation,
        "sanitized": removed,
        "model": routed.get("model"),
        "provider": routed.get("provider"),
        "latency_ms": routed.get("latency_ms"),
        "llm_error": llm_error,
        "depth": depth,
        "forged_from": forged_from or None,
        "derive_mode": derive_mode or None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": 1,
    }
    try:
        await _db.playables.insert_one(dict(doc))
    except Exception:
        pass
    # VII.5 auto-gate: deterministic content-policy scan at creation so unsafe
    # content never reaches the public catalogue. block→hidden, review→review.
    try:
        from routes.governance import _policy_scan, _audit
        scan = _policy_scan(" ".join([title or "", brief or "", html or ""]))
        mod = "hidden" if scan["verdict"] == "block" else ("review" if scan["verdict"] == "review" else "ok")
        await _db.playables.update_one(
            {"playable_id": pid},
            {"$set": {"policy_scan": {**scan, "scanned_at": datetime.now(timezone.utc).isoformat()},
                      "moderation_status": mod}})
        doc["moderation_status"] = mod
        doc["policy_scan"] = scan
        if mod != "ok":
            await _audit("auto_scan", pid, "system",
                         {"verdict": scan["verdict"], "flags": len(scan["flags"]), "moderation_status": mod})
    except Exception:
        pass
    out = {k: v for k, v in doc.items() if k != "html"}
    out["raw_path"] = f"/api/playable/{pid}/raw"
    return out


async def _do_generate(brief: str, spec_id: str, title_override: str, depth: str = "studio", creator_id: str = "", forged_from: str = "", derive_mode: str = "") -> dict:
    """Fresh generation from a brief or design-spec."""
    prompt, title, genre = await _resolve_brief(brief, spec_id)
    if title_override:
        title = title_override
    # Per-creator Studio Preferences bias (additive; brief still wins).
    try:
        from routes.creator_prefs import preference_bias
        bias = await preference_bias(creator_id)
        if bias:
            prompt = f"{prompt}{bias}"
    except Exception:
        pass
    return await _persist(prompt, title, genre, brief, spec_id, "", "", depth, forged_from, derive_mode)




def _validate_body(body: "GenerateBody") -> str:
    brief = (body.brief or "").strip()
    if not brief and not body.spec_id:
        return "provide a brief or a spec_id"
    if brief and len(brief) < 8:
        return "brief too short (min 8 chars)"
    if len(brief) > 6000:
        return "brief exceeds 6k char limit"
    return ""


@router.post("/generate")
async def generate(body: GenerateBody):
    """Generate synchronously (can run 60-180s with repair+eval). Prefer
    /generate/async + /job/{id} polling from clients."""
    err = _validate_body(body)
    if err:
        return {"error": err}
    return await _do_generate((body.brief or "").strip(), body.spec_id, body.title, body.depth, body.creator_id)


async def _run_job(job_id: str, coro):
    """Background runner — full generation never hits a request timeout."""
    try:
        out = await coro
        out["job_id"] = job_id
        out["job_status"] = "done"
        await _db.playable_jobs.update_one({"job_id": job_id}, {"$set": out}, upsert=True)
    except Exception as e:
        await _db.playable_jobs.update_one(
            {"job_id": job_id}, {"$set": {"job_status": "error", "error": str(e)}}, upsert=True)


@router.post("/generate/async")
async def generate_async(body: GenerateBody):
    """Kick a game generation (with auto-repair + judge eval) in the background;
    poll /job/{job_id}."""
    err = _validate_body(body)
    if err:
        return {"error": err}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "generate",
        "brief": (body.brief or "").strip()[:500],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    asyncio.create_task(_run_job(job_id, _do_generate((body.brief or "").strip(), body.spec_id, body.title, body.depth, body.creator_id, body.forged_from, body.derive_mode)))
    return {"job_id": job_id, "job_status": "running"}




class VoteBody(BaseModel):
    opponent_id: str = ""
    winner_id: str = ""


@router.post("/{pid}/vote")
async def vote(pid: str, body: VoteBody):
    """★ VS PLAY — record a head-to-head vote between two playables. Increments
    wins on the winner and matches on both; returns the updated tallies."""
    opp = (body.opponent_id or "").strip()
    winner = (body.winner_id or "").strip()
    if not opp or winner not in (pid, opp):
        return {"error": "winner_id must be this id or opponent_id, and opponent_id is required"}
    both = await _db.playables.find({"playable_id": {"$in": [pid, opp]}}, {"_id": 0, "playable_id": 1}).to_list(2)
    found = {d["playable_id"] for d in both}
    if pid not in found or opp not in found:
        return {"error": "both playables must exist"}
    loser = opp if winner == pid else pid
    await _db.playables.update_one({"playable_id": winner}, {"$inc": {"wins": 1, "matches": 1}})
    await _db.playables.update_one({"playable_id": loser}, {"$inc": {"matches": 1}})
    await _log_event(winner, "vote")

    async def _tally(x):
        d = await _db.playables.find_one({"playable_id": x}, {"_id": 0, "wins": 1, "matches": 1})
        return {"wins": (d or {}).get("wins", 0), "matches": (d or {}).get("matches", 0)}
    return {"this": await _tally(pid), "opponent": await _tally(opp), "winner_id": winner}


# ── EXPANSION: import a Galaxy-Studio questionnaire build into a Playable ──
def _brief_from_build(b: dict) -> tuple:
    """Translate a Galaxy-Studio questionnaire build (galaxy_builds doc) into a
    playable brief + title + genre, so games designed via the builder import in
    one tap."""
    genres = [g for g in (b.get("genres") or [b.get("genre")]) if g]
    subs = [s for s in (b.get("subgenres") or ([b.get("subgenre")] if b.get("subgenre") else [])) if s]
    title = b.get("title") or "Untitled"
    parts = [f"TITLE: {title}"]
    if genres:
        parts.append("GENRE: " + ", ".join(genres))
    if subs:
        parts.append("SUBGENRE: " + ", ".join(subs))
    for key, label in (("perspective", "PERSPECTIVE"), ("era", "ERA"), ("setting", "SETTING"),
                       ("theme", "THEME"), ("art_style", "ART STYLE"), ("tone", "TONE"),
                       ("logline", "LOGLINE"), ("description", "DESCRIPTION")):
        v = b.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(f"{label}: {v.strip()[:300]}")
    mechs = [k[:-10].replace("_", " ") for k, v in b.items()
             if k.endswith("_mechanics") and isinstance(v, (int, float)) and v >= 7]
    if mechs:
        parts.append("EMPHASIZED MECHANICS: " + ", ".join(sorted(mechs)[:12]))
    parts.append("Build a single-screen, mobile-touch playable mini-game that captures this game's "
                 "core loop, genre feel and theme — a faithful, fun distillation of the full design.")
    return "\n".join(parts), title, (genres[0] if genres else "arcade")


class ImportBody(BaseModel):
    build_id: str = ""
    depth: str = "studio"


async def _get_build(bid: str) -> dict:
    """Find a Galaxy build by id in the active collection or the archive
    (completed builds are moved to galaxy_build_archive by the watchdog)."""
    b = await _db.galaxy_builds.find_one({"build_id": bid}, {"_id": 0})
    if not b:
        b = await _db.galaxy_build_archive.find_one({"build_id": bid}, {"_id": 0})
    return b or {}


async def _do_import(build: dict, depth: str) -> dict:
    prompt, title, genre = _brief_from_build(build)
    brief = f"(imported from Galaxy build {build.get('build_id')})"
    out = await _persist(prompt, title, genre, brief, "", "", "", depth)
    try:
        await _db.playables.update_one(
            {"playable_id": out["playable_id"]},
            {"$set": {"source_build_id": build.get("build_id"), "imported": True}})
        out["source_build_id"] = build.get("build_id")
        out["imported"] = True
    except Exception:
        pass
    return out


@router.get("/import/builds")
async def importable_builds(limit: int = Query(40, le=100)):
    """List Galaxy-Studio questionnaire builds available to import as playables —
    merges active builds + the completed-build archive (deduped, newest first)."""
    LIGHT = {"_id": 0, "build_id": 1, "title": 1, "genre": 1, "subgenre": 1,
             "status": 1, "created_at": 1}
    active = await _db.galaxy_builds.find({}, LIGHT).sort("created_at", -1).limit(limit).to_list(limit)
    archived = await _db.galaxy_build_archive.find({}, LIGHT).sort("created_at", -1).limit(limit).to_list(limit)
    seen, merged = set(), []
    for b in active + archived:
        bid = b.get("build_id")
        if bid and bid not in seen:
            seen.add(bid)
            merged.append(b)
    merged.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return {"builds": merged[:limit], "count": len(merged[:limit])}


@router.post("/import-build/async")
async def import_build_async(body: ImportBody):
    """★ VAULT IMPORT — turn a game designed in the Galaxy Studio questionnaire
    into an instantly-playable game. Async (poll /job/{id})."""
    bid = (body.build_id or "").strip()
    if not bid:
        return {"error": "build_id required"}
    build = await _get_build(bid)
    if not build:
        return {"error": "build not found in vault"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "import",
        "source_build_id": bid, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    asyncio.create_task(_run_job(job_id, _do_import(build, body.depth)))
    return {"job_id": job_id, "job_status": "running"}


def _champ_rank(d: dict) -> float:
    wins = d.get("wins", 0) or 0
    matches = d.get("matches", 0) or 0
    win_rate = (wins + 2) / (matches + 4) if matches else 0.5
    ev = (d.get("evaluation") or {}).get("overall", 0) or 0
    intr = d.get("intricacy", 0) or 0
    popularity = min((d.get("plays", 0) or 0) / 50.0, 1.0) * 8
    loved = min(sum((d.get("reactions") or {}).values()) / 30.0, 1.0) * 6
    return win_rate * 55 + (ev / 100) * 35 + (intr / 7) * 10 + popularity + loved







# ── Engagement & Discovery: play counters · trending · daily challenge · arena ──
async def _log_event(pid: str, kind: str):
    """Append a lightweight activity event (play / vote) used to compute Trending.
    Best-effort: never raises into the request path."""
    try:
        await _db.playable_events.insert_one({
            "playable_id": pid, "kind": kind,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass




@router.get("/job/{job_id}")
async def get_job(job_id: str):
    doc = await _db.playable_jobs.find_one({"job_id": job_id}, PROJ)
    if not doc:
        return {"error": "not found", "job_status": "unknown"}
    # self-heal orphaned jobs: an async task that was killed by a server restart
    # leaves its doc stuck "running" forever — expire it so the UI stops spinning.
    if doc.get("job_status") == "running":
        created = doc.get("created_at")
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(created))).total_seconds()
        except Exception:
            age = 0
        if age > 480:  # 8 min hard ceiling — frees a stage if a forge task was killed by a restart
            await _db.playable_jobs.update_one({"job_id": job_id}, {"$set": {
                "job_status": "error", "error": "job interrupted (likely a server restart) — please retry",
                "swept_at": datetime.now(timezone.utc).isoformat()}})
            doc["job_status"] = "error"
            doc["error"] = "job interrupted (likely a server restart) — please retry"
    return doc


@router.get("/llm-stats")
async def llm_stats():
    """🔭 Tiny ops surface: current in-flight LLM calls vs the global concurrency cap."""
    mx = int(os.environ.get("LLM_MAX_CONCURRENCY", "3"))
    avail = _LLM_SEM._value
    return {"max": mx, "available": avail, "in_flight": max(0, mx - avail)}


@router.get("/list")
async def list_playables(limit: int = Query(20, le=100)):
    items = await _db.playables.find(
        {}, {**PROJ, "html": 0, "cover_b64": 0, "repair_trail": 0, "sanitized": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"playables": items, "count": len(items)}


@router.get("/{pid}/lineage")
async def get_lineage(pid: str):
    """★ LINEAGE — the family tree of a playable: its ancestor chain (parents up
    to the original) and its direct children (remix / sequel / competitor)."""
    LIGHT = {"_id": 0, "playable_id": 1, "title": 1, "genre": 1, "status": 1,
             "parent_id": 1, "derive_mode": 1, "playability_score": 1, "has_cover": 1,
             "remix_count": 1, "evaluation.overall": 1, "evaluation.verdict": 1, "created_at": 1}
    node = await _db.playables.find_one({"playable_id": pid}, LIGHT)
    if not node:
        return {"error": "not found"}
    # ancestors (walk parent_id up, guard against cycles / runaway)
    ancestors = []
    cur, seen, hops = node, {pid}, 0
    while cur.get("parent_id") and hops < 25:
        hops += 1
        if cur["parent_id"] in seen:
            break
        seen.add(cur["parent_id"])
        parent = await _db.playables.find_one({"playable_id": cur["parent_id"]}, LIGHT)
        if not parent:
            break
        ancestors.append(parent)
        cur = parent
    ancestors.reverse()  # original first
    children = await _db.playables.find(
        {"parent_id": pid}, LIGHT
    ).sort("created_at", -1).limit(50).to_list(50)
    return {"node": node, "ancestors": ancestors, "children": children,
            "ancestor_count": len(ancestors), "child_count": len(children)}


@router.get("/{pid}")
async def get_playable(pid: str):
    doc = await _db.playables.find_one({"playable_id": pid}, PROJ)
    if not doc:
        return {"error": "not found"}
    return doc


@router.get("/{pid}/validate")
async def validate_playable(pid: str):
    """DEBUG — return the per-check structural breakdown from _validate() for a
    stored game, alongside its persisted playability_score. Lets you eyeball the
    scoring heuristics against existing games and confirm gate parity."""
    doc = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "html": 1, "title": 1, "playability_score": 1, "status": 1})
    if not doc:
        return {"error": "not found"}
    val = _validate(doc.get("html") or "")
    return {
        "playable_id": pid, "title": doc.get("title"), "status": doc.get("status"),
        "stored_playability_score": doc.get("playability_score"),
        "recomputed_score": val["score"],
        "passes_gate": val["score"] >= PLAYABILITY_THRESHOLD,
        "threshold": PLAYABILITY_THRESHOLD,
        "checks": val["checks"], "missing": val["missing"], "intricacy": val["intricacy"],
        "signals": val.get("signals", {}), "depth_hits": val.get("depth_hits", 0),
        "bytes": val.get("bytes", 0),
    }


@router.get("/{pid}/raw", response_class=HTMLResponse)
async def get_playable_raw(pid: str):
    """Serve the game HTML directly so a WebView can load it by URI.
    A tiny error-reporter shim is injected so the host /playable screen can detect
    runtime crashes and offer one-tap Auto-repair (works in both iframe & WebView)."""
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1})
    if not doc or not doc.get("html"):
        return HTMLResponse(
            "<!DOCTYPE html><html><body style='background:#0a0a14;color:#fca5a5;"
            "font-family:sans-serif;display:flex;align-items:center;justify-content:center;"
            "height:100vh;margin:0'><div>Game not found.</div></body></html>",
            status_code=404,
        )
    return HTMLResponse(_inject_error_reporter(doc["html"]))


_ERROR_REPORTER = (
    "<script>(function(){function R(m){try{if(window.ReactNativeWebView)"
    "window.ReactNativeWebView.postMessage(JSON.stringify({__pl_error:true,message:String(m)}));}catch(e){}"
    "try{if(window.parent&&window.parent!==window)window.parent.postMessage({__pl_error:true,message:String(m)},'*');}catch(e){}}"
    "window.addEventListener('error',function(e){R((e&&e.message)||'Script error');"
    "if(e&&e.preventDefault){e.preventDefault();}return true;},true);"
    "window.addEventListener('unhandledrejection',function(e){R('Unhandled rejection: '+((e&&e.reason&&e.reason.message)||e.reason||''));"
    "if(e&&e.preventDefault){e.preventDefault();}});"
    "window.onerror=function(m){R(m||'Script error');return true;};"
    "})();</script>"
)


def _inject_error_reporter(html: str) -> str:
    """Insert the runtime error-reporter as the FIRST script so it catches early
    temporal-dead-zone / reference errors in the game's own code."""
    if not html:
        return html
    low = html.lower()
    i = low.find("<head>")
    if i != -1:
        pos = i + len("<head>")
        return html[:pos] + _ERROR_REPORTER + html[pos:]
    i = low.find("<body")
    if i != -1:
        end = html.find(">", i)
        if end != -1:
            return html[:end + 1] + _ERROR_REPORTER + html[end + 1:]
    return _ERROR_REPORTER + html
