#!/usr/bin/env python3
"""Validate the explicit, time-bounded flaky-test quarantine registry."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / ".ci" / "flaky-tests.json"
MAX_QUARANTINE_DAYS = 30
REQUIRED_FIELDS = {"id", "test", "owner", "reason", "expires"}


def fail(message: str) -> int:
    print(f"Flaky quarantine policy violation: {message}", file=sys.stderr)
    return 1


def main() -> int:
    try:
        payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return fail(f"cannot load {REGISTRY.relative_to(ROOT)}: {exc}")

    if payload.get("version") != 1 or not isinstance(payload.get("quarantines"), list):
        return fail("registry must contain version=1 and a quarantines list")

    today = date.today()
    seen: set[str] = set()
    errors: list[str] = []
    for index, entry in enumerate(payload["quarantines"], start=1):
        if not isinstance(entry, dict):
            errors.append(f"entry {index} is not an object")
            continue
        missing = REQUIRED_FIELDS - entry.keys()
        if missing:
            errors.append(f"entry {index} missing fields: {', '.join(sorted(missing))}")
            continue
        identifier = str(entry["id"]).strip()
        if not identifier or identifier in seen:
            errors.append(f"entry {index} has an empty or duplicate id")
        seen.add(identifier)
        if not all(str(entry[field]).strip() for field in ("test", "owner", "reason")):
            errors.append(f"entry {identifier or index} has blank metadata")
        try:
            expires = datetime.strptime(str(entry["expires"]), "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"entry {identifier or index} has invalid expires date")
            continue
        if expires < today:
            errors.append(f"entry {identifier or index} expired on {expires.isoformat()}")
        if (expires - today).days > MAX_QUARANTINE_DAYS:
            errors.append(
                f"entry {identifier or index} expires more than {MAX_QUARANTINE_DAYS} days from now"
            )

    if errors:
        print("Flaky quarantine policy violations:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Flaky quarantine policy passed: {len(payload['quarantines'])} active quarantine(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
