"""Universal Forge API — activates the entire forge roadmap as live, buildable
3D assets (one engine, ~190 categories). Shares the Construct Forge store +
Vault connection (mount / save-to-gamefiles / extract)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import construct_forge as cf
from core import universal_forge as uf

router = APIRouter(prefix="/api/galaxy-studio/forge", tags=["universal-forge"])


class GenerateReq(BaseModel):
    category: str = Field(..., min_length=1)
    era: str | None = None
    preset_id: str | None = None
    user_prompt: str = Field("", max_length=uf.MAX_PROMPT)
    use_llm: bool = True
    seed: int | None = None
    skin_style: str | None = None
    complexity: str | None = None
    intricacy: str | None = None
    detail_level: str | None = None
    axes: dict | None = None
    treatment: str | None = None
    region: str | None = None
    inscribe: str | None = None
    inscription: dict | None = None


class StylePackReq(BaseModel):
    label: str = Field("My Pack", min_length=1, max_length=40)
    icon: str | None = None
    skin_style: str | None = None
    axes: dict | None = None
    treatment: str | None = None
    intricacy: str | None = None


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
    style: dict | None = None
    variants: int = 0
    region: str | None = None


class SeedReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    era: str | None = None
    genre: str = "rpg"
    seed: int = 0
    mount: bool = True


@router.get("/catalog")
def catalog():
    """Families + grouped categories + counts — drives the Forge Hub."""
    return uf.catalog()


@router.get("/capacity")
def capacity():
    return uf.capacity()


@router.get("/presets")
def presets(category: str, era: str | None = None, offset: int = 0, limit: int = 60):
    return uf.list_presets(category, era, offset, limit)


@router.post("/generate")
def generate(req: GenerateReq):
    return uf.generate(req.category, req.era, req.preset_id, req.user_prompt,
                       req.use_llm, req.seed, skin_style=req.skin_style,
                       complexity=req.complexity, intricacy=req.intricacy,
                       detail_level=req.detail_level, axes=req.axes,
                       treatment=req.treatment, region=req.region,
                       inscribe=req.inscribe, inscription=req.inscription)


@router.get("/search")
def search(q: str, limit: int = 60):
    """Search the full forge library (server-side)."""
    return uf.search_categories(q, limit)


@router.get("/random")
def random_forge(seed: int | None = None, require: str | None = None):
    """One random forge from the full multi-tier namespace + suggested style
    axes — powers the Forge Hub 'Surprise Me' and ECS mask filter (`require`
    is a comma list of components, e.g. 'metallic,script')."""
    reqs = [r.strip() for r in (require or "").split(",") if r.strip()]
    return uf.random_category(seed, require=reqs)


@router.get("/asset")
def asset(id: str, era: str | None = None, seed: int | None = None,
          preset_id: str | None = None, axes: str | None = None,
          full: bool = False):
    """Targeted single-asset fetch (ID-only architecture).

    Deterministic + no-LLM → fully GET-cacheable. LIGHT by default: returns the
    descriptor/spec WITHOUT the heavy `geometry` mesh array so the Forge Hub can
    render ID-only cards with a 2D palette thumbnail and never pull raw meshes
    into the JS heap. Pass `full=1` to fetch the raw 3D mesh on demand — only
    when an asset is actually opened in the 3D viewport. `axes` is an optional
    JSON object of style-axis selections (used by the Variations carousel)."""
    import json as _json
    ax = None
    if axes:
        try:
            _d = _json.loads(axes)
            ax = _d if isinstance(_d, dict) else None
        except Exception:
            ax = None
    spec = uf.generate(id, era or "modern", preset_id=preset_id, use_llm=False,
                       seed=seed, axes=ax)
    if full:
        return spec
    geo = spec.get("geometry") or []
    light = {k: v for k, v in spec.items() if k != "geometry"}
    light["part_count"] = len(geo)
    light["thumb_palette"] = (spec.get("palette") or [])[:5]
    light["light"] = True
    return light


@router.get("/axis-tree")
def axis_tree():
    """The complete axis tree — every group → axes → options (>=9 each)."""
    return uf.axis_tree()


class StylePackReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    label: str = "Style Pack"
    axes: dict = {}
    skin_style: str | None = None


@router.post("/style-pack")
def save_style_pack(req: StylePackReq):
    """Persist a creator's axis combo as a reusable per-build Style Pack."""
    return uf.save_build_style_pack(req.build_id, req.label, req.axes, req.skin_style)


@router.get("/style-pack")
def list_style_packs(build_id: str):
    """List the saved Style Packs for a build."""
    return uf.list_build_style_packs(build_id)


@router.post("/decode")
def decode_forge(body: dict):
    """DNA reverse-lookup: paste a reproducible Forge Code → rebuild the exact
    forge (the 2048-bit DNA hash itself is one-way; the forge_code is the
    shareable reproducible token)."""
    from core import forge_dna as fdna
    params = fdna.decode_forge_code((body or {}).get("code", ""))
    if not params.get("category"):
        return {"ok": False, "error": "Invalid code. Paste a Forge Code (not the DNA fingerprint)."}
    forge = uf.generate(
        params["category"], params.get("era") or "modern", use_llm=False,
        skin_style=params.get("skin_style"), complexity=params.get("complexity"),
        intricacy=params.get("intricacy"), detail_level=params.get("detail_level"),
        axes=params.get("style_axes"), treatment=params.get("treatment"),
        region=params.get("region"), inscription=params.get("inscription_text"))
    return {"ok": True, "category": forge.get("category"),
            "label": forge.get("category_label"), "params": params, "forge": forge}


@router.get("/components")
def ecs_components():
    """ECS component bit registry — each forge carries a `component_mask`
    (integer) decoded from these bits for O(1) capability filtering."""
    from core import forge_dna as fdna
    return {"bits": fdna.COMPONENT_BITS, "count": len(fdna.COMPONENT_BITS)}


@router.get("/cache-stats")
def dna_cache_stats():
    """Lazy DNA-token cache stats (LRU pruning) — proves memory stays bounded."""
    from core import forge_dna as fdna
    return {"token_cache": fdna.TOKEN_CACHE.stats(), "dna_bits": fdna.DNA_BITS}


@router.post("/dna")
def compute_dna(req: GenerateReq):
    """Deterministic 2048-bit Procedural DNA token + ECS component mask for the
    given forge parameters (no LLM, fully reproducible)."""
    res = uf.generate(req.category, req.era or "modern", use_llm=False,
                      axes=req.axes, treatment=req.treatment, region=req.region,
                      inscribe=req.inscribe, inscription=req.inscription)
    return {"category": res.get("category"), "category_label": res.get("category_label"),
            "dna": res.get("dna"), "component_mask": res.get("component_mask"),
            "components": res.get("components"), "pruned_axes": res.get("pruned_axes")}


@router.get("/style-packs")
def list_packs():
    """Built-in + custom one-tap style packs."""
    return {"packs": uf.STYLE_PACKS + uf.list_custom_packs()}


@router.post("/style-packs")
def save_pack(req: StylePackReq):
    return uf.save_custom_pack(req.label, req.skin_style, req.axes,
                               req.treatment, req.intricacy, req.icon)


@router.delete("/style-packs/{key}")
def delete_pack(key: str):
    return uf.delete_custom_pack(key)


@router.get("/styles")
def styles():
    """Skin styles + detail/intricacy/complexity bands + diorama regions."""
    return uf.styles_catalog()


@router.post("/save")
def save(req: SaveReq):
    spec = dict(req.spec)
    # Universal assets keep their family as `kind` so they never collide with
    # the construct/material lists; default to a generic family if missing.
    spec.setdefault("kind", spec.get("family") or "prop")
    try:
        return cf.save_construct(spec, req.construct_id)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/list")
def list_saved(category: str | None = None, build_id: str | None = None,
               mounted: bool | None = None, offset: int = 0, limit: int = 60):
    return uf.list_saved(category, build_id, mounted, offset, limit)


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


@router.post("/compose")
def compose(req: ComposeReq):
    """Forge a themed multi-category scene (e.g. a forest) and mount it."""
    return uf.compose_scene(req.build_id, req.era, req.items, req.seed, req.mount,
                            style=req.style, variants=req.variants, region=req.region)


@router.post("/seed")
def seed(req: SeedReq):
    """Snowball auto-seed — mint a genre-themed batch of universal assets."""
    return uf.seed_for_build(req.build_id, req.era, req.genre, req.seed, req.mount)
