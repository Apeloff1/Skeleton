#!/usr/bin/env python3
"""Fail-closed GB-30 gate. Exit 2 on miss."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.telemetry import EventStore, Stream  # noqa: E402


def main() -> int:
    store = EventStore()
    store.append("forge")
    store.append("gossip")
    if Stream(store).open():
        print("GB-30 FAIL default-on")
        return 2
    frames = Stream(store, enabled=True).client_read(2)
    if len(frames) != 2:
        print("GB-30 FAIL frames", len(frames))
        return 2
    print("GB-30 OK default-off two-events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
