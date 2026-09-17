"""Bind era citations on game sessions. stored_prose stays 0."""

from __future__ import annotations

from typing import Any


HOUSE_ERA = "extraction_now"
ALLOWED_ERAS = frozenset(
    {
        "extraction_now",
        "heat_discipline",
        "scavenge_rights",
        "forge_yard",
        "last_extract",
    }
)
MAX_TITLE = 120


class EraBindError(ValueError):
    """Era bind contract violation."""


def bind_era(
    *,
    era: str = HOUSE_ERA,
    title: str = "NEXUS-EXTRACT",
    citation: str = "#807",
    url: str = "https://github.com/Apeloff1/Skeleton/issues/807",
) -> dict[str, Any]:
    name = str(era or "").strip().lower()
    if name not in ALLOWED_ERAS:
        raise EraBindError(f"unknown era: {era}")
    heading = str(title or "").strip()
    if not heading or len(heading) > MAX_TITLE:
        raise EraBindError("title invalid")
    if " " in heading and len(heading.split()) > 12:
        raise EraBindError("title looks like stored prose")
    cite = str(citation or "").strip()
    if not cite:
        raise EraBindError("citation required")
    link = str(url or "").strip()
    if not link.startswith("https://"):
        raise EraBindError("citation url must be https")
    return {
        "title": heading,
        "era": name,
        "citation": cite,
        "url": link,
        "stored_prose": 0,
    }
