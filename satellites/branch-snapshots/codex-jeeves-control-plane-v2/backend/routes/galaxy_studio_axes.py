"""routes/galaxy_studio_axes.py — spec-aware advanced Choice Axes API.

Serves the genuine, crosswired axis catalog: the questionnaire asks for the
spec (genre/era/dimension + how far the snowball has escalated) and gets back
ONLY the options that pertain to that spec, with advanced options dominating.
Every selection resolves to concrete forge directives (the actual change).
"""
from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import snowball_axes as ax

router = APIRouter(prefix="/api/galaxy-studio/axes", tags=["snowball-axes"])


@router.get("")
def catalog(genre: str = "", era: str = "", dimension: str = "",
            stage_index: int = 99, advanced_only: bool = False):
    spec = {"genre": genre, "era": era, "dimension": dimension}
    # full catalog: spec-filtered axes + advanced toggles + highest-as-minimum defaults
    return ax.full_catalog(spec, stage_index=stage_index)


@router.get("/stats")
def stats():
    return ax.catalog_stats()


class DeriveReq(BaseModel):
    selections: dict = Field(default_factory=dict)  # {axis_key: option_id}
    toggles: list = Field(default_factory=list)      # enabled advanced toggle ids
    spec: dict = Field(default_factory=dict)         # {genre, era, dimension}
    stage_index: int = 99
    build_id: str = ""


@router.post("/derive")
def derive(req: DeriveReq):
    """Resolve selections + advanced toggles → concrete forge directives."""
    res = ax.apply_effects(req.selections, req.spec, req.stage_index)
    tog = ax.apply_toggles(req.toggles, req.spec, req.stage_index)
    res["directives"].update(tog["directives"])
    res["toggles_applied"] = tog["applied"]
    res["toggles_dropped"] = tog["dropped"]
    res["advanced_count"] = res.get("advanced_count", 0) + len(tog["applied"])
    if req.build_id:
        try:
            from core import build_ledger as bl
            bl.log(req.build_id, "axis_selection",
                   {"applied": res["applied"], "toggles": tog["applied"],
                    "directives": res["directives"],
                    "advanced_count": res.get("advanced_count", 0),
                    "dropped": res.get("dropped", []), "spec": req.spec})
        except Exception:
            pass
    return res


class FlavorReq(BaseModel):
    axis_key: str
    option_id: str
    spec: dict = Field(default_factory=dict)


@router.post("/flavor")
def flavor(req: FlavorReq):
    """Optional LLM flavour pass — enriches an option's blurb. Never replaces
    the hand-authored effect/spec data; deterministic fallback if no key."""
    opt = ax.find_option(req.axis_key, req.option_id)
    if not opt:
        return {"error": "unknown_option"}
    base = {"axis": req.axis_key, "option": opt["id"], "label": opt["label"],
            "tier": opt["tier"], "effect": opt["effect"]}
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        base["flavor"] = (f"{opt['label']} ({opt['tier']}): applies "
                          + ", ".join(f"{k}={v}" for k, v in opt["effect"].items()) + ".")
        base["llm"] = False
        return base
    try:
        import asyncio
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        g = (req.spec or {}).get("genre", "game")
        prompt = (f"In 2 punchy sentences, describe how the '{opt['label']}' choice "
                  f"({opt['tier']} tier; directives {opt['effect']}) concretely shapes a "
                  f"{g}. Be specific and production-grounded; no fluff.")

        async def _run():
            chat = LlmChat(api_key=key, session_id=f"axis-{opt['id']}",
                           system_message="You are a senior technical art director.")
            chat.with_model("anthropic", "claude-sonnet-4-5-20250929")
            return await chat.send_message(UserMessage(text=prompt))
        base["flavor"] = (asyncio.run(_run()) or "").strip()
        base["llm"] = True
    except Exception:
        base["flavor"] = f"{opt['label']} ({opt['tier']})."
        base["llm"] = False
    return base
