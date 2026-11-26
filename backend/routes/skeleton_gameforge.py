"""HTTP surface for the Skeleton GameForge pipeline (eras, intake, run)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Literal, Optional
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictBool, field_validator

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

router = APIRouter(prefix="/api/skeleton", tags=["skeleton-gameforge"])

_EXPORT_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
_EXPORT_DEVICES = {"con", "nul", "aux", "prn"} | {
    f"{prefix}{index}" for prefix in ("com", "lpt") for index in range(1, 10)
}


def _safe_export_path(name: str) -> bool:
    """Match the limited portable ZIP path contract before returning files."""
    if not isinstance(name, str) or not name or len(name) > 240:
        return False
    if "\\" in name or ":" in name or name.startswith("/"):
        return False
    parts = name.split("/")
    return all(
        part and part not in {".", ".."} and not part.startswith(".")
        and part.rstrip(" .") == part
        and _EXPORT_SEGMENT.fullmatch(part) is not None
        and part.split(".")[0].casefold() not in _EXPORT_DEVICES
        for part in parts
    )


class RunRequest(BaseModel):
    vision: str = Field(default="", max_length=4000)
    era: Optional[str] = Field(default=None, max_length=80)
    archetype: str = Field(default="extraction", max_length=80)
    target: str = Field(default="godot", max_length=16)
    project_root: Optional[str] = Field(default=None, max_length=1024)
    overwrite: bool = False
    include_files: bool = False
    answers: Dict[str, str] = Field(default_factory=dict, max_length=64)
    # Sparse, explicit design-instrument edits. Raw values are validated by GameForge.
    operator_axes: Optional[Dict[str, Any]] = Field(default=None, max_length=16)
    galaxy_profile: Optional[Dict[str, Any]] = Field(default=None, max_length=2)
    blend: Optional[list] = Field(default=None, max_length=3)
    t: float = Field(default=0.5, ge=0.0, le=1.0, allow_inf_nan=False)
    generation: Optional[str] = Field(default=None, max_length=80)
    playable_content: StrictBool = False
    playable_archetype: Optional[str] = Field(default=None, max_length=64)
    playable_main_scene: StrictBool = False
    playtest: Optional[Literal["off", "auto", "require"]] = None
    quest_content: bool = False
    quest_length: int = Field(default=3, ge=1, le=8)

    @field_validator("galaxy_profile")
    @classmethod
    def _validate_galaxy_profile(cls, profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        from skeleton.context.galaxy_profile import normalise_galaxy_profile
        return normalise_galaxy_profile(profile)

    @field_validator("answers")
    @classmethod
    def _validate_brief_answers(cls, answers: Dict[str, str]) -> Dict[str, str]:
        # The guided brief is a bounded list of facet/beat votes, not an
        # arbitrary unbounded prompt injection or bulk JSON transport.
        if any(
            re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", key) is None
            or len(value) > 80
            for key, value in answers.items()
        ):
            raise ValueError("GameForge answer facets must be bounded design votes")
        return answers

    @field_validator("operator_axes")
    @classmethod
    def _validate_axis_payload(cls, axes: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if axes is None:
            return None
        if any(
            re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", key) is None
            for key in axes
        ):
            raise ValueError("GameForge operator axis IDs must be bounded")
        return axes


class DurableRunRequest(RunRequest):
    model_config = ConfigDict(extra="forbid")
    target: Literal["godot"] = "godot"
    include_files: StrictBool = True
    overwrite: StrictBool = False
    playtest: Literal["off"] = "off"
    quest_content: StrictBool = False
    quest_length: int = Field(default=3, ge=1, le=8, strict=True)

    @field_validator("operator_axes")
    @classmethod
    def bounded_creator_axes(cls, value):
        if value is None:
            return None
        from skeleton.context.pipeline import normalise_operator_axes
        return normalise_operator_axes(value)

    @model_validator(mode="after")
    def source_only_request(self):
        if self.project_root is not None or self.overwrite or not self.include_files:
            raise ValueError("Durable builds require in-memory source export without host paths")
        if self.blend is not None and (
            len(self.blend) != 2 or any(not isinstance(item, str) or not 1 <= len(item) <= 80 for item in self.blend)
        ):
            raise ValueError("Blend requires exactly two bounded era IDs")
        if not self.playable_content and (self.playable_archetype is not None or self.playable_main_scene):
            raise ValueError("Playable source selection requires explicit opt-in")
        if self.playable_archetype is not None:
            from skeleton.forge.archetype_content import content_archetypes
            if self.playable_archetype not in content_archetypes():
                raise ValueError("Choose a supported native playable archetype")
        if self.playable_main_scene and self.quest_content:
            raise ValueError("Playable startup and quest startup cannot both own the main scene")
        return self


class ForgeProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=512)

    @field_validator("name", "idempotency_key")
    @classmethod
    def normalized_identity(cls, value):
        if value != value.strip() or not value.strip():
            raise ValueError("Project name and request ID must be normalized")
        return value


class ForgeBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)
    run: DurableRunRequest
    timeout_seconds: int = Field(default=60, ge=5, le=120, strict=True)

    @field_validator("idempotency_key")
    @classmethod
    def normalized_identity(cls, value):
        if value != value.strip():
            raise ValueError("Build request ID must be normalized")
        return value


register_forge_source_handler()


def _forge_private_response(response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"


@router.get("/projects", dependencies=[Depends(_forge_private_response)])
async def forge_projects(user: User):
    return {"projects": await _call(list_forge_projects(_scope(user)))}


@router.post("/projects", dependencies=[Depends(_forge_private_response)])
async def create_forge_project(body: ForgeProjectRequest, user: User):
    return {"project": await _call(workspace.create_project(
        _write_scope(user), {**body.model_dump(), "console_id": "forge:godot"},
        initial_files=[], source_only=True,
    ))}


@router.get("/projects/{project_id}", dependencies=[Depends(_forge_private_response)])
async def forge_project(project_id: str, user: User):
    return await _call(get_forge_project(_scope(user), project_id))


@router.post("/projects/{project_id}/builds", dependencies=[Depends(_forge_private_response)])
async def create_forge_build(project_id: str, body: ForgeBuildRequest, user: User):
    scope = _write_scope(user)
    await _call(workspace.start_job(scope, project_id, "forge_source", body.model_dump(exclude_none=True)))
    from core.game_learning import _key
    return {"job": await _call(get_forge_build(scope, project_id, _key(project_id, "forge_source", body.idempotency_key)))}


@router.get("/projects/{project_id}/builds", dependencies=[Depends(_forge_private_response)])
async def forge_build_history(
    project_id: str, user: User,
    before: Optional[str] = Query(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"),
    limit: int = Query(default=24, ge=1, le=24),
):
    return await _call(list_forge_builds(_scope(user), project_id, before=before, limit=limit))


@router.get("/projects/{project_id}/builds/{job_id}", dependencies=[Depends(_forge_private_response)])
async def forge_build(project_id: str, job_id: str, user: User):
    return {"job": await _call(get_forge_build(_scope(user), project_id, job_id))}


@router.post("/projects/{project_id}/builds/{job_id}/cancel", dependencies=[Depends(_forge_private_response)])
async def cancel_forge_build(project_id: str, job_id: str, user: User):
    scope = _write_scope(user)
    await _call(get_forge_build(scope, project_id, job_id, schedule=False))
    await _call(workspace.cancel_job(scope, job_id))
    return {"job": await _call(get_forge_build(scope, project_id, job_id))}


@router.post("/projects/{project_id}/builds/{job_id}/resume", dependencies=[Depends(_forge_private_response)])
async def recover_forge_build(project_id: str, job_id: str, user: User):
    return {"job": await _call(resume_forge_build(_write_scope(user), project_id, job_id))}


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


@router.get("/genres")
def genres() -> Dict[str, Any]:
    """Read-only grouped genre vocabulary, mapped to existing design eras."""
    from skeleton.context.genre_catalog import genre_catalog_payload
    return genre_catalog_payload()


@router.get("/generations")
def generations() -> Dict[str, Any]:
    from skeleton.forge.hardware import catalog
    rows = catalog()
    return {"generations": rows, "count": len(rows)}


@router.get("/playable/archetypes")
def playable_archetypes() -> Dict[str, Any]:
    """List only source-authored native mini-games available for explicit opt-in.

    Discoverability is not proof of compiled Godot, device input, game quality,
    installation, or release qualification.
    """
    from skeleton.forge.archetype_content import content_archetypes

    admitted = list(content_archetypes())
    return {
        "archetypes": admitted,
        "count": len(admitted),
        "kind": "original_self_contained_godot_2d_mini_game",
    }


@router.post("/run")
def run(req: RunRequest) -> Dict[str, Any]:
    # HTTP callers may generate an in-memory source manifest or download the
    # bounded ZIP. They must never supply arbitrary server filesystem write
    # destinations. CLI/internal callers retain the standalone project writer.
    if req.project_root is not None or req.overwrite:
        raise HTTPException(
            status_code=400,
            detail="HTTP GameForge builds cannot write server project paths; export source ZIP instead",
        )
    if not req.playable_content and (req.playable_archetype is not None or req.playable_main_scene):
        raise HTTPException(status_code=422, detail="playable selection requires explicit opt-in")
    from skeleton.context.pipeline import GameForgeRun
    try:
        payload = GameForgeRun.live().execute(
            req.vision,
            era=req.era,
            archetype=req.archetype,
            target=req.target,
            project_root=None,
            overwrite=False,
            answers=req.answers or None,
            **({"operator_axes": req.operator_axes} if req.operator_axes is not None else {}),
            **({"galaxy_profile": req.galaxy_profile} if req.galaxy_profile is not None else {}),
            blend=(tuple(req.blend) + (req.t,)) if req.blend and len(req.blend) >= 2 else None,
            generation=req.generation,
            **({"playable_content": True} if req.playable_content else {}),
            **({"playable_archetype": req.playable_archetype} if req.playable_archetype is not None else {}),
            **({"playable_main_scene": True} if req.playable_main_scene else {}),
            **({"playtest": req.playtest} if req.playtest and req.playtest != "off" else {}),
            **({"quest_content": True, "quest_length": req.quest_length} if req.quest_content else {}),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    files = payload.get("files") or {}
    payload = dict(payload)
    payload["file_names"] = sorted(files)
    if req.include_files:
        manifest = payload.get("source_manifest")
        ready = (
            req.target == "godot"
            and payload.get("succeeded") is True
            and isinstance(manifest, dict)
            and manifest.get("schema") == "skeleton.forge.source_manifest.v1"
            and isinstance(manifest.get("sha256"), str)
            and len(manifest["sha256"]) == 64
            and manifest.get("file_count") == len(files)
            and isinstance(files, dict)
            and 0 < len(files) <= 256
        )
        source_bytes = 0
        if ready:
            for name, body in files.items():
                if not _safe_export_path(name) or not isinstance(body, str):
                    ready = False
                    break
                try:
                    source_bytes += len(body.encode("utf-8"))
                except UnicodeEncodeError:
                    ready = False
                    break
                if source_bytes > 8 * 1024 * 1024:
                    ready = False
                    break
        if ready:
            # The build's manifest is evidence, not authority by assertion.
            # Recompute against the exact source returned to this caller.
            # Size limits run first, then the source projector validates all
            # paths and content, then the full SHA-256 inventory must match.
            from skeleton.forge.source_manifest import source_manifest
            try:
                ready = source_manifest(files) == manifest
            except (ValueError, TypeError, UnicodeError):
                ready = False
        if ready:
            payload["source_export"] = {
                "status": "ready",
                "bytes": source_bytes,
                "file_count": len(files),
                "manifest_sha256": manifest["sha256"],
            }
        else:
            payload["source_export"] = {
                "status": "unavailable",
                "reason": "Godot source export unavailable (build failed, unsealed, or exceeds 256 files / 8 MiB)",
            }
            payload.pop("files", None)
    else:
        payload.pop("files", None)
    return payload


class ConductRequest(BaseModel):
    """One product path: GameForge 7-step conductor -> ten-stage forge -> Godot."""

    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=120)
    pitch: str = Field(min_length=1, max_length=2000)
    genre: str = Field(min_length=1, max_length=40)
    pillars: list[str] = Field(default_factory=list, max_length=5)
    target_minutes: int = Field(default=10, ge=1, le=600)
    era: Optional[str] = Field(default=None, max_length=40)
    forge_era: Optional[str] = Field(default=None, max_length=80)
    playable_content: bool = True
    operator_axes: Optional[Dict[str, Any]] = Field(default=None, max_length=16)
    playtest: Optional[Literal["off", "auto", "require"]] = None
    include_files: bool = False

    @field_validator("pillars")
    @classmethod
    def _bounded_pillars(cls, pillars: list[str]) -> list[str]:
        if any(not isinstance(p, str) or not 0 < len(p) <= 40 for p in pillars):
            raise ValueError("GameForge pillars must be short design words")
        return pillars

    @field_validator("operator_axes")
    @classmethod
    def _bounded_axis_ids(cls, axes: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if axes is not None and any(
            re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", key) is None for key in axes
        ):
            raise ValueError("GameForge operator axis IDs must be bounded")
        return axes


@router.post("/conduct")
def conduct(req: ConductRequest) -> Dict[str, Any]:
    """Run vision..export (receipt-chained) and emit the playable Godot project.

    ``extra="forbid"`` rejects ``project_root``/``overwrite``: like ``/run``,
    HTTP callers never choose server filesystem write destinations. A failed
    conductor step halts with 422 before any Godot source is produced.
    """
    from skeleton.context.pipeline import GameForgeRun
    from skeleton.gameforge.serving import conduct as conduct_and_emit, public_envelope
    request = {
        "title": req.title, "pitch": req.pitch, "genre": req.genre,
        "pillars": list(req.pillars), "target_minutes": req.target_minutes,
        **({"era": req.era} if req.era else {}),
    }
    try:
        envelope = conduct_and_emit(
            request,
            conductor_era=req.era,
            forge_era=req.forge_era,
            playable_content=req.playable_content,
            operator_axes=req.operator_axes,
            project_root=None,
            overwrite=False,
            playtest=req.playtest if req.playtest and req.playtest != "off" else None,
            runner_factory=GameForgeRun.live,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not envelope["conductor"]["ok"]:
        raise HTTPException(status_code=422, detail={
            "halted_at": envelope.get("halted_at"),
            "error": envelope["conductor"].get("error"),
            "completed": envelope["conductor"].get("completed"),
        })
    files = envelope.get("files") or {}
    manifest = (envelope.get("forge") or {}).get("source_manifest")
    ready = bool(
        req.include_files and envelope["ok"] and isinstance(manifest, dict)
        and isinstance(files, dict) and 0 < len(files) <= 256
        and all(_safe_export_path(name) and isinstance(body, str) for name, body in files.items())
        and sum(len(body.encode("utf-8")) for body in files.values()) <= 8 * 1024 * 1024
    )
    if ready:
        from skeleton.forge.source_manifest import source_manifest
        try:
            ready = source_manifest(files) == manifest
        except (ValueError, TypeError, UnicodeError):
            ready = False
    out = public_envelope(envelope, include_files=ready)
    if req.include_files:
        out["source_export"] = (
            {"status": "ready", "file_count": len(files), "manifest_sha256": manifest["sha256"]}
            if ready else
            {"status": "unavailable",
             "reason": "Godot source export unavailable (build failed, unsealed, or exceeds 256 files / 8 MiB)"}
        )
    return out


@router.get("/controls/genres")
def gameforge_control_genres() -> Dict[str, Any]:
    """Discover the native device-agnostic action profiles for creator genres."""
    from skeleton.game.presentation.genre_action_profiles import GENRE_FAMILY, FAMILIES
    return {
        "schema": "skeleton.game.genre_action_catalog.v1",
        "genres": sorted(GENRE_FAMILY),
        "families": sorted(FAMILIES),
        "count": len(GENRE_FAMILY),
    }


@router.get("/controls/genres/{genre}")
def gameforge_control_genre(genre: str) -> Dict[str, Any]:
    """Expose exact semantic gameplay controls without executing a game."""
    from skeleton.game.presentation.input_actions import InputContractError
    from skeleton.game.presentation.genre_action_profiles import genre_control_profile
    try:
        return genre_control_profile(genre)
    except InputContractError as exc:
        raise HTTPException(status_code=404, detail="unknown creator genre") from exc


class HistoricalConductorPreviewRequest(BaseModel):
    """Bounded archival seven-stage preview; does not mutate current GameForge."""
    title: str = Field(min_length=1, max_length=120)
    pitch: str = Field(min_length=1, max_length=4000)
    genre: str = Field(min_length=1, max_length=48)
    pillars: list[str] = Field(default_factory=lambda: ["gameplay"], min_length=1, max_length=5)
    era: str = Field(default="HOUSE_ERA", max_length=32)
    target_minutes: int = Field(default=15, ge=1, le=600)
    target: str = Field(default="bundle", max_length=16)
    budget_bytes: int = Field(default=1_000_000, ge=1024, le=1_000_000)
    regions: int = Field(default=5, ge=1, le=20)


@router.post("/conductor/preview")
def historical_conductor_preview(req: HistoricalConductorPreviewRequest) -> Dict[str, Any]:
    """Restored archived #807 seven-step planning; return only bounded receipts.

    No file writes, project overwrites or native game readiness claims.
    """
    from skeleton.gameforge import ConductorConfig, GameForgeConductor
    from skeleton.gameforge.plans import GENRES
    from skeleton.gameforge.eras import BUILTIN_ERAS
    if req.genre not in GENRES:
        raise HTTPException(status_code=422, detail="unsupported historical conductor genre")
    if req.era not in BUILTIN_ERAS:
        raise HTTPException(status_code=422, detail="unsupported historical conductor era")
    if req.target not in {"web", "desktop", "bundle"}:
        raise HTTPException(status_code=422, detail="unsupported historical conductor export target")
    if not 1 <= len(req.pillars) <= 5 or any(
        not isinstance(pillar, str) or not 1 <= len(pillar) <= 100 for pillar in req.pillars
    ):
        raise HTTPException(status_code=422, detail="pillars must contain one to five short strings")
    result = GameForgeConductor(config=ConductorConfig(
        budget_bytes=req.budget_bytes, regions=req.regions, target=req.target
    )).run({
        "title": req.title, "pitch": req.pitch, "genre": req.genre,
        "pillars": req.pillars, "target_minutes": req.target_minutes, "era": req.era,
    })
    if not result.ok:
        raise HTTPException(status_code=422, detail="historical conductor preview rejected")
    return {
        **result.to_dict(),
        "mode": "historical_7_stage_preview",
        "artifacts": sorted(result.artifacts),
        "artifact_count": len(result.artifacts),
        "byte_total": sum(len(data) for data in result.artifacts.values()),
    }


@router.get("/jeeves/game-quality")
def jeeves_game_quality_catalog() -> Dict[str, Any]:
    """Discover deterministic public diagnostic coverage; never invoke a model.

    Scores from this public taskset cannot certify model quality or authorize
    project publication. Inference remains operator-controlled and local-only.
    """
    from skeleton.eval.game_builder_quality import (
        TASKSET_ID, SCORER_ID, DIMENSIONS, TASKS, taskset_digest,
    )
    return {
        "schema": "skeleton.jeeves.game_quality.catalog.v1",
        "taskset_id": TASKSET_ID,
        "scorer_id": SCORER_ID,
        "taskset_sha256": taskset_digest(),
        "task_count": len(TASKS),
        "categories": sorted({task.category for task in TASKS}),
        "dimensions": list(DIMENSIONS),
        "evidence_kind": "public_deterministic_diagnostics",
        "model_quality_certified": False,
        "inference_started": False,
        "local_gguf_required_for_run": True,
    }


class ComposeRequest(BaseModel):
    vision: str = Field(default="", max_length=4000)


@router.post("/compose")
def compose(req: ComposeRequest) -> Dict[str, Any]:
    """Preview the vision-derived blueprint that ``archetype="auto"`` would forge."""
    from skeleton.forge.universal import Forge
    from skeleton.forge.vision_compose import compose_from_vision, describe
    try:
        bp, composition = compose_from_vision(Forge(), req.vision)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = composition.to_dict()
    payload["summary"] = describe(payload)
    payload["topology"] = bp.to_dict()
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


@router.post("/cortex/contact")
def cortex_contact(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    slot = str((body or {}).get("slot") or "left")
    stim = str((body or {}).get("stimulus") or (body or {}).get("prefix") or "plan tensor ttk")
    out = live_cortex().contact(slot, stim)
    persist()
    return out


@router.post("/cortex/refer")
def cortex_refer(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    out = live_cortex().refer(str((body or {}).get("stimulus") or "elden ring"), live=bool((body or {}).get("live")))
    persist()
    return out


@router.post("/cortex/improve")
def cortex_improve(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    out = live_cortex().improve(str((body or {}).get("stimulus") or "like elden ring"), rounds=int((body or {}).get("rounds") or 8))
    persist()
    return out


@router.post("/cortex/ascend")
def cortex_ascend(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex, persist
    out = live_cortex().ascend(str((body or {}).get("stimulus") or "like elden ring"), rounds=int((body or {}).get("rounds") or 8))
    persist()
    return out


@router.post("/jeeves/plan")
def jeeves_plan(body: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.live import live_jeeves, persist
    out = live_jeeves().plan_build(vision=str((body or {}).get("vision") or "like elden ring"))
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
