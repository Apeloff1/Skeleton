"""Original low-poly 3D asset forge for all authored expedition waypoints.

Generates real Wavefront OBJ mesh geometry and material data at multiple
levels of detail; no images, music, copyrighted textures or proprietary
assets are copied. Source hashes bind procedural geometry to the actual
world, seed, biome and LOD so a stale mesh cannot enter a later build.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import random
from typing import Mapping

from .game_frontier_expedition import ExpeditionWorld,ExpeditionError,_digest

_PALETTE={
    "sky_island":(0.32,0.65,0.78),
    "underwater":(0.11,0.28,0.62),
    "cavern":(0.34,0.29,0.42),
    "settlement":(0.70,0.53,0.32),
    "ruins":(0.58,0.47,0.72),
    "canopy":(0.16,0.62,0.29),
    "volcano":(0.75,0.19,0.08),
    "ice":(0.69,0.85,0.95),
    "airship":(0.62,0.49,0.24),
    "ground":(0.36,0.54,0.27),
}
SCHEMA="skeleton.game.original_3d_assets.v1"


@dataclass(frozen=True,slots=True)
class VisualDesign:
    seed:int=42
    radius_m:float=6.0
    height_m:float=2.0
    detail_scale:float=0.25
    shadow_strength:float=0.7
    roughness:float=0.7
    foliage_density:float=0.6
    material_variation:float=0.12

    def __post_init__(self):
        if type(self.seed) is not int or not 0<=self.seed<2**63:
            raise ExpeditionError("procedural asset seed must be bounded")
        for field,lo,hi in (
            ("radius_m",0.1,10000),("height_m",0.1,10000),
            ("detail_scale",0,1),("shadow_strength",0,1),
            ("roughness",0,1),("foliage_density",0,1),
            ("material_variation",0,1),
        ):
            value=getattr(self,field)
            if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
                raise ExpeditionError("procedural asset parameter invalid")


def _original_mesh(kind:str,seed:int,segments:int,design:VisualDesign)->str:
    """Create actual closed triangulated floating-island geology with normals."""
    if segments<3 or segments>256:
        raise ExpeditionError("mesh segment budget invalid")
    rng=random.Random(seed)
    vertices=[]
    # Three rings form a sculpted top, middle lip and tapering rocky underside.
    for ring in range(3):
        altitude=(design.height_m if ring==0 else
                  design.height_m*0.45 if ring==1 else -design.height_m*1.25)
        radius=design.radius_m*(0.85 if ring==0 else
                                1.0 if ring==1 else 0.28)
        for i in range(segments):
            theta=2*math.pi*i/segments
            jitter=(rng.random()-.5)*design.detail_scale
            k=radius*(1+jitter)
            x=math.cos(theta)*k
            z=math.sin(theta)*k
            vertices.append((x,altitude+jitter*design.height_m*0.2,z))
    center_top=len(vertices)+1
    vertices.append((0,design.height_m*1.1,0))
    center_bottom=len(vertices)+1
    vertices.append((0,-design.height_m*1.35,0))
    lines=[
        "# Original Skeleton game terrain; generated deterministic polygon mesh",
        "o Original_"+kind,
    ]
    lines.extend("v %.6f %.6f %.6f"%p for p in vertices)
    lines.append("s 1")
    # Every normal is computed from the actual original triangle.
    faces=[]
    for i in range(segments):
        nxt=(i+1)%segments
        faces.extend((
            (center_top,i+1,nxt+1),
            (i+1,segments+i+1,segments+nxt+1),
            (i+1,segments+nxt+1,nxt+1),
            (segments+i+1,2*segments+i+1,2*segments+nxt+1),
            (segments+i+1,2*segments+nxt+1,segments+nxt+1),
            (2*segments+i+1,center_bottom,2*segments+nxt+1),
        ))
    for a,b,c in faces:
        v0,v1,v2=vertices[a-1],vertices[b-1],vertices[c-1]
        u=(v1[0]-v0[0],v1[1]-v0[1],v1[2]-v0[2])
        v=(v2[0]-v0[0],v2[1]-v0[1],v2[2]-v0[2])
        cross=(u[1]*v[2]-u[2]*v[1],
               u[2]*v[0]-u[0]*v[2],
               u[0]*v[1]-u[1]*v[0])
        length=math.sqrt(sum(q*q for q in cross))
        if length<1e-9:
            raise ExpeditionError("procedural source geometry has degenerate face")
        normal=tuple(q/length for q in cross)
        lines.append("vn %.6f %.6f %.6f"%normal)
        idx=len([1 for item in lines if item.startswith("vn ")])
        lines.append(f"f {a}//{idx} {b}//{idx} {c}//{idx}")
    return "\n".join(lines)+"\n"


def forge_expedition_assets(
    world:ExpeditionWorld, design:VisualDesign=VisualDesign(), *,
    lod_segments:tuple[int,...]=(24,12,6), max_assets:int=2048,
)->dict:
    if not isinstance(world,ExpeditionWorld) or not isinstance(design,VisualDesign):
        raise ExpeditionError("original world and validated visual design required")
    if (type(lod_segments) is not tuple or not 1<=len(lod_segments)<=4
            or any(type(n) is not int or not 3<=n<=128 for n in lod_segments)
            or list(lod_segments)!=sorted(lod_segments,reverse=True)
            or len(set(lod_segments))!=len(lod_segments)):
        raise ExpeditionError("LOD topology must be finite and decreasing")
    if type(max_assets) is not int or not 1<=max_assets<=2048:
        raise ExpeditionError("asset forge budget must be bounded")
    if len(world.waypoints)*len(lod_segments)>max_assets:
        raise ExpeditionError("asset forge budget exhausted before creation")
    from dataclasses import asdict
    assets={}
    inventory=[]
    for node in world.waypoints:
        kind=node.kind
        color=_PALETTE[kind]
        for lod,segments in enumerate(lod_segments):
            # Stable 64-bit RNG seed, not Python's randomized hash().
            material_seed=int(sha256(
                f"{world.digest}:{node.waypoint_id}:{design.seed}:{lod}".encode()
            ).hexdigest()[:15],16)
            mesh=_original_mesh(kind,material_seed,segments,design)
            key=f"game/frontier/assets/{node.waypoint_id}_lod{lod}.obj"
            assets[key]=mesh
            inventory.append({
                "waypoint":node.waypoint_id,"lod":lod,"triangles":segments*6,
                "kind":kind,"x_m":node.x_m,"y_m":node.y_m,
                "altitude_m":node.altitude_m,
                "mesh_path":key,"sha256":sha256(mesh.encode()).hexdigest(),
                "albedo_rgb":list(color),
                "roughness":design.roughness,
                "shadow_strength":design.shadow_strength,
                "foliage_density":design.foliage_density,
            })
    manifest={
        "schema":SCHEMA,"world_digest":world.digest,
        "source_digest":world.source_digest,
        "design":asdict(design),"lod_segments":list(lod_segments),
        "count":len(inventory),"assets":inventory,
        "generator": "original_triangular_sky_geology",
        "native_render_verified":False,
    }
    manifest["receipt_digest"]=_digest(manifest)
    return {"files":assets,"manifest":manifest}


def verify_expedition_assets(world:ExpeditionWorld, design:VisualDesign,
                             exported:Mapping, *, lod_segments=(24,12,6))->dict:
    if not isinstance(exported,Mapping) or set(exported)!={"files","manifest"}:
        raise ExpeditionError("asset bundle missing actual geometry or manifest")
    actual=forge_expedition_assets(world,design,lod_segments=lod_segments)
    if actual!=exported:
        raise ExpeditionError("asset manifest or geometry not reproduced on source")
    return {
        "world_digest":world.digest,
        "asset_count":actual["manifest"]["count"],
        "geometry_receipt":actual["manifest"]["receipt_digest"],
        "originality_origin":"deterministic homebrew geometry",
        "native_render_verified":False,
    }
