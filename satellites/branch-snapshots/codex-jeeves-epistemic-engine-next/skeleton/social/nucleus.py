"""Bind wiki nucleus URLs when a stimulus carries no pointers."""
from __future__ import annotations

from typing import Any, Dict, List


def wiki_urls(mesh, *, k: int = 3) -> List[str]:
    vals = [str(v) for v in (mesh.wiki.topics or {}).values() if str(v).startswith("http")]
    return vals[: max(1, k)]


def bind_if_empty(social: Dict[str, Any], mesh, *, live: bool = False) -> Dict[str, Any]:
    if social.get("cards"):
        return social
    urls = wiki_urls(mesh)
    if not urls:
        return social
    from skeleton.social.ingest import ingest
    extra = ingest(" ".join(urls), live=live)
    extra["from_nucleus"] = 1
    return extra
