"""Explicit inert source dispatch for URDF, SDF and MJCF articulated models."""
from __future__ import annotations

from .urdf_documents import URDF_TYPES,extract_urdf
from .sdf_documents import SDF_TYPES,extract_sdf
from .mjcf_documents import MJCF_TYPES,extract_mjcf
from .research_projection import ResearchFormatError,ResearchProjection

ROBOT_SCENE_TYPES=URDF_TYPES | SDF_TYPES | MJCF_TYPES


def extract_robot_scene(
    raw:str,mime:str,*,max_chars:int,max_links:int,
)->ResearchProjection:
    for types,parser in (
        (URDF_TYPES,extract_urdf),
        (SDF_TYPES,extract_sdf),
        (MJCF_TYPES,extract_mjcf),
    ):
        if mime in types:
            return parser(raw,max_chars=max_chars,max_links=max_links)
    raise ResearchFormatError("unsupported articulated source media type")
