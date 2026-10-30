"""Read-only, fail-closed original studio blueprint catalog and playable preview bridge.

These are authored *production briefs*, not finished 3D worlds, real audio, or
consumer-certified games. Existing game_builder owns compilation and export.
No provider activation, external network, privileged file writes, or native SDKs.
"""
from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

from .playable_world import GameBuildIntent

SCHEMA = "skeleton.game_builder.studio_ecosystem.index.v1"
ROOT = Path(__file__).resolve().parent / "catalogs" / "studio_ecosystem" / "v1"
SECTIONS = ("intent", "narrative", "cast", "quest", "scene", "visual", "audio", "verification")
IDENT = re.compile(r"^[a-z][a-z0-9_-]{2,75}$")
MAX_FILE_BYTES = 32768


class StudioEcosystemError(ValueError):
    """Untrusted or incomplete studio production blueprint."""


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise StudioEcosystemError("missing or linked blueprint file")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise StudioEcosystemError("oversize blueprint file")
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise StudioEcosystemError("blueprint file changed during read")
    try:
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            output: dict[str, Any] = {}
            for key, value in pairs:
                if key in output:
                    raise StudioEcosystemError("ambiguous duplicate JSON key")
                output[key] = value
            return output
        result = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=unique,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                StudioEcosystemError("nonfinite blueprint number")
            ),
        )
    except (UnicodeError, ValueError) as exc:
        raise StudioEcosystemError("invalid blueprint JSON") from exc
    if not isinstance(result, dict):
        raise StudioEcosystemError("blueprint root must be an object")
    return result


def catalog_index(*, root: Path = ROOT) -> tuple[dict[str, str], ...]:
    index = _read_json(root / "index.json")
    if index.get("schema") != SCHEMA or index.get("sections") != list(SECTIONS):
        raise StudioEcosystemError("wrong studio ecosystem index contract")
    records = index.get("projects")
    if not isinstance(records, list) or not records:
        raise StudioEcosystemError("missing studio project index")
    if index.get("project_count") != len(records):
        raise StudioEcosystemError("index count mismatch")
    seen: set[str] = set()
    entries: list[dict[str, str]] = []
    for record in records:
        if not isinstance(record, dict) or set(record) != {"id", "genre", "biome", "theme"}:
            raise StudioEcosystemError("invalid index entry shape")
        pid = record["id"]
        if not isinstance(pid, str) or not IDENT.fullmatch(pid) or pid in seen:
            raise StudioEcosystemError("invalid or repeated project ID")
        if any(not isinstance(record[key], str) or not record[key]
               for key in ("genre", "biome", "theme")):
            raise StudioEcosystemError("missing typed catalog taxonomy")
        seen.add(pid)
        entries.append(record)
    return tuple(entries)


def list_blueprints(*, genre: str | None = None, biome: str | None = None,
                    root: Path = ROOT) -> tuple[dict[str, str], ...]:
    return tuple(item for item in catalog_index(root=root)
                 if (genre is None or item["genre"] == genre)
                 and (biome is None or item["biome"] == biome))


def read_blueprint(project_id: str, *, root: Path = ROOT) -> dict[str, dict[str, Any]]:
    if not isinstance(project_id, str) or not IDENT.fullmatch(project_id):
        raise StudioEcosystemError("unsafe project ID")
    record = next((r for r in catalog_index(root=root) if r["id"] == project_id), None)
    if record is None:
        raise StudioEcosystemError("project not registered in ecosystem index")
    project_root = root / project_id
    if project_root.is_symlink() or not project_root.is_dir():
        raise StudioEcosystemError("invalid project directory")
    parts = {section: _read_json(project_root / (section + ".json"))
             for section in SECTIONS}
    intent = parts["intent"]
    if set(intent) != {
        "project_id", "title", "subtitle", "seed", "width", "height", "levels",
        "collectibles_per_level", "hazards_per_level", "theme", "starting_health",
    }:
        raise StudioEcosystemError("intent is not a canonical GameBuildIntent payload")
    if intent.get("project_id") != project_id or intent.get("theme") != record["theme"]:
        raise StudioEcosystemError("index/intent identity mismatch")
    try:
        GameBuildIntent(**intent)
    except (ValueError, TypeError) as exc:
        raise StudioEcosystemError("invalid canonical playable preview intent") from exc
    for section in SECTIONS[1:]:
        part = parts[section]
        if (part.get("schema") != "skeleton.game_builder.studio_ecosystem." + section + ".v1"
                or part.get("project_id") != project_id
                or part.get("genre") != record["genre"]
                or part.get("biome") != record["biome"]):
            raise StudioEcosystemError("broken cross-document ownership or schema")
        if part.get("release_certified") is not False:
            raise StudioEcosystemError("unearned release certification")
    return parts


def compile_preview(project_id: str, *, authorized: bool, root: Path = ROOT):
    """Compile an actual winning offline HTML5 maze proof, not the full genre design.

    Leaves native rendering, music, 3D asset production and game certification
    unclaimed; caller explicitly authorizes canonical existing compiler.
    """
    if not authorized:
        raise PermissionError("studio preview compilation requires authorization")
    from .playable_compiler import compile_original_game
    parts = read_blueprint(project_id, root=root)
    return compile_original_game(GameBuildIntent(**parts["intent"]), authorized=True)


__all__ = [
    "SCHEMA", "ROOT", "SECTIONS", "StudioEcosystemError", "catalog_index",
    "list_blueprints", "read_blueprint", "compile_preview",
]
