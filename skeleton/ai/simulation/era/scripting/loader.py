"""Loaders for era/room data. Fail-closed; never touches the network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from skeleton.simulation.era.scripting.schema import EraSpec, SchemaError

MAX_BYTES = 2 * 1024 * 1024


def load_era(data: Any) -> EraSpec:
    """Validate a decoded mapping and return an :class:`EraSpec`."""
    return EraSpec.from_dict(data)


def load_era_json(source: str | bytes | Path) -> EraSpec:
    """Load an era from JSON text, bytes, or a local file path."""
    if isinstance(source, Path):
        if not source.is_file():
            raise SchemaError("missing-file", str(source), "not a file")
        if source.stat().st_size > MAX_BYTES:
            raise SchemaError("too-large", str(source), f"max {MAX_BYTES} bytes")
        raw: str | bytes = source.read_bytes()
    else:
        raw = source
    if len(raw) > MAX_BYTES:
        raise SchemaError("too-large", "era", f"max {MAX_BYTES} bytes")
    try:
        decoded = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SchemaError("bad-json", "era", str(exc)) from None
    return load_era(decoded)


def load_eras(items: Iterable[Any]) -> tuple[EraSpec, ...]:
    """Load several eras, reject duplicate ids, and sort by (order, id)."""
    eras: list[EraSpec] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        era = EraSpec.from_dict(item, f"eras[{i}]")
        if era.id in seen:
            raise SchemaError("duplicate-era", f"eras[{i}].id", era.id)
        seen.add(era.id)
        eras.append(era)
    return tuple(sorted(eras, key=lambda e: (e.order, e.id)))
