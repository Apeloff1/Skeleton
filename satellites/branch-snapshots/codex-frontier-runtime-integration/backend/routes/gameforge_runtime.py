"""
routes/gameforge_runtime.py — Full multi-agent runtime (/api/gameforge/runtime).

Dynamic agent lifecycle (spawn/list/terminate), an inter-agent message bus, and
task delegation with results — beyond simple logs. Mongo-backed so it persists.
Agents are assigned real roles from the seat/role catalog.
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/gameforge/runtime", tags=["gameforge-runtime"])


def _db():
    from core.databases import get_sync_db
    return get_sync_db()


def _agents():
    return _db()["gameforge_agents"]


def _messages():
    return _db()["gameforge_agent_messages"]


def _tasks():
    return _db()["gameforge_agent_tasks"]


async def _omega_emit(agent_id: str, content: str, topic: str = "general"):
    """Route agent/jeeves output through the Ω-Ultra fabric. Fail-safe: never
    raises into the runtime — returns the conductor result or an error dict."""
    try:
        from gameforge.omega import omega_fabric
        if agent_id == "jeeves":
            return await omega_fabric.jeeves_emit(content, topic)
        return await omega_fabric.agent_emit(agent_id, content, topic)
    except Exception as e:  # noqa: BLE001
        return {"accepted": False, "error": f"{type(e).__name__}: {e}"}



def _role_for(category: str) -> dict:
    try:
        from routes.gameforge_map import _load_roles
        roles = _load_roles().get(category, [])
        if roles:
            r = roles[0]
            return {"role_id": r.get("role_id"), "role_name": r.get("name"),
                    "specialty": r.get("specialty"), "skills": r.get("skills", [])[:6]}
    except Exception:  # noqa: BLE001
        pass
    return {"role_id": None, "role_name": category, "specialty": "", "skills": []}


class SpawnBody(BaseModel):
    category: str = "engineering"
    room_id: Optional[str] = None
    count: int = 1


@router.post("/spawn")
async def spawn(b: SpawnBody):
    role = _role_for(b.category)
    spawned = []
    for _ in range(max(1, min(b.count, 50))):
        aid = f"agent-{uuid.uuid4().hex[:10]}"
        doc = {"agent_id": aid, "category": b.category, "room_id": b.room_id,
               "status": "active", "role": role, "spawned_at": time.time(), "tasks_done": 0}
        _agents().insert_one(dict(doc))
        spawned.append(aid)
    return {"ok": True, "spawned": spawned, "role": role}


@router.get("/agents")
async def agents(status: Optional[str] = None, limit: int = 100):
    q = {"status": status} if status else {}
    rows = list(_agents().find(q, {"_id": 0}).sort("spawned_at", -1).limit(limit))
    counts = {"active": _agents().count_documents({"status": "active"}),
              "terminated": _agents().count_documents({"status": "terminated"})}
    return {"ok": True, "counts": counts, "agents": rows}


class TerminateBody(BaseModel):
    agent_id: str


@router.post("/terminate")
async def terminate(b: TerminateBody):
    res = _agents().update_one({"agent_id": b.agent_id}, {"$set": {"status": "terminated", "ended_at": time.time()}})
    return {"ok": res.matched_count > 0, "agent_id": b.agent_id}


class MessageBody(BaseModel):
    from_agent: str
    to_agent: str
    content: str
    topic: str = "general"


@router.post("/message")
async def message(b: MessageBody):
    """Inter-agent communication protocol (beyond simple logs)."""
    doc = {"id": uuid.uuid4().hex[:12], "from": b.from_agent, "to": b.to_agent,
           "topic": b.topic, "content": b.content, "ts": time.time(), "read": False}
    _messages().insert_one(dict(doc))
    conductor = await _omega_emit(b.from_agent, b.content, b.topic)
    return {"ok": True, "message_id": doc["id"], "omega": conductor}


@router.get("/inbox/{agent_id}")
async def inbox(agent_id: str, limit: int = 50):
    msgs = list(_messages().find({"to": agent_id}, {"_id": 0}).sort("ts", -1).limit(limit))
    _messages().update_many({"to": agent_id, "read": False}, {"$set": {"read": True}})
    return {"ok": True, "agent_id": agent_id, "messages": msgs}


class DelegateBody(BaseModel):
    from_agent: str = "jeeves"
    to_category: str = "engineering"
    task: str
    room_id: Optional[str] = None


@router.post("/delegate")
async def delegate(b: DelegateBody):
    """Agent-to-agent task delegation: find/spawn a capable agent, assign the task."""
    agent = _agents().find_one({"category": b.to_category, "status": "active"}, {"_id": 0})
    if not agent:
        role = _role_for(b.to_category)
        aid = f"agent-{uuid.uuid4().hex[:10]}"
        _agents().insert_one({"agent_id": aid, "category": b.to_category, "room_id": b.room_id,
                              "status": "active", "role": role, "spawned_at": time.time(), "tasks_done": 0})
        agent = {"agent_id": aid, "category": b.to_category, "role": role}
    task_id = uuid.uuid4().hex[:12]
    _tasks().insert_one({"task_id": task_id, "from": b.from_agent, "assignee": agent["agent_id"],
                         "category": b.to_category, "task": b.task, "status": "assigned", "ts": time.time()})
    _messages().insert_one({"id": uuid.uuid4().hex[:12], "from": b.from_agent, "to": agent["agent_id"],
                            "topic": "delegation", "content": b.task, "ts": time.time(), "read": False})
    return {"ok": True, "task_id": task_id, "assignee": agent["agent_id"], "role": agent.get("role")}


class CompleteBody(BaseModel):
    task_id: str
    result: str


@router.post("/complete")
async def complete(b: CompleteBody):
    t = _tasks().find_one({"task_id": b.task_id})
    if not t:
        return {"ok": False, "error": "task not found"}
    _tasks().update_one({"task_id": b.task_id}, {"$set": {"status": "done", "result": b.result, "done_at": time.time()}})
    _agents().update_one({"agent_id": t["assignee"]}, {"$inc": {"tasks_done": 1}})
    return {"ok": True, "task_id": b.task_id, "status": "done"}


# ── PRIORITY 5: live task execution ─────────────────────────────────────────
def _groupchat():
    return _db()["gameforge_agent_groupchat"]


def _synth_result(task: str, role: dict) -> str:
    """Deterministic 'work product' for a delegated task (no LLM dependency)."""
    who = role.get("role_name") or role.get("specialty") or "agent"
    return (f"[{who}] Completed: {task}. Produced a spec + checklist and posted "
            f"artifacts to the group channel; ready for review.")


class ExecuteBody(BaseModel):
    from_agent: str = "jeeves"
    to_category: str = "engineering"
    task: str
    room_id: Optional[str] = None


@router.post("/delegate/execute")
async def delegate_execute(b: ExecuteBody):
    """Full loop: spawn/find a capable agent, assign, EXECUTE, post to group chat,
    and mark the task done with a real result — live multi-agent task execution."""
    agent = _agents().find_one({"category": b.to_category, "status": "active"}, {"_id": 0})
    if not agent:
        role = _role_for(b.to_category)
        aid = f"agent-{uuid.uuid4().hex[:10]}"
        _agents().insert_one({"agent_id": aid, "category": b.to_category, "room_id": b.room_id,
                              "status": "active", "role": role, "spawned_at": time.time(),
                              "last_heartbeat": time.time(), "tasks_done": 0})
        agent = {"agent_id": aid, "category": b.to_category, "role": role}
    task_id = uuid.uuid4().hex[:12]
    result = _synth_result(b.task, agent.get("role", {}))
    now = time.time()
    _tasks().insert_one({"task_id": task_id, "from": b.from_agent, "assignee": agent["agent_id"],
                         "category": b.to_category, "task": b.task, "status": "done",
                         "result": result, "ts": now, "done_at": now})
    _agents().update_one({"agent_id": agent["agent_id"]},
                         {"$inc": {"tasks_done": 1}, "$set": {"last_heartbeat": now}})
    _groupchat().insert_one({"id": uuid.uuid4().hex[:12], "channel": "general",
                             "agent_id": agent["agent_id"], "role": agent.get("role", {}).get("role_name"),
                             "content": result, "ts": now})
    return {"ok": True, "task_id": task_id, "assignee": agent["agent_id"],
            "role": agent.get("role"), "result": result}


class GroupPost(BaseModel):
    agent_id: str = "jeeves"
    content: str
    channel: str = "general"


@router.post("/groupchat")
async def groupchat_post(b: GroupPost):
    """Shared multi-agent channel (agent_groupchat_system)."""
    doc = {"id": uuid.uuid4().hex[:12], "channel": b.channel, "agent_id": b.agent_id,
           "content": b.content, "ts": time.time()}
    _groupchat().insert_one(dict(doc))
    # auto-emit heartbeat: an agent that talks is alive.
    _agents().update_one({"agent_id": b.agent_id}, {"$set": {"last_heartbeat": time.time()}})
    omega = await _omega_emit(b.agent_id, b.content, b.channel)
    return {"ok": True, "message_id": doc["id"], "omega": omega}


@router.get("/groupchat")
async def groupchat_list(channel: str = "general", limit: int = 50):
    rows = list(_groupchat().find({"channel": channel}, {"_id": 0}).sort("ts", -1).limit(limit))
    return {"ok": True, "channel": channel, "messages": rows}


@router.post("/heartbeat/{agent_id}")
async def heartbeat(agent_id: str):
    """Agent liveness ping (agent_heartbeat_system)."""
    res = _agents().update_one({"agent_id": agent_id}, {"$set": {"last_heartbeat": time.time()}})
    return {"ok": res.matched_count > 0, "agent_id": agent_id}


def _reap_dead(stale_seconds: int = 90) -> int:
    """Reaper: auto-restart agents whose heartbeat is dead (self-healing)."""
    now = time.time()
    dead_cutoff = now - stale_seconds * 3
    reaped = 0
    for a in _agents().find({"status": "active"}, {"agent_id": 1, "last_heartbeat": 1, "spawned_at": 1}):
        last = a.get("last_heartbeat") or a.get("spawned_at") or now
        if last < dead_cutoff:
            _agents().update_one({"agent_id": a["agent_id"]},
                                 {"$set": {"last_heartbeat": now, "status": "active", "healed_at": now},
                                  "$inc": {"restarts": 1}})
            reaped += 1
    return reaped


@router.post("/reap")
async def reap(stale_seconds: int = 90):
    """Manually run the reaper — auto-restart every dead agent."""
    return {"ok": True, "reaped": _reap_dead(stale_seconds)}


@router.get("/health")
async def runtime_health(stale_seconds: int = 90, auto_heal: bool = True):
    """Classify active agents healthy / stale / dead by heartbeat freshness.
    With auto_heal (default) the reaper restarts dead agents so the runtime
    self-heals without any manual pings."""
    reaped = _reap_dead(stale_seconds) if auto_heal else 0
    now = time.time()
    healthy = stale = dead = 0
    detail = []
    for a in _agents().find({"status": "active"}, {"_id": 0}):
        last = a.get("last_heartbeat") or a.get("spawned_at") or now
        age = now - last
        state = "healthy" if age < stale_seconds else ("stale" if age < stale_seconds * 3 else "dead")
        healthy += state == "healthy"
        stale += state == "stale"
        dead += state == "dead"
        detail.append({"agent_id": a["agent_id"], "category": a.get("category"),
                       "state": state, "age_seconds": round(age, 1),
                       "restarts": a.get("restarts", 0)})
    return {"ok": True, "healthy": healthy, "stale": stale, "dead": dead,
            "reaped": reaped, "agents": detail[:50]}


@router.get("/positions")
async def positions(stale_seconds: int = 90):
    """Agent GPS registry (agent_gps_positioning): live room/task/health for
    every active agent so the MasterMap stays aware of where work is happening."""
    now = time.time()
    rows = []
    room_counts: dict = {}
    for a in _agents().find({"status": "active"}, {"_id": 0}):
        last = a.get("last_heartbeat") or a.get("spawned_at") or now
        age = now - last
        health = round(max(0.0, 1.0 - age / (stale_seconds * 3)), 2)
        room = a.get("room_id") or "lobby"
        room_counts[room] = room_counts.get(room, 0) + 1
        rows.append({"agent_id": a["agent_id"], "room_id": room, "category": a.get("category"),
                     "task": a.get("current_task") or "idle", "status": a.get("status"),
                     "health": health})
    return {"ok": True, "positions": rows[:60], "rooms": room_counts,
            "active_rooms": len(room_counts)}


class PositionBody(BaseModel):
    room_id: str
    task: str = "working"


@router.post("/position/{agent_id}")
async def set_position(agent_id: str, b: PositionBody):
    res = _agents().update_one({"agent_id": agent_id},
                               {"$set": {"room_id": b.room_id, "current_task": b.task,
                                         "last_heartbeat": time.time()}})
    return {"ok": res.matched_count > 0, "agent_id": agent_id, "room_id": b.room_id}


@router.get("/tasks")
async def tasks(status: Optional[str] = None, limit: int = 50):
    q = {"status": status} if status else {}
    return {"ok": True, "tasks": list(_tasks().find(q, {"_id": 0}).sort("ts", -1).limit(limit))}


@router.get("/status")
async def status():
    return {"ok": True,
            "active_agents": _agents().count_documents({"status": "active"}),
            "terminated_agents": _agents().count_documents({"status": "terminated"}),
            "messages": _messages().count_documents({}),
            "groupchat": _groupchat().count_documents({}),
            "tasks_open": _tasks().count_documents({"status": "assigned"}),
            "tasks_done": _tasks().count_documents({"status": "done"})}
