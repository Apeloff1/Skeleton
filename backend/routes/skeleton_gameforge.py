"""HTTP surface for the Skeleton GameForge pipeline (eras, intake, run)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

router = APIRouter(prefix="/api/skeleton", tags=["skeleton-gameforge"])


class RunRequest(BaseModel):
    vision: str = ""
    era: Optional[str] = None
    archetype: str = "extraction"
    target: str = "godot"
    project_root: Optional[str] = None
    overwrite: bool = False
    include_files: bool = False
    answers: Dict[str, str] = Field(default_factory=dict)
    blend: Optional[list] = None
    t: float = 0.5


@router.get("/eras")
def eras() -> Dict[str, Any]:
    from skeleton.forge.eras import compile_era, list_eras
    out = []
    for era in list_eras():
        pack = compile_era(era)
        out.append({
            "id": era,
            "primary_dps": pack["primary_dps"],
            "speed": pack["player"]["speed"],
            "ttk": pack["ttk"],
            "philosophy": pack["meta"]["philosophy"],
        })
    return {"eras": out, "count": len(out)}


@router.post("/run")
def run(req: RunRequest) -> Dict[str, Any]:
    from skeleton.context.pipeline import GameForgeRun
    try:
        payload = GameForgeRun().execute(
            req.vision,
            era=req.era,
            archetype=req.archetype,
            target=req.target,
            project_root=req.project_root,
            overwrite=req.overwrite,
            answers=req.answers or None,
            blend=(tuple(req.blend) + (req.t,)) if req.blend and len(req.blend) >= 2 else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    files = payload.get("files") or {}
    payload = dict(payload)
    payload["file_names"] = sorted(files)
    if not req.include_files:
        payload.pop("files", None)
    return payload


@router.get("/beats")
def beats() -> Dict[str, Any]:
    from skeleton.context.questionnaire import BEATS
    return {
        "beats": [
            {"id": b["id"], "prompt": b["prompt"], "options": list(b["options"])}
            for b in BEATS
        ]
    }


class PlanRequest(BaseModel):
    vision: str = ""
    era: Optional[str] = None
    blend: Optional[list] = None
    t: float = 0.5


@router.post("/plan")
def plan(req: PlanRequest) -> Dict[str, Any]:
    from skeleton.context.dodeca import Dodecahedron
    from skeleton.context.oracle import Magic8Ball
    from skeleton.context.tensor import ContextTensor, detect_era
    from skeleton.forge.eras import blend_eras, compile_era
    from skeleton.jeeves.builder import BuilderBrain
    try:
        if req.blend and len(req.blend) >= 2:
            t = float(req.t)
            pack = blend_eras(str(req.blend[0]), str(req.blend[1]), t)
            tensor = ContextTensor.from_era(str(req.blend[0])).lerp(
                ContextTensor.from_era(str(req.blend[1])), t
            )
            object.__setattr__(tensor, "era", pack["era"])
        elif req.era:
            pack = compile_era(req.era)
            tensor = ContextTensor.from_era(req.era)
        else:
            era, _ = detect_era(req.vision or "")
            pack = compile_era(era)
            tensor = ContextTensor.from_era(era)
        reading = Magic8Ball(Dodecahedron.from_tensor(tensor)).roll(tensor)
        built = BuilderBrain().plan(pack, tensor=tensor, reading=reading)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return built.to_dict()


@router.post("/cockpit")
def cockpit(body: Dict[str, str]) -> Dict[str, Any]:
    from skeleton.context.cockpit import Cockpit, CockpitError
    cmd = (body or {}).get("command") or (body or {}).get("cmd") or ""
    try:
        return Cockpit().apply(cmd)
    except CockpitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
