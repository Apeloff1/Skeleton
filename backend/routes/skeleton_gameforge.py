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
    generation: Optional[str] = None


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


@router.get("/generations")
def generations() -> Dict[str, Any]:
    from skeleton.forge.hardware import catalog
    rows = catalog()
    return {"generations": rows, "count": len(rows)}


@router.post("/run")
def run(req: RunRequest) -> Dict[str, Any]:
    from skeleton.context.pipeline import GameForgeRun
    try:
        payload = GameForgeRun.live().execute(
            req.vision,
            era=req.era,
            archetype=req.archetype,
            target=req.target,
            project_root=req.project_root,
            overwrite=req.overwrite,
            answers=req.answers or None,
            blend=(tuple(req.blend) + (req.t,)) if req.blend and len(req.blend) >= 2 else None,
            generation=req.generation,
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
        from skeleton.cortex.live import live_cortex, persist
        built = BuilderBrain().plan(pack, tensor=tensor, reading=reading, cortex=live_cortex())
        persist()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return built.to_dict()


@router.post("/walk")
def walk(req: PlanRequest) -> Dict[str, Any]:
    from skeleton.context.dodeca import Dodecahedron
    from skeleton.context.oracle import Magic8Ball
    from skeleton.context.tensor import ContextTensor, detect_era
    from skeleton.forge.eras import blend_eras, compile_era
    from skeleton.forge.walk import walk_from_pack
    from skeleton.jeeves.builder import BuilderBrain
    try:
        if req.blend and len(req.blend) >= 2:
            pack = blend_eras(str(req.blend[0]), str(req.blend[1]), float(req.t))
            tensor = ContextTensor.from_era(str(req.blend[0])).lerp(
                ContextTensor.from_era(str(req.blend[1])), float(req.t)
            )
        elif req.era:
            pack = compile_era(req.era)
            tensor = ContextTensor.from_era(req.era)
        else:
            era, _ = detect_era(req.vision or "")
            pack = compile_era(era)
            tensor = ContextTensor.from_era(era)
        reading = Magic8Ball(Dodecahedron.from_tensor(tensor)).roll(tensor)
        from skeleton.cortex.live import live_cortex, persist
        built = BuilderBrain().plan(pack, tensor=tensor, reading=reading, cortex=live_cortex())
        wr = walk_from_pack(pack, plan=built.to_dict())
        persist()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"walk": wr.to_dict(), "plan": built.to_dict()}


@router.post("/cockpit")
def cockpit(body: Dict[str, str]) -> Dict[str, Any]:
    from skeleton.context.cockpit import Cockpit, CockpitError
    cmd = (body or {}).get("command") or (body or {}).get("cmd") or ""
    try:
        return Cockpit().apply(cmd)
    except CockpitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ThinkRequest(BaseModel):
    stimulus: str = ""
    era: Optional[str] = None
    bind: Optional[list] = None  # [slot, echo|local]
    acquire: Optional[str] = None
    surpass: Optional[str] = None


class TrainRequest(BaseModel):
    epochs: int = 1


class TractPayload(BaseModel):
    slot: str = "left"
    backend: str = "own"
    scale: str = "neo"
    capabilities: list = Field(default_factory=list)
    exemplars: list = Field(default_factory=list)


@router.post("/think")
def think(req: ThinkRequest) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    from skeleton.context.tensor import ContextTensor
    neo = live_cortex()
    if req.bind and len(req.bind) >= 2:
        slot, how = str(req.bind[0]), str(req.bind[1]).lower()
        if how == "echo":
            neo.bind_echo(slot)
        else:
            neo.bind_local(slot)
    ctx = {}
    if req.era:
        t = ContextTensor.from_era(req.era)
        ctx = {"era": t.era, "tensor": t.as_dict()}
    trace = neo.think(req.stimulus, ctx)
    acquired = neo.acquire(req.acquire) if req.acquire else None
    surpassed = None
    if req.surpass:
        surpassed = neo.surpass(req.surpass)
        trace = neo.think(req.stimulus, ctx)
    persist()
    return {
        "trace": trace.to_dict(),
        "status": neo.status(),
        "acquired": acquired,
        "surpassed": surpassed,
    }


@router.get("/cortex")
def cortex_status() -> Dict[str, Any]:
    from skeleton.cortex import SLOTS, SCALES, TEMPLATES, default_curriculum
    from skeleton.cortex.live import live_cortex
    return {
        "slots": list(SLOTS),
        "scales": list(SCALES),
        "pfc_templates": list(TEMPLATES),
        "live": live_cortex().status(),
        "curriculum_items": len(default_curriculum()),
    }


@router.post("/train")
def train(req: TrainRequest) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    out = live_cortex().train(epochs=max(1, int(req.epochs)))
    saved = persist()
    out["saved"] = saved
    return out


@router.post("/cortex/import")
def cortex_import(body: TractPayload) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    neo = live_cortex()
    payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    out = neo.import_tract(payload)
    persist()
    return out


@router.get("/cortex/export")
def cortex_export(slot: str = "left") -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex
    return live_cortex().export_tract(slot)


@router.get("/cortex/merkle")
def cortex_merkle() -> Dict[str, Any]:
    from skeleton.cortex.hive import merkle_card
    from skeleton.cortex.live import live_cortex
    return merkle_card(live_cortex())


@router.get("/cortex/metrics")
def cortex_metrics() -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex
    from skeleton.cortex.metrics import evaluate
    return evaluate(live_cortex())


@router.post("/cortex/sync")
def cortex_sync(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.hive import pull
    from skeleton.cortex.live import live_cortex, persist
    out = pull(live_cortex(), body or {})
    persist()
    return out


@router.get("/cortex/bundle")
def cortex_bundle() -> Dict[str, Any]:
    from skeleton.cortex.hive import bundle
    from skeleton.cortex.live import live_cortex
    return bundle(live_cortex())


@router.get("/cortex/zaibatsu")
def cortex_zaibatsu() -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex
    from skeleton.cortex.zaibatsu import tournament
    return tournament(live_cortex())


@router.post("/cortex/speak")
def cortex_speak(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    stim = (body or {}).get("stimulus") or (body or {}).get("prefix") or "plan tensor ttk"
    n = int((body or {}).get("n") or 12)
    mouth = str((body or {}).get("mouth") or "gelu")
    text = live_cortex().speak(stim, n=n, seed=int((body or {}).get("seed") or 0), mouth=mouth)
    persist()
    return {"text": text, "n": n, "mouth": mouth}


@router.post("/cortex/beam")
def cortex_beam(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    stim = (body or {}).get("stimulus") or (body or {}).get("prefix") or "plan tensor ttk"
    out = live_cortex().beam(
        stim,
        n=int((body or {}).get("n") or 8),
        width=int((body or {}).get("width") or 4),
        mouth=str((body or {}).get("mouth") or "gelu"),
    )
    persist()
    return out


@router.post("/cortex/bind-hf")
def cortex_bind_hf(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    slot = str((body or {}).get("slot") or "left")
    model = str((body or {}).get("model") or "sshleifer/tiny-gpt2")
    out = live_cortex().bind_hf(slot, model)
    persist()
    return out


@router.post("/cortex/bind-kimi")
def cortex_bind_kimi(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    slot = str((body or {}).get("slot") or "right")
    model = str((body or {}).get("model") or "kimi-k2-0711-preview")
    out = live_cortex().bind_kimi(slot, model)
    persist()
    return out


@router.post("/cortex/distill")
def cortex_distill(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    slot = str((body or {}).get("slot") or "left")
    stim = str((body or {}).get("stimulus") or (body or {}).get("prefix") or "plan tensor ttk")
    out = live_cortex().distill(slot, stim)
    persist()
    return out


@router.post("/cortex/lora")
def cortex_lora(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    neo = live_cortex()
    out = neo.merge_lora() if (body or {}).get("merge") else neo.attach_lora(rank=int((body or {}).get("rank") or 2))
    persist()
    return out


@router.post("/cortex/gossip")
def cortex_gossip(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex import JeevesCortex
    from skeleton.cortex.live import live_cortex, persist
    neo = live_cortex()
    alpha = float((body or {}).get("alpha") or 0.25)
    if (body or {}).get("mouths"):
        out = neo.gossip_mouths(alpha=alpha, direction=str((body or {}).get("direction") or "rms-into-gelu"))
    else:
        out = neo.gossip_with(JeevesCortex(), alpha=alpha)
    persist()
    return out


@router.post("/cortex/speculate")
def cortex_speculate(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex
    from skeleton.cortex.speculate import speculate
    stim = (body or {}).get("stimulus") or (body or {}).get("prefix") or "plan tensor ttk"
    n = int((body or {}).get("n") or 8)
    k = int((body or {}).get("k") or 4)
    return speculate(live_cortex(), stim, n=n, k=k)


@router.post("/cortex/export")
def cortex_export_post(body: Dict[str, str]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex
    slot = (body or {}).get("slot") or "left"
    return live_cortex().export_tract(slot)


@router.post("/recall")
def recall(body: Dict[str, str]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex
    stim = (body or {}).get("stimulus") or (body or {}).get("text") or ""
    return live_cortex().recall(stim)
