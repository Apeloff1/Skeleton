"""Tiny validation harness for era/room JSON files (STU-ERAS slice 2).

Usage::

    python -m skeleton.simulation.era.scripting.cli FILE [FILE ...]
        [--base FILE ...] [--templates FILE]

Each FILE is one era. ``--base`` files supply eras that FILEs may ``extends``
(keyed by their ``id``). ``--templates`` is a JSON object of room templates.
Prints one JSON line per FILE and exits 0 only when every FILE is valid.
Local files only; no network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from skeleton.simulation.era.scripting.compose import load_composed
from skeleton.simulation.era.scripting.loader import MAX_BYTES
from skeleton.simulation.era.scripting.schema import SchemaError


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise SchemaError("missing-file", str(path), "not a file")
    if path.stat().st_size > MAX_BYTES:
        raise SchemaError("too-large", str(path), f"max {MAX_BYTES} bytes")
    try:
        return json.loads(path.read_bytes())
    except (ValueError, UnicodeDecodeError) as exc:
        raise SchemaError("bad-json", str(path), str(exc)) from None


def validate_file(path: Path, bases: dict[str, Any], templates: dict[str, Any]) -> dict[str, Any]:
    try:
        data = _read_json(path)
        if not isinstance(data, dict):
            raise SchemaError("bad-type", str(path), "expected object")
        era = load_composed(data, bases, templates)
    except SchemaError as exc:
        return {"file": str(path), "ok": False, "error": exc.as_dict()}
    return {"file": str(path), "ok": True, "era": era.id, "rooms": len(era.rooms)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="era-validate", description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--base", action="append", default=[], type=Path)
    parser.add_argument("--templates", type=Path)
    args = parser.parse_args(argv)
    try:
        bases: dict[str, Any] = {}
        for p in args.base:
            raw = _read_json(p)
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                raise SchemaError("bad-base", str(p), "base era needs a string id")
            if raw["id"] in bases:
                raise SchemaError("duplicate-base", str(p), raw["id"])
            bases[raw["id"]] = raw
        templates: dict[str, Any] = {}
        if args.templates is not None:
            templates = _read_json(args.templates)
            if not isinstance(templates, dict):
                raise SchemaError("bad-templates", str(args.templates), "expected object")
    except SchemaError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, sort_keys=True))
        return 2
    ok = True
    for path in args.files:
        result = validate_file(path, bases, templates)
        ok = ok and result["ok"]
        print(json.dumps(result, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
