"""Safely compile human-authored tile levels into the existing playable engine.

An authored level is DATA, never a script. This adapter shares the canonical
TileLevel/PlayableWorld geometry, safe-path solver and Python game simulator.
It supports editor iteration without mutating generated worlds or inventing a
second gameplay authority. Authorship is not a copyright clearance verdict.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .playable_world import (
    GameBuildIntent, PlayableWorld, PlayableWorldError,
    TileLevel, solve_safe_path,
)

AUTHORED_SCHEMA = "skeleton.game_builder.authored_tiles.v1"
AUTHORED_ALGORITHM = "skeleton.game_builder.authored-tiles.v1"
MAX_DOCUMENT_BYTES = 100_000
ALLOWED_TILES = frozenset("#.SGCH")


class AuthoredGameError(PlayableWorldError):
    """Designer-authored input cannot be promoted into a playable world."""


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthoredGameError("duplicate JSON key")
        result[key] = value
    return result


def _json_number_reject(value: str) -> None:
    raise AuthoredGameError("non-finite authored input value")


def read_authored_document(
    path: str | Path, *, authorized: bool,
) -> dict[str, Any]:
    """Read a strict bounded local JSON document, not a URL or source script."""
    if not authorized:
        raise PermissionError("authored game import requires authorization")
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise AuthoredGameError("authored input must be a regular local file")
    if source.stat().st_size > MAX_DOCUMENT_BYTES:
        raise AuthoredGameError("authored input exceeds 100 KB budget")
    try:
        content = source.read_bytes()
        if len(content) > MAX_DOCUMENT_BYTES:
            raise AuthoredGameError("authored input exceeds 100 KB budget")
        result = json.loads(
            content.decode("utf-8", "strict"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_json_number_reject,
        )
    except AuthoredGameError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise AuthoredGameError("invalid authored JSON document") from exc
    if not isinstance(result, dict):
        raise AuthoredGameError("authored file must contain one JSON object")
    return result


def _scan_level(
    intent: GameBuildIntent, index: int, rows: object,
) -> TileLevel:
    if not isinstance(rows, list) or len(rows) != intent.height:
        raise AuthoredGameError("authored level height mismatch")
    if any(not isinstance(row, str) or len(row) != intent.width
           or set(row) - ALLOWED_TILES for row in rows):
        raise AuthoredGameError("authored map contains unknown or uneven tiles")
    markers: dict[str, list[tuple[int, int]]] = {"S": [], "G": [], "C": [], "H": []}
    for y, row in enumerate(rows):
        for x, tile in enumerate(row):
            if tile in markers:
                markers[tile].append((x, y))
    if len(markers["S"]) != 1 or len(markers["G"]) != 1:
        raise AuthoredGameError("exactly one start and one exit per level required")
    if len(markers["C"]) != intent.collectibles_per_level:
        raise AuthoredGameError("authored level collectible count differs from intent")
    if len(markers["H"]) > intent.hazards_per_level:
        raise AuthoredGameError("authored level exceeds hazard budget")
    frozen_rows = tuple(rows)
    try:
        route = solve_safe_path(frozen_rows)
        return TileLevel(
            index=index,
            rows=frozen_rows,
            start=markers["S"][0],
            exit=markers["G"][0],
            collectibles=tuple(sorted(markers["C"])),
            hazards=tuple(sorted(markers["H"])),
            safe_solution=route,
        )
    except PlayableWorldError as exc:
        raise AuthoredGameError(
            f"authored level {index + 1} is invalid or lacks a safe winning route"
        ) from exc


def compile_authored_world(
    intent: GameBuildIntent,
    authored_levels: Sequence[object],
    *,
    human_reviewed: bool,
    authorized: bool,
) -> PlayableWorld:
    """Create an immutable, content-addressed and proved editor-made world.

    Human review acknowledges the owner reviewed the geometry. It does not
    automatically clear a license, prove novelty or authorize distribution.
    """
    if not authorized:
        raise PermissionError("authored game compilation requires authorization")
    if human_reviewed is not True:
        raise AuthoredGameError("human-reviewed authored geometry required")
    if not isinstance(intent, GameBuildIntent):
        raise AuthoredGameError("typed game build intent required")
    if not isinstance(authored_levels, (list, tuple)) or len(authored_levels) != intent.levels:
        raise AuthoredGameError("authored level count differs from intent")
    levels = tuple(
        _scan_level(intent, idx, rows) for idx, rows in enumerate(authored_levels)
    )
    return PlayableWorld(intent, levels, algorithm=AUTHORED_ALGORITHM)


def compile_authored_document(
    data: dict[str, Any], *, human_reviewed: bool, authorized: bool,
) -> PlayableWorld:
    """Strict operator JSON schema; avoid importing any executable snippets."""
    if not authorized:
        raise PermissionError("authored game import requires authorization")
    if not isinstance(data, dict) or set(data) != {"schema", "intent", "levels"}:
        raise AuthoredGameError("invalid authored game document structure")
    if data["schema"] != AUTHORED_SCHEMA:
        raise AuthoredGameError("unsupported authored document version")
    raw_intent = data["intent"]
    fields = set(GameBuildIntent.__dataclass_fields__)
    if not isinstance(raw_intent, dict) or set(raw_intent) != fields:
        raise AuthoredGameError("authored game must provide an exact intent schema")
    try:
        intent = GameBuildIntent(**raw_intent)
    except (TypeError, PlayableWorldError) as exc:
        raise AuthoredGameError("invalid authored intent") from exc
    return compile_authored_world(
        intent, data["levels"], human_reviewed=human_reviewed,
        authorized=True,
    )


__all__ = [
    "AUTHORED_SCHEMA", "AUTHORED_ALGORITHM", "AuthoredGameError",
    "read_authored_document", "compile_authored_world",
    "compile_authored_document",
]
