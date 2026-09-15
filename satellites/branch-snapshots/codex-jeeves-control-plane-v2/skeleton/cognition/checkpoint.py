"""Versioned in-memory checkpoint manager with deterministic digests."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True, slots=True)
class Checkpoint:
    name: str
    version: int
    payload: dict[str, Any]
    digest: str

class CheckpointManager:
    SCHEMA = 1
    def __init__(self) -> None:
        self._items: dict[str, Checkpoint] = {}

    @classmethod
    def _digest(cls, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(raw).hexdigest()

    def save(self, name: str, payload: dict[str, Any], *, version: int = 1) -> Checkpoint:
        if not name or version < 1:
            raise ValueError("invalid checkpoint identity")
        wrapped = {"schema": self.SCHEMA, "version": version, "payload": payload}
        cp = Checkpoint(name, version, json.loads(json.dumps(wrapped, sort_keys=True, default=str)), self._digest(wrapped))
        self._items[name] = cp
        return cp

    def load(self, name: str, *, verify: bool = True) -> dict[str, Any]:
        cp = self._items[name]
        if verify and self._digest(cp.payload) != cp.digest:
            raise ValueError(f"checkpoint integrity failure: {name}")
        return dict(cp.payload.get("payload") or {})

    def restore(self, name: str, apply: Callable[[dict[str, Any]], None]) -> Checkpoint:
        cp = self._items[name]
        apply(self.load(name))
        return cp

    def delete(self, name: str) -> None:
        self._items.pop(name, None)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))

    def export(self) -> str:
        data = {name: {"version": cp.version, "payload": cp.payload, "digest": cp.digest} for name, cp in sorted(self._items.items())}
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

__all__ = ["Checkpoint", "CheckpointManager"]
