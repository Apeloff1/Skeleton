"""Construct Forge & Material Forge API — large composite assets + surfaces,
full edit/CRUD, 100k-asset store, Vault mount/extract, snowball integration."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import construct_forge as cf

# Two sibling forges sharing one engine (kind="construct" | "material").
construct_router = APIRouter(prefix="/api/galaxy-studio/constructs", tags=["construct-forge"])
material_router = APIRouter(prefix="/api/galaxy-studio/materials", tags=["material-forge"])


class GenerateReq(BaseModel):
    era: str | None = None
    category: str | None = None
    preset_id: str | None = None
    user_prompt: str = Field("", max_length=cf.MAX_PROMPT)
    use_llm: bool = False
    seed: int | None = None


class SaveReq(BaseModel):
    spec: dict
    construct_id: str | None = None


class UpdateReq(BaseModel):
    patch: dict


class MountReq(BaseModel):
    construct_ids: list[str]
    build_id: str = Field(..., min_length=1)


class ComposeReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    era: str | None = None
    items: list[dict]
    seed: int = 0
    mount: bool = True


class SnowballReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    era: str | None = None
    seed: int = 0
    construct_count: int = 12
    material_count: int = 12
    config: dict | None = None
    mount: bool = True


def _make_router(router: APIRouter, kind: str) -> None:
    @router.get("/presets")
    def presets(era: str | None = None, offset: int = 0, limit: int = 60,
                category: str | None = None):
        return cf.list_presets(kind, era, offset, limit, category)

    @router.get("/capacity")
    def capacity():
        return cf.count(kind)

    @router.post("/generate")
    def generate(req: GenerateReq):
        return cf.generate(kind, req.era, req.category, req.preset_id,
                           req.user_prompt, req.use_llm, req.seed)

    @router.post("/save")
    def save(req: SaveReq):
        spec = dict(req.spec)
        spec["kind"] = kind
        try:
            return cf.save_construct(spec, req.construct_id)
        except ValueError as e:
            raise HTTPException(409, str(e))

    @router.get("/list")
    def list_saved(era: str | None = None, build_id: str | None = None,
                   mounted: bool | None = None, offset: int = 0, limit: int = 60):
        return cf.list_constructs(kind, era, build_id, mounted, offset, limit)

    @router.get("/item/{construct_id}")
    def get_one(construct_id: str):
        doc = cf.get_construct(construct_id)
        if not doc:
            raise HTTPException(404, "not found")
        return doc

    @router.put("/item/{construct_id}")
    def update_one(construct_id: str, req: UpdateReq):
        doc = cf.update_construct(construct_id, req.patch)
        if not doc:
            raise HTTPException(404, "not found")
        return doc

    @router.delete("/item/{construct_id}")
    def delete_one(construct_id: str):
        return {"deleted": cf.delete_construct(construct_id)}

    @router.post("/mount")
    def mount(req: MountReq):
        return cf.mount_to_build(req.construct_ids, req.build_id)

    @router.post("/save-to-gamefiles")
    def save_gamefiles(req: MountReq):
        return cf.save_to_gamefiles(req.build_id, req.construct_ids)

    @router.get("/extract/{build_id}")
    def extract(build_id: str, into_library: bool = True):
        return cf.extract_from_build(build_id, into_library)

    @router.post("/snowball/forge")
    def snowball_forge(req: SnowballReq):
        """Snowball stage — runs AFTER the 100-phase questionnaire."""
        if kind == "construct":
            mats = 0
            cons = req.construct_count
        else:
            mats = req.material_count
            cons = 0
        return cf.forge_for_build(req.build_id, req.era, req.seed, cons, mats,
                                  req.config, req.mount)


_make_router(construct_router, "construct")
_make_router(material_router, "material")


@construct_router.post("/compose")
def compose(req: ComposeReq):
    """Compose a themed settlement (mixed categories+counts) and mount it."""
    return cf.forge_compose(req.build_id, req.era, req.items, req.seed, req.mount)

# Single combined symbol the registry can mount (it mounts both sub-routers).
router = APIRouter()
router.include_router(construct_router)
router.include_router(material_router)
