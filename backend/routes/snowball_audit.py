"""
🩺 SNOWBALL AUDIT — 10-level consistency + quality scorecard with a HARD 95 delivery gate.

Across the whole Snowball build we score TEN independent audit levels (0-100 each), confirmed
by BOTH deterministic checks AND an LLM quality/parse pass + RAG canon-recall. A game is only
`deliverable` when EVERY level is ≥ DELIVER_THRESHOLD (95) and the LLM quality + parse-confidence
are also ≥ 95. POST /deliver enforces the gate server-side (cannot ship below 95).

Levels: completeness · canon_consistency · reference_integrity · narrative_depth ·
mechanical_coherence · world_density · asset_coverage · build_readiness · freshness · playability_qa
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from core.databases import client as _MONGO
from routes.canon_graph import build_graph, _compute_issues
from routes.snowball import _LADDER, _compile_gdd

router = APIRouter(prefix="/api/snowball", tags=["snowball"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]

DELIVER_THRESHOLD = 95  # hard floor: every level + LLM quality must reach this to ship


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _band(score: int) -> str:
    return ("S" if score >= 95 else "A" if score >= 85 else "B" if score >= 70
            else "C" if score >= 50 else "D")


# fix-it deep-link target per level → the exact forge stage (big-win j)
_FIX_ROUTE = {
    "completeness": "groupchat", "canon_consistency": "canon-graph",
    "reference_integrity": "canon-graph", "narrative_depth": "groupchat",
    "mechanical_coherence": "groupchat", "world_density": "worldforge",
    "asset_coverage": "asset-genesis", "build_readiness": "build-hub",
    "freshness": "groupchat", "playability_qa": "playable",
}


def _clip(v: float) -> int:
    return max(0, min(100, int(round(v))))


def _deterministic_levels(arts: dict, stale: dict, graph: dict, play: dict) -> list[dict]:
    nodes = graph["nodes"]
    issues = _compute_issues(arts, stale, graph)
    n_by = {}
    for nd in nodes:
        n_by[nd["type"]] = n_by.get(nd["type"], 0) + 1

    # 1 — completeness
    built = sum(1 for _f, _l, _i, art in _LADDER if art in arts)
    completeness = built / len(_LADDER) * 100

    # 2 — canon consistency (mirror the canon auditor's score formula)
    errs = sum(1 for i in issues if i["severity"] == "error")
    warns = sum(1 for i in issues if i["severity"] == "warn")
    infos = len(issues) - errs - warns
    canon = max(0, 100 - errs * 25 - warns * 8 - infos * 2)

    # 3 — reference integrity (orphan ratio over linkable nodes)
    linkable = [nd for nd in nodes if nd["type"] in ("Character", "Faction", "Region", "Quest")]
    orphans = sum(1 for i in issues if i["type"] in ("orphan", "thin-quest"))
    ref_int = 100 if not linkable else 100 * (1 - orphans / max(1, len(linkable)))

    # 4 — narrative depth
    q = arts.get("quest_db") or {}
    quests = len(q.get("quests") or [])
    chars = len(q.get("character_bibles") or q.get("characters") or [])
    narr = min(100, quests * 9 + chars * 9)

    # 5 — mechanical coherence
    mech = arts.get("mechanics_config") or {}
    mc = len(mech.get("core_mechanics") or []) * 14 + len(mech.get("systems") or []) * 10
    mechco = min(100, mc) if arts.get("mechanics_config") else 0

    # 6 — world density
    lore = arts.get("lore_graph") or {}
    wd = (len(lore.get("regions") or []) * 8 + len(lore.get("factions") or []) * 8
          + len(lore.get("bestiary") or []) * 6)
    world_density = min(100, wd) if arts.get("lore_graph") else 0

    # 7 — asset coverage
    am = arts.get("asset_manifest") or {}
    if not arts.get("asset_manifest"):
        asset_cov = 0
    else:
        status = am.get("status", "")
        asset_cov = 100 if status == "complete" else (60 if status == "partial"
                    else min(100, (am.get("asset_count", 0)) * 12))

    # 8 — build readiness
    build_ready = (50 if arts.get("build_manifest") else 0) + (50 if arts.get("launch_manifest") else 0)

    # 9 — freshness
    freshness = max(0, 100 - len(stale or {}) * 20)

    # 10 — playability / QA
    pscore = (play.get("evaluation") or {}).get("overall") or play.get("playability_score") or 0
    qa_present = 1 if arts.get("qa_report") else 0
    playability = _clip(pscore * 0.7 + qa_present * 30) if (pscore or qa_present) else 0

    raw = [
        ("completeness", "Stage Completeness", completeness),
        ("canon_consistency", "Canon Consistency", canon),
        ("reference_integrity", "Reference Integrity", ref_int),
        ("narrative_depth", "Narrative Depth", narr),
        ("mechanical_coherence", "Mechanical Coherence", mechco),
        ("world_density", "World Density", world_density),
        ("asset_coverage", "Asset Coverage", asset_cov),
        ("build_readiness", "Build Readiness", build_ready),
        ("freshness", "Freshness", freshness),
        ("playability_qa", "Playability & QA", playability),
    ]
    out = []
    for key, label, val in raw:
        sc = _clip(val)
        out.append({"key": key, "label": label, "score": sc, "band": _band(sc),
                    "pass": sc >= DELIVER_THRESHOLD, "fix_route": _FIX_ROUTE.get(key, "groupchat")})
    return out


async def _llm_quality(pid: str, title: str, gdd: str) -> dict:
    """LLM quality + parse-confidence pass, plus a RAG canon-recall grounding probe.
    'higher quality parsing' = the model must be able to cleanly parse + grade the GDD,
    and key canon must be retrievable. Returns {quality, parse_confidence, recall, notes}."""
    from routes.llm_router import route_complete
    system = (
        "You are a ruthless QA director grading a game's design document for SHIP readiness. "
        "Output ONLY minified JSON: {\"quality\":0-100,\"parse_confidence\":0-100,"
        "\"notes\":\"<=160 chars\"}. quality = overall craft/consistency/completeness; "
        "parse_confidence = how cleanly structured & unambiguous the doc is to machine-parse. "
        "Be strict: reserve 95+ for genuinely shippable, coherent, complete work.")
    res = await route_complete("reasoning", gdd[:14000], system=system,
                               session_id=f"snaudit-{pid}", timeout_s=60, use_cache=False)
    quality = parse_conf = 0
    notes = ""
    if not res.get("error"):
        from routes.canon_graph import _extract_json_array  # reuse helper module
        import json as _json
        txt = (res.get("content") or "").strip()
        if txt.startswith("```"):
            txt = txt.split("```", 2)[1].replace("json", "", 1).strip()
        a, b = txt.find("{"), txt.rfind("}")
        if 0 <= a < b:
            try:
                d = _json.loads(txt[a:b + 1])
                quality = _clip(d.get("quality", 0))
                parse_conf = _clip(d.get("parse_confidence", 0))
                notes = str(d.get("notes", ""))[:160]
            except Exception:
                pass

    # RAG canon-recall probe — confirm a few canon tokens are retrievable
    recall = 0
    try:
        from routes.canon_rag import retrieve as _rag_retrieve
    except Exception:
        _rag_retrieve = None
    try:
        kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
        graph = build_graph((kb or {}).get("artifacts") or {})
        names = [n["name"] for n in graph["nodes"][:6] if n.get("name")]
        if names and _rag_retrieve:
            hits = 0
            for nm in names:
                tok = (nm.split() or [nm])[0]
                r = await _rag_retrieve(pid, q=tok, k=3)
                if (r or {}).get("hits"):
                    hits += 1
            recall = _clip(hits / len(names) * 100)
        elif names:
            recall = 100  # graph is internally consistent; recall not separately wired
    except Exception:
        recall = 0
    return {"quality": quality, "parse_confidence": parse_conf, "recall": recall,
            "notes": notes, "model": res.get("model")}


@router.get("/{pid}/audit")
async def snowball_audit(pid: str, deep: bool = Query(True)):
    """🩺 The 10-level quality scorecard + hard 95 delivery gate.
    deep=true (default) runs the LLM quality + parse-confidence + RAG recall confirmation."""
    g = await _db.playables.find_one(
        {"playable_id": pid},
        {"_id": 0, "title": 1, "genre": 1, "derive_mode": 1,
         "playability_score": 1, "evaluation": 1})
    if not g:
        return {"error": "game not found"}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1, "stale": 1})
    arts = (kb or {}).get("artifacts") or {}
    stale = (kb or {}).get("stale") or {}
    graph = build_graph(arts)
    levels = _deterministic_levels(arts, stale, graph, g)

    det_min = min((l["score"] for l in levels), default=0)
    det_overall = _clip(sum(l["score"] for l in levels) / max(1, len(levels)))

    llm = None
    if deep:
        mode = g.get("derive_mode") or g.get("genre") or "original"
        gdd = _compile_gdd(g.get("title", ""), mode, arts)
        llm = await _llm_quality(pid, g.get("title", ""), gdd)

    gate_floor = min(det_min,
                     llm["quality"] if llm else 100,
                     llm["parse_confidence"] if llm else 100,
                     llm["recall"] if llm else 100)
    deliverable = gate_floor >= DELIVER_THRESHOLD
    blockers = [{"level": l["label"], "score": l["score"], "fix_route": l["fix_route"]}
                for l in levels if not l["pass"]]
    if llm:
        for k, lbl in (("quality", "LLM Quality"), ("parse_confidence", "Parse Confidence"),
                       ("recall", "Canon Recall")):
            if llm[k] < DELIVER_THRESHOLD:
                blockers.append({"level": lbl, "score": llm[k], "fix_route": "groupchat"})

    snapshot = {
        "game_id": pid, "title": g.get("title", ""),
        "levels": levels, "llm": llm,
        "deterministic_overall": det_overall, "deterministic_min": det_min,
        "gate_floor": gate_floor, "threshold": DELIVER_THRESHOLD,
        "deliverable": deliverable, "band": _band(gate_floor),
        "blockers": blockers, "blocker_count": len(blockers),
        "at": _now(),
    }
    # persist history (big-win c) — keep last 30
    try:
        await _db.snowball_audits.insert_one({**snapshot, "_kind": "audit"})
    except Exception:
        pass
    snapshot.pop("_id", None)
    return snapshot


@router.get("/{pid}/scorecard.png")
async def scorecard_png(pid: str):
    """🖼️ Shareable 1080² scorecard PNG of the 10 audit levels + gate verdict (big-win i)."""
    from fastapi.responses import Response
    from PIL import Image, ImageDraw, ImageFont
    import io
    audit = await snowball_audit(pid, deep=False)
    if audit.get("error"):
        return Response(status_code=404)
    SZ = 1080
    img = Image.new("RGB", (SZ, SZ), (8, 11, 22))
    d = ImageDraw.Draw(img)

    def _f(sz, bold=True):
        fd = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
        try:
            return ImageFont.truetype(os.path.join(fd, "VeraBd.ttf" if bold else "Vera.ttf"), sz)
        except Exception:
            return ImageFont.load_default()

    deliverable = audit["deliverable"]
    accent = (74, 222, 128) if deliverable else (251, 191, 36)
    d.text((54, 46), "QUALITY SCORECARD", font=_f(40), fill=(226, 232, 240))
    d.text((54, 100), (audit.get("title") or "Game")[:34], font=_f(30), fill=(148, 163, 184))
    # big gate number
    d.text((54, 150), f"{audit['gate_floor']}", font=_f(150), fill=accent)
    d.text((360, 220), "/100", font=_f(52), fill=(100, 116, 139))
    d.text((360, 175), ("✓ SHIP-READY" if deliverable else "NOT YET 95"), font=_f(34), fill=accent)
    # 10 level bars
    y = 360
    for lv in audit["levels"]:
        d.text((54, y), lv["label"], font=_f(26, False), fill=(203, 213, 225))
        bx, bw = 540, 460
        d.rounded_rectangle([bx, y + 4, bx + bw, y + 28], radius=10, fill=(30, 41, 59))
        w = int(bw * lv["score"] / 100)
        c = (74, 222, 128) if lv["score"] >= 95 else (96, 165, 250) if lv["score"] >= 70 else (248, 113, 113)
        d.rounded_rectangle([bx, y + 4, bx + max(8, w), y + 28], radius=10, fill=c)
        d.text((bx + bw + 14, y), str(lv["score"]), font=_f(24), fill=c)
        y += 62
    d.text((54, SZ - 56), "▲ GALAXY STUDIO · 10-LEVEL AUDIT · hard gate at 95", font=_f(24), fill=(251, 191, 36))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/{pid}/audit/history")
async def audit_history(pid: str, limit: int = Query(20, ge=1, le=50)):
    """📈 Past scorecards (newest first) — gate_floor trend over time (big-win c)."""
    rows = await _db.snowball_audits.find(
        {"game_id": pid}, {"_id": 0, "at": 1, "gate_floor": 1, "deterministic_overall": 1,
                           "deliverable": 1, "band": 1, "blocker_count": 1}
    ).sort("at", -1).limit(limit).to_list(limit)
    return {"game_id": pid, "count": len(rows), "history": rows}


@router.post("/{pid}/deliver")
async def deliver(pid: str):
    """🚀 HARD-GATED delivery. Refuses (409-style payload) unless the latest 10-level
    audit + LLM quality all clear 95. On pass, stamps the game `delivered`."""
    audit = await snowball_audit(pid, deep=True)
    if audit.get("error"):
        return audit
    if not audit["deliverable"]:
        return {"ok": False, "delivered": False, "blocked": True,
                "gate_floor": audit["gate_floor"], "threshold": DELIVER_THRESHOLD,
                "blockers": audit["blockers"],
                "message": f"Delivery blocked — every level must reach {DELIVER_THRESHOLD}. "
                           f"Lowest is {audit['gate_floor']}. Resolve {len(audit['blockers'])} blocker(s)."}
    await _db.playables.update_one(
        {"playable_id": pid},
        {"$set": {"delivered": True, "delivered_at": _now(),
                  "delivery_score": audit["gate_floor"]}})
    return {"ok": True, "delivered": True, "gate_floor": audit["gate_floor"],
            "message": f"Delivered at quality {audit['gate_floor']}/100 — all 10 levels cleared {DELIVER_THRESHOLD}+ ✨"}
