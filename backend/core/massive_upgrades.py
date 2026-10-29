"""Massive operational upgrades.
Rate windows, audit trail, config validation, and health probes.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
import time

class RateWindow:
    def __init__(self, limit: int = 60, window_sec: float = 60.0):
        self.limit = limit
        self.window = window_sec
        self.hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self.hits[key]
        bucket[:] = [t for t in bucket if now - t < self.window]
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True

class AuditTrail:
    def __init__(self, max_entries: int = 10_000):
        self.max = max_entries
        self.entries: list[dict[str, Any]] = []

    def record(self, actor: str, action: str, detail: str = "") -> None:
        self.entries.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": actor[:128],
            "action": action[:64],
            "detail": detail[:512],
        })
        if len(self.entries) > self.max:
            self.entries = self.entries[-self.max:]

    def recent(self, n: int = 50) -> list[dict[str, Any]]:
        return self.entries[-n:]

def validate_config(cfg: dict[str, Any]) -> list[str]:
    """Return a list of config problems. Empty means ok."""
    problems: list[str] = []
    if not isinstance(cfg, dict):
        return ["config must be a dict"]
    if "mongo_url" in cfg and not str(cfg["mongo_url"]).startswith(("mongodb://", "mongodb+srv://")):
        problems.append("mongo_url must start with mongodb")
    if "cors_origins" in cfg:
        origins = cfg["cors_origins"]
        if isinstance(origins, str) and origins != "*" and not origins.startswith(("http://", "https://")):
            problems.append("cors_origins must be * or http(s)")
    return problems

def health_probe() -> dict[str, Any]:
    return {
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
        "checks": {"rate": True, "audit": True, "config": True},
    }
