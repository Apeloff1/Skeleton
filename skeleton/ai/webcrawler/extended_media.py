"""Explicit read-only dispatch for additional bounded binary source metadata."""
from __future__ import annotations
from .webp_metadata import WEBP_TYPES, extract_webp
from .flac_metadata import FLAC_TYPES, extract_flac
from .ogg_metadata import OGG_TYPES, extract_ogg_opus
from .mp4_metadata import MP4_TYPES, extract_mp4
from .glb_metadata import GLB_TYPES, extract_glb
from .stl_metadata import STL_TYPES, extract_binary_stl
from .ico_metadata import ICO_TYPES, extract_ico
from .tar_inventory import TAR_TYPES, extract_tar
from .research_projection import ResearchFormatError, ResearchProjection

EXTENDED_MEDIA_TYPES=frozenset().union(
    WEBP_TYPES, FLAC_TYPES, OGG_TYPES, MP4_TYPES,
    GLB_TYPES, STL_TYPES, ICO_TYPES, TAR_TYPES,
)


def extract_extended_media(
    raw: bytes, mime: str, *, max_chars: int,
) -> ResearchProjection:
    for types, parser in (
        (WEBP_TYPES,extract_webp),
        (FLAC_TYPES,extract_flac),
        (OGG_TYPES,extract_ogg_opus),
        (MP4_TYPES,extract_mp4),
        (GLB_TYPES,extract_glb),
        (STL_TYPES,extract_binary_stl),
        (ICO_TYPES,extract_ico),
        (TAR_TYPES,extract_tar),
    ):
        if mime in types:
            return parser(raw,max_chars=max_chars)
    raise ResearchFormatError("unapproved extended binary metadata")
