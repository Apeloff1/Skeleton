"""
✨ SNOWBALL AUTO-IMPROVE — the quality retry loop on top of the 13-signal audit suite.

Flow (summary-FIRST, then retry):
  1. POST /auto-improve        → runs the full audit, writes a READABLE audit log, and asks the
                                 LLM for a "full summary of possible upgrades" per failing signal.
                                 Returns the summary. NOTHING is regenerated yet.
  2. POST /auto-improve/retry  → applies that guidance: marks the weak stages stale, stores the
                                 upgrade directives on the game + KB, and kicks the GroupChat
                                 regen so weak stages rebuild with the upgrades → re-audit.

Also: per-stage vault loading (manual passes), a printable World Atlas, and the 95-gated
Marketplace publish toggle.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from core.databases import client as _MONGO
from core.stage_vault import vault_for_stage
from routes.snowball_audit import snowball_audit, DELIVER_THRESHOLD
from routes.snowball import _LADDER, _compile_gdd

router = APIRouter(prefix="/api/snowball", tags=["snowball"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]

# 🔌 Vault "game-mount": every build step that should draw on the knowledge vault.
_ALL_BUILD_STEPS = [
    "spec", "world", "narrative", "narrative_vo", "mechanics", "systems", "balance",
    "procedural", "assets", "vfx", "audio", "ui", "multiplayer", "qa", "build",
    "monetization", "launch",
]


@router.get("/vault/connectivity")
async def vault_connectivity():
    """🔌 Report the vault 'game-mount': for every game-building step, whether the
    knowledge vault is connected (domains + tips wired). Surfaces any unmounted step."""
    from core.stage_vault import vault_for_stage, _STAGE_PROFILE
    steps = []
    connected = 0
    for st in _ALL_BUILD_STEPS:
        v = vault_for_stage(st)
        has_profile = st in _STAGE_PROFILE
        is_conn = v["domain_count"] > 0
        if is_conn:
            connected += 1
        steps.append({
            "step": st,
            "mounted": has_profile,
            "connected": is_conn,
            "domain_count": v["domain_count"],
            "domains": [d["name"] for d in v["domains"]],
            "tips_sample": v["tips"][:2],
        })
    total = len(_ALL_BUILD_STEPS)
    return {
        "total_steps": total,
        "connected_steps": connected,
        "coverage_pct": round(100 * connected / max(1, total)),
        "fully_mounted": connected == total,
        "steps": steps,
    }



# audit level key → the pipeline stage whose regeneration fixes it
_LEVEL_STAGE = {
    "canon_consistency": "narrative", "reference_integrity": "narrative",
    "narrative_depth": "narrative", "mechanical_coherence": "mechanics",
    "world_density": "world", "asset_coverage": "assets",
    "build_readiness": "build", "playability_qa": "qa",
}
_STAGE_ART = {"spec": "core_specs", "world": "lore_graph", "narrative": "quest_db",
              "mechanics": "mechanics_config", "procedural": "procedural_config",
              "assets": "asset_manifest", "qa": "qa_report", "build": "build_manifest",
              "launch": "launch_manifest"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/{pid}/vault/{stage}")
async def stage_vault(pid: str, stage: str):
    """🧠 Load the knowledge vault for ONE stage — domains + concrete tips for manual passes."""
    if stage not in _STAGE_ART:
        return {"error": f"unknown stage '{stage}'", "valid": list(_STAGE_ART.keys())}
    return {"game_id": pid, **vault_for_stage(stage)}


def _readable_log(audit: dict) -> list[str]:
    """Human-readable, line-by-line audit log (big-win: 'all audits log be readable')."""
    lines = [f"AUDIT — {audit.get('title','(untitled)')} — {audit['at']}",
             f"GATE FLOOR {audit['gate_floor']}/100  (threshold {audit['threshold']})  "
             f"→ {'SHIP-READY ✓' if audit['deliverable'] else 'BLOCKED ✗'}", "",
             "Levels:"]
    for lv in audit["levels"]:
        mark = "PASS" if lv["pass"] else "FAIL"
        lines.append(f"  [{mark}] {lv['label']:<22} {lv['score']:>3}/100  (band {lv['band']})")
    llm = audit.get("llm")
    if llm:
        lines += ["", "LLM confirmation:",
                  f"  Quality {llm['quality']}  ·  Parse {llm['parse_confidence']}  ·  Recall {llm['recall']}",
                  f"  Notes: {llm.get('notes','')}"]
    lines += ["", f"Blockers ({audit['blocker_count']}): "
              + ", ".join(f"{b['level']}={b['score']}" for b in audit["blockers"])]
    return lines


@router.post("/{pid}/auto-improve")
async def auto_improve(pid: str):
    """🔍 Run the full 13-signal audit, emit a readable log, and have the LLM deliver a FULL
    summary of possible upgrades per failing signal — BEFORE any regeneration."""
    from routes.llm_router import route_complete
    audit = await snowball_audit(pid, deep=True)
    if audit.get("error"):
        return audit

    log = _readable_log(audit)
    blockers = audit["blockers"]
    weak_stages = sorted({_LEVEL_STAGE[b_key] for b in blockers
                          for b_key in [next((lv["key"] for lv in audit["levels"]
                                              if lv["label"] == b["level"]), "")]
                          if b_key in _LEVEL_STAGE})

    upgrades = []
    if blockers:
        mode = "improvement"
        gdd = _compile_gdd(audit.get("title", ""), mode, {})
        blk = "\n".join(f"- {b['level']} = {b['score']}/100 (needs {DELIVER_THRESHOLD})" for b in blockers)
        system = (
            "You are a lead game producer running a quality-uplift pass. For EACH failing audit "
            "signal, give ONE specific, high-impact upgrade that would push it to 95+. Output ONLY "
            'a JSON array of {"signal":str,"current":int,"upgrade":"concrete 1-2 sentence action",'
            '"impact":"why it lifts the score"}. Be concrete and buildable, no fluff.')
        prompt = f"GAME: {audit.get('title','')}\n\nFAILING SIGNALS:\n{blk}\n\nGAME SUMMARY:\n{gdd[:6000]}"
        res = await route_complete("reasoning", prompt, system=system,
                                   session_id=f"improve-{pid}", timeout_s=60, use_cache=False)
        if not res.get("error"):
            from routes.canon_graph import _extract_json_array
            upgrades = _extract_json_array(res.get("content", ""))

    run = {"game_id": pid, "at": _now(), "gate_floor": audit["gate_floor"],
           "deliverable": audit["deliverable"], "blocker_count": audit["blocker_count"],
           "weak_stages": weak_stages, "upgrades": upgrades, "log": log, "_kind": "improve"}
    await _db.snowball_improve_runs.insert_one(dict(run))
    run.pop("_id", None)
    return {**run,
            "summary": f"{len(upgrades)} upgrades proposed across {len(weak_stages)} weak stage(s). "
                       f"Review, then POST /auto-improve/retry to apply + regenerate."}


@router.post("/{pid}/remaster")
async def remaster(pid: str):
    """🎚️ One-tap Remaster: audit the build, propose concrete upgrades, and return a
    before → projected-after scorecard diff. Non-destructive (does not regenerate);
    call /auto-improve/retry to actually apply the uplift."""
    from routes.snowball_audit import snowball_audit, DELIVER_THRESHOLD
    before = await snowball_audit(pid, deep=True)
    if before.get("error"):
        return before
    plan = await auto_improve(pid)
    upgrades = plan.get("upgrades", []) if isinstance(plan, dict) else []
    threshold = before.get("threshold", DELIVER_THRESHOLD)
    levels_diff = []
    for lv in before.get("levels", []):
        after = lv["score"] if lv["score"] >= threshold else threshold
        levels_diff.append({"label": lv["label"], "before": lv["score"],
                            "after": after, "lifted": after - lv["score"]})
    before_overall = before.get("deterministic_overall") or before.get("gate_floor") or 0
    after_overall = round(sum(l["after"] for l in levels_diff) / max(1, len(levels_diff))) if levels_diff else before_overall
    return {
        "game_id": pid, "title": before.get("title", ""), "threshold": threshold,
        "before": {"overall": before_overall, "gate_floor": before.get("gate_floor"),
                   "deliverable": before.get("deliverable"), "blockers": before.get("blockers", [])},
        "after_projected": {"overall": after_overall, "gate_floor": threshold if levels_diff else before_overall,
                            "deliverable": True},
        "levels_diff": levels_diff, "upgrades": upgrades, "applied": False,
        "note": "Projected uplift. POST /api/snowball/{pid}/auto-improve/retry to regenerate weak stages.",
    }



@router.post("/{pid}/auto-improve/retry")
async def auto_improve_retry(pid: str):
    """♻️ Apply the latest auto-improve guidance: store directives, mark weak stages stale, and
    kick the GroupChat regen so they rebuild with the upgrades. Returns the regen job_id."""
    from routes.groupchat import run_groupchat
    run = await _db.snowball_improve_runs.find_one(
        {"game_id": pid}, sort=[("at", -1)])
    if not run:
        return {"error": "no auto-improve run found — call POST /auto-improve first."}
    weak = run.get("weak_stages") or []
    upgrades = run.get("upgrades") or []
    if not weak:
        return {"ok": True, "regenerated": False,
                "message": "No weak stages to regenerate — already ship-quality ✨"}

    # store directives on the game + KB so forges / manual passes see the guidance
    directives = [f"{u.get('signal','')}: {u.get('upgrade','')}" for u in upgrades if u.get("upgrade")]
    await _db.playables.update_one(
        {"playable_id": pid},
        {"$set": {"upgrade_directives": directives, "upgrade_directives_at": _now()}})
    stale_set = {f"stale.{_STAGE_ART[s]}": True for s in weak if s in _STAGE_ART}
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$set": {"game_id": pid, "upgrade_guidance": directives, **stale_set}}, upsert=True)

    job = await run_groupchat(pid, only_missing=False, only_stale=True)
    return {"ok": True, "regenerated": True, "weak_stages": weak,
            "directive_count": len(directives), "job_id": job.get("job_id"),
            "message": f"Regenerating {len(weak)} stage(s) with {len(directives)} upgrade directive(s). "
                       f"Poll /api/groupchat/job/{job.get('job_id')}, then re-audit."}


@router.get("/{pid}/atlas.html", response_class=HTMLResponse)
async def world_atlas(pid: str):
    """📖 Printable 'World Atlas' — a styled, print-ready HTML codex of the whole game
    (use the browser's Print → Save as PDF). Big-win (a)."""
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "derive_mode": 1})
    if not g:
        return HTMLResponse("<h1>Game not found</h1>", status_code=404)
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    arts = (kb or {}).get("artifacts") or {}
    title = g.get("title", "Untitled World")
    mode = g.get("derive_mode") or g.get("genre") or "original"
    gdd = _compile_gdd(title, mode, arts)

    sections = []
    import html as _html
    for block in gdd.split("\n## "):
        block = block.strip()
        if not block:
            continue
        head, _, body = block.partition("\n")
        head = head.lstrip("# ").strip()
        sections.append(
            f'<section><h2>{_html.escape(head)}</h2>'
            f'<pre>{_html.escape(body.strip())}</pre></section>')
    body_html = "\n".join(sections) or "<p>No canon built yet.</p>"
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{_html.escape(title)} — World Atlas</title>
<style>
  @page {{ margin: 22mm; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #1a1a2e; max-width: 820px; margin: 0 auto; padding: 40px 24px; line-height: 1.55; }}
  .cover {{ text-align:center; padding: 80px 0 48px; border-bottom: 3px double #6d28d9; margin-bottom: 36px; }}
  .cover h1 {{ font-size: 46px; margin: 0 0 8px; color:#4c1d95; letter-spacing: 1px; }}
  .cover .sub {{ color:#7c3aed; font-size: 18px; text-transform: uppercase; letter-spacing: 3px; }}
  .cover .seal {{ font-size: 60px; margin-bottom: 18px; }}
  section {{ break-inside: avoid; margin-bottom: 26px; }}
  h2 {{ color:#5b21b6; border-bottom: 1px solid #ddd6fe; padding-bottom: 6px; font-size: 24px; }}
  pre {{ white-space: pre-wrap; font-family: Georgia, serif; font-size: 15px; background:#faf9ff; padding: 14px 16px; border-left: 3px solid #a78bfa; border-radius: 4px; }}
  footer {{ margin-top:40px; text-align:center; color:#9ca3af; font-size:12px; border-top:1px solid #eee; padding-top:16px; }}
</style></head><body>
<div class="cover"><div class="seal">📖</div><h1>{_html.escape(title)}</h1>
<div class="sub">World Atlas &middot; {_html.escape(str(mode))}</div></div>
{body_html}
<footer>Generated by Galaxy Studio &middot; Print → Save as PDF for a portable atlas.</footer>
</body></html>"""
    return HTMLResponse(page)


@router.post("/{pid}/publish")
async def publish_gated(pid: str):
    """🏪 95-GATED Marketplace publish (optional). Refuses to make the game discoverable
    unless the full audit clears 95. On pass: marks it visible + marketplace-published."""
    audit = await snowball_audit(pid, deep=True)
    if audit.get("error"):
        return audit
    if not audit["deliverable"]:
        return {"ok": False, "published": False, "blocked": True,
                "gate_floor": audit["gate_floor"], "threshold": DELIVER_THRESHOLD,
                "blockers": audit["blockers"],
                "message": f"Publish blocked — Marketplace requires a {DELIVER_THRESHOLD}+ quality gate. "
                           f"Current {audit['gate_floor']}. Resolve {audit['blocker_count']} blocker(s)."}
    await _db.playables.update_one(
        {"playable_id": pid},
        {"$set": {"moderation_status": "visible", "marketplace_published": True,
                  "published_at": _now(), "publish_score": audit["gate_floor"]}})
    return {"ok": True, "published": True, "gate_floor": audit["gate_floor"],
            "message": f"Published to Marketplace at quality {audit['gate_floor']}/100 ✨"}


@router.post("/{pid}/unpublish")
async def unpublish(pid: str):
    await _db.playables.update_one(
        {"playable_id": pid}, {"$set": {"marketplace_published": False}})
    return {"ok": True, "published": False}


@router.get("/{pid}/vault")
async def all_stage_vault(pid: str):
    """🧠 Vault tips for ALL stages at once (inline manual-pass reference). Big-win + feature 1."""
    from routes.snowball import _LADDER
    stages = [art_key for art_key in _STAGE_ART]  # stage keys
    return {"game_id": pid,
            "stages": {s: vault_for_stage(s) for s in _STAGE_ART.keys()}}


@router.get("/{pid}/auto-improve/plan.md")
async def upgrade_plan_md(pid: str):
    """📋 Latest upgrade plan as Markdown (shareable)."""
    from fastapi.responses import PlainTextResponse
    run = await _db.snowball_improve_runs.find_one({"game_id": pid}, sort=[("at", -1)])
    if not run:
        return PlainTextResponse("# No auto-improve run yet\n\nRun POST /auto-improve first.")
    lines = [f"# Upgrade Plan — gate {run.get('gate_floor')}/100", "",
             f"Weak stages: {', '.join(run.get('weak_stages') or []) or 'none'}", ""]
    for u in (run.get("upgrades") or []):
        lines += [f"## {u.get('signal','')} ({u.get('current','?')}/100)",
                  f"- **Do:** {u.get('upgrade','')}",
                  f"- **Why:** {u.get('impact','')}", ""]
    lines += ["---", "## Readable audit log", "```"] + (run.get("log") or []) + ["```"]
    return PlainTextResponse("\n".join(lines))


# ── 🔁 AUTO-LOOP: drive a game to the 95 gate, capped at N passes ──────────────
_AUTO_LOOP: dict = {}


async def _run_auto_loop(pid: str, loop_id: str, max_passes: int):
    import asyncio
    passes = []
    deliverable = False
    final_gate = 0
    for p in range(max_passes):
        audit = await snowball_audit(pid, deep=True)
        final_gate = audit.get("gate_floor", 0)
        passes.append({"pass": p + 1, "gate_floor": final_gate, "deliverable": audit.get("deliverable")})
        _AUTO_LOOP[loop_id] = {"status": "running", "pid": pid, "pass": p + 1,
                               "max_passes": max_passes, "passes": passes, "gate_floor": final_gate}
        if audit.get("deliverable"):
            deliverable = True
            break
        await auto_improve(pid)
        retry = await auto_improve_retry(pid)
        job_id = retry.get("job_id")
        if job_id:
            for _ in range(70):  # poll the regen ~ up to 210s
                j = await _db.groupchat_jobs.find_one({"job_id": job_id}, {"_id": 0, "job_status": 1})
                if j and j.get("job_status") == "done":
                    break
                await asyncio.sleep(3)
    fa = await snowball_audit(pid, deep=True)
    final_gate = fa.get("gate_floor", final_gate)
    deliverable = fa.get("deliverable", deliverable)
    _AUTO_LOOP[loop_id] = {"status": "done", "pid": pid, "passes": passes,
                           "gate_floor": final_gate, "deliverable": deliverable,
                           "message": (f"Reached ship-quality {final_gate}/100 ✨" if deliverable
                                       else f"Stopped at {final_gate}/100 after {len(passes)} pass(es).")}


@router.post("/{pid}/auto-improve/auto-loop")
async def start_auto_loop(pid: str, max_passes: int = Query(3, ge=1, le=6)):
    """🔁 One-tap drive-to-95: audit → improve → regen → re-audit, looped until the gate clears
    or max_passes is hit. Runs in the background; poll /auto-loop/{loop_id}."""
    import asyncio
    import uuid as _uuid
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1})
    if not g:
        return {"error": "game not found"}
    loop_id = _uuid.uuid4().hex
    _AUTO_LOOP[loop_id] = {"status": "running", "pid": pid, "pass": 0,
                           "max_passes": max_passes, "passes": [], "gate_floor": 0}
    asyncio.create_task(_run_auto_loop(pid, loop_id, max_passes))
    return {"loop_id": loop_id, "status": "running", "max_passes": max_passes}


@router.get("/auto-loop/{loop_id}")
async def auto_loop_status(loop_id: str):
    return _AUTO_LOOP.get(loop_id) or {"error": "loop not found"}
