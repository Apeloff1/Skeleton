"""Citations — schema.org CreativeWork + SPDX. Industry shape.

A reference is not a copy. It is:
  @type CreativeWork
  identifier (Steam appid)
  name
  url
  license (SPDX id or LicenseRef)
  citation (how to credit)
  retrieved (ISO-8601, only when parse_ref ran)

No article body. No store blurb.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


SPDX_STEAM = "LicenseRef-Steam-Store-Terms"
SPDX_WIKI = "CC-BY-SA-4.0"
AGENT = "SkeletonGenos/1.0 (+https://github.com/Apeloff1/Skeleton; cite-do-not-copy)"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def steam_cite(appid: int, title: str, *, era: str = "", dialect: str = "") -> Dict[str, Any]:
    url = f"https://store.steampowered.com/app/{int(appid)}/"
    return {
        "@context": "https://schema.org",
        "@type": "VideoGame",
        "identifier": f"steam:{int(appid)}",
        "name": title,
        "url": url,
        "genre": era or None,
        "license": SPDX_STEAM,
        "citation": f"{title}. Steam Store. {url}",
        "dialect": dialect,
        "stored_prose": 0,
    }


def wiki_cite(title: str) -> Dict[str, Any]:
    slug = title.replace(" ", "_")
    url = f"https://en.wikipedia.org/wiki/{slug}"
    return {
        "@context": "https://schema.org",
        "@type": "CreativeWork",
        "name": title,
        "url": url,
        "license": SPDX_WIKI,
        "citation": f'"{title}," Wikipedia, {url} (CC BY-SA 4.0)',
        "stored_prose": 0,
    }


def stamp(card: Dict[str, Any], *, retrieved: Optional[str] = None) -> Dict[str, Any]:
    out = dict(card)
    out["retrieved"] = retrieved or utc_now()
    return out
