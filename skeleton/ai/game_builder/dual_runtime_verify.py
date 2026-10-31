"""Verify a published original browser/Godot game against an independent pin.

Canonical owner: skeleton.ai.game_builder. Verification uses only read-only,
descriptor-relative local filesystem operations and the canonical Python game
simulation. A valid source bundle is not a signed release or device test.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from .contracts import canonical_digest
from .playable_simulation import MAX_REPLAY_ACTIONS, play_actions
from .playable_world import (
    GameBuildIntent, PlayableWorld, TileLevel, solve_safe_path,
)

SCHEMA = "skeleton.game_builder.dual_runtime_verification.v1"
_MAX_FILES = 128
_MAX_BYTES = 2_100_000
_MAX_MANIFEST = 65_536
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_COMPONENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")
_REQUIRED = frozenset({
    "index.html", "godot/world.json", "godot/proof.json",
    "proof/verified_solution.json", "godot/project.godot",
    "godot/scripts/main.gd", "release.json",
})


class DualRuntimeVerificationError(ValueError):
    """A published package is untrusted, inconsistent, or unsupported."""


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise DualRuntimeVerificationError("duplicate JSON member")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise DualRuntimeVerificationError("nonfinite JSON value: " + value)


def _json(data: bytes, limit: int) -> dict[str, object]:
    if len(data) > limit:
        raise DualRuntimeVerificationError("JSON document exceeds budget")
    try:
        parsed = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except DualRuntimeVerificationError:
        raise
    except (UnicodeError, ValueError, TypeError) as exc:
        raise DualRuntimeVerificationError("invalid JSON document") from exc
    if type(parsed) is not dict:
        raise DualRuntimeVerificationError("JSON document must be an object")
    return parsed


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _parts(path: str) -> tuple[str, ...]:
    if type(path) is not str or not path or len(path) > 512:
        raise DualRuntimeVerificationError("invalid package path")
    parts = tuple(path.split("/"))
    if (len(parts) > 8 or any(
        not _COMPONENT.fullmatch(p) or p in (".", "..", ".git")
        for p in parts
    )):
        raise DualRuntimeVerificationError("unsafe package path")
    return parts


def _flags(directory: bool) -> int:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise DualRuntimeVerificationError(
            "descriptor-safe verifier requires POSIX O_NOFOLLOW"
        )
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if directory:
        flags |= os.O_DIRECTORY
    return flags


def _root_fd(root: str | Path) -> int:
    # Walk from a trusted anchor; an intermediate symlink is not accepted.
    absolute = os.path.abspath(os.fspath(root))
    if not absolute.startswith("/") or absolute == "/":
        raise DualRuntimeVerificationError("package root must be a directory")
    current = os.open("/", _flags(True))
    try:
        for part in absolute.split("/")[1:]:
            if not part:
                continue
            following = os.open(part, _flags(True), dir_fd=current)
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _child_fd(root: int, parts: tuple[str, ...], *, directory: bool) -> int:
    current = os.dup(root)
    try:
        for index, part in enumerate(parts):
            next_fd = os.open(
                part, _flags(directory or index < len(parts) - 1),
                dir_fd=current,
            )
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise


def _read(root: int, path: str, limit: int) -> bytes:
    with_fd = _child_fd(root, _parts(path), directory=False)
    try:
        info = os.fstat(with_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_size < 0 or info.st_size > limit):
            raise DualRuntimeVerificationError("unsafe or oversized package file")
        with os.fdopen(os.dup(with_fd), "rb", closefd=True) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit or len(data) != info.st_size:
            raise DualRuntimeVerificationError("file changed while verifying")
        if os.fstat(with_fd).st_size != info.st_size:
            raise DualRuntimeVerificationError("file changed while verifying")
        return data
    finally:
        os.close(with_fd)


def _bounded_names(fd: int, maximum: int) -> tuple[str, ...]:
    """Enumerate descriptor-relative names without an unbounded allocation.

    The scandir iterator closes even on rejection. At most maximum + 1
    directory entries are consumed, and callers still validate inode types.
    """
    if type(maximum) is not int or maximum < 0:
        raise DualRuntimeVerificationError("invalid directory entry budget")
    names: list[str] = []
    with os.scandir(fd) as entries:
        for entry in entries:
            if len(names) >= maximum:
                raise DualRuntimeVerificationError("directory entry budget exceeded")
            names.append(entry.name)
    return tuple(names)


def _inventory(root: int) -> set[str]:
    paths: set[str] = set()
    visited = 0

    def visit(fd: int, prefix: tuple[str, ...]) -> None:
        nonlocal visited
        names = _bounded_names(fd, _MAX_FILES + 8)
        for name in names:
            parts = prefix + (name,)
            _parts("/".join(parts))
            visited += 1
            if visited > _MAX_FILES * 3:
                raise DualRuntimeVerificationError("package entry budget exceeded")
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, _flags(True), dir_fd=fd)
                try:
                    visit(child, parts)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                paths.add("/".join(parts))
            else:
                raise DualRuntimeVerificationError("nonregular package entry")

    visit(root, ())
    return paths


def _world(native: dict[str, object], manifest: dict[str, object]) -> PlayableWorld:
    if native.get("schema") != "skeleton.game_builder.godot_world.v1":
        raise DualRuntimeVerificationError("unsupported Godot world")
    raw_intent = native.get("intent")
    raw_levels = native.get("levels")
    if type(raw_intent) is not dict or type(raw_levels) is not list:
        raise DualRuntimeVerificationError("missing world intent or levels")
    try:
        intent = GameBuildIntent(**raw_intent)
        if len(raw_levels) != intent.levels:
            raise DualRuntimeVerificationError("world level count exceeds declared intent")
        levels: list[TileLevel] = []
        for index, item in enumerate(raw_levels):
            if type(item) is not dict or set(item) != {
                "rows", "start", "collectibles"
            }:
                raise DualRuntimeVerificationError("unsupported level structure")
            raw_rows = item["rows"]
            if (type(raw_rows) is not list
                    or len(raw_rows) != intent.height
                    or any(type(row) is not str or len(row) != intent.width
                           or set(row) - set("#.SGCH") for row in raw_rows)):
                raise DualRuntimeVerificationError("world geometry exceeds declared bounds")
            rows = tuple(raw_rows)
            raw_start = item["start"]
            raw_collectibles = item["collectibles"]
            if (type(raw_start) is not list or len(raw_start) != 2
                    or any(type(coord) is not int for coord in raw_start)
                    or type(raw_collectibles) is not list
                    or len(raw_collectibles) != intent.collectibles_per_level
                    or any(type(point) is not list or len(point) != 2
                           or any(type(coord) is not int for coord in point)
                           for point in raw_collectibles)):
                raise DualRuntimeVerificationError("world coordinates exceed declared bounds")
            markers = {
                tile: tuple(sorted((x, y) for y, row in enumerate(rows)
                                   for x, char in enumerate(row) if char == tile))
                for tile in ("S", "G", "C", "H")
            }
            start = tuple(item["start"])
            if (markers["S"] != (start,)
                    or tuple(tuple(p) for p in item["collectibles"]) != markers["C"]):
                raise DualRuntimeVerificationError("world level marker mismatch")
            levels.append(TileLevel(
                index, rows, start, markers["G"][0], markers["C"],
                markers["H"], solve_safe_path(rows),
            ))
        world = PlayableWorld(intent, tuple(levels), manifest["world_algorithm"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise DualRuntimeVerificationError("invalid canonical world geometry") from exc
    if (world.digest != manifest.get("world_digest")
            or native.get("world_digest") != world.digest
            or intent.project_id != manifest.get("project_id")):
        raise DualRuntimeVerificationError("world identity does not match release")
    return world


def verify_exported_package(
    root: str | Path | int, *, expected_manifest_sha256: str, authorized: bool,
) -> dict[str, object]:
    """Read-only, independently pinned source and gameplay verification.

    Does not authorize publication, attest third-party rights, or assert that
    a Godot binary has been built or executed.
    """
    if authorized is not True:
        raise PermissionError("operator authorization required for verification")
    if type(expected_manifest_sha256) is not str or not _HEX.fullmatch(
        expected_manifest_sha256
    ):
        raise DualRuntimeVerificationError("independent release pin required")
    if isinstance(root, bool):
        raise DualRuntimeVerificationError("invalid package root descriptor")
    try:
        fd = os.dup(root) if type(root) is int else _root_fd(root)
    except (OSError, TypeError, ValueError) as exc:
        raise DualRuntimeVerificationError("unsafe or inaccessible package root") from exc
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise DualRuntimeVerificationError("package root descriptor is not a directory")
        release = _read(fd, "release.json", _MAX_MANIFEST)
        if sha256(release).hexdigest() != expected_manifest_sha256:
            raise DualRuntimeVerificationError("release differs from trusted pin")
        manifest = _json(release, _MAX_MANIFEST)
        if release != _canonical_bytes(manifest):
            raise DualRuntimeVerificationError("noncanonical release JSON")
        if manifest.get("schema") != "skeleton.game_builder.dual_runtime_package.v1":
            raise DualRuntimeVerificationError("unsupported release schema")
        digest = manifest.get("manifest_digest")
        body = {key: value for key, value in manifest.items()
                if key != "manifest_digest"}
        if type(digest) is not str or digest != canonical_digest(body):
            raise DualRuntimeVerificationError("release manifest digest mismatch")
        if (manifest.get("automatic_publication") is not False
                or manifest.get("godot_hardware_tested") is not False
                or manifest.get("proof_status") != "python-simulated-winning-actions"):
            raise DualRuntimeVerificationError("unsupported release authority claim")
        declared = manifest.get("files")
        if type(declared) is not dict or not 1 <= len(declared) <= _MAX_FILES:
            raise DualRuntimeVerificationError("invalid file manifest")
        expected = set(declared) | {"release.json"}
        if not _REQUIRED <= expected or "release.json" in declared:
            raise DualRuntimeVerificationError("missing required game source")
        for path, digest in declared.items():
            _parts(path)
            if type(digest) is not str or not _HEX.fullmatch(digest):
                raise DualRuntimeVerificationError("invalid file digest")
        if _inventory(fd) != expected:
            raise DualRuntimeVerificationError("unexpected or missing package files")
        files: dict[str, bytes] = {}
        total = len(release)
        for path, expected_digest in sorted(declared.items()):
            payload = _read(fd, path, _MAX_BYTES - total)
            total += len(payload)
            if sha256(payload).hexdigest() != expected_digest:
                raise DualRuntimeVerificationError("package file digest mismatch")
            files[path] = payload
        if _inventory(fd) != expected:
            raise DualRuntimeVerificationError("package changed during verification")
        if files["godot/proof.json"] != files["proof/verified_solution.json"]:
            raise DualRuntimeVerificationError("browser and Godot proofs differ")
        native = _json(files["godot/world.json"], _MAX_BYTES)
        proof = _json(files["godot/proof.json"], _MAX_BYTES)
        world = _world(native, manifest)
        if (proof.get("schema") != "skeleton.game_builder.solution_trace.v1"
                or proof.get("world_digest") != world.digest):
            raise DualRuntimeVerificationError("foreign replay source")
        actions = proof.get("actions")
        if (type(actions) is not list or not 1 <= len(actions) <= MAX_REPLAY_ACTIONS
                or any(type(a) is not str for a in actions)):
            raise DualRuntimeVerificationError("invalid replay actions")
        try:
            replay = play_actions(world, actions, authorized=True)
        except (ValueError, PermissionError) as exc:
            raise DualRuntimeVerificationError("gameplay replay rejected") from exc
        if (replay.final_state.status != "won"
                or replay.digest != proof.get("replay_digest")
                or replay.digest != manifest.get("proof_digest")
                or replay.final_state.to_payload() != proof.get("final_state")):
            raise DualRuntimeVerificationError("winning replay does not reproduce")
        return {
            "schema": SCHEMA,
            "project_id": world.intent.project_id,
            "manifest_sha256": expected_manifest_sha256,
            "world_digest": world.digest,
            "replay_digest": replay.digest,
            "verified_files": len(expected),
            "verified_bytes": total,
            "replayed_actions": len(actions),
            "offline_gameplay_reexecuted": True,
            "godot_executed": False,
            "rights_certified": False,
            "release_certified": False,
        }
    except (OSError, UnicodeError) as exc:
        raise DualRuntimeVerificationError("unsafe or inaccessible package") from exc
    finally:
        os.close(fd)


__all__ = ["DualRuntimeVerificationError", "verify_exported_package"]
