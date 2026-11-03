"""Launch-ready event bus and save/load.

Simple, immediately usable systems the app needs at launch.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
import json
import time


class EventBus:
    """In-process pub/sub for game and AI events."""

    def __init__(self) -> None:
        self._subs: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._log: List[Dict[str, Any]] = []

    def subscribe(self, event: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        self._subs.setdefault(event, []).append(handler)

    def publish(self, event: str, payload: Optional[Dict[str, Any]] = None) -> int:
        payload = payload or {}
        record = {"event": event, "payload": payload, "ts": time.time()}
        self._log.append(record)
        handlers = self._subs.get(event, [])
        for h in handlers:
            try:
                h(payload)
            except Exception:
                pass  # fail-soft on individual handlers
        return len(handlers)

    def history(self, event: Optional[str] = None) -> List[Dict[str, Any]]:
        if event is None:
            return list(self._log)
        return [r for r in self._log if r["event"] == event]

    def clear(self) -> None:
        self._log.clear()


class SaveSystem:
    """Minimal JSON save/load for player state and session data."""

    def __init__(self) -> None:
        self._slots: Dict[str, Dict[str, Any]] = {}

    def save(self, slot: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not slot:
            return {"ok": False, "reason": "empty_slot"}
        self._slots[slot] = {
            "data": data,
            "saved_at": time.time(),
        }
        return {"ok": True, "slot": slot, "size": len(json.dumps(data, default=str))}

    def load(self, slot: str) -> Dict[str, Any]:
        if slot not in self._slots:
            return {"ok": False, "reason": "not_found"}
        entry = self._slots[slot]
        return {"ok": True, "slot": slot, "data": entry["data"], "saved_at": entry["saved_at"]}

    def list_slots(self) -> List[str]:
        return list(self._slots.keys())

    def delete(self, slot: str) -> Dict[str, Any]:
        if slot in self._slots:
            del self._slots[slot]
            return {"ok": True, "slot": slot}
        return {"ok": False, "reason": "not_found"}
