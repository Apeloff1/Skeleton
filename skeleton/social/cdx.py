"""Opt-in Wayback CDX probe — headers / first row only.

Default off. Enable with live=True or SKELETON_CDX=1.
Throttle: one request per host per second. Timeout 2s. Read cap 2KB.
Stores timestamp + statuscode. Never stores the capture body.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from skeleton.social.archivex import wayback_cdx_url

_LAST: Dict[str, float] = {}
_MIN_GAP = 1.0
_CAP = 2048


def enabled(live: bool = False) -> bool:
    if live:
        return True
    return str(os.environ.get("SKELETON_CDX") or "") in {"1", "true", "yes"}


def probe(original: str, *, live: bool = False, opener=None) -> Dict[str, Any]:
    card = {
        "kind": "cdx-probe",
        "url": (original or "")[:240],
        "live": 0,
        "stored_prose": 0,
    }
    if not original or not enabled(live):
        card["reason"] = "offline"
        return card
    host = urlparse("https://web.archive.org").hostname or "web.archive.org"
    now = time.monotonic()
    if now - _LAST.get(host, 0.0) < _MIN_GAP:
        card["reason"] = "throttled"
        return card
    _LAST[host] = now
    cdx = wayback_cdx_url(original)
    card["cdx"] = cdx
    fetch = opener or _fetch
    try:
        raw = fetch(cdx)
    except Exception as exc:
        card["reason"] = type(exc).__name__
        return card
    card["live"] = 1
    card.update(_parse_cdx(raw))
    return card


def _cap() -> int:
    try:
        from skeleton.organism.caps import live as live_caps
        return int(live_caps().cdx_bytes)
    except Exception:
        return _CAP


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "SkeletonOrganism/1.0 (+research; header-only)"})
    with urllib.request.urlopen(req, timeout=2) as resp:
        return resp.read(_cap()).decode("utf-8", "replace")


def _parse_cdx(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {"captures": 0}
    try:
        data = json.loads(text if text.startswith("[") else f"[{text}]")
    except json.JSONDecodeError:
        return {"captures": 0, "raw_kind": "non-json"}
    rows = data[1:] if data and data[0] and str(data[0][0]).lower() == "timestamp" else data
    if not rows:
        return {"captures": 0}
    first = rows[0]
    ts = str(first[0]) if first else ""
    status = str(first[2]) if len(first) > 2 else ""
    return {"captures": min(len(rows), 32), "timestamp": ts[:14], "status": status[:8]}


def reset_throttle() -> None:
    _LAST.clear()
