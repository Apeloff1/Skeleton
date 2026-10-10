"""Canonical serialization, digests, and diffs for era data (STU-ERAS slice 4).

One era can be written many ways: rooms in any order, exits in any order,
tags shuffled, defaults spelled out or omitted. This module maps every
equivalent spelling of a validated :class:`EraSpec` to one canonical form so
that tooling can

* store eras in a stable, review-friendly layout (``dumps_canonical``),
* cache or pin an era by content (``digest``),
* gate checked-in files on formatting (``python -m ...canonical --check``),
* and report what actually changed between two versions (``diff_eras``).

Canonical form rules (all deterministic, stdlib-only, no network, no forge
writes):

* rooms sorted by ``id`` (room order carries no meaning; ``start`` does);
* exits sorted by :data:`DIRECTIONS` order;
* era and room tags sorted;
* JSON object keys sorted; default-valued exit fields omitted (as
  :meth:`ExitSpec.to_dict` already does);
* compact form uses ``(",", ":")`` separators; pretty form uses a 2-space
  indent and a trailing newline. Both are UTF-8 with non-ASCII kept as-is.

Canonicalization always goes through :meth:`EraSpec.from_dict`, so the output
re-validates by construction (``roundtrip``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from skeleton.simulation.era.scripting.loader import MAX_BYTES, load_era_json
from skeleton.simulation.era.scripting.schema import DIRECTIONS, EraSpec, RoomSpec, SchemaError

DIGEST_ALGO = "sha256"
_RANK = {d: i for i, d in enumerate(DIRECTIONS)}
_ERA_FIELDS = ("title", "order", "start", "citation", "tags", "schema")
_ROOM_FIELDS = ("name", "kind", "depth", "tags", "exits")


def _require_era(era: Any) -> EraSpec:
    if not isinstance(era, EraSpec):
        raise SchemaError("bad-type", "era", f"expected EraSpec, got {type(era).__name__}")
    return era


def canonical_room(room: RoomSpec) -> dict[str, Any]:
    """Canonical mapping for one room (exits by direction rank, tags sorted)."""
    data = room.to_dict()
    data["tags"] = sorted(room.tags)
    data["exits"] = [e.to_dict() for e in sorted(room.exits, key=lambda e: _RANK[e.direction])]
    return data


def canonical_dict(era: EraSpec) -> dict[str, Any]:
    """Canonical mapping for an era. Equal for every equivalent spelling."""
    era = _require_era(era)
    data = era.to_dict()
    data["tags"] = sorted(era.tags)
    data["rooms"] = [canonical_room(r) for r in sorted(era.rooms, key=lambda r: r.id)]
    return data


def dumps_canonical(era: EraSpec, *, pretty: bool = False) -> str:
    """Serialize ``era`` to canonical JSON text."""
    data = canonical_dict(era)
    if pretty:
        return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(era: EraSpec) -> str:
    """Content digest of the compact canonical form, e.g. ``sha256:ab12...``."""
    blob = dumps_canonical(era).encode("utf-8")
    return f"{DIGEST_ALGO}:{hashlib.sha256(blob).hexdigest()}"


def roundtrip(era: EraSpec) -> EraSpec:
    """Re-validate the canonical form; result is :func:`equivalent` to ``era``."""
    return EraSpec.from_dict(json.loads(dumps_canonical(era)))


def equivalent(a: EraSpec, b: EraSpec) -> bool:
    """True when two eras differ only in spelling (order, defaults, tag order)."""
    return canonical_dict(a) == canonical_dict(b)


def is_canonical_text(text: str | bytes) -> bool:
    """True when ``text`` is exactly the pretty canonical form of a valid era."""
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            return False
    try:
        era = load_era_json(text)
    except SchemaError:
        return False
    return text == dumps_canonical(era, pretty=True)


def diff_eras(old: EraSpec, new: EraSpec) -> dict[str, Any]:
    """Stable, JSON-ready description of what changed from ``old`` to ``new``.

    Keys: ``same`` (bool), ``era`` (changed era-level field names, sorted),
    ``added`` / ``removed`` (room ids, sorted), ``changed`` (room id -> sorted
    changed field names). Spelling-only differences are ignored.
    """
    a, b = canonical_dict(old), canonical_dict(new)
    era_changes = [f for f in ("id",) + _ERA_FIELDS if a[f] != b[f]]
    rooms_a = {r["id"]: r for r in a["rooms"]}
    rooms_b = {r["id"]: r for r in b["rooms"]}
    added = sorted(set(rooms_b) - set(rooms_a))
    removed = sorted(set(rooms_a) - set(rooms_b))
    changed: dict[str, list[str]] = {}
    for rid in sorted(set(rooms_a) & set(rooms_b)):
        fields = [f for f in _ROOM_FIELDS if rooms_a[rid][f] != rooms_b[rid][f]]
        if fields:
            changed[rid] = fields
    return {
        "same": not (era_changes or added or removed or changed),
        "era": era_changes,
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """``era-canon FILE [FILE ...] [--check]``.

    Without ``--check``: print ``{"file", "ok", "digest"}`` per FILE (or the
    error). With ``--check``: additionally require each FILE to already be in
    pretty canonical form (``"canonical": false`` and exit 1 otherwise).
    Exit 0 only when every FILE passes. Never rewrites files.
    """
    parser = argparse.ArgumentParser(prog="era-canon", description="Canonical era JSON check")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    ok = True
    for path in args.files:
        result: dict[str, Any] = {"file": str(path)}
        try:
            if path.is_file() and path.stat().st_size > MAX_BYTES:
                raise SchemaError("too-large", str(path), f"max {MAX_BYTES} bytes")
            era = load_era_json(path)
            raw = path.read_bytes()
        except SchemaError as exc:
            result.update(ok=False, error=exc.as_dict())
        else:
            result.update(ok=True, era=era.id, digest=digest(era))
            if args.check:
                canon = is_canonical_text(raw)
                result["canonical"] = canon
                result["ok"] = canon
        ok = ok and result["ok"]
        print(json.dumps(result, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
