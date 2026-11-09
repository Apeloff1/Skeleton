"""Bidirectional old/new era authored game asset mesh generation.

Imports pixel silhouettes as transparent 2D sprites; voxel-extrudes exposed
faces into true indexed 3D meshes with normals and UV-like source mapping,
preserving the original bitmap. Era-specific detail budgets are explicit.
No reverse engineering of third-party ROMs or proprietary texture sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math

from .game_frontier_production import Vec3, ERA_TRIANGLE_BUDGETS


class MeshEvolutionError(ValueError):
    pass


@dataclass(frozen=True)
class PixelAsset:
    asset_id: str
    rows: tuple[str, ...]
    palette: tuple[str, ...] = ("#000000", "#FFFFFF")

    def __post_init__(self):
        if not self.asset_id or len(self.asset_id)>128:
            raise MeshEvolutionError("asset id required")
        if not 1<=len(self.rows)<=128 or any(not row or len(row)!=len(self.rows[0]) for row in self.rows):
            raise MeshEvolutionError("1..128 equal width sprite rows required")
        if len(self.rows[0])>128:
            raise MeshEvolutionError("width too large")
        if len(self.palette)>64 or len(self.palette)<2:
            raise MeshEvolutionError("invalid palette")
        if any(c not in ".#0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" for row in self.rows for c in row):
            raise MeshEvolutionError("unsupported sprite token")
        if not any(c!="." for row in self.rows for c in row):
            raise MeshEvolutionError("sprite must have at least one solid cell")

    @property
    def digest(self) -> str:
        return sha256(json.dumps([self.asset_id,self.rows,self.palette],
                                  separators=(",",":")).encode()).hexdigest()


@dataclass(frozen=True)
class EraMesh:
    source_digest: str
    era: str
    vertices: tuple[Vec3, ...]
    triangles: tuple[tuple[int,int,int], ...]
    vertex_normals: tuple[Vec3, ...]
    source_pixels: tuple[tuple[int,int], ...]
    source_width: int
    source_height: int
    pixel_resolution: int
    depth_m: float
    source_preserved: bool = True

    @property
    def triangle_count(self) -> int:
        return len(self.triangles)


def sprite_to_3d(asset: PixelAsset, *, era: str,
                 pixel_size_m: float = .1, depth_m: float = .1,
                 detail_scale: int | None = None) -> EraMesh:
    if era not in ERA_TRIANGLE_BUDGETS:
        raise MeshEvolutionError("era must be registered rendering era")
    if any(type(v) not in (int,float) or not math.isfinite(v) or not .001<=v<=100
           for v in (pixel_size_m,depth_m)):
        raise MeshEvolutionError("finite geometry scale required")
    # A nearest-neighbor scale increases detail topology *without* pretending
    # to invent pixel fidelity. A real learned upscaler must be separately used.
    scale = (detail_scale if detail_scale is not None else
             (1 if era=="early_3d" else 2 if era in ("fixed_3d","shader")
              else 3 if era in ("hd","modern") else 4))
    if type(scale) is not int or not 1<=scale<=4:
        raise MeshEvolutionError("detail scale 1..4")
    width,height=len(asset.rows[0]),len(asset.rows)
    solids={(x,y) for y,row in enumerate(asset.rows)
            for x,c in enumerate(row) if c!="."}
    expanded={(x*scale+sx,y*scale+sy):(x,y)
              for x,y in solids for sx in range(scale) for sy in range(scale)}
    if len(expanded)*12>max(ERA_TRIANGLE_BUDGETS[era]*24,2000000):
        raise MeshEvolutionError("source pixel density exceeds era budget")
    step=pixel_size_m/scale
    vertices=[]
    triangles=[]
    normals=[]
    pixels=[]
    # Exposed faces only, never hidden internal voxel surfaces.
    # Coordinates (X,Y,Z) use the same Z-up convention as Jeeves.
    facespec=(
        ((-1,0),(-1,0,0),((0,0,0),(0,0,1),(0,1,1),(0,1,0))),
        ((1,0),(1,0,0),((1,0,0),(1,1,0),(1,1,1),(1,0,1))),
        ((0,-1),(0,-1,0),((0,0,0),(1,0,0),(1,0,1),(0,0,1))),
        ((0,1),(0,1,0),((0,1,0),(0,1,1),(1,1,1),(1,1,0))),
    )
    for (x,y),pixel in sorted(expanded.items(),key=lambda z:(z[0][1],z[0][0])):
        for (dx,dy),(nx,ny,nz),corners in facespec:
            if (x+dx,y+dy) in expanded:
                continue
            base=len(vertices)
            for cx,cy,cz in corners:
                vertices.append(Vec3((x+cx)*step,(height*scale-y-cy)*step,cz*depth_m))
                normals.append(Vec3(nx,ny,nz))
                pixels.append(pixel)
            triangles.extend(((base,base+1,base+2),(base,base+2,base+3)))
        for z,normal,order in (
            (1,Vec3(0,0,1),((0,0),(1,0),(1,1),(0,1))),
            (0,Vec3(0,0,-1),((0,0),(0,1),(1,1),(1,0)))):
            base=len(vertices)
            for ox,oy in order:
                vertices.append(Vec3((x+ox)*step,(height*scale-y-oy)*step,z*depth_m))
                normals.append(normal)
                pixels.append(pixel)
            triangles.extend(((base,base+1,base+2),(base,base+2,base+3)))
        if len(triangles)>ERA_TRIANGLE_BUDGETS[era]:
            raise MeshEvolutionError("source silhouette exceeds era triangle budget; author LOD explicitly")
    return EraMesh(asset.digest,era,tuple(vertices),tuple(triangles),
                   tuple(normals),tuple(pixels),width,height,scale,depth_m)


def create_old_new_asset_pair(asset: PixelAsset, *, old_era: str = "early_3d",
                              new_era: str = "modern", depth_m: float = .1) -> tuple[EraMesh, EraMesh]:
    """Preserve one canonical source for two distinct engine-target meshes."""
    a=sprite_to_3d(asset,era=old_era,depth_m=depth_m)
    b=sprite_to_3d(asset,era=new_era,depth_m=depth_m)
    if a.source_digest!=b.source_digest:
        raise MeshEvolutionError("old/new source provenance diverged")
    return a,b
