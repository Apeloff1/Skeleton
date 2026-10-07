"""
🕸️ CANON GRAPH — a queryable knowledge graph of the game's canon.

Builds typed NODES (Faction, Region, Creature, Character, Quest, Mechanic) and RELATIONSHIPS
between them from the Central KB (lore_graph + quest_db + mechanics_config). Edges are inferred
by name co-occurrence (e.g. a Quest that mentions a Character → involves; a Character bible that
mentions a Faction → member_of). This is the schematic's graph-DB layer over the KB.
"""
from __future__ import annotations

import json
import os
import re

from fastapi import APIRouter
from pydantic import BaseModel

from core.databases import client as _MONGO
from routes.canon_rag import _entity_name, _entity_text

router = APIRouter(prefix="/api/graph", tags=["graph"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]


def _extract_json_array(text: str) -> list:
    """Best-effort extraction of a JSON array from an LLM response."""
    if not text:
        return []
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if "```" in s[3:] else s
        s = s.replace("json", "", 1).strip() if s[:4].lower() == "json" else s
    a, b = s.find("["), s.rfind("]")
    if a == -1 or b == -1:
        return []
    try:
        obj = json.loads(s[a:b + 1])
        return obj if isinstance(obj, list) else []
    except Exception:
        return []


def _slug(t: str, n: str) -> str:
    return t + ":" + re.sub(r"[^a-z0-9]+", "-", (n or "").lower()).strip("-")[:40]


def _mentions(haystack: str, name: str) -> bool:
    if not name or len(name) < 3:
        return False
    return re.search(r"\b" + re.escape(name.lower()) + r"\b", (haystack or "").lower()) is not None


def build_graph(arts: dict) -> dict:
    nodes, edges, by_type = [], [], {}
    seen = set()

    def add(typ, ent):
        name = _entity_name(ent, typ)
        nid = _slug(typ, name)
        if nid in seen:
            return nid
        seen.add(nid)
        nodes.append({"id": nid, "type": typ, "name": name, "text": _entity_text(ent)[:160]})
        by_type[typ] = by_type.get(typ, 0) + 1
        return nid

    lore = arts.get("lore_graph") or {}
    factions = [(add("Faction", e), e) for e in (lore.get("factions") or [])[:20]]
    regions = [(add("Region", e), e) for e in (lore.get("regions") or [])[:20]]
    for e in (lore.get("bestiary") or [])[:20]:
        add("Creature", e)
    quest = arts.get("quest_db") or {}
    characters = [(add("Character", e), e) for e in
                  (quest.get("character_bibles") or quest.get("characters") or [])[:20]]
    quests = [(add("Quest", e), e) for e in (quest.get("quests") or [])[:30]]
    mech = arts.get("mechanics_config") or {}
    for e in (mech.get("core_mechanics") or [])[:20]:
        add("Mechanic", e)

    def edge(s, t, rel):
        if s and t and s != t:
            edges.append({"source": s, "target": t, "rel": rel})

    name_of = {nid: n for nid, n in [(nid, nm["name"]) for nid, nm in
               [(nd["id"], nd) for nd in nodes]]}

    # Character → member_of → Faction ; Character → from → Region
    for cid, c in characters:
        ctext = _entity_text(c)
        for fid, f in factions:
            if _mentions(ctext, name_of.get(fid, "")):
                edge(cid, fid, "member_of")
        for rid, r in regions:
            if _mentions(ctext, name_of.get(rid, "")):
                edge(cid, rid, "from")
    # Quest → involves → Character ; Quest → set_in → Region ; Quest → concerns → Faction
    for qid, q in quests:
        qtext = _entity_text(q)
        for cid, c in characters:
            if _mentions(qtext, name_of.get(cid, "")):
                edge(qid, cid, "involves")
        for rid, r in regions:
            if _mentions(qtext, name_of.get(rid, "")):
                edge(qid, rid, "set_in")
        for fid, f in factions:
            if _mentions(qtext, name_of.get(fid, "")):
                edge(qid, fid, "concerns")
    # Faction → controls → Region
    for fid, f in factions:
        ftext = _entity_text(f)
        for rid, r in regions:
            if _mentions(ftext, name_of.get(rid, "")):
                edge(fid, rid, "controls")

    return {"nodes": nodes, "edges": edges, "by_type": by_type}


@router.get("/{pid}")
async def get_graph(pid: str):
    """🕸️ The canon knowledge graph (nodes + inferred relationships)."""
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1})
    if not g:
        return {"error": "game not found"}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    arts = (kb or {}).get("artifacts") or {}
    graph = build_graph(arts)
    return {"game_id": pid, "title": g.get("title", ""),
            "node_count": len(graph["nodes"]), "edge_count": len(graph["edges"]),
            **graph}


def _compute_issues(arts: dict, stale: dict, graph: dict) -> list:
    """Shared issue computation for both /audit and /heal. Each issue carries an
    `entity`/`etype` ref (when applicable) so heal can ground the LLM in the real node."""
    nodes = graph["nodes"]
    deg: dict = {}
    for e in graph["edges"]:
        deg[e["source"]] = deg.get(e["source"], 0) + 1
        deg[e["target"]] = deg.get(e["target"], 0) + 1

    issues = []
    # 1) stale artifacts (upstream changed)
    for art in stale:
        issues.append({"severity": "warn", "type": "stale",
                       "message": f"'{art}' is stale — an upstream stage changed; regenerate to stay consistent."})
    # 2) characters / factions never referenced by any quest (isolated canon)
    for n in nodes:
        if n["type"] in ("Character", "Faction", "Region") and deg.get(n["id"], 0) == 0:
            issues.append({"severity": "warn", "type": "orphan", "etype": n["type"], "entity": n["name"],
                           "message": f"{n['type']} '{n['name']}' is never referenced by any quest or relationship."})
    # 3) quests with no links (no characters/regions/factions)
    for n in nodes:
        if n["type"] == "Quest" and deg.get(n["id"], 0) == 0:
            issues.append({"severity": "info", "type": "thin-quest", "etype": "Quest", "entity": n["name"],
                           "message": f"Quest '{n['name']}' has no linked characters, regions or factions."})
    # 4) missing core stages
    need = {"core_specs": "Core Specs", "lore_graph": "WorldForge",
            "quest_db": "Narrative", "mechanics_config": "Mechanics"}
    for art, label in need.items():
        if art not in arts:
            issues.append({"severity": "error", "type": "missing-stage",
                           "message": f"{label} has not been built yet."})
    return issues


@router.get("/{pid}/audit")
async def audit_canon(pid: str):
    """🩺 Consistency Auditor — uses the graph + KB to surface canon problems:
    orphaned entities, never-referenced characters/factions, stale artifacts, missing stages."""
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1})
    if not g:
        return {"error": "game not found"}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1, "stale": 1})
    arts = (kb or {}).get("artifacts") or {}
    stale = (kb or {}).get("stale") or {}
    graph = build_graph(arts)
    issues = _compute_issues(arts, stale, graph)

    errors = sum(1 for i in issues if i["severity"] == "error")
    warns = sum(1 for i in issues if i["severity"] == "warn")
    score = max(0, 100 - errors * 25 - warns * 8 - (len(issues) - errors - warns) * 2)
    # strip internal grounding keys from the public audit payload
    public = [{k: v for k, v in i.items() if k in ("severity", "type", "message")} for i in issues[:40]]
    return {"game_id": pid, "title": g.get("title", ""),
            "score": score, "issue_count": min(len(issues), 40),
            "errors": errors, "warnings": warns,
            "issues": public}


@router.post("/{pid}/heal")
async def heal_canon(pid: str):
    """🪄 Canon Auto-Heal — closes the loop on the auditor. For each fixable canon
    gap (orphaned entities, thin quests) the LLM proposes a concrete, grounded patch
    that weaves the loose entity back into the world. Suggest-only: returns structured
    fixes the creator can review; persists nothing. Stale/missing-stage issues are
    excluded (they're resolved by re-running the upstream stage, not by narrative edits)."""
    from routes.llm_router import route_complete

    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1})
    if not g:
        return {"error": "game not found"}
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1, "stale": 1})
    arts = (kb or {}).get("artifacts") or {}
    stale = (kb or {}).get("stale") or {}
    graph = build_graph(arts)
    issues = _compute_issues(arts, stale, graph)

    fixable = [i for i in issues if i["type"] in ("orphan", "thin-quest")][:12]
    if not fixable:
        return {"game_id": pid, "title": g.get("title", ""), "fixable_count": 0, "fixes": [],
                "message": "No narrative gaps to heal — canon is well-connected ✨"}

    # ground the model in the real world: a slice of existing connected entities by type
    nodes = graph["nodes"]
    roster: dict = {}
    for n in nodes:
        roster.setdefault(n["type"], [])
        if len(roster[n["type"]]) < 8:
            roster[n["type"]].append(n["name"])
    roster_txt = "\n".join(f"- {t}: {', '.join(v)}" for t, v in roster.items() if v)
    gaps_txt = "\n".join(
        f'{idx}. [{i["type"]}] {i.get("etype","")} "{i.get("entity","")}" — {i["message"]}'
        for idx, i in enumerate(fixable))

    system = (
        "You are a senior narrative designer doing a canon-consistency pass on a game world. "
        "For each flagged gap, propose ONE concrete, lore-faithful patch that weaves the loose "
        "entity into the existing canon WITHOUT inventing contradictions. Re-use the existing "
        "entities listed in the roster wherever possible. Output ONLY a JSON array (no prose) of "
        'objects: {"entity": str, "type": str (orphan|thin-quest), "title": short imperative fix title, '
        '"patch": 1-2 sentence concrete change to make, "links": [names of existing entities to connect to]}. '
        "Keep it tight, buildable and grounded.")
    prompt = (f"GAME: {g.get('title','(untitled)')}\n\n"
              f"EXISTING CANON ROSTER:\n{roster_txt}\n\n"
              f"GAPS TO HEAL:\n{gaps_txt}\n\n"
              f"Return exactly {len(fixable)} fix objects, one per gap, in order.")

    res = await route_complete("creative", prompt, system=system,
                               session_id=f"heal-{pid}", timeout_s=90, use_cache=False)
    if res.get("error"):
        return {"game_id": pid, "title": g.get("title", ""), "error": res["error"],
                "fixable_count": len(fixable), "fixes": []}

    parsed = _extract_json_array(res.get("content", ""))
    fixes = []
    for idx, gap in enumerate(fixable):
        p = parsed[idx] if idx < len(parsed) and isinstance(parsed[idx], dict) else {}
        fixes.append({
            "entity": p.get("entity") or gap.get("entity", ""),
            "etype": gap.get("etype", ""),
            "type": gap.get("type", ""),
            "issue": gap["message"],
            "title": (p.get("title") or "Reconnect to canon")[:120],
            "patch": (p.get("patch") or "")[:600],
            "links": [str(x) for x in (p.get("links") or [])][:6],
        })

    return {"game_id": pid, "title": g.get("title", ""),
            "model": res.get("model"), "fixable_count": len(fixable),
            "fixes": fixes}


# Faction/Region live in the WorldForge lore_graph; Character/Quest in the Narrative quest_db.
_ETYPE_ARTIFACT = {"Faction": "lore_graph", "Region": "lore_graph",
                   "Character": "quest_db", "Quest": "quest_db"}


class ApplyFixBody(BaseModel):
    entity: str = ""
    etype: str = ""
    title: str = ""
    patch: str = ""
    links: list = []


async def _kick_regen(pid: str):
    """Auto-regen-on-apply: rebuild the stale stage(s) via GroupChat. Returns job_id or None."""
    try:
        from routes.groupchat import run_groupchat
        job = await run_groupchat(pid, only_missing=False, only_stale=True)
        return job.get("job_id")
    except Exception:
        return None


@router.post("/{pid}/heal/apply")
async def apply_canon_fix(pid: str, body: ApplyFixBody, regen: bool = True):
    """🩹 Accept a proposed heal patch: record it on game_kb.canon_patches and mark the
    target artifact STALE so the next Snowball/GroupChat regeneration weaves the fix in.
    Suggest→accept is the bridge between the auditor and the regeneration pipeline."""
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1})
    if not g:
        return {"error": "game not found"}
    artifact = _ETYPE_ARTIFACT.get(body.etype)
    patch_rec = {
        "entity": body.entity, "etype": body.etype, "title": body.title[:120],
        "patch": body.patch[:600], "links": [str(x) for x in (body.links or [])][:6],
        "artifact": artifact, "at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
    }
    sets = {"game_id": pid}
    if artifact:
        sets[f"stale.{artifact}"] = True
    await _db.game_kb.update_one(
        {"game_id": pid},
        {"$push": {"canon_patches": patch_rec}, "$set": sets},
        upsert=True)
    job_id = await _kick_regen(pid) if (regen and artifact) else None
    return {"ok": True, "game_id": pid, "applied": patch_rec,
            "marked_stale": artifact, "regen_job_id": job_id,
            "note": (f"Patch recorded — regenerating {artifact} now (job {job_id})."
                     if job_id else
                     f"Patch recorded — regenerate {artifact or 'the stage'} to apply it to canon.")}


class ApplyAllBody(BaseModel):
    fixes: list = []


@router.post("/{pid}/heal/apply-all")
async def apply_all_canon_fixes(pid: str, body: ApplyAllBody, regen: bool = True):
    """🩹✨ Batch-accept EVERY proposed heal patch in one tap (big-win g). Records all to
    canon_patches and marks each affected artifact stale for the next regeneration."""
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1})
    if not g:
        return {"error": "game not found"}
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    recs, stale_arts = [], set()
    for f in (body.fixes or [])[:12]:
        if not isinstance(f, dict):
            continue
        artifact = _ETYPE_ARTIFACT.get(f.get("etype", ""))
        recs.append({"entity": f.get("entity", ""), "etype": f.get("etype", ""),
                     "title": str(f.get("title", ""))[:120], "patch": str(f.get("patch", ""))[:600],
                     "links": [str(x) for x in (f.get("links") or [])][:6],
                     "artifact": artifact, "at": now})
        if artifact:
            stale_arts.add(artifact)
    if not recs:
        return {"ok": False, "applied_count": 0, "error": "no fixes provided"}
    sets = {"game_id": pid, **{f"stale.{a}": True for a in stale_arts}}
    await _db.game_kb.update_one(
        {"game_id": pid}, {"$push": {"canon_patches": {"$each": recs}}, "$set": sets}, upsert=True)
    job_id = await _kick_regen(pid) if (regen and stale_arts) else None
    return {"ok": True, "game_id": pid, "applied_count": len(recs),
            "marked_stale": sorted(stale_arts), "regen_job_id": job_id,
            "note": (f"{len(recs)} patches recorded — regenerating {', '.join(sorted(stale_arts))} (job {job_id})."
                     if job_id else
                     f"{len(recs)} patches recorded — regenerate {', '.join(sorted(stale_arts)) or 'stages'} to apply.")}
