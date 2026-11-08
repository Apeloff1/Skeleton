"""IIIF Presentation 3 Manifest metadata projected as inert source evidence.

No image-service requests, canvas rendering, annotation fetch, full-text
publication, rights inference, audio/video decode or external JSON-LD
context dereferencing occurs here. This is a finite *source assertion*.
"""
from __future__ import annotations

import math

from .archive_catalog_common import CatalogDiscoveryError, load_json_catalog
from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

IIIF_DOCUMENT_TYPES = frozenset({"application/vnd.iiif.presentation+json"})
_CONTEXTS = frozenset({
    "https://iiif.io/api/presentation/3/context.json",
    "http://iiif.io/api/presentation/3/context.json",
})


def _label(value: object) -> str:
    if not isinstance(value, dict) or len(value) > 16:
        return ""
    for lang in ("en", "none", *sorted(value)):
        rows = value.get(lang)
        if (isinstance(rows, list) and 1 <= len(rows) <= 8
                and all(isinstance(item, str) and len(item) <= 2048 for item in rows)):
            return " | ".join(x.strip() for x in rows)[:512]
    return ""


def extract_iiif_manifest(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    try:
        document = load_json_catalog(raw.encode("utf-8"))
    except CatalogDiscoveryError as exc:
        raise ResearchFormatError(str(exc)) from exc
    context = document.get("@context")
    if (not isinstance(context, str) or context not in _CONTEXTS
            or document.get("type") != "Manifest"):
        raise ResearchFormatError("source is not a supported IIIF v3 Manifest")
    items = document.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 256:
        raise ResearchFormatError("IIIF Manifest canvas capacity invalid")
    label = _label(document.get("label")) or "Unlabeled IIIF Manifest"
    summary = _label(document.get("summary"))
    metadata = document.get("metadata", [])
    if not isinstance(metadata, list) or len(metadata) > 64:
        raise ResearchFormatError("IIIF Manifest metadata count exceeded")
    lines = [
        "IIIF Presentation 3 Manifest (unreviewed public-source metadata)",
        f"Title: {label}",
        f"Canvas count: {len(items)}",
    ]
    if summary:
        lines.append(f"Summary: {summary}")
    visual = 0
    timed = 0
    for i, canvas in enumerate(items, 1):
        if not isinstance(canvas, dict) or canvas.get("type") != "Canvas":
            raise ResearchFormatError("IIIF Manifest contains invalid Canvas row")
        w, h, duration = canvas.get("width"), canvas.get("height"), canvas.get("duration")
        if w is not None or h is not None:
            if (type(w) is not int or type(h) is not int or
                    not 1 <= w <= 32768 or not 1 <= h <= 32768):
                raise ResearchFormatError("IIIF Canvas dimensions invalid")
            visual += 1
        if duration is not None:
            if (type(duration) not in (int, float)
                    or not math.isfinite(duration)
                    or not 0 < duration <= 86400):
                raise ResearchFormatError("IIIF Canvas duration invalid")
            timed += 1
    lines.extend([
        f"Dimensioned canvases: {visual}; timed canvases: {timed}",
        "Canvas content and remote image services: not acquired",
    ])
    for item in metadata:
        if not isinstance(item, dict):
            raise ResearchFormatError("invalid IIIF metadata declaration")
        name, value = _label(item.get("label")), _label(item.get("value"))
        if name and value:
            lines.append(f"Declared metadata: {name}: {value}")
    lines.append("Source rights, licences and external annotations: not verified or fetched")
    return project_lines(lines, title=label, max_chars=max_chars)
