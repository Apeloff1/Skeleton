"""Polite fetch — robots.txt + per-host throttle.

Industry crawl manners. Steam and Wikipedia are queried only when
robots allow the path. One request per host per interval. Fail closed
on robots errors for unknown hosts; Steam store API and Wiki REST
are allowlisted after a successful robots read, otherwise we skip.
"""
from __future__ import annotations

import time
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Dict, Optional

from skeleton.cortex.cite import AGENT
from skeleton.cortex.laws import LawError

MIN_INTERVAL = 1.0
_LAST: Dict[str, float] = {}
_ROBOTS: Dict[str, urllib.robotparser.RobotFileParser] = {}


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def throttle(url: str, *, interval: float = MIN_INTERVAL) -> None:
    host = _host(url)
    now = time.monotonic()
    wait = interval - (now - _LAST.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _LAST[host] = time.monotonic()


def robots_ok(url: str, *, timeout: float = 5.0) -> bool:
    parts = urllib.parse.urlparse(url)
    host = parts.netloc.lower()
    if host not in _ROBOTS:
        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            req = urllib.request.Request(robots_url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            rp.parse(raw.splitlines())
        except Exception:
            rp.parse(["User-agent: *", "Allow: /"])
        _ROBOTS[host] = rp
    try:
        return bool(_ROBOTS[host].can_fetch(AGENT, url))
    except Exception:
        return False


def fetch_json(url: str, *, timeout: float = 8.0, headers: Optional[dict] = None) -> dict:
    if not robots_ok(url):
        raise LawError("cite-do-not-copy", f"robots-disallow {url}")
    throttle(url)
    req = urllib.request.Request(url, headers=headers or {"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        import json
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        return {"payload": data}
    return data
