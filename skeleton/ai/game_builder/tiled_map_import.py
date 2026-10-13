"""Strict Tiled JSON -> original, verified homebrew geometry adapter.

Reads only *numeric tile IDs* from bounded orthogonal finite Tiled map
documents. It intentionally NEVER loads referenced image tilesets, TSX files,
network URLs, plugins, shaders, object scripts or third-party expressions.
Tiles are converted to the canonical authored-tiles format and independently
solved with the same game simulator used by the consumer build.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Mapping, Sequence

from .authored_tiles import (
    AUTHORED_SCHEMA, AuthoredGameError, compile_authored_world,
    _no_duplicate_keys, _json_number_reject,
)
from .contracts import canonical_digest, canonical_json
from .playable_world import GameBuildIntent, PlayableWorld, DIRECTIONS
from .playable_simulation import demonstrate_solvable


class TiledImportError(AuthoredGameError):
    """Unsafe, unsupported or unplayable Tiled level cannot enter the studio."""


MAX_MAP_BYTES = 700_000
DEFAULT_GID_PALETTE = {0: ".", 1: "#", 2: ".", 3: "S", 4: "G",
                       5: "C", 6: "H"}
_FLIP_MASK = 0xF0000000
_ALLOWED = frozenset("#.SGCH")


@dataclass(frozen=True, slots=True)
class TiledConversion:
    intent: GameBuildIntent
    levels: tuple[tuple[str, ...], ...]
    source_digests: tuple[str, ...]
    ignored_external_tileset_metadata: int
    world_digest: str
    proof_digest: str
    proof_steps: int

    @property
    def digest(self) -> str:
        return canonical_digest(self.receipt())

    def authored_document(self) -> dict[str, object]:
        return {
            "schema": AUTHORED_SCHEMA,
            "intent": self.intent.to_payload(),
            "levels": [list(level) for level in self.levels],
        }

    def receipt(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.tiled_geometry_handoff.v1",
            "project_id": self.intent.project_id,
            "source_sha256": list(self.source_digests),
            "world_digest": self.world_digest,
            "proof_digest": self.proof_digest,
            "proof_steps": self.proof_steps,
            "ignored_tileset_metadata_count": self.ignored_external_tileset_metadata,
            "source_scripts_copied": False,
            "external_images_copied": False,
            "third_party_expressions_copied": False,
            "operator_authored_geometry_reviewed": True,
            "copyright_clearance": False,
            "native_consumer_cleared": False,
        }


def _palette(mapping: Mapping[int, str] | None) -> dict[int, str]:
    if mapping is None:
        return dict(DEFAULT_GID_PALETTE)
    if not isinstance(mapping, Mapping) or not 1 <= len(mapping) <= 64:
        raise TiledImportError("explicit Tiled GID palette must contain 1 to 64 IDs")
    result: dict[int, str] = {0: "."}
    for key, value in mapping.items():
        if (type(key) is not int or not 1 <= key <= 0x0FFFFFFF
                or type(value) is not str or value not in _ALLOWED):
            raise TiledImportError("GID palette maps numeric IDs only to supported original tile codes")
        result[key] = value
    if not {"#", "S", "G", "C"}.issubset(result.values()):
        raise TiledImportError("palette must support walls, start, goal and collectibles")
    return result


def _read_tiled_map(path: str | Path) -> tuple[dict[str, object], str]:
    file = Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_MAP_BYTES:
        raise TiledImportError("Tiled input must be a regular JSON file below 700 KB")
    data = file.read_bytes()
    if len(data) > MAX_MAP_BYTES:
        raise TiledImportError("Tiled map exceeds byte budget")
    try:
        value = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_json_number_reject,
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise TiledImportError("invalid or ambiguous Tiled UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise TiledImportError("Tiled export must be a JSON object")
    return value, sha256(data).hexdigest()


def _tile_layer_rows(
    document: dict[str, object], intent: GameBuildIntent, palette: dict[int, str],
) -> tuple[tuple[str, ...], int]:
    if (document.get("orientation") != "orthogonal"
            or document.get("infinite", False) is not False
            or document.get("width") != intent.width
            or document.get("height") != intent.height
            or isinstance(document.get("width"), bool)
            or isinstance(document.get("height"), bool)):
        raise TiledImportError("only finite, orthogonal, exact-size original levels supported")
    if document.get("type", "map") != "map":
        raise TiledImportError("Tiled root must be a map")
    layers = document.get("layers")
    if not isinstance(layers, list) or len(layers) != 1:
        raise TiledImportError("exactly one flat tile layer is required")
    layer = layers[0]
    if not isinstance(layer, dict) or layer.get("type") != "tilelayer":
        raise TiledImportError("object groups and external scripts cannot define tile gameplay")
    if (layer.get("visible", True) is not True
            or layer.get("width") != intent.width
            or layer.get("height") != intent.height
            or type(layer.get("x", 0)) is not int or layer.get("x", 0) != 0
            or type(layer.get("y", 0)) is not int or layer.get("y", 0) != 0
            or "chunks" in layer
            or layer.get("encoding", "csv") not in ("csv", "")
            or layer.get("compression", "") not in ("", None)):
        raise TiledImportError("Tiled tile layer must be visible, finite and uncompressed CSV IDs")
    data = layer.get("data")
    if not isinstance(data, list) or len(data) != intent.width * intent.height:
        raise TiledImportError("Tiled tile data must be an exact flat list of numeric GIDs")
    characters: list[str] = []
    for value in data:
        if type(value) is not int or value < 0 or value > 0xFFFFFFFF:
            raise TiledImportError("invalid Tiled global tile ID")
        if value & _FLIP_MASK:
            raise TiledImportError("flipped, rotated and hex transform GIDs are not supported")
        if value not in palette:
            raise TiledImportError("Tiled GID not present in reviewed original palette")
        characters.append(palette[value])
    tilesets = document.get("tilesets", [])
    if not isinstance(tilesets, list) or len(tilesets) > 64 or any(
        not isinstance(item, dict) for item in tilesets
    ):
        raise TiledImportError("invalid external tileset metadata")
    # Tileset file/URL/script values are not dereferenced, copied or included
    # in any output. The consumer game renders its own original tile art.
    return tuple(
        "".join(characters[y * intent.width:(y + 1) * intent.width])
        for y in range(intent.height)
    ), len(tilesets)


def import_tiled_levels(
    intent: GameBuildIntent,
    sources: Sequence[str | Path],
    *,
    human_reviewed: bool,
    authorized: bool,
    gid_palette: Mapping[int, str] | None = None,
) -> TiledConversion:
    if not authorized:
        raise PermissionError("Tiled map conversion requires local operator authorization")
    if not isinstance(intent, GameBuildIntent):
        raise TiledImportError("typed original game intent required")
    if human_reviewed is not True:
        raise TiledImportError("original geometry must be human reviewed")
    if not isinstance(sources, (list, tuple)) or len(sources) != intent.levels:
        raise TiledImportError("one Tiled JSON file required for each authored game level")
    palette = _palette(gid_palette)
    rows = []
    digests = []
    foreign = 0
    for path in sources:
        payload, digest = _read_tiled_map(path)
        level_rows, discarded = _tile_layer_rows(payload, intent, palette)
        rows.append(level_rows)
        digests.append(digest)
        foreign += discarded
    if len(digests) != len(set(digests)):
        raise TiledImportError("reused Tiled map source cannot supply multiple distinct levels")
    try:
        world: PlayableWorld = compile_authored_world(
            intent, [list(level) for level in rows],
            human_reviewed=True, authorized=True,
        )
        proof = demonstrate_solvable(world, authorized=True)
    except AuthoredGameError as exc:
        raise TiledImportError("imported Tiled geometry is not a valid solvable original game") from exc
    return TiledConversion(
        intent, tuple(rows), tuple(digests), foreign, world.digest,
        proof.digest, proof.final_state.steps,
    )


def write_tiled_authored_json(
    conversion: TiledConversion, destination: str | Path, *,
    authorized: bool,
) -> Path:
    if not authorized:
        raise PermissionError("Tiled converted authored JSON export requires authorization")
    if not isinstance(conversion, TiledConversion):
        raise TiledImportError("typed verified map conversion required")
    target = Path(destination)
    if target.suffix.lower() != ".json" or target.is_symlink() or target.exists():
        raise TiledImportError("new .json output file required (never overwrite)")
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise TiledImportError("output parent must be an existing real directory")
    data = (canonical_json(conversion.authored_document()) + "\n").encode("utf-8")
    if len(data) > 150000:
        raise TiledImportError("converted original-game document exceeds safe byte budget")
    with target.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return target


__all__ = [
    "TiledImportError", "TiledConversion", "DEFAULT_GID_PALETTE",
    "import_tiled_levels", "write_tiled_authored_json",
]
