"""Inert MIME dispatch for scientific, archival and research text artifacts."""
from __future__ import annotations

from .bibliography_documents import (
    BIBLIOGRAPHY_MEDIA_TYPES, extract_ris, extract_bibtex,
)
from .calendar_documents import CALENDAR_MEDIA_TYPES, extract_calendar
from .notebook_documents import NOTEBOOK_MEDIA_TYPES, extract_notebook
from .rdf_documents import RDF_MEDIA_TYPES, extract_rdf_lines
from .timed_media import TIMED_MEDIA_TYPES, extract_timed_media
from .research_projection import ResearchFormatError, ResearchProjection

RESEARCH_ARTIFACT_TYPES = frozenset().union(
    BIBLIOGRAPHY_MEDIA_TYPES, CALENDAR_MEDIA_TYPES, NOTEBOOK_MEDIA_TYPES,
    RDF_MEDIA_TYPES, TIMED_MEDIA_TYPES,
)


def extract_research_artifact(
    raw: str, media_type: str, *, max_chars: int, max_links: int,
) -> ResearchProjection:
    """No URL discovery or executable output from any admitted artifact."""
    if media_type in TIMED_MEDIA_TYPES:
        return extract_timed_media(
            raw, media_type, max_chars=max_chars, max_links=max_links,
        )
    if media_type in CALENDAR_MEDIA_TYPES:
        return extract_calendar(raw, max_chars=max_chars, max_links=max_links)
    if media_type in NOTEBOOK_MEDIA_TYPES:
        return extract_notebook(raw, max_chars=max_chars, max_links=max_links)
    if media_type in RDF_MEDIA_TYPES:
        return extract_rdf_lines(
            raw, media_type, max_chars=max_chars, max_links=max_links,
        )
    if media_type in BIBLIOGRAPHY_MEDIA_TYPES:
        fn = extract_bibtex if "bibtex" in media_type else extract_ris
        return fn(raw, max_chars=max_chars, max_links=max_links)
    raise ResearchFormatError("unapproved external research artifact format")
