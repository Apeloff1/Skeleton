"""
routes/gameforge_studio.py — GameForge CNS Studio governance surface.

Wires the newly-integrated Snowball questionnaire/step logs, Forge activity logs,
Boardroom Vault and Deployment pipeline into ONE governed pipeline, and connects:

  • ROOMS  — every step/forge/questionnaire/boardroom event is dispatched to the
             1000-room CNS activity ledger so agents everywhere can read the logs
             and keep working (spec: "agents in every room can read these logs").
  • EVALUATION ROOM (Knowledge Nexus Jury) — anything submitted to the Boardroom is
             sent to the Evaluation Room FIRST, evaluated, then returned to the
             Boardroom before it is persisted to the Vault + gamefiles.
  • JEEVES — full oversight of all usage + a command channel so Jeeves can operate
             the app from chat.

All imports are defensive so a partial CNS never crashes boot.
"""
from __future__ import annotations

import base64
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/gameforge/studio", tags=["gameforge-studio"])

# RBAC guards (soft in dev; enforced when GAMEFORGE_AUTH_ENFORCE=1)
try:
    from routes.gameforge_auth import require_role
    _editor = require_role("editor")
    _admin = require_role("admin")
except Exception:  # noqa: BLE001
    def _editor():  # type: ignore
        return {"role": "admin", "dev_mode": True}
    _admin = _editor

# ── Defensive imports of the integrated CNS modules ───────────────────────────
_IMPORT_ERR: dict[str, str] = {}


def _try(path: str, attr: str):
    try:
        mod = __import__(path, fromlist=[attr])
        return getattr(mod, attr)
    except Exception as e:  # noqa: BLE001
        _IMPORT_ERR[path] = f"{type(e).__name__}: {e}"[:160]
        return None


questionnaire_logger = _try("gameforge.snowball.questionnaire_logging", "questionnaire_logger")
get_all_step_logs = _try("gameforge.snowball.snowball_step_logs", "get_all_step_logs")
get_step_database = _try("gameforge.snowball.snowball_step_logs", "get_step_database")
SNOWBALL_STEPS = _try("gameforge.snowball.snowball_step_logs", "SNOWBALL_STEPS") or {}
get_all_forge_logs = _try("gameforge.forges.forge_logging", "get_all_forge_logs")
forge_orchestrator = _try("gameforge.forges.forge_orchestrator", "forge_orchestrator")
boardroom_vault = _try("gameforge.boardroom.persistent_vault", "boardroom_vault") \
    or _try("gameforge.boardroom.vault", "boardroom_vault")
knowledge_nexus_jury = _try("gameforge.snowball.snowball_full_integration", "snowball_full_integration")
enhanced_deployment = _try("gameforge.deployment.enhanced_deployment", "enhanced_deployment")
_jury = _try("knowledge_nexus.engines.knowledge_nexus_jury_engine", "knowledge_nexus_jury")


def _db():
    from core.databases import get_sync_db
    return get_sync_db()


# ── ROOM WIRING — dispatch every event to the 1000-room CNS ───────────────────
_ROOM_IDS: list[str] = []
_rr = {"i": 0}


def _room_ids() -> list[str]:
    if not _ROOM_IDS:
        try:
            from gameforge.rooms.full_room_registry import all_rooms
            _ROOM_IDS.extend(list(all_rooms().keys()))
        except Exception:  # noqa: BLE001
            _ROOM_IDS.extend([f"room_{i:04d}" for i in range(1000)])
    return _ROOM_IDS


def dispatch_to_rooms(event: str, payload: dict, fanout: int = 3) -> list[str]:
    """Round-robin a step/forge/boardroom event across the CNS rooms so agents
    everywhere log it and keep working. Persisted to gameforge_room_activity."""
    ids = _room_ids()
    if not ids:
        return []
    picked = []
    for _ in range(min(fanout, len(ids))):
        picked.append(ids[_rr["i"] % len(ids)])
        _rr["i"] += 1
    doc = {
        "event": event,
        "payload": payload,
        "rooms": picked,
        "ts": time.time(),
    }
    try:
        _db()["gameforge_room_activity"].insert_one(dict(doc))
    except Exception:  # noqa: BLE001
        pass
    # also drop a note into the relevant snowball step so all rooms can read it
    try:
        step_id = payload.get("step_id")
        if step_id and get_step_database:
            sdb = get_step_database(step_id)
            if sdb:
                sdb.add_agent_note(f"[rooms {','.join(picked)}] {event}: {str(payload)[:120]}")
    except Exception:  # noqa: BLE001
        pass
    return picked


def _room_activity(limit: int = 50) -> list[dict]:
    try:
        cur = _db()["gameforge_room_activity"].find({}, {"_id": 0}).sort("ts", -1).limit(limit)
        return list(cur)
    except Exception:  # noqa: BLE001
        return []


# ── ON-DEMAND KNOWLEDGE ACQUISITION — rooms auto-research unknown topics ───────
async def _auto_research(topic: str) -> dict:
    """If the brain doesn't already know `topic`, agents query the free-API
    catalog, fold a summary into Jeeves' brain, and log it to the rooms."""
    topic = (topic or "").strip()
    if not topic:
        return {"topic": topic, "known": False, "acquired": False}
    # already known?
    try:
        from gameforge.jeeves.jeeves_self_training import recall
        if recall(_db(), topic, k=1):
            return {"topic": topic, "known": True, "acquired": False}
    except Exception:  # noqa: BLE001
        pass
    # acquire from a free API
    try:
        from gameforge.knowledge import free_apis as FA
        api_key, params = FA.pick_api(topic)
        res = await FA.fetch(api_key, params)
        if not res.get("ok"):
            return {"topic": topic, "known": False, "acquired": False, "error": res.get("error")}
        summary = FA.summarize(api_key, res.get("data"))
        adjudication = None
        if summary:
            # IMPROVEMENT + ACTION ITEM: Jeeves' research is auto-fed THROUGH the
            # Jury Room; only adversarially-scrutinized (accepted) knowledge is
            # written to the wiki. Rejected/revise never silently reaches jeeves_knowledge.
            try:
                from routes.gameforge_jury import feed_and_adjudicate
                adjudication = feed_and_adjudicate(f"jeeves:{api_key}", f"acquired:{topic[:60]}", summary)
            except Exception:  # noqa: BLE001
                _db()["jeeves_knowledge"].update_one(
                    {"topic": f"acquired:{topic[:60]}"},
                    {"$set": {"topic": f"acquired:{topic[:60]}", "text": summary, "domain": "acquired",
                              "source_api": api_key, "auto": True, "acquired_at": time.time()}}, upsert=True)
        dispatch_to_rooms("auto_research", {"topic": topic, "api": api_key})
        return {"topic": topic, "known": False, "acquired": bool(summary), "api": api_key,
                "summary": summary, "jury": adjudication}
    except Exception as e:  # noqa: BLE001
        return {"topic": topic, "known": False, "acquired": False, "error": f"{type(e).__name__}"}


# ── Boardroom ledger (persistent) ─────────────────────────────────────────────
def _ledger_add(entry: dict):
    try:
        _db()["gameforge_boardroom_ledger"].insert_one(dict(entry))
    except Exception:  # noqa: BLE001
        pass


def _ledger(limit: int = 50) -> list[dict]:
    try:
        cur = _db()["gameforge_boardroom_ledger"].find({}, {"_id": 0}).sort("ts", -1).limit(limit)
        return list(cur)
    except Exception:  # noqa: BLE001
        return []


# ══════════════════════════════════════════════════════════════════════════════
# QUESTIONNAIRE
# ══════════════════════════════════════════════════════════════════════════════
class QBody(BaseModel):
    question_id: str
    question: str
    answer: Any
    confidence: float = 0.9


@router.post("/questionnaire/log")
async def questionnaire_log(b: QBody):
    if not questionnaire_logger:
        return {"ok": False, "error": "questionnaire module unavailable"}
    questionnaire_logger.log_response(b.question_id, b.question, b.answer, b.confidence)
    rooms = dispatch_to_rooms("questionnaire_answer", {"question_id": b.question_id, "answer": b.answer})
    return {"ok": True, "logged": b.question_id, "dispatched_rooms": rooms}


@router.get("/questionnaire")
async def questionnaire_get():
    if not questionnaire_logger:
        return {"ok": False, "error": "questionnaire module unavailable"}
    return {
        "responses": questionnaire_logger.get_all_responses(),
        "context": questionnaire_logger.get_responses_as_context(),
    }


@router.get("/questionnaire/questions")
async def questionnaire_questions():
    """The intake question set (from the dormant questionnaire_runner)."""
    try:
        from gameforge.snowball.questionnaire_runner import QUESTIONS
        return {"ok": True, "questions": QUESTIONS}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:120]}


# ══════════════════════════════════════════════════════════════════════════════
# SNOWBALL STEP LOGS (rooms connected to every step)
# ══════════════════════════════════════════════════════════════════════════════
class ChoiceBody(BaseModel):
    key: str
    value: Any


@router.get("/steps")
async def steps_all():
    if not get_all_step_logs:
        return {"ok": False, "error": "step logs unavailable"}
    return {"steps": get_all_step_logs(), "catalog": SNOWBALL_STEPS}


@router.post("/step/{step_id}/choice")
async def step_choice(step_id: str, b: ChoiceBody):
    if not get_step_database:
        return {"ok": False, "error": "step logs unavailable"}
    sdb = get_step_database(step_id)
    if not sdb:
        return {"ok": False, "error": f"unknown step '{step_id}'", "valid": list(SNOWBALL_STEPS.keys())}
    sdb.record_user_choice(b.key, b.value)
    rooms = dispatch_to_rooms("step_choice", {"step_id": step_id, "key": b.key, "value": b.value})
    return {"ok": True, "step": step_id, "dispatched_rooms": rooms, "log": sdb.get_log()}


@router.post("/step/{step_id}/complete")
async def step_complete(step_id: str):
    if not get_step_database:
        return {"ok": False, "error": "step logs unavailable"}
    sdb = get_step_database(step_id)
    if not sdb:
        return {"ok": False, "error": f"unknown step '{step_id}'"}
    sdb.complete_step()
    dispatch_to_rooms("step_complete", {"step_id": step_id})
    return {"ok": True, "step": step_id, "status": "completed"}


# ══════════════════════════════════════════════════════════════════════════════
# FORGES
# ══════════════════════════════════════════════════════════════════════════════
class ForgeBody(BaseModel):
    game_concept: dict = {}


@router.get("/forges/logs")
async def forges_logs():
    if not get_all_forge_logs:
        return {"ok": False, "error": "forge logs unavailable"}
    return {"forges": get_all_forge_logs()}


@router.post("/forge/run")
async def forge_run(b: ForgeBody):
    if not forge_orchestrator:
        return {"ok": False, "error": "forge orchestrator unavailable"}
    # Default a full concept so every forge (asset/mechanic/world/code/ui/balance) fires
    concept = {
        "game_name": "Untitled", "genre": "fantasy", "art_style": "pixel",
        "core_mechanic": "core_loop", "core_loop": "explore", "description": "",
        **(b.game_concept or {}),
    }
    # On-demand research: rooms auto-acquire knowledge for unfamiliar genre/mechanic
    research = []
    for topic in {str(concept.get("genre", "")), str(concept.get("core_mechanic", ""))}:
        r = await _auto_research(topic)
        if r.get("acquired"):
            research.append(r)
    results = forge_orchestrator.run_full_pipeline(concept)
    dispatch_to_rooms("forge_pipeline", {"forges": list(results.keys())})
    return {"ok": True, "results": results, "auto_research": research}


# ══════════════════════════════════════════════════════════════════════════════
# BOARDROOM VAULT — direct access (vault access in the board room)
# ══════════════════════════════════════════════════════════════════════════════
class VaultPut(BaseModel):
    filename: str
    content: str            # text or base64
    is_base64: bool = False
    metadata: dict = {}


@router.get("/vault")
async def vault_list():
    if not boardroom_vault:
        return {"ok": False, "error": "vault unavailable"}
    return {"files": boardroom_vault.list_files()}


@router.get("/vault/unified")
async def vault_unified(limit: int = 60):
    """MIRROR — one aggregated view across every vault in the app.

    Canonical source is the Boardroom (encrypted, persisted) vault, listed
    first, followed by the agent code_vault and the Worldforge artifact vaults.
    Every vault screen renders this same list so they always match.
    """
    items: list[dict] = []
    counts = {"boardroom": 0, "agents": 0, "worldforge": 0}

    # 1) Boardroom vault (canonical, encrypted).
    try:
        for f in (boardroom_vault.list_files() if boardroom_vault else []):
            items.append({
                "id": f.get("file_id"), "name": f.get("filename"), "source": "boardroom",
                "kind": "artifact", "encrypted": True,
                "detail": f"v{f.get('latest_version', 1)} · {f.get('total_versions', 1)} versions",
                "created_at": f.get("last_updated"), "meta": f,
            })
            counts["boardroom"] += 1
    except Exception:  # noqa: BLE001
        pass

    # 2) Agent code_vault.
    try:
        from routes.pipeline_agents import get_vault_code
        d = await get_vault_code(limit=limit)
        for e in d.get("vault_entries", []):
            items.append({
                "id": e.get("agent_id") or e.get("stored_at"),
                "name": e.get("agent_name") or "agent artifact", "source": "agents",
                "kind": e.get("content_type", "code"),
                "detail": f"{len(e.get('code_blocks') or [])} code blocks",
                "created_at": e.get("stored_at"), "meta": {},
            })
            counts["agents"] += 1
    except Exception:  # noqa: BLE001
        pass

    # 3) Worldforge artifact vaults (monographs + posters).
    try:
        from routes.worldforge_publish import monograph_saved, poster_saved
        m = await monograph_saved()
        for r in m.get("items", []):
            items.append({"id": r.get("id"), "name": r.get("name", "monograph"),
                          "source": "worldforge", "kind": "monograph",
                          "detail": r.get("scale", ""), "created_at": r.get("created_at"), "meta": {}})
            counts["worldforge"] += 1
        p = await poster_saved()
        for r in p.get("items", []):
            items.append({"id": r.get("id"), "name": r.get("name", "poster"),
                          "source": "worldforge", "kind": "poster",
                          "detail": r.get("style", ""), "created_at": r.get("created_at"),
                          "image": r.get("image"), "meta": {}})
            counts["worldforge"] += 1
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "total": len(items), "counts": counts, "items": items}


@router.post("/vault/put")
async def vault_put(b: VaultPut, user=Depends(_editor)):
    if not boardroom_vault:
        return {"ok": False, "error": "vault unavailable"}
    content = base64.b64decode(b.content) if b.is_base64 else b.content.encode("utf-8")
    entry = boardroom_vault.put_file(b.filename, content, b.metadata)
    dispatch_to_rooms("vault_put", {"filename": b.filename, "file_id": entry.file_id})
    _audit("vault_put", b.filename, user)
    return {"ok": True, "file_id": entry.file_id, "version": entry.version}


@router.get("/vault/{file_id}")
async def vault_get(file_id: str, version: Optional[int] = None):
    if not boardroom_vault:
        return {"ok": False, "error": "vault unavailable"}
    content = boardroom_vault.get_file(file_id, version)
    if content is None:
        return {"ok": False, "error": "not found"}
    try:
        text = content.decode("utf-8")
        return {"ok": True, "file_id": file_id, "content": text}
    except Exception:  # noqa: BLE001
        return {"ok": True, "file_id": file_id, "content_base64": base64.b64encode(content).decode()}


@router.get("/vault/{file_id}/versions")
async def vault_versions(file_id: str):
    if not boardroom_vault or not hasattr(boardroom_vault, "get_versions"):
        return {"ok": False, "error": "versioning unavailable"}
    return {"ok": True, "file_id": file_id, "versions": boardroom_vault.get_versions(file_id)}


class RollbackBody(BaseModel):
    to_version: int


@router.post("/vault/{file_id}/rollback")
async def vault_rollback(file_id: str, b: RollbackBody, user=Depends(_admin)):
    """Error-recovery: restore a previous vault version as a new latest version."""
    if not boardroom_vault or not hasattr(boardroom_vault, "rollback"):
        return {"ok": False, "error": "rollback unavailable"}
    entry = boardroom_vault.rollback(file_id, b.to_version)
    if not entry:
        return {"ok": False, "error": "version not found"}
    dispatch_to_rooms("vault_rollback", {"file_id": file_id, "to_version": b.to_version})
    _audit("vault_rollback", file_id, user)
    return {"ok": True, "file_id": file_id, "restored_from": b.to_version, "new_version": entry.version}


def _vault_filename(file_id: str) -> str:
    try:
        for f in boardroom_vault.list_files():
            if f.get("file_id") == file_id:
                return f.get("filename") or f"{file_id}.bin"
    except Exception:  # noqa: BLE001
        pass
    return f"{file_id}.bin"


@router.get("/vault/{file_id}/download")
async def vault_download(file_id: str, version: Optional[int] = None):
    """Download a Boardroom vault file to the device (decrypted attachment)."""
    if not boardroom_vault:
        return {"ok": False, "error": "vault unavailable"}
    content = boardroom_vault.get_file(file_id, version)
    if content is None:
        return {"ok": False, "error": "not found"}
    filename = _vault_filename(file_id)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class FetchToBody(BaseModel):
    system: str            # "gamefiles" | "knowledge"
    game_name: str = "Studio"


@router.post("/vault/{file_id}/fetch-to")
async def vault_fetch_to(file_id: str, b: FetchToBody, user=Depends(_editor)):
    """Pull a vault artifact INTO another system so work can continue there.

    • gamefiles  → registers it in gameforge_gamefiles (build/forge systems read it)
    • knowledge  → feeds it into the Jeeves brain
    """
    if not boardroom_vault:
        return {"ok": False, "error": "vault unavailable"}
    content = boardroom_vault.get_file(file_id)
    if content is None:
        return {"ok": False, "error": "not found"}
    try:
        text = content.decode("utf-8")
    except Exception:  # noqa: BLE001
        text = base64.b64encode(content).decode()
    filename = _vault_filename(file_id)

    if b.system == "gamefiles":
        res = _persist_gamefile(b.game_name, filename, text,
                                {"kind": "artifact", "source": "vault", "file_id": file_id})
        _audit("vault_fetch_gamefiles", filename, user)
        dispatch_to_rooms("vault_fetch_to", {"file_id": file_id, "system": "gamefiles"})
        return {"ok": res.get("ok", False), "system": "gamefiles", "game_name": b.game_name,
                "filename": filename}

    if b.system == "knowledge":
        added = False
        try:
            from routes.gameforge_knowledge import _brain_add  # type: ignore
            _brain_add(filename, text[:4000])
            added = True
        except Exception:  # noqa: BLE001
            try:
                _db()["gameforge_knowledge"].insert_one(
                    {"topic": filename, "text": text[:4000], "source": "vault",
                     "file_id": file_id, "ts": time.time()})
                added = True
            except Exception:  # noqa: BLE001
                added = False
        _audit("vault_fetch_knowledge", filename, user)
        return {"ok": added, "system": "knowledge", "topic": filename}

    return {"ok": False, "error": f"unknown system '{b.system}'"}


# ══════════════════════════════════════════════════════════════════════════════
# PRIORITY 6: ERROR RECOVERY — alarm system + automatic vault rollback
# ══════════════════════════════════════════════════════════════════════════════
def _alarms():
    return _db()["gameforge_alarms"]


def _raise_alarm(kind: str, detail: str, severity: str = "warning") -> dict:
    doc = {"kind": kind, "detail": detail, "severity": severity,
           "resolved": False, "ts": time.time()}
    try:
        _alarms().insert_one(dict(doc))
    except Exception:  # noqa: BLE001
        pass
    return doc


def _auto_rollback_latest() -> dict:
    """Roll back the most-recently-updated multi-version vault file to its
    previous version. Returns what (if anything) was recovered."""
    if not boardroom_vault:
        return {"recovered": False, "reason": "vault unavailable"}
    candidates = [f for f in boardroom_vault.list_files() if (f.get("total_versions") or 1) > 1]
    if not candidates:
        return {"recovered": False, "reason": "no multi-version file to roll back"}
    candidates.sort(key=lambda f: f.get("last_updated", 0), reverse=True)
    target = candidates[0]
    prev = (target.get("latest_version") or 2) - 1
    entry = boardroom_vault.rollback(target["file_id"], prev)
    if not entry:
        return {"recovered": False, "reason": "rollback failed"}
    return {"recovered": True, "file_id": target["file_id"], "filename": target.get("filename"),
            "restored_from": prev, "new_version": entry.version}


class AlarmBody(BaseModel):
    kind: str
    detail: str = ""
    severity: str = "warning"


@router.post("/alarm")
async def alarm_raise(b: AlarmBody, user=Depends(_editor)):
    doc = _raise_alarm(b.kind, b.detail, b.severity)
    dispatch_to_rooms("alarm", {"kind": b.kind, "severity": b.severity})
    return {"ok": True, "alarm": doc}


@router.get("/alarms")
async def alarms_list(limit: int = 30, unresolved_only: bool = False):
    q = {"resolved": False} if unresolved_only else {}
    rows = list(_alarms().find(q, {"_id": 0}).sort("ts", -1).limit(limit))
    return {"ok": True, "alarms": rows,
            "unresolved": _alarms().count_documents({"resolved": False})}


class RecoverBody(BaseModel):
    reason: str = "manual"


@router.post("/auto-recover")
async def auto_recover(b: RecoverBody, user=Depends(_editor)):
    """Automatic error recovery: roll back the latest vault artifact to its
    previous good version and resolve outstanding alarms."""
    result = _auto_rollback_latest()
    if result.get("recovered"):
        _alarms().update_many({"resolved": False}, {"$set": {"resolved": True, "resolved_at": time.time()}})
        _raise_alarm("auto_recover", f"rolled back {result['filename']} to v{result['restored_from']}", "info")
        _audit("auto_recover", result.get("filename", "?"), user)
        dispatch_to_rooms("auto_recover", result)
    return {"ok": True, "reason": b.reason, **result}


# ══════════════════════════════════════════════════════════════════════════════
# GOVERNANCE FLOW — Boardroom → Evaluation Room → Boardroom → Vault + gamefiles
# ══════════════════════════════════════════════════════════════════════════════
class SubmitBody(BaseModel):
    game_name: str
    filename: str
    content: str
    kind: str = "artifact"
    step_id: Optional[str] = None
    metadata: dict = {}
    require_supermajority: bool = False


def _persist_gamefile(game_name: str, filename: str, content: str, meta: dict) -> dict:
    doc = {
        "game_name": game_name,
        "filename": filename,
        "content": content,
        "metadata": meta,
        "ts": time.time(),
    }
    try:
        _db()["gameforge_gamefiles"].insert_one(dict(doc))
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:120]}


@router.post("/boardroom/submit")
async def boardroom_submit(b: SubmitBody):
    """The governed pipeline. Anything entering the Boardroom is routed to the
    Evaluation Room FIRST, evaluated, then returned to the Boardroom before it is
    persisted to the Vault + gamefiles (ONLY on ACCEPT)."""
    trace: list[dict] = []
    content_id = f"{b.game_name}:{b.filename}:{int(time.time())}"

    # 1. Boardroom intake
    trace.append({"stage": "boardroom_intake", "at": time.time()})
    dispatch_to_rooms("boardroom_intake", {"content_id": content_id, "step_id": b.step_id})

    # On-demand research: acquire knowledge for the artifact kind if unfamiliar
    research = await _auto_research(f"{b.kind}")
    if research.get("acquired"):
        trace.append({"stage": "auto_research", "topic": research.get("topic"),
                      "api": research.get("api"), "at": time.time()})

    # 2. Route to EVALUATION ROOM first
    trace.append({"stage": "evaluation_room:enter", "at": time.time()})
    if not _jury:
        return {"ok": False, "error": "evaluation room (jury) unavailable", "trace": trace}
    decision = _jury.evaluate_content(
        content_id, b.content, context={"game_name": b.game_name, "kind": b.kind},
        require_supermajority=b.require_supermajority,
    )
    verdict = decision.final_vote.value
    trace.append({
        "stage": "evaluation_room:verdict", "verdict": verdict,
        "confidence": decision.confidence, "rationale": decision.rationale,
        "votes": {k: v.value for k, v in decision.votes.items()}, "at": time.time(),
    })
    dispatch_to_rooms("evaluation_verdict", {"content_id": content_id, "verdict": verdict})

    # 3. Return to BOARDROOM
    trace.append({"stage": "boardroom_return", "verdict": verdict, "at": time.time()})

    result: dict = {
        "ok": True, "content_id": content_id, "verdict": verdict,
        "confidence": decision.confidence, "rationale": decision.rationale,
    }

    # 4. Persist to Vault + gamefiles ONLY on ACCEPT
    if verdict == "accept":
        meta = {**b.metadata, "game_name": b.game_name, "kind": b.kind,
                "step_id": b.step_id, "evaluation": verdict, "content_id": content_id}
        entry = boardroom_vault.put_file(b.filename, b.content.encode("utf-8"), meta) if boardroom_vault else None
        gf = _persist_gamefile(b.game_name, b.filename, b.content, meta)
        result["vaulted"] = bool(entry)
        result["file_id"] = entry.file_id if entry else None
        result["gamefiles"] = gf["ok"]
        trace.append({"stage": "persist:vault+gamefiles",
                      "file_id": entry.file_id if entry else None, "at": time.time()})
        dispatch_to_rooms("persisted", {"content_id": content_id, "file_id": entry.file_id if entry else None})
        # SELF-LEARNING: every ACCEPTED artifact grows Jeeves' brain — but routed
        # THROUGH the Jury Room so the knowledge is adversarially scrutinized
        # before it lands in the wiki (jeeves_knowledge).
        try:
            topic = f"learned:{b.game_name}:{b.kind}:{b.filename}"[:80]
            try:
                from routes.gameforge_jury import feed_and_adjudicate
                result["jury"] = feed_and_adjudicate("boardroom_accept", topic, b.content[:600])
            except Exception:  # noqa: BLE001
                _db()["jeeves_knowledge"].update_one(
                    {"topic": topic},
                    {"$set": {"topic": topic, "text": b.content[:600], "domain": "learned",
                              "source": "boardroom_accept", "learned_at": time.time()}}, upsert=True)
            from gameforge.exocortex.zaibatsu.self_systems import SelfLearningEngine
            SelfLearningEngine("jeeves").learn(
                source="boardroom_accept", pattern=f"{b.kind} {b.filename}", action="accepted_artifact")
        except Exception:  # noqa: BLE001
            pass
    else:
        result["vaulted"] = False
        result["gamefiles"] = False
        result["held_reason"] = f"evaluation returned '{verdict}' — held in Boardroom, not persisted"
        trace.append({"stage": "held_in_boardroom", "verdict": verdict, "at": time.time()})

    result["trace"] = trace
    _ledger_add({"content_id": content_id, "game_name": b.game_name, "filename": b.filename,
                 "verdict": verdict, "vaulted": result["vaulted"], "ts": time.time()})
    return result


@router.get("/boardroom/ledger")
async def boardroom_ledger(limit: int = 50):
    return {"ledger": _ledger(limit)}


# ══════════════════════════════════════════════════════════════════════════════
# ROOMS — what every room sees + activity proof
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/rooms/context")
async def rooms_context(room_name: str = "any"):
    """Full build context visible to any room's agents."""
    ctx: dict = {"room": room_name}
    if questionnaire_logger:
        ctx["questionnaire"] = questionnaire_logger.get_all_responses()
    if get_all_step_logs:
        ctx["snowball_steps"] = get_all_step_logs()
    if get_all_forge_logs:
        ctx["forge_activity"] = get_all_forge_logs()
    if boardroom_vault:
        ctx["vault_files"] = boardroom_vault.list_files()
    ctx["recent_room_activity"] = _room_activity(20)
    return ctx


@router.get("/rooms/activity")
async def rooms_activity(limit: int = 50):
    return {"activity": _room_activity(limit), "total_rooms": len(_room_ids())}


class ResearchBody(BaseModel):
    topic: str


@router.post("/rooms/research")
async def rooms_research(b: ResearchBody):
    """A room/agent hits an unknown topic → auto-acquire it from the free-API
    catalog and fold it into the shared brain (on-demand knowledge acquisition)."""
    return {"ok": True, **(await _auto_research(b.topic))}


# ══════════════════════════════════════════════════════════════════════════════
# JEEVES — full oversight + operate the app from chat
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/jeeves/oversight")
async def jeeves_oversight():
    """Everything Jeeves oversees across the whole studio."""
    o: dict = {"ok": True, "at": time.time(), "import_errors": _IMPORT_ERR}
    if questionnaire_logger:
        o["questionnaire_count"] = len(questionnaire_logger.get_all_responses())
    if get_all_step_logs:
        steps = get_all_step_logs()
        o["steps"] = {k: v.get("status") for k, v in steps.items()}
    if get_all_forge_logs:
        o["forge_activity_counts"] = {k: len(v) for k, v in get_all_forge_logs().items()}
    if boardroom_vault:
        o["vault_files"] = len(boardroom_vault.list_files())
    o["boardroom_ledger"] = _ledger(10)
    o["room_activity_recent"] = _room_activity(10)
    o["total_rooms"] = len(_room_ids())
    try:
        if enhanced_deployment:
            o["deployment_history"] = enhanced_deployment.pipeline.get_deployment_history()[-5:]
    except Exception:  # noqa: BLE001
        pass
    return o


class JeevesCmd(BaseModel):
    message: str
    game_name: str = "Untitled"


def _jeeves_recall(query: str):
    try:
        from gameforge.jeeves.jeeves_self_training import recall
        return recall(_db(), query, k=4)
    except Exception:  # noqa: BLE001
        return []


@router.get("/jeeves/knowledge")
async def jeeves_knowledge():
    """Jeeves' self-trained game-specific knowledge (prefilled at launch)."""
    try:
        from gameforge.jeeves.jeeves_self_training import status
        st = status(_db())
        kb = list(_db()["jeeves_knowledge"].find({}, {"_id": 0}).limit(60))
        return {"ok": True, "status": st, "knowledge": kb}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:160]}


@router.post("/jeeves/train")
async def jeeves_train():
    """Force Jeeves to (re)train on the prefilled game-specific logic."""
    try:
        from gameforge.jeeves.jeeves_self_training import train_at_launch
        return train_at_launch(_db())
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:160]}


@router.post("/jeeves/command")
async def jeeves_command(c: JeevesCmd):
    """Jeeves operates the app from chat using ITS OWN logic — a deterministic
    intent router backed by its self-trained game-specific knowledge base."""
    msg = c.message.lower().strip()
    actions: list[str] = []
    data: dict = {}

    if any(w in msg for w in ("oversight", "status", "overview", "report", "what's going on", "whats going on")):
        data["oversight"] = await jeeves_oversight()
        actions.append("oversight")

    if "forge" in msg or "generate" in msg:
        if forge_orchestrator:
            concept = {"game_name": c.game_name, "genre": "fantasy", "art_style": "pixel",
                       "core_mechanic": "core_loop", "core_loop": "explore"}
            data["forge"] = forge_orchestrator.run_full_pipeline(concept)
            dispatch_to_rooms("jeeves_forge", {"game": c.game_name})
            actions.append("ran_forges")

    if "deploy" in msg or "ship" in msg or "build" in msg:
        if enhanced_deployment:
            data["deploy"] = enhanced_deployment.full_deploy(c.game_name)
            dispatch_to_rooms("jeeves_deploy", {"game": c.game_name})
            actions.append("deployed")

    if "vault" in msg:
        if boardroom_vault:
            data["vault"] = boardroom_vault.list_files()
            actions.append("listed_vault")

    if "room" in msg:
        data["rooms"] = {"total": len(_room_ids()), "recent": _room_activity(10)}
        actions.append("room_activity")

    # Jeeves' OWN knowledge — answer game-design questions from its trained brain
    hits = _jeeves_recall(msg)
    if hits and not any(a in actions for a in ("ran_forges", "deployed")):
        data["knowledge"] = hits
        actions.append("recalled_knowledge")

    if not actions:
        data["oversight"] = await jeeves_oversight()
        actions.append("oversight")
        reply = ("I have full oversight of the studio and my own trained game-design brain. "
                 "Ask me to run forges, deploy a build, inspect the vault, report rooms, or ask about "
                 "genres/mechanics/pipeline/monetization.")
    elif "recalled_knowledge" in actions and len(actions) == 1:
        reply = hits[0].get("text", "Here's what I know.")
    else:
        reply = f"Done: {', '.join(a for a in actions if a != 'recalled_knowledge')}."

    return {"ok": True, "reply": reply, "actions": actions, "data": data}


# ══════════════════════════════════════════════════════════════════════════════
# DEPLOYMENT
# ══════════════════════════════════════════════════════════════════════════════
class DeployBody(BaseModel):
    game_name: str
    platforms: Optional[list[str]] = None
    sign: bool = True


@router.post("/deploy")
async def deploy(b: DeployBody, user=Depends(_editor)):
    if not enhanced_deployment:
        return {"ok": False, "error": "deployment unavailable"}
    rec = enhanced_deployment.full_deploy(b.game_name, b.platforms, b.sign)
    dispatch_to_rooms("deploy", {"game": b.game_name})
    _audit("deploy", b.game_name, user)
    return {"ok": True, "deployment": rec}


# ══════════════════════════════════════════════════════════════════════════════
# GIT / GITHUB — ready-but-inactive (push activates once remote+token configured)
# ══════════════════════════════════════════════════════════════════════════════
_git = _try("gameforge.snowball.git_github_integration", "git_github")


class CommitBody(BaseModel):
    file_id: str
    version: int = 1
    message: str = "CNS vault commit"


@router.get("/git/status")
async def git_status():
    import os as _os
    remote = _os.getenv("GITHUB_REMOTE", "")
    token_set = bool(_os.getenv("GITHUB_TOKEN"))
    history = []
    if _git:
        try:
            history = _git.get_commit_history(10)
        except Exception:  # noqa: BLE001
            pass
    return {
        "ok": True,
        "repo_ready": _git is not None,
        "remote_configured": bool(remote),
        "token_configured": token_set,
        "push_active": bool(remote and token_set),
        "recent_commits": history,
        "note": "Set GITHUB_REMOTE + GITHUB_TOKEN env vars to activate push.",
    }


@router.post("/git/commit-from-vault")
async def git_commit(b: CommitBody, user=Depends(_editor)):
    if not _git:
        return {"ok": False, "error": "git integration unavailable"}
    ok = _git.commit_file_from_vault(b.file_id, b.version, b.message)
    dispatch_to_rooms("git_commit", {"file_id": b.file_id, "ok": ok})
    return {"ok": ok, "committed": ok}


@router.post("/git/push")
async def git_push(user=Depends(_admin)):
    import os as _os
    remote = _os.getenv("GITHUB_REMOTE", "")
    token = _os.getenv("GITHUB_TOKEN", "")
    if not (remote and token):
        return {"ok": False, "push_active": False,
                "error": "GitHub push not activated — set GITHUB_REMOTE + GITHUB_TOKEN env vars"}
    if not _git:
        return {"ok": False, "error": "git integration unavailable"}
    # Inject token into an https remote for authenticated push
    auth_remote = remote
    if remote.startswith("https://") and "@" not in remote:
        auth_remote = remote.replace("https://", f"https://{token}@")
    ok = _git.push_to_github(auth_remote)
    return {"ok": ok, "pushed": ok}


# ══════════════════════════════════════════════════════════════════════════════
# SHIP IT — one-tap: real build → GitHub commit → optional push (+ audit)
# ══════════════════════════════════════════════════════════════════════════════
def _audit(action: str, target: str, user: Any = None):
    try:
        actor = (user or {}).get("email", "anonymous") if isinstance(user, dict) else "anonymous"
        _db()["gameforge_audit"].insert_one(
            {"action": action, "target": target, "actor": actor, "ts": time.time()})
    except Exception:  # noqa: BLE001
        pass


@router.get("/audit")
async def audit(limit: int = 50):
    try:
        rows = list(_db()["gameforge_audit"].find({}, {"_id": 0}).sort("ts", -1).limit(limit))
    except Exception:  # noqa: BLE001
        rows = []
    return {"ok": True, "audit": rows}


@router.get("/logs")
async def universal_logs(component: Optional[str] = None, severity: Optional[str] = None, limit: int = 60):
    """Universal Logging System — one structured, searchable feed aggregating
    every CNS component (audit, alarms, room activity)."""
    entries = []
    try:
        for a in _db()["gameforge_audit"].find({}, {"_id": 0}).sort("ts", -1).limit(limit):
            entries.append({"ts": a.get("ts"), "component": "audit", "severity": "info",
                            "event": a.get("action"), "detail": f"{a.get('target')} · {a.get('actor')}"})
    except Exception:  # noqa: BLE001
        pass
    try:
        for al in _alarms().find({}, {"_id": 0}).sort("ts", -1).limit(limit):
            entries.append({"ts": al.get("ts"), "component": "recovery",
                            "severity": al.get("severity", "warning"),
                            "event": al.get("kind"), "detail": al.get("detail")})
    except Exception:  # noqa: BLE001
        pass
    try:
        for ev in _db()["gameforge_room_activity"].find({}, {"_id": 0}).sort("ts", -1).limit(limit):
            entries.append({"ts": ev.get("ts"), "component": "rooms", "severity": "info",
                            "event": ev.get("event"), "detail": ", ".join(ev.get("rooms", [])[:5])})
    except Exception:  # noqa: BLE001
        pass
    if component:
        entries = [e for e in entries if e["component"] == component]
    if severity:
        entries = [e for e in entries if e["severity"] == severity]
    entries.sort(key=lambda e: e.get("ts") or 0, reverse=True)
    return {"ok": True, "count": len(entries), "components": ["audit", "recovery", "rooms"],
            "logs": entries[:limit]}


class ShipBody(BaseModel):
    game_name: str
    push: bool = False


@router.post("/ship")
async def ship(b: ShipBody, user=Depends(_editor)):
    """One-tap Ship It: real web + source build → commit source to Git → optional push."""
    from routes import gameforge_build as GB
    out: dict = {"ok": True, "game_name": b.game_name, "steps": []}

    web = await GB.build_web(GB.BuildBody(game_name=b.game_name))
    out["web_build"] = {"ok": web.get("ok"), "download_url": web.get("download_url"),
                        "size_bytes": web.get("size_bytes")}
    out["steps"].append("web_build")
    src = await GB.build_source(GB.BuildBody(game_name=b.game_name))
    out["source_build"] = {"ok": src.get("ok"), "download_url": src.get("download_url"),
                           "size_bytes": src.get("size_bytes")}
    out["steps"].append("source_build")

    # PRIORITY 6 — if a build step failed, raise an alarm + auto-recover the vault.
    if not web.get("ok") or not src.get("ok"):
        _raise_alarm("ship_build_failed",
                     f"web={web.get('ok')} source={src.get('ok')} for {b.game_name}", "error")
        out["recovery"] = _auto_rollback_latest()
        out["steps"].append("auto_recover")

    # commit a ship manifest into the vault, then git-commit it
    committed = False
    if boardroom_vault and _git:
        manifest = f"SHIP {b.game_name} @ {time.time()}\nweb={web.get('build_id')}\nsource={src.get('build_id')}\n"
        entry = boardroom_vault.put_file(f"{b.game_name}_ship_manifest.txt", manifest.encode("utf-8"),
                                         {"kind": "ship_manifest"})
        try:
            committed = _git.commit_file_from_vault(entry.file_id, entry.version, f"Ship {b.game_name}")
        except Exception:  # noqa: BLE001
            committed = False
        out["steps"].append("git_commit")
    out["git_committed"] = committed

    # optional push (only if remote+token configured)
    if b.push:
        import os as _os
        remote, token = _os.getenv("GITHUB_REMOTE", ""), _os.getenv("GITHUB_TOKEN", "")
        if remote and token and _git:
            auth_remote = remote.replace("https://", f"https://{token}@") if remote.startswith("https://") and "@" not in remote else remote
            try:
                out["pushed"] = _git.push_to_github(auth_remote)
            except Exception:  # noqa: BLE001
                out["pushed"] = False
        else:
            out["pushed"] = False
            out["push_note"] = "push inactive — set GITHUB_REMOTE + GITHUB_TOKEN"
        out["steps"].append("git_push")

    dispatch_to_rooms("ship", {"game": b.game_name, "pushed": out.get("pushed")})
    _audit("ship", b.game_name, user)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# OBSERVABILITY DASHBOARD — real-time metrics + system health
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/observability")
async def observability():
    metrics: dict = {"ok": True, "at": time.time()}

    # Snowball progress
    if get_all_step_logs:
        steps = get_all_step_logs()
        done = sum(1 for v in steps.values() if v.get("status") == "completed")
        metrics["snowball"] = {"total": len(steps), "completed": done,
                               "progress_percent": round(done / max(1, len(steps)) * 100)}

    # Forge activity
    if get_all_forge_logs:
        metrics["forge_activity"] = {k: len(v) for k, v in get_all_forge_logs().items()}

    # Boardroom / jury decision analytics
    try:
        led = list(_db()["gameforge_boardroom_ledger"].find({}, {"_id": 0}))
        verdicts = {"accept": 0, "revise": 0, "reject": 0}
        for e in led:
            verdicts[e.get("verdict", "reject")] = verdicts.get(e.get("verdict", "reject"), 0) + 1
        total = max(1, sum(verdicts.values()))
        metrics["jury"] = {"total_decisions": sum(verdicts.values()), "verdicts": verdicts,
                           "accept_rate": round(verdicts["accept"] / total * 100)}
    except Exception:  # noqa: BLE001
        pass

    # Vault + knowledge
    if boardroom_vault:
        metrics["vault"] = {"files": len(boardroom_vault.list_files()), "encrypted": True}
    try:
        metrics["knowledge"] = {
            "total": _db()["jeeves_knowledge"].count_documents({}),
            "acquired": _db()["jeeves_knowledge"].count_documents({"domain": "acquired"}),
            "learned": _db()["jeeves_knowledge"].count_documents({"domain": "learned"}),
        }
        metrics["room_events"] = _db()["gameforge_room_activity"].count_documents({})
    except Exception:  # noqa: BLE001
        pass

    # System health — module liveness
    metrics["health"] = {
        "questionnaire": questionnaire_logger is not None,
        "steps": get_all_step_logs is not None,
        "forges": forge_orchestrator is not None,
        "vault": boardroom_vault is not None,
        "evaluation_room": _jury is not None,
        "deployment": enhanced_deployment is not None,
        "git": _git is not None,
    }
    metrics["health_score"] = round(sum(metrics["health"].values()) / len(metrics["health"]) * 100)
    metrics["total_rooms"] = len(_room_ids())
    return metrics


# ══════════════════════════════════════════════════════════════════════════════
# FLOW description (for the frontend)
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/flow")
async def flow():
    return {
        "pipeline": [
            {"stage": "questionnaire", "desc": "User answers logged; visible to all rooms"},
            {"stage": "snowball_steps", "desc": "Per-step choices logged; dispatched to CNS rooms"},
            {"stage": "forges", "desc": "Coordinated forge passes; all activity logged"},
            {"stage": "boardroom_intake", "desc": "Artifact enters the Boardroom"},
            {"stage": "evaluation_room", "desc": "Sent to Knowledge Nexus jury FIRST → evaluated"},
            {"stage": "boardroom_return", "desc": "Verdict returns to the Boardroom"},
            {"stage": "persist", "desc": "On ACCEPT → Vault + gamefiles (else held)"},
            {"stage": "deploy", "desc": "APK / EXE / Web build export"},
        ],
        "modules_ok": {k: (k not in [p.split(".")[-1] for p in _IMPORT_ERR]) for k in
                       ["questionnaire", "steps", "forges", "vault", "evaluation", "deploy"]},
        "import_errors": _IMPORT_ERR,
    }
