"""
☃️ SNOWBALL BUILD — manual, stage-by-stage game construction.

The creator runs ONE pipeline stage at a time; each stage's artifact is accumulated
("snowballed") into the Central Knowledge Base, and a GROWING Game Design Document is
recompiled from everything built so far. Fully manual: run → review/refine → lock → next.

This module is read-only orchestration glue: the actual RUN / REFINE / LOCK actions reuse
the existing forge endpoints —
  run   : POST /api/pipeline/{pid}/forge/{stage}/async
  refine: POST /api/pipeline/{pid}/refine/{stage}/async
  lock  : POST /api/pipeline/{pid}/approve/{stage}
GET /api/snowball/{pid} returns the ordered ladder + the growing GDD + a "snowball size".
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from core.databases import client as _MONGO
from core.stage_vault import vault_for_stage, vault_brief

router = APIRouter(prefix="/api/snowball", tags=["snowball"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]

# ── Execution modes: Manual · Auto · Agentic/Jeeves ─────────────────────────
_EXEC_MODES = {
    "manual":  {"label": "Manual", "icon": "✋",
                "desc": "Run one stage at a time — run, review, refine, lock, next. You drive.",
                "driver": "you"},
    "auto":    {"label": "Auto", "icon": "⚡",
                "desc": "Build the whole ladder autonomously end-to-end, then audit at the 95 gate.",
                "driver": "pipeline",
                "entrypoint": "POST /api/groupchat/{pid}/run/async"},
    "agentic": {"label": "Agentic · Jeeves", "icon": "🤵",
                "desc": "Jeeves orchestrates the agent cast and narrates each stage in his cinematic voice.",
                "driver": "jeeves",
                "entrypoint": "POST /api/groupchat/{pid}/run/async"},
}
_DEFAULT_MODE = "manual"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

# ordered manual ladder — each rolls the snowball bigger (forge key, label, emoji, GDD section)
_LADDER = [
    ("questionnaire", "Questionnaire",  "📝", "questionnaire"),
    ("spec",       "Core Specs",        "📋", "core_specs"),
    ("world",      "WorldForge",        "🌍", "lore_graph"),
    ("narrative",  "Narrative & Quests", "📖", "quest_db"),
    ("mechanics",  "Mechanics",         "⚙️", "mechanics_config"),
    ("physics",    "Physics System",    "🧲", "physics_system"),
    ("procedural", "Procedural",        "🧬", "procedural_config"),
    ("tileset",    "Tile Set",          "🧱", "tileset"),
    ("assets",     "Asset Manifest",    "🎨", "asset_manifest"),
    ("qa",         "Playtest & QA",     "🧪", "qa_report"),
    ("build",      "Build & Package",   "📦", "build_manifest"),
    ("cinematics", "Cinematic Camera",  "🎥", "camera_director"),
    ("launch",     "Launch Prep",       "🚀", "launch_manifest"),
]


def _bullets(items, key=None, limit=8):
    # normalise: dicts → "k: v" rows, scalars → single row, lists → as-is
    if items is None:
        return ""
    if isinstance(items, dict):
        return "\n".join(f"- **{k}**: {v}" for k, v in list(items.items())[:limit])
    if isinstance(items, (str, int, float)):
        return f"- {items}"
    if not isinstance(items, (list, tuple)):
        return ""
    out = []
    for it in list(items)[:limit]:
        if key and isinstance(it, dict):
            v = it.get(key)
        elif isinstance(it, dict):
            v = it.get("name") or it.get("title") or it.get("item") or next(iter(it.values()), "")
        else:
            v = it
        if v:
            out.append(f"- {v}")
    return "\n".join(out)


def _compile_gdd(title: str, mode: str, arts: dict) -> str:
    """Recompile a growing GDD from whatever has been built so far. Sections only appear
    once their stage has run — so the document literally grows with the snowball."""
    L = [f"# 🎮 Game Design Document — {title or 'Untitled'}", ""]
    L.append(f"**Creation mode:** {mode or 'original'}")
    L.append("")

    quiz = arts.get("questionnaire")
    if quiz:
        L += ["## 0. Discovery Questionnaire", ""]
        if quiz.get("target_audience"):
            L.append(f"**Audience:** {quiz['target_audience']}")
        if quiz.get("core_fantasy"):
            L.append(f"**Core fantasy:** {quiz['core_fantasy']}")
        if quiz.get("must_haves"):
            L.append("**Must-haves:**\n" + _bullets(quiz["must_haves"]))
        if quiz.get("answers"):
            L.append("**Key answers:**\n" + _bullets(
                [f"{x.get('q')}: {x.get('answer')}" for x in quiz["answers"][:6]]))
        L.append("")

    spec = arts.get("core_specs")
    if spec:
        L += ["## 1. Concept & Core Specs", ""]
        if spec.get("logline"):
            L.append(f"_{spec['logline']}_\n")
        if spec.get("genre"):
            L.append(f"**Genre:** {spec['genre']}")
        if spec.get("pillars"):
            L.append("**Design pillars:**\n" + _bullets(spec["pillars"]))
        if spec.get("core_loop"):
            L.append("**Core loop:**\n" + _bullets(spec["core_loop"]))
        if spec.get("controls"):
            ctl = spec["controls"]
            if isinstance(ctl, dict):
                L.append("**Controls:**\n" + "\n".join(f"- `{k}` → {v}" for k, v in list(ctl.items())[:8]))
        if spec.get("win_condition"):
            L.append(f"**Win:** {spec['win_condition']}")
        if spec.get("lose_condition"):
            L.append(f"**Lose:** {spec['lose_condition']}")
        if spec.get("progression"):
            L.append(f"**Progression:** {spec['progression']}")
        L.append("")

    lore = arts.get("lore_graph")
    if lore:
        L += ["## 2. World & Lore", ""]
        if lore.get("setting"):
            L.append(f"{lore['setting']}\n")
        if lore.get("regions"):
            L.append("**Regions:**\n" + _bullets(lore["regions"]))
        if lore.get("factions"):
            L.append("**Factions:**\n" + _bullets(lore["factions"]))
        if lore.get("bestiary"):
            L.append("**Bestiary:**\n" + _bullets(lore["bestiary"]))
        L.append("")

    quest = arts.get("quest_db")
    if quest:
        L += ["## 3. Narrative & Quests", ""]
        if quest.get("character_bibles"):
            L.append("**Characters:**\n" + _bullets(quest["character_bibles"]))
        if quest.get("quests"):
            L.append("**Quests / beats:**\n" + _bullets(quest["quests"]))
        L.append("")

    mech = arts.get("mechanics_config")
    if mech:
        L += ["## 4. Mechanics & Systems", ""]
        if mech.get("core_mechanics"):
            L.append("**Core mechanics:**\n" + _bullets(mech["core_mechanics"]))
        if mech.get("systems"):
            L.append("**Systems:**\n" + _bullets(mech["systems"]))
        if mech.get("loops"):
            L.append("**Loops:**\n" + _bullets(mech["loops"]))
        L.append("")

    proc = arts.get("procedural_config")
    if proc:
        L += ["## 5. Procedural Generation", ""]
        if proc.get("requirements"):
            L.append("**Content requirements:**\n" + _bullets(proc["requirements"], key="item"))
        if proc.get("pcg_systems"):
            L.append("**PCG systems:**\n" + _bullets(proc["pcg_systems"], key="system"))
        if isinstance(proc.get("optimization"), dict):
            budget = proc["optimization"].get("budget")
            if budget:
                L.append(f"**Budget:** {budget}")
        L.append("")

    ts = arts.get("tileset")
    if ts:
        L += ["## 5.5 Tile Set", ""]
        tsz = ts.get("tile_size") or {}
        L.append(f"**Name:** {ts.get('name', 'tileset')} · **Tiles:** {len(ts.get('tiles') or [])} · "
                 f"**Palette:** {len(ts.get('palette') or [])} colors · "
                 f"**Tile size:** {tsz.get('w','?')}x{tsz.get('h','?')}")
        if ts.get("tiles"):
            L.append("**Tiles:**\n" + _bullets(
                [f"{t.get('id')} ({t.get('role')}{', solid' if t.get('solid') else ''})"
                 for t in ts["tiles"]]))
        L.append("")

    am = arts.get("asset_manifest")
    if am:
        L += ["## 6. Assets", ""]
        L.append(f"**Status:** {am.get('status', 'n/a')} · "
                 f"{am.get('asset_count', 0)} assets · "
                 f"kinds: {', '.join(am.get('generated_kinds', []) or ['none'])}")
        if am.get("missing_kinds"):
            L.append(f"**Missing:** {', '.join(am['missing_kinds'])}")
        L.append("")

    qa = arts.get("qa_report")
    if qa:
        L += ["## 7. Playtest & QA", ""]
        m = qa.get("metrics")
        if isinstance(m, dict):
            L.append("**Metrics:** " + ", ".join(f"{k}: {v}" for k, v in list(m.items())[:8]))
        for fld in ("issues", "bugs", "recommendations"):
            if qa.get(fld):
                L.append(f"**{fld.title()}:**\n" + _bullets(qa[fld]))
        L.append("")

    bm = arts.get("build_manifest")
    if bm:
        L += ["## 8. Build & Package", ""]
        L.append(f"**Version:** v{bm.get('version', 1)} · **Platform:** {bm.get('platform', 'web')} · "
                 f"**Checksum:** `{bm.get('checksum', '')}` · {len(bm.get('files', []))} files")
        L.append("")

    phys = arts.get("physics_system")
    if phys:
        L += ["## 4.5 Physics System", ""]
        w = phys.get("world") or {}
        g = w.get("gravity") or {}
        L.append(f"**Gravity:** ({g.get('x', 0)}, {g.get('y', '—')}, {g.get('z', 0)}) · "
                 f"**Bodies:** {len(phys.get('bodies') or [])} · "
                 f"**Materials:** {len(phys.get('materials') or [])} · "
                 f"**Forces:** {len(phys.get('forces') or [])}")
        if phys.get("tuning"):
            t = phys["tuning"]
            L.append(f"**Feel:** {t.get('feel', '—')} · gravity_scale {t.get('gravity_scale', '—')} · "
                     f"max_velocity {t.get('max_velocity', '—')}")
        L.append("")

    cam = arts.get("camera_director")
    if cam:
        L += ["## 8.5 Cinematic Camera Director", ""]
        rigs = cam.get("rigs") or []
        scenes = cam.get("scenes") or []
        shots = sum(len(s.get("shots") or []) for s in scenes)
        gl = cam.get("global") or {}
        L.append(f"**Rigs:** {len(rigs)} · **Scenes:** {len(scenes)} · **Shots:** {shots} · "
                 f"**Default rig:** {gl.get('default_rig', '—')} · FOV {gl.get('fov', '—')}")
        if rigs:
            L.append("**Camera rigs:**\n" + _bullets(
                [f"{r.get('id')} ({r.get('type')}, FOV {r.get('fov')})" for r in rigs]))
        if scenes:
            L.append("**Scene coverage:**\n" + _bullets(
                [f"{s.get('scene')}: {len(s.get('shots') or [])} shots" for s in scenes]))
        L.append("")

    lm = arts.get("launch_manifest")
    if lm:
        L += ["## 9. Launch Prep", ""]
        sl = lm.get("store_listing") or {}
        if sl.get("app_name"):
            L.append(f"**Store name:** {sl['app_name']}")
        if sl.get("short_description"):
            L.append(f"_{sl['short_description']}_")
        if sl.get("keywords"):
            L.append("**Keywords:** " + ", ".join(sl["keywords"][:8]))
        L.append(f"**Build ready:** {'yes' if lm.get('build_ready') else 'no'}")
        L.append("")

    return "\n".join(L).strip()


@router.get("/{pid}")
async def get_snowball(pid: str):
    """☃️ The manual Snowball ladder + the growing GDD for one game."""
    g = await _db.playables.find_one(
        {"playable_id": pid},
        {"_id": 0, "title": 1, "genre": 1, "derive_mode": 1, "html": 1})
    if not g:
        return {"error": "game not found"}
    kb = await _db.game_kb.find_one(
        {"game_id": pid}, {"_id": 0, "artifacts": 1, "approvals": 1, "stale": 1, "provenance": 1})
    arts = (kb or {}).get("artifacts") or {}
    approvals = (kb or {}).get("approvals") or {}
    stale = (kb or {}).get("stale") or {}
    provenance = (kb or {}).get("provenance") or {}
    _stt = await _db.snowball_state.find_one({"pid": pid}, {"_id": 0, "skipped": 1})
    skipped_set = set((_stt or {}).get("skipped") or [])
    mode = g.get("derive_mode") or g.get("genre") or "original"

    steps = []
    # step 0 — Mode (set at creation; informational, not forgeable)
    steps.append({"key": "mode", "label": "Mode", "icon": "🎬", "forge": None,
                  "done": True, "locked": True, "summary": str(mode), "is_next": False})

    next_assigned = False
    for fkey, label, icon, art in _LADDER:
        done = art in arts
        is_skipped = fkey in skipped_set
        locked = bool(approvals.get(fkey, {}).get("approved"))
        # next runnable = first stage that is neither built nor skipped
        is_next = (not done) and (not is_skipped) and (not next_assigned)
        if is_next:
            next_assigned = True
        a = arts.get(art) or {}
        summary = ""
        if done:
            if fkey == "questionnaire":
                summary = f"{len(a.get('questions', []))} Qs · {a.get('target_audience', '')[:40]}"
            elif fkey == "tileset":
                summary = f"{len(a.get('tiles', []))} tiles · {len(a.get('palette', []))} colors"
            elif fkey == "spec":
                summary = a.get("logline", "core_specs.json")[:80]
            elif fkey == "world":
                summary = f"{len(a.get('regions', []))} regions · {len(a.get('factions', []))} factions"
            elif fkey == "narrative":
                summary = f"{len(a.get('quests', []))} quests · {len(a.get('character_bibles', []))} chars"
            elif fkey == "mechanics":
                summary = f"{len(a.get('core_mechanics', []))} mechanics"
            elif fkey == "physics":
                summary = (f"{len(a.get('bodies', []))} bodies · {len(a.get('materials', []))} materials")
            elif fkey == "procedural":
                summary = f"{len(a.get('requirements', []))} reqs · {len(a.get('pcg_systems', []))} PCG"
            elif fkey == "assets":
                summary = f"{a.get('asset_count', 0)} assets · {a.get('status', '')}"
            elif fkey == "qa":
                summary = "qa_report.json"
            elif fkey == "build":
                summary = f"v{a.get('version', 1)} · {a.get('checksum', '')}"
            elif fkey == "cinematics":
                summary = (f"{len(a.get('rigs', []))} rigs · {len(a.get('scenes', []))} scenes")
            elif fkey == "launch":
                summary = (a.get("store_listing") or {}).get("app_name", "store-ready")
        steps.append({
            "key": fkey, "label": label, "icon": icon, "forge": fkey,
            "done": done, "locked": locked, "is_next": is_next,
            "skipped": is_skipped, "skippable": True,
            "skip": f"/api/snowball/{pid}/skip/{fkey}",
            "stale": art in stale, "provenance": provenance.get(art),
            "quality": (a or {}).get("_quality"),
            "summary": ("skipped" if is_skipped else (summary or "not built yet")),
        })

    gdd = _compile_gdd(g.get("title", ""), mode, arts)
    built = sum(1 for s in steps if s["done"]) - 1   # minus the always-on mode step
    locked_count = sum(1 for s in steps if s["locked"]) - 1
    next_step = next((s for s in steps if s.get("is_next")), None)

    return {
        "game_id": pid, "title": g.get("title", ""), "mode": mode,
        "steps": steps,
        "built": built, "locked": locked_count, "total": len(_LADDER),
        "percent": round(built / len(_LADDER) * 100),
        "next": next_step["key"] if next_step else None,
        "next_label": next_step["label"] if next_step else "Snowball complete!",
        "stale": stale, "stale_count": len(stale), "provenance": provenance,
        "gdd": gdd, "gdd_chars": len(gdd),
        "size_label": f"{built}/{len(_LADDER)} stages · {len(gdd)} chars of GDD",
    }


# ════════════════════════════════════════════════════════════════════════════
#  MOUNT · FLOW · MODE — wire the snowball into one solid, organized flow
# ════════════════════════════════════════════════════════════════════════════
def _gdd_vault_appendix() -> str:
    """A knowledge-vault appendix mounted onto the GDD: per-stage domain grounding."""
    L = ["", "---", "", "## 📚 Knowledge Vault Grounding", "",
         "_Every stage below is mounted to the knowledge vault — the agents draw on these domains._", ""]
    for fkey, label, icon, _art in _LADDER:
        v = vault_for_stage(fkey)
        doms = ", ".join(d["name"] for d in v["domains"]) or "general"
        L.append(f"### {icon} {label}")
        L.append(f"**Vault domains:** {doms}")
        if v["tips"]:
            L.append("**Key tips:**\n" + "\n".join(f"- {t}" for t in v["tips"][:3]))
        L.append("")
    return "\n".join(L)


def _gdd_with_vault(title: str, mode: str, arts: dict, build_id: str = "") -> str:
    base = _compile_gdd(title, mode, arts) + "\n" + _gdd_vault_appendix()
    if build_id:
        try:
            from core import systems_forge as _sf
            base += "\n" + (_sf.build_systems_markdown(build_id) or "")
        except Exception:
            pass
    return base


async def _get_state(pid: str) -> dict:
    st = await _db.snowball_state.find_one({"pid": pid}, {"_id": 0})
    return st or {}


@router.post("/{pid}/mount")
async def mount_snowball(pid: str, exec_mode: str = "manual"):
    """🔌 Mount a game into the Snowball system: generate the vault-grounded GDD on mount,
    set the execution mode (manual/auto/agentic), and persist the flow state."""
    if exec_mode not in _EXEC_MODES:
        exec_mode = _DEFAULT_MODE
    g = await _db.playables.find_one({"playable_id": pid},
                                     {"_id": 0, "title": 1, "genre": 1, "derive_mode": 1})
    if not g:
        return {"error": "game not found"}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    arts = (kb or {}).get("artifacts") or {}
    mode = g.get("derive_mode") or g.get("genre") or "original"
    gdd = _gdd_with_vault(g.get("title", ""), mode, arts, build_id=pid)
    # vault coverage across the ladder
    connected = sum(1 for fkey, *_ in _LADDER if vault_for_stage(fkey)["domain_count"] > 0)
    state = {
        "pid": pid, "exec_mode": exec_mode,
        "gdd": gdd, "gdd_chars": len(gdd),
        "vault_connected_stages": connected, "vault_total_stages": len(_LADDER),
        "vault_coverage_pct": round(100 * connected / len(_LADDER)),
        "mounted_at": _now(),
    }
    await _db.snowball_state.update_one({"pid": pid}, {"$set": state}, upsert=True)
    return {
        "ok": True, "pid": pid, "title": g.get("title", ""),
        "exec_mode": exec_mode, "mode_meta": _EXEC_MODES[exec_mode],
        "gdd_chars": len(gdd), "gdd_generated_on_mount": True,
        "vault_coverage_pct": state["vault_coverage_pct"],
        "vault_connected_stages": connected, "vault_total_stages": len(_LADDER),
        "mounted_at": state["mounted_at"],
    }


@router.post("/{pid}/mode")
async def set_mode(pid: str, exec_mode: str = "manual"):
    """Switch the snowball execution mode: manual · auto · agentic/jeeves."""
    if exec_mode not in _EXEC_MODES:
        return {"error": f"invalid mode; choose one of {list(_EXEC_MODES)}"}
    await _db.snowball_state.update_one(
        {"pid": pid}, {"$set": {"exec_mode": exec_mode, "mode_set_at": _now()}}, upsert=True)
    return {"ok": True, "pid": pid, "exec_mode": exec_mode, "mode_meta": _EXEC_MODES[exec_mode]}


@router.get("/{pid}/flow")
async def snowball_flow(pid: str):
    """🌊 The solid, organized flow: every ladder stage with its status, vault grounding,
    and the action available in the current execution mode (manual/auto/agentic)."""
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1})
    if not g:
        return {"error": "game not found"}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1, "approvals": 1})
    arts = (kb or {}).get("artifacts") or {}
    approvals = (kb or {}).get("approvals") or {}
    st = await _get_state(pid)
    exec_mode = st.get("exec_mode", _DEFAULT_MODE)
    skipped_set = set(st.get("skipped") or [])

    next_assigned = False
    stages = []
    for fkey, label, icon, art in _LADDER:
        done = art in arts
        is_skipped = fkey in skipped_set
        locked = bool(approvals.get(fkey, {}).get("approved"))
        is_next = (not done) and (not is_skipped) and (not next_assigned)
        if is_next:
            next_assigned = True
        v = vault_for_stage(fkey)
        # action depends on the mounted execution mode
        if exec_mode == "manual":
            action = {"type": "stage",
                      "run": f"/api/pipeline/{pid}/forge/{fkey}/async",
                      "refine": f"/api/pipeline/{pid}/refine/{fkey}/async",
                      "lock": f"/api/pipeline/{pid}/approve/{fkey}"}
        elif exec_mode == "auto":
            action = {"type": "auto", "run_all": f"/api/groupchat/{pid}/run/async"}
        else:  # agentic / jeeves
            action = {"type": "agentic", "run_all": f"/api/groupchat/{pid}/run/async",
                      "voice": f"/api/jeeves-voice/voice/speak",
                      "tone": fkey}
        status = ("locked" if locked else ("done" if done else
                  ("skipped" if is_skipped else ("next" if is_next else "pending"))))
        stages.append({
            "key": fkey, "label": label, "icon": icon, "status": status,
            "done": done, "locked": locked, "is_next": is_next,
            "skipped": is_skipped, "skippable": True,
            "skip": f"/api/snowball/{pid}/skip/{fkey}",
            "vault": {"connected": v["domain_count"] > 0,
                      "domains": [d["name"] for d in v["domains"]],
                      "tips": v["tips"][:3]},
            "action": action,
        })
    built = sum(1 for s in stages if s["done"])
    return {
        "pid": pid, "title": g.get("title", ""),
        "exec_mode": exec_mode, "mode_meta": _EXEC_MODES[exec_mode],
        "mounted": bool(st.get("mounted_at")), "mounted_at": st.get("mounted_at"),
        "built": built, "total": len(_LADDER),
        "percent": round(100 * built / len(_LADDER)),
        "vault_coverage_pct": st.get("vault_coverage_pct", 100),
        "next": next((s["key"] for s in stages if s["is_next"]), None),
        "stages": stages,
    }


@router.post("/{pid}/lock-all")
async def lock_all(pid: str):
    """🔒 Lock every built-but-unlocked stage in one tap (Iterate & Refine approvals)."""
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1, "approvals": 1})
    arts = (kb or {}).get("artifacts") or {}
    approvals = (kb or {}).get("approvals") or {}
    now = _now()
    sets, locked = {}, []
    for fkey, _label, _icon, art in _LADDER:
        if art in arts and not approvals.get(fkey, {}).get("approved"):
            sets[f"approvals.{fkey}"] = {"approved": True, "at": now, "note": "lock-all"}
            locked.append(fkey)
    if sets:
        sets["game_id"] = pid
        await _db.game_kb.update_one({"game_id": pid}, {"$set": sets}, upsert=True)
    return {"ok": True, "locked": locked, "count": len(locked)}



_LADDER_KEYS = {k for k, *_ in _LADDER}
_LADDER_ART = {k: a for k, _l, _i, a in _LADDER}


@router.get("/{pid}/options/{stage}")
async def stage_options(pid: str, stage: str):
    """🧭 Advanced options — the exhaustive ALTERNATIVES the forge generated for this
    stage (area -> choices with pros/cons/recommended). Powers the per-stage Advanced panel;
    a creator can adopt a non-default choice and re-forge via /refine."""
    art = _LADDER_ART.get(stage)
    if not art:
        return {"stage": stage, "options": [], "error": "unknown stage"}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, f"artifacts.{art}": 1})
    obj = ((kb or {}).get("artifacts") or {}).get(art) or {}
    return {"stage": stage, "artifact": art,
            "present": bool(obj), "options": obj.get("options") or []}


@router.post("/{pid}/skip/{stage}")
async def skip_stage(pid: str, stage: str, undo: bool = False):
    """⏭️ Skip (or un-skip) a snowball stage. Skipped stages are passed over by the
    'next' pointer and don't block progress; the rest of the ladder still builds."""
    if stage not in _LADDER_KEYS:
        return {"error": f"unknown stage '{stage}'", "stages": sorted(_LADDER_KEYS)}
    op = {"$pull": {"skipped": stage}} if undo else {"$addToSet": {"skipped": stage}}
    op.setdefault("$set", {})["skip_updated_at"] = _now()
    await _db.snowball_state.update_one({"pid": pid}, op, upsert=True)
    st = await _db.snowball_state.find_one({"pid": pid}, {"_id": 0, "skipped": 1})
    return {"ok": True, "pid": pid, "stage": stage,
            "skipped": not undo, "all_skipped": (st or {}).get("skipped") or []}


@router.get("/{pid}/gdd.md")
async def export_gdd(pid: str):
    """⬇️ Download the growing GDD as a Markdown file."""
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "derive_mode": 1})
    if not g:
        return PlainTextResponse("game not found", status_code=404)
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    arts = (kb or {}).get("artifacts") or {}
    mode = g.get("derive_mode") or g.get("genre") or "original"
    md = _compile_gdd(g.get("title", ""), mode, arts)
    try:
        from core import systems_forge as _sf
        md += "\n" + (_sf.build_systems_markdown(pid) or "")
    except Exception:
        pass
    fname = (g.get("title", "game") or "game").replace(" ", "_")[:40] + "_GDD.md"
    return PlainTextResponse(md, media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})



# ── /phases cache: the heavy escalate+forge+pg.build deterministic structure is
#    cached per (pid, era, seed); the LIVE band overlay (locked/forged state) is
#    re-applied fresh on every call so Roll/Lock fills the meter without recompute.
_PHASES_CACHE: dict[tuple, tuple[float, dict]] = {}
_PHASES_TTL = 90.0  # seconds


def _phases_compute(pid: str, use_genre: str, seed: int, era: str) -> dict:
    from core import snowball_forge as sf
    from core import phase_gates as pg
    from core import construct_forge as cf
    from core import eras as eras_mod
    import copy
    key = (pid, era, seed, use_genre)
    hit = _PHASES_CACHE.get(key)
    if hit and (time.time() - hit[0]) < _PHASES_TTL:
        return copy.deepcopy(hit[1])
    m = sf.escalate(build_id=pid, genre=use_genre, seed=seed, era=era,
                    persist=False)
    combined = cf.build_assets(pid)
    fams = sorted({(a.get("family") or a.get("kind"))
                   for a in combined if (a.get("family") or a.get("kind"))})
    out = pg.build(m, assets={"forged": len(combined), "families": fams})
    out["era"] = m.get("era", era)
    out["eras"] = eras_mod.catalog()
    if len(_PHASES_CACHE) > 256:  # simple bound — drop the oldest entries
        for k in sorted(_PHASES_CACHE, key=lambda kk: _PHASES_CACHE[kk][0])[:128]:
            _PHASES_CACHE.pop(k, None)
    _PHASES_CACHE[key] = (time.time(), copy.deepcopy(out))
    return out


@router.get("/{pid}/phases")
async def snowball_phases(pid: str, era: str = "modern", genre: str = "",
                          seed: int = 1):
    """🧮 The 100-phase advanced ladder, crosswired to THIS snowball game.

    Landing view for the snowball: maps the build onto the 8-band / 100-phase
    checkpoint ladder and reports the era-scaled INDUSTRY-STANDARD file output
    the build targets (file_plan). The heavy compute is cached per (pid, era,
    seed); the live Roll/Lock/forge state is overlaid fresh so bands turn green
    and the file meter fills as the build progresses."""
    import time as _t  # noqa
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "derive_mode": 1})
    if not g:
        return {"error": "game not found"}
    use_genre = (genre or g.get("genre") or "rpg")
    try:
        out = _phases_compute(pid, use_genre, seed, era)
        # ── LIVE overlay: turn each band green based on real locked/forged state
        from core import build_journey as bj
        band_done = await bj.band_overlay(pid)
        target = int((out.get("file_plan") or {}).get("file_target", 0))
        produced = 0
        for b in out.get("bands", []):
            live = bool(band_done.get(b["band"], b.get("passed")))
            b["passed"] = live
            b["files_produced"] = b.get("file_target", 0) if live else 0
            produced += b["files_produced"]
            for ph in out.get("phases", []):
                if ph.get("band") == b["band"]:
                    ph["passed"] = live
        fp = out.get("file_plan") or {}
        fp["files_produced"] = produced
        fp["produced_pct"] = round(100 * produced / max(1, target))
        out["file_plan"] = fp
        out["bands_passed"] = sum(1 for b in out.get("bands", []) if b["passed"])
        out["phases_passed"] = sum(1 for p in out.get("phases", []) if p["passed"])
        out["pass_pct"] = round(100 * out["phases_passed"] / max(1, len(out.get("phases", []))))
        out["all_gates_green"] = all(b["passed"] for b in out.get("bands", []))
        out["build_id"] = pid
        out["title"] = g.get("title", "")
        out["genre"] = use_genre
        return out
    except Exception as e:  # never break the snowball landing
        return {"error": "phase_build_failed", "detail": str(e)[:200]}

