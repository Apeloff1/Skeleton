"""Deterministic mesh LOD and skin-weight transfer for Game Frontier.

This package does not download models, decode images, or claim a licensed
external asset. Geometry is whatever the caller already holds in memory.

Seam copies that start within ``SEAM_POSITION_EPSILON`` (1e-6) and touch two
materials are held to one position during edge collapse. Bone correspondence
is by bone name.
"""

from skeleton.frontier_mesh.records import (
    AREA_EPSILON,
    MAX_TRIANGLES,
    MAX_VERTICES,
    SEAM_POSITION_EPSILON,
    WEIGHT_SUM_EPSILON,
    FrontierMeshError,
    SkinWeight,
    SurfaceMesh,
    SurfaceTriangle,
    SurfaceVertex,
    Vec3,
    bone_names,
    from_era_mesh,
    from_skinned_mesh,
    make_mesh,
    make_vertex,
    vertex_digest,
)
from skeleton.frontier_mesh.simplify import MeshLod, retarget, simplify_lod
from skeleton.frontier_mesh.surface import (
    SurfaceHit,
    closest_point,
    directed_hausdorff,
    seam_position_delta,
)

__all__ = [
    "AREA_EPSILON",
    "MAX_TRIANGLES",
    "MAX_VERTICES",
    "SEAM_POSITION_EPSILON",
    "WEIGHT_SUM_EPSILON",
    "FrontierMeshError",
    "MeshLod",
    "SkinWeight",
    "SurfaceHit",
    "SurfaceMesh",
    "SurfaceTriangle",
    "SurfaceVertex",
    "Vec3",
    "bone_names",
    "closest_point",
    "directed_hausdorff",
    "from_era_mesh",
    "from_skinned_mesh",
    "make_mesh",
    "make_vertex",
    "retarget",
    "seam_position_delta",
    "simplify_lod",
    "vertex_digest",
]
