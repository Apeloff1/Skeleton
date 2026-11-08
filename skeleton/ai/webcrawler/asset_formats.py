"""Explicit text-format dispatch for inert OBJ and glTF source inventories."""
from __future__ import annotations

from .gltf_documents import GLTF_MEDIA_TYPES, extract_gltf
from .obj_documents import OBJ_MEDIA_TYPES, extract_obj
from .research_projection import ResearchFormatError, ResearchProjection

ASSET_TEXT_MEDIA_TYPES = GLTF_MEDIA_TYPES | OBJ_MEDIA_TYPES


def extract_asset_text(
    raw: str, media_type: str, *, max_chars: int, max_links: int,
) -> ResearchProjection:
    if media_type in GLTF_MEDIA_TYPES:
        return extract_gltf(raw, max_chars=max_chars, max_links=max_links)
    if media_type in OBJ_MEDIA_TYPES:
        return extract_obj(raw, max_chars=max_chars, max_links=max_links)
    raise ResearchFormatError("unapproved asset text source type")
