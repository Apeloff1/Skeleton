"""Canonical inert dispatch for finite SBOM and vulnerability-claim evidence."""
from __future__ import annotations

from .cyclonedx_documents import CYCLONEDX_MEDIA_TYPES, extract_cyclonedx
from .spdx_documents import SPDX_MEDIA_TYPES, extract_spdx
from .vex_documents import OPENVEX_MEDIA_TYPES, extract_openvex
from .research_projection import ResearchFormatError, ResearchProjection

SUPPLY_CHAIN_TYPES=CYCLONEDX_MEDIA_TYPES | SPDX_MEDIA_TYPES | OPENVEX_MEDIA_TYPES


def extract_supply_chain_artifact(
    raw:str, media_type:str, *, max_chars:int, max_links:int,
)->ResearchProjection:
    if media_type in CYCLONEDX_MEDIA_TYPES:
        return extract_cyclonedx(raw,max_chars=max_chars,max_links=max_links)
    if media_type in SPDX_MEDIA_TYPES:
        return extract_spdx(raw,max_chars=max_chars,max_links=max_links)
    if media_type in OPENVEX_MEDIA_TYPES:
        return extract_openvex(raw,max_chars=max_chars,max_links=max_links)
    raise ResearchFormatError("unsupported source-side software inventory type")
