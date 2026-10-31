"""Read-only, fail-closed original studio blueprint catalog and playable preview bridge.

These are authored *production briefs*, not finished 3D worlds, real audio, or
consumer-certified games. Existing game_builder owns compilation and export.
No provider activation, external network, privileged file writes, or native SDKs.
"""
from __future__ import annotations

import json
import os
import re
import stat
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from .playable_world import GameBuildIntent

SCHEMA = "skeleton.game_builder.studio_ecosystem.index.v1"
ROOT = Path(__file__).resolve().parent / "catalogs" / "studio_ecosystem" / "v1"
SECTIONS = ("intent", "narrative", "cast", "quest", "scene", "visual", "audio", "verification")
IDENT = re.compile(r"^[a-z][a-z0-9_-]{2,75}$")
MAX_FILE_BYTES = 32768
MAX_INDEX_BYTES = 256 * 1024  # legacy minimum, not a fixed corpus ceiling


def _available_index_memory_bytes() -> int:
    """Best-effort live physical RAM headroom; refuse speculative unlimited JSON."""
    try:
        import psutil
        return max(0, int(psutil.virtual_memory().available))
    except (ImportError, OSError, ValueError, AttributeError):
        pass
    if hasattr(os, "sysconf"):
        try:
            pages = int(os.sysconf("SC_AVPHYS_PAGES"))
            size = int(os.sysconf("SC_PAGE_SIZE"))
            if pages > 0 and size > 0:
                return pages * size
        except (OSError, ValueError, KeyError):
            pass
    return 0


def _adaptive_index_bytes() -> int:
    """Admit an expanding catalog using measured RAM instead of file count."""
    return max(MAX_INDEX_BYTES, _available_index_memory_bytes() // 32)


class StudioEcosystemError(ValueError):
    """Untrusted or incomplete studio production blueprint."""


def _read_json(
    path: Path, *, maximum: int = MAX_FILE_BYTES, root: Path,
) -> dict[str, Any]:
    """Read a catalog object without following untrusted POSIX path components.

    The catalog root is the authority boundary. Each descendant directory and
    the final regular file are opened relative to already-open descriptors.
    Reading by pathname after checking is_symlink() is not race-safe.
    """
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise StudioEcosystemError("blueprint escaped catalog root") from exc
    if (not relative.parts or any(part in (".", "..") for part in relative.parts)
            or root.is_symlink()):
        raise StudioEcosystemError("unsafe blueprint path")
    if not isinstance(maximum, int) or maximum < 1:
        raise StudioEcosystemError("invalid blueprint size budget")

    try:
        if (os.name == "posix" and hasattr(os, "O_NOFOLLOW")
                and hasattr(os, "O_DIRECTORY") and os.open in os.supports_dir_fd):
            directory_flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                               | getattr(os, "O_CLOEXEC", 0))
            with ExitStack() as stack:
                parent = os.open(root, directory_flags)
                stack.callback(os.close, parent)
                for part in relative.parts[:-1]:
                    parent = os.open(part, directory_flags, dir_fd=parent)
                    stack.callback(os.close, parent)
                flags = (os.O_RDONLY | os.O_NOFOLLOW
                         | getattr(os, "O_NONBLOCK", 0)
                         | getattr(os, "O_CLOEXEC", 0))
                fd = os.open(relative.parts[-1], flags, dir_fd=parent)
                stack.callback(os.close, fd)
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                    raise StudioEcosystemError("missing or oversize regular blueprint")
                blocks: list[bytes] = []
                remaining = maximum + 1
                while remaining:
                    block = os.read(fd, min(remaining, 65536))
                    if not block:
                        break
                    blocks.append(block)
                    remaining -= len(block)
                data = b"".join(blocks)
                after = os.fstat(fd)
                if (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns):
                    raise StudioEcosystemError("blueprint changed during read")
        else:
            # Platforms without descriptor-relative no-follow need a native
            # reparse-safe reader before they can accept untrusted catalogs.
            # Keep the bundled read-only catalog usable, but never accept a
            # caller-supplied external root on an unqualified platform.
            if root != ROOT:
                raise StudioEcosystemError(
                    "external catalog requires descriptor-safe filesystem support"
                )
            if path.is_symlink() or not path.is_file():
                raise StudioEcosystemError("missing or linked blueprint file")
            with path.open("rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                    raise StudioEcosystemError("oversize blueprint file")
                data = stream.read(maximum + 1)
                after = os.fstat(stream.fileno())
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise StudioEcosystemError("blueprint changed during read")
    except OSError as exc:
        raise StudioEcosystemError("catalog filesystem access refused") from exc
    if len(data) > maximum:
        raise StudioEcosystemError("oversize blueprint file")
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
    index = _read_json(root / "index.json", maximum=_adaptive_index_bytes(), root=root)
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
    parts = {section: _read_json(project_root / (section + ".json"), root=root)
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
    mandatory = {
        "narrative": ("foundation", "premise", "plot_beats", "endings"),
        "cast": ("protagonist", "support", "factions"),
        "quest": ("objective",),
        "scene": ("episode_plan",),
        "visual": ("art_direction",),
        "audio": (),
        "verification": ("quality_gates", "release_blockers"),
    }
    for section, fields in mandatory.items():
        if any(not parts[section].get(field) for field in fields):
            raise StudioEcosystemError("incomplete substantive studio section")
    if not (parts["quest"].get("stages") or parts["quest"].get("stage_graph")):
        raise StudioEcosystemError("missing quest graph")
    if not (parts["visual"].get("jobs") or parts["visual"].get("asset_recipes")):
        raise StudioEcosystemError("missing visual production plan")
    if not (parts["audio"].get("audio_accessibility") or parts["audio"].get("accessibility")):
        raise StudioEcosystemError("missing audio accessibility requirements")
    if not (parts["audio"].get("cue_sheet") or parts["audio"].get("sound_layers")):
        raise StudioEcosystemError("missing audio cue graph")
    if len(parts["scene"]["episode_plan"]) < 3 or len(parts["verification"]["quality_gates"]) < 4:
        raise StudioEcosystemError("insufficient scene or QA coverage")
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
