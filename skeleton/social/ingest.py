"""Social ingest — extract pointers from a stimulus, file as citation atoms.

Robots/throttle law: default path is regex-only. No GET. Bodies stay
on the far side of the URL.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from skeleton.social.archivex import parse_arxiv, parse_x_status, pointer
from skeleton.social.cdx import probe
from skeleton.social.sources import SOTA_POINTERS, classify

_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)


def extract_urls(text: str) -> List[str]:
    return _URL_RE.findall(text or "")


def ingest(stimulus: str, *, live: bool = False) -> Dict[str, Any]:
    urls = extract_urls(stimulus)
    cards: List[Dict[str, Any]] = []
    houses: List[str] = []
    for u in urls:
        card = pointer(u)
        src = classify(u)
        if src:
            card["source_id"] = src["id"]
            card["house"] = src["house"]
            houses.append(str(src["id"]))
        cards.append(card)
    xs = parse_x_status(stimulus)
    if xs and not any(c.get("kind") == "x-status" for c in cards):
        cards.append({**xs, "source_id": "x-status", "house": "X"})
        houses.append("x-status")
    ax = parse_arxiv(stimulus)
    if ax and not any(c.get("kind") == "arxiv" for c in cards):
        cards.append({**ax, "source_id": "arxiv", "house": "arXiv"})
        houses.append("arxiv")
    probes: List[Dict[str, Any]] = []
    if live:
        for card in cards[:2]:
            target = str(card.get("url") or "")
            if target.startswith("http"):
                probes.append(probe(target, live=True))
    return {
        "kind": "social-ingest",
        "urls": urls,
        "cards": cards,
        "houses": sorted(set(houses)),
        "x_posts": sum(1 for c in cards if c.get("kind") == "x-status"),
        "papers": sum(1 for c in cards if c.get("kind") == "arxiv"),
        "archives": sum(1 for c in cards if "xarchive" in c or c.get("kind") == "url"),
        "cdx": probes,
        "stored_prose": 0,
    }


def seed_sota() -> List[Dict[str, str]]:
    return [dict(p) for p in SOTA_POINTERS]
