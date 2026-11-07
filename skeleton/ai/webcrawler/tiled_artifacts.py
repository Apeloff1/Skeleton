"""Dispatch finite TMX, TSX and Tiled JSON source-side world metadata."""
from __future__ import annotations

from .tiled_xml_documents import TMX_TYPES,TSX_TYPES,extract_tmx,extract_tsx
from .tiled_json_documents import TILED_JSON_TYPES,extract_tiled_json
from .research_projection import ResearchFormatError,ResearchProjection

TILED_ARTIFACT_TYPES=TMX_TYPES | TSX_TYPES | TILED_JSON_TYPES


def extract_tiled_artifact(
    raw:str,mime:str,*,max_chars:int,max_links:int,
)->ResearchProjection:
    if mime in TMX_TYPES:
        return extract_tmx(raw,max_chars=max_chars,max_links=max_links)
    if mime in TSX_TYPES:
        return extract_tsx(raw,max_chars=max_chars,max_links=max_links)
    if mime in TILED_JSON_TYPES:
        return extract_tiled_json(raw,max_chars=max_chars,max_links=max_links)
    raise ResearchFormatError("unsupported Tiled source class")
