#!/usr/bin/env python3
"""Verify an already-built wheel carries the recovered native JSON inventory.

No extraction, model execution, or network. Fail if any source member is
missing, duplicated, altered, or represented by an unexpected ZIP member.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "skeleton/ai/runtime/operational_ai/"
COUNTS = {
    "durable_jobs": 672,
    "guarded_request": 384,
    "native_candidate": 864,
    "native_genesis": 288,
    "native_qualification": 480,
    "native_supervised": 768,
}
MAX_RECORD_BYTES = 1024 * 1024
MAX_WHEEL_ENTRIES = 150_000


def inventory() -> dict[str, tuple[int, str]]:
    expected = {}
    for name, count in COUNTS.items():
        root = ROOT / PREFIX / name
        members = sorted(root.rglob("*.json"))
        if len(members) != count:
            raise ValueError(f"{name}: expected {count} source records, got {len(members)}")
        for member in members:
            if member.is_symlink() or not member.is_file():
                raise ValueError(f"invalid source member: {member}")
            with member.open("rb") as source:
                raw = source.read(MAX_RECORD_BYTES + 1)
            if not raw or len(raw) > MAX_RECORD_BYTES:
                raise ValueError(f"invalid source size: {member}")
            expected[member.relative_to(ROOT).as_posix()] = (len(raw), sha256(raw).hexdigest())
    return expected


def verify(wheel: Path) -> int:
    expected = inventory()
    prefixes = tuple(PREFIX + name + "/" for name in COUNTS)
    found = set()
    with ZipFile(wheel) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_WHEEL_ENTRIES:
            raise ValueError("wheel entry ceiling")
        for entry in entries:
            name = entry.filename
            if not name.startswith(prefixes) or not name.lower().endswith(".json"):
                continue
            if name not in expected or name in found:
                raise ValueError(f"unexpected or duplicate wheel record: {name}")
            size, digest = expected[name]
            if entry.is_dir() or entry.file_size != size or size > MAX_RECORD_BYTES:
                raise ValueError(f"wheel size mismatch: {name}")
            with archive.open(entry) as member:
                raw = member.read(MAX_RECORD_BYTES + 1)
            if len(raw) != size or sha256(raw).hexdigest() != digest:
                raise ValueError(f"wheel digest mismatch: {name}")
            found.add(name)
    missing = expected.keys() - found
    if missing:
        raise ValueError(f"missing {len(missing)} wheel records; first: {min(missing)}")
    return len(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    try:
        count = verify(args.wheel)
    except (OSError, ValueError, RuntimeError, EOFError) as exc:
        print(f"native wheel inventory: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"native wheel inventory: PASS ({count} byte-verified records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
