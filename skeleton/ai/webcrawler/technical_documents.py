"""Explicit MIME dispatch for finite external technical research documents."""
from __future__ import annotations

from .geojson_documents import GEOJSON_MEDIA_TYPES, extract_geojson
from .openapi_documents import OPENAPI_MEDIA_TYPES, extract_openapi
from .jsonschema_documents import JSONSCHEMA_MEDIA_TYPES, extract_jsonschema
from .tsv_documents import TSV_MEDIA_TYPES, extract_tsv
from .research_projection import ResearchFormatError, ResearchProjection

TECHNICAL_MEDIA_TYPES = frozenset().union(
    GEOJSON_MEDIA_TYPES, OPENAPI_MEDIA_TYPES, JSONSCHEMA_MEDIA_TYPES,
    TSV_MEDIA_TYPES,
)


def extract_technical_document(
    raw: str, media_type: str, *, max_chars: int, max_links: int,
) -> ResearchProjection:
    mapping = (
        (GEOJSON_MEDIA_TYPES, extract_geojson),
        (OPENAPI_MEDIA_TYPES, extract_openapi),
        (JSONSCHEMA_MEDIA_TYPES, extract_jsonschema),
        (TSV_MEDIA_TYPES, extract_tsv),
    )
    for types, parser in mapping:
        if media_type in types:
            return parser(raw, max_chars=max_chars, max_links=max_links)
    raise ResearchFormatError("unapproved technical source MIME type")
