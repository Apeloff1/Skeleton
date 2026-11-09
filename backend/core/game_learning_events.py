"""Bounded derived frame delivery for existing game-learning authorities."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

MAX_EVENT_BYTES = 2 * 1024 * 1024
MAX_STREAM_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


class FrameCursorError(ValueError):
    pass


class GameFrameHub:
    def __init__(self):
        self.streams: dict[str, dict[str, Any]] = {}
        self.total_bytes = 0

    def open(self, resource_id: str, stream_id: str | None = None) -> str:
        identifier = stream_id or str(uuid4())
        if identifier not in self.streams:
            self._expire()
            if len(self.streams) >= 128:
                oldest = min(self.streams, key=lambda key: self.streams[key]["touched"])
                self._drop(oldest)
            self.streams[identifier] = {
                "resource_id": resource_id,
                "sequence": 0,
                "rows": deque(),
                "bytes": 0,
                "touched": time.monotonic(),
                "changed": asyncio.Event(),
            }
        elif self.streams[identifier]["resource_id"] != resource_id:
            raise FrameCursorError("stream belongs to another resource")
        return identifier

    def _drop(self, identifier):
        row = self.streams.pop(identifier)
        self.total_bytes -= row["bytes"]
        row["changed"].set()

    def _expire(self):
        for key, row in tuple(self.streams.items()):
            if time.monotonic() - row["touched"] > 900:
                self._drop(key)

    def publish(
        self, resource_id: str, stream_id: str, payload: dict, *, event="frame", sequence: int | None = None
    ):
        self.open(resource_id, stream_id)
        stream = self.streams[stream_id]
        value = stream["sequence"] + 1 if sequence is None else sequence
        if type(value) is not int or value <= stream["sequence"]:
            raise FrameCursorError("actual event sequence must advance")
        row = {
            "stream_id": stream_id,
            "sequence": value,
            "event": event,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(encoded) > MAX_EVENT_BYTES:
            raise FrameCursorError("actual frame exceeds delivery byte limit")
        stream["rows"].append((row, len(encoded)))
        stream["bytes"] += len(encoded)
        self.total_bytes += len(encoded)
        stream["sequence"] = value
        stream["touched"] = time.monotonic()
        while len(stream["rows"]) > 128 or stream["bytes"] > MAX_STREAM_BYTES:
            _, size = stream["rows"].popleft()
            stream["bytes"] -= size
            self.total_bytes -= size
        while self.total_bytes > MAX_TOTAL_BYTES:
            candidate = min(
                (key for key in self.streams if self.streams[key]["rows"]),
                key=lambda key: self.streams[key]["touched"],
            )
            _, size = self.streams[candidate]["rows"].popleft()
            self.streams[candidate]["bytes"] -= size
            self.total_bytes -= size
        stream["changed"].set()
        return row

    def read(self, resource_id: str, stream_id: str, after: int):
        if type(after) is not int or after < 0:
            raise FrameCursorError("cursor must be a nonnegative integer")
        stream = self.streams.get(stream_id)
        if stream is None or stream["resource_id"] != resource_id:
            raise FrameCursorError("stream is unavailable; reload current state")
        if after > stream["sequence"]:
            raise FrameCursorError("cursor is ahead of actual events")
        rows = [row for row, _ in stream["rows"]]
        if rows and after and after < rows[0]["sequence"] - 1:
            raise FrameCursorError("cursor expired; reload current state")
        return [row for row in rows if row["sequence"] > after]

    async def wait(self, stream_id: str, timeout=1.0):
        stream = self.streams.get(stream_id)
        if stream is None:
            return
        stream["changed"].clear()
        try:
            await asyncio.wait_for(stream["changed"].wait(), timeout)
        except TimeoutError:
            return


frame_hub = GameFrameHub()
