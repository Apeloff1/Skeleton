"""Telemetry SSE facade (GB-30). Default off. No operator route edit."""

from __future__ import annotations

from skeleton.telemetry.capabilities import capabilities
from skeleton.telemetry.law import PACKET, PATH, VERSION
from skeleton.telemetry.sse import Stream
from skeleton.telemetry.store import EventStore

__all__ = ["PACKET", "PATH", "VERSION", "EventStore", "Stream", "capabilities"]
