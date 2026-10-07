"""
routes/gameforge_map.py — GameForge CNS Master Map surface (/api/gameforge/map).

Surfaces the previously-dormant "in-room" systems so they are visible + usable:
  • Jeeves MasterMap (agent map / god-mode capabilities)
  • Rooms + structure map + per-room contents (bookshelf, rolodex, toolbox, skills)
  • Master Skill Bank + per-room skill trees + Jeeves permanent skill bank
  • Per-room Toolbox (repair coordinator) + Mishima Zaibatsu toolbox tools
  • Seat & Role selector system (role→seat assignment, 100 seats/category)
  • Agent Fast-Travel (optimized midpoint pathing)
  • RAG mesh (Hybrid RAG / Omni RAG) + AAAHRAG (Knowledge Nexus librarian)

Everything is defensive: a missing module/file degrades to a status note, never
crashes boot.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/gameforge/map", tags=["gameforge-map"])

_GF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gameforge")

# ── caches ────────────────────────────────────────────────────────────────────
_seat_cache: dict[str, Any] = {}


def _load_json(rel: str) -> Optional[Any]:
    p = os.path.join(_GF, rel)
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _latest_mastermap() -> dict:
    """The most-advanced mastermap = the file with the longest name (most 'ultimate')."""
    files = glob.glob(os.path.join(_GF, "jeeves", "jeeves_mastermap_*.json"))
    if not files:
        return {}
    files.sort(key=lambda p: len(os.path.basename(p)))
    try:
        with open(files[-1], "r", encoding="utf-8") as f:
            data = json.load(f)
        key = next(iter(data))
        payload = data[key]
        payload["_source"] = os.path.basename(files[-1])
        payload["_versions"] = len(files)
        return payload
    except Exception:  # noqa: BLE001
        return {}


def _load_roles() -> dict[str, list]:
    """Load all role sets from every roles subdir (category -> roles)."""
    if "roles" in _seat_cache:
        return _seat_cache["roles"]
    roles: dict[str, list] = {}
    for jp in glob.glob(os.path.join(_GF, "roles", "**", "*.json"), recursive=True):
        if "seat_assignment_system" in jp:
            continue
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, dict):
            continue
        cat = data.get("room_category") or data.get("category") or "unknown"
        rl = data.get("roles")
        if isinstance(rl, list) and rl:
            roles.setdefault(cat, []).extend(rl)
    _seat_cache["roles"] = roles
    return roles


def _import(path: str, attr: str = None):
    try:
        m = __import__(path, fromlist=[attr or "x"])
        return getattr(m, attr) if attr else m
    except Exception:  # noqa: BLE001
        return None


# ══════════════════════════════════════════════════════════════════════════════
@router.get("/overview")
async def overview():
    roles = _load_roles()
    rooms = _import("gameforge.rooms.full_room_registry", "all_rooms")
    room_count = len(rooms()) if rooms else 0
    skill_bank = _load_json("datasets/skill_dataset/master_skill_bank.json") or {}
    cats = skill_bank.get("skill_categories", {})
    mm = _latest_mastermap()
    systems = await systems_status()
    return {
        "ok": True,
        "mastermap": {"source": mm.get("_source"), "versions": mm.get("_versions", 0),
                      "new_components": mm.get("new_components", [])},
        "rooms": room_count,
        "role_categories": len(roles),
        "total_roles": sum(len(v) for v in roles.values()),
        "seats_per_category": 100,
        "total_seats": len(roles) * 100,
        "skill_categories": len(cats),
        "total_skills": sum(len(v) for v in cats.values()),
        "systems_live": systems["live"], "systems_total": systems["total"],
    }


@router.get("/mastermap")
async def mastermap():
    mm = _latest_mastermap()
    if not mm:
        return {"ok": False, "error": "no mastermap found"}
    return {"ok": True, "mastermap": mm}


@router.get("/rooms")
async def rooms():
    structure = _import("gameforge.rooms.structure_map", "structure_map")
    by_div = _import("gameforge.rooms.full_room_registry", "rooms_by_division")
    all_rooms = _import("gameforge.rooms.full_room_registry", "all_rooms")
    out: dict = {"ok": True}
    if all_rooms:
        rm = all_rooms()
        out["total"] = len(rm)
        out["sample"] = list(rm.keys())[:40]
    if by_div:
        try:
            out["divisions"] = {k: len(v) for k, v in by_div().items()}
        except Exception:  # noqa: BLE001
            pass
    if structure:
        try:
            out["structure"] = structure()
        except Exception:  # noqa: BLE001
            pass
    return out


@router.get("/room/{room_id}")
async def room(room_id: str):
    all_rooms = _import("gameforge.rooms.full_room_registry", "all_rooms")
    rm = all_rooms() if all_rooms else {}
    info = rm.get(room_id)
    if info is None:
        return {"ok": False, "error": "room not found", "sample": list(rm.keys())[:20]}
    return {
        "ok": True,
        "room_id": room_id,
        "registry": info,
        "toolbox": (_load_json("toolbox/per_room_toolbox_assignment.json") or {}).get("per_room_toolbox_assignment", {}),
        "skill_tree_template": (_load_json("skills/skill_tree_per_room.json") or {}).get("room_skill_tree", {}),
        "has_bookshelf": _import("gameforge.rooms.room_bookshelf", "RoomBookshelf") is not None,
        "has_rolodex": _import("gameforge.rooms.team_rolodex", "TeamRolodex") is not None,
    }


@router.get("/skills")
async def skills():
    bank = _load_json("datasets/skill_dataset/master_skill_bank.json") or {}
    return {
        "ok": True,
        "master_skill_bank": bank,
        "jeeves_permanent": _load_json("skills/skill_bank_jeeves_permanent.json"),
        "per_room_template": _load_json("skills/skill_bank_per_room.json"),
        "skill_tree_template": _load_json("skills/skill_tree_per_room.json"),
        "github_unlock": _load_json("skills/skill_unlock_via_github.json"),
    }


@router.get("/toolbox")
async def toolbox():
    checkout = _import("gameforge.agent_tools.room_toolbox_checkout_manager", "RoomToolboxCheckoutManager")
    return {
        "ok": True,
        "per_room_assignment": (_load_json("toolbox/per_room_toolbox_assignment.json") or {}).get("per_room_toolbox_assignment", {}),
        "mishima_toolbox": (_load_json("navigation/mishima_zaibatsu_toolbox.json") or {}).get("mishima_zaibatsu_toolbox", {}),
        "delegation_status": _load_json("status/zaibatsu_delegation_toolbox_blockchain_active.json"),
        "checkout_manager_available": checkout is not None,
    }


# ── SEAT & ROLE SELECTOR ──────────────────────────────────────────────────────
@router.get("/seats")
async def seats():
    roles = _load_roles()
    per_cat = {cat: {"roles_available": len(rl), "seats": 100} for cat, rl in roles.items()}
    return {
        "ok": True,
        "total_categories": len(roles),
        "seats_per_category": 100,
        "total_seats": len(roles) * 100,
        "categories": per_cat,
    }


@router.get("/seats/roles")
async def seat_roles(category: Optional[str] = None):
    roles = _load_roles()
    if category:
        rl = roles.get(category, [])
        return {"ok": True, "category": category,
                "roles": [{"role_id": r.get("role_id"), "name": r.get("name"),
                           "specialty": r.get("specialty"), "skills": r.get("skills", [])}
                          for r in rl[:100]]}
    return {"ok": True, "categories": sorted(roles.keys())}


class AssignBody(BaseModel):
    category: str
    seat_number: int = 1
    agent_id: str = "agent"


@router.post("/seats/assign")
async def seat_assign(b: AssignBody):
    roles = _load_roles()
    rl = roles.get(b.category)
    if not rl:
        return {"ok": False, "error": f"unknown category '{b.category}'", "categories": sorted(roles.keys())}
    role = rl[(b.seat_number - 1) % len(rl)]
    return {
        "ok": True, "assigned": True,
        "seat": {"seat_id": b.seat_number, "category": b.category, "agent_id": b.agent_id,
                 "role_id": role.get("role_id"), "role_name": role.get("name"),
                 "specialty": role.get("specialty"), "skills": role.get("skills", []),
                 "prompt_template": role.get("prompt_template", "")[:400]},
    }


# ── FAST TRAVEL ───────────────────────────────────────────────────────────────
class TravelBody(BaseModel):
    agent_id: str = "agent"
    start: str
    goal: str
    context: dict = {}


@router.post("/navigation/fast-travel")
async def fast_travel(b: TravelBody):
    FT = _import("gameforge.navigation.fast_travel_optimized_pathing", "FastTravelOptimizedPathing")
    if not FT:
        return {"ok": False, "error": "fast-travel engine unavailable"}
    ft = FT(None)
    res = ft.fast_travel_to_midpoint(b.agent_id, b.start, b.goal, b.context)
    return {"ok": True, "result": res}


@router.get("/navigation")
async def navigation():
    return {
        "ok": True,
        "fast_travel": _import("gameforge.navigation.fast_travel_optimized_pathing", "FastTravelOptimizedPathing") is not None,
        "nav_map": _import("gameforge.navigation.agentic_nav_map") is not None,
        "sota_nav_map": _import("gameforge.navigation.true_sota_exquisite_nav_map") is not None,
        "fog_of_knowledge": _import("gameforge.navigation.fog_of_knowledge_system") is not None,
        "synergy": (_load_json("synergy/nav_map_delegation_toolbox_blockchain_synergy.json") or {}),
    }


# ── RAG mesh + AAAHRAG ────────────────────────────────────────────────────────
@router.get("/rag")
async def rag():
    return {
        "ok": True,
        "hybrid_rag_engine": _import("gameforge.exocortex.agentic.hybrid_rag_engine") is not None,
        "omni_advanced_rag": _import("gameforge.rag.omni_advanced_rag_system") is not None,
        "room_hybrid_rag": _import("gameforge.rooms.room_hybrid_rag") is not None,
        "rag_nav_synergy": _import("gameforge.synergy.rag_navigation_synergy_engine") is not None,
        "aaahrag_librarian": _import("knowledge_nexus.agents.librarian_agent_implementation") is not None,
    }


# ── ALL SYSTEMS introspection (live vs dormant) ───────────────────────────────
_SYSTEMS = {
    "mastermap": ("file", "jeeves/jeeves_mastermap_cowabunga_expansion.json"),
    "room_registry": ("mod", "gameforge.rooms.full_room_registry"),
    "structure_map": ("mod", "gameforge.rooms.structure_map"),
    "seat_manager": ("mod", "gameforge.rooms.room_seat_manager"),
    "role_seat_engine": ("mod", "gameforge.roles.seat_assignment_system.role_seat_assignment_engine"),
    "seat_cycling": ("mod", "gameforge.rooms.agent_seat_cycling_engine"),
    "master_skill_bank": ("file", "datasets/skill_dataset/master_skill_bank.json"),
    "toolbox_assignment": ("file", "toolbox/per_room_toolbox_assignment.json"),
    "toolbox_checkout": ("mod", "gameforge.agent_tools.room_toolbox_checkout_manager"),
    "mishima_toolbox": ("file", "navigation/mishima_zaibatsu_toolbox.json"),
    "fast_travel": ("mod", "gameforge.navigation.fast_travel_optimized_pathing"),
    "nav_map": ("mod", "gameforge.navigation.agentic_nav_map"),
    "hybrid_rag": ("mod", "gameforge.exocortex.agentic.hybrid_rag_engine"),
    "omni_rag": ("mod", "gameforge.rag.omni_advanced_rag_system"),
    "aaahrag_librarian": ("mod", "knowledge_nexus.agents.librarian_agent_implementation"),
    "room_bookshelf": ("mod", "gameforge.rooms.room_bookshelf"),
    "team_rolodex": ("mod", "gameforge.rooms.team_rolodex"),
    "coder_pool": ("mod", "gameforge.rooms.coder_pool"),
    "style_applicator": ("mod", "gameforge.agents.style_application"),
}


@router.get("/systems")
async def systems_status():
    report: dict[str, str] = {}
    for name, (kind, target) in _SYSTEMS.items():
        if kind == "mod":
            report[name] = "live" if _import(target) else "dormant"
        else:
            report[name] = "live" if os.path.exists(os.path.join(_GF, target)) else "dormant"
    live = sum(1 for v in report.values() if v == "live")
    return {"ok": True, "live": live, "total": len(report), "systems": report}
