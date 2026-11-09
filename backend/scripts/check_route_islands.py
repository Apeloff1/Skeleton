#!/usr/bin/env python3
"""Fail closed when FastAPI route modules have no runtime owner."""
from __future__ import annotations

import json

from core.route_islands import build_route_island_report


def main() -> int:
    report = build_route_island_report()
    print(json.dumps(report, indent=2))
    islands = report["islands"]
    if islands:
        print(f"route island audit: FAIL ({len(islands)} unintegrated router module(s))")
        return 1
    print("route island audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
