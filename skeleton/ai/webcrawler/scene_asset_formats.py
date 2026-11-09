"""Read-only dispatcher for bounded vector, mesh and game-scene sources."""
from __future__ import annotations
from .svg_inventory import SVG_TYPES, extract_svg
from .ply_inventory import PLY_TYPES, extract_ply
from .off_inventory import OFF_TYPES, extract_off
from .godot_scene import GODOT_TYPES, extract_godot_scene
from .unity_scene import UNITY_TYPES, extract_unity_scene
from .usda_scene import USDA_TYPES, extract_usda
from .ldraw_scene import LDRAW_TYPES, extract_ldraw
from .research_projection import ResearchFormatError,ResearchProjection

SCENE_ASSET_TYPES=frozenset().union(
    SVG_TYPES,PLY_TYPES,OFF_TYPES,GODOT_TYPES,UNITY_TYPES,USDA_TYPES,LDRAW_TYPES,
)


def extract_scene_asset(
    raw:str,mime:str,*,max_chars:int,max_links:int,
)->ResearchProjection:
    for types,parser in (
        (SVG_TYPES,extract_svg),(PLY_TYPES,extract_ply),(OFF_TYPES,extract_off),
        (GODOT_TYPES,extract_godot_scene),(UNITY_TYPES,extract_unity_scene),
        (USDA_TYPES,extract_usda),(LDRAW_TYPES,extract_ldraw),
    ):
        if mime in types:
            return parser(raw,max_chars=max_chars,max_links=max_links)
    raise ResearchFormatError("unsupported vector or game scene source")
