"""ArchiveX / Wayback pointer factory.

Xarchive indexes Wayback CDX. It stores no post copies. House does
the same: we mint a capture pointer (original URL + archive URL +
timestamp slot) and refuse bodies.

Throttle: at most one synthetic CDX URL per call; no network in the
default path. Live fetch is opt-in and still stores only headers.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional
from urllib.parse import quote

XARCHIVE_ABOUT = "https://xarchive.net/about"
CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK = "https://web.archive.org/web/"

_STATUS_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:x|twitter)\.com/([^/]+)/status/(\d+)",
    re.I,
)
_ARXIV_RE = re.compile(r"(?:https?://)?arxiv\.org/(?:abs|html|pdf)/([0-9.]+)", re.I)


def parse_x_status(text: str) -> Optional[Dict[str, str]]:
    m = _STATUS_RE.search(text or "")
    if not m:
        return None
    handle, pid = m.group(1), m.group(2)
    orig = f"https://x.com/{handle}/status/{pid}"
    return {
        "kind": "x-status",
        "handle": handle,
        "post_id": pid,
        "url": orig,
        "xarchive": f"https://xarchive.net/?q={quote(orig)}",
        "cdx": f"{CDX}?url={quote(orig)}&output=json",
        "wayback": f"{WAYBACK}*/{orig}",
        "stored_prose": "0",
    }


def parse_arxiv(text: str) -> Optional[Dict[str, str]]:
    m = _ARXIV_RE.search(text or "")
    if not m:
        return None
    aid = m.group(1)
    return {
        "kind": "arxiv",
        "arxiv_id": aid,
        "url": f"https://arxiv.org/abs/{aid}",
        "html": f"https://arxiv.org/html/{aid}",
        "stored_prose": "0",
    }


def pointer(url: str) -> Dict[str, Any]:
    """Mint a citation card. Never fetches the body."""
    xs = parse_x_status(url)
    if xs:
        return {**xs, "via": "archivex-pointer"}
    ax = parse_arxiv(url)
    if ax:
        return {**ax, "via": "arxiv-pointer"}
    raw = (url or "").strip()
    if raw.startswith("http"):
        return {
            "kind": "url",
            "url": raw.split()[0],
            "xarchive": f"https://xarchive.net/?q={quote(raw.split()[0])}",
            "cdx": f"{CDX}?url={quote(raw.split()[0])}&output=json",
            "via": "url-pointer",
            "stored_prose": 0,
        }
    return {"kind": "none", "stored_prose": 0}


def wayback_cdx_url(original: str) -> str:
    return f"{CDX}?url={quote(original)}&output=json&fl=timestamp,original,statuscode,mimetype"
