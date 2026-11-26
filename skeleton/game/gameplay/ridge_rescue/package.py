"""Portable offline game source package with reproducible manifest and replay smoke proof."""
from __future__ import annotations
from typing import Any
from .schema import World, parse_world, world_dict
from .authoring import validate_reachability
from .custody import canonical, digest, export_run, verify_run
from .engine import initial_state

MAX_PACKAGE_BYTES = 192_000
class PackageError(ValueError):
    pass

def build_package(world: World) -> dict:
    validate_reachability(world)
    source = world_dict(world)
    manifest = {
        "schema": "ridge.rescue.manifest.v1",
        "game_id": "cinder-ridge-rescue",
        "title": world.name,
        "entrypoint": "skeleton.game.gameplay.ridge_rescue.cli",
        "runtime_schema": "ridge.rescue.state.v1",
        "source_sha256": digest(source),
        "offline": True,
        "supported_actions": ["move", "gather", "craft", "attack", "rescue", "rest", "signal", "evacuate", "trade"],
        "asset_format": "ascii-terrain-v1",
        "max_turns": world.max_turns,
    }
    payload = {"schema": "ridge.rescue.package.v1", "manifest": manifest, "world": source}
    if len(canonical(payload)) > MAX_PACKAGE_BYTES:
        raise PackageError("package exceeds byte budget")
    return {"payload": payload, "sha256": digest(payload)}

def verify_package(package: dict | bytes | str) -> dict:
    if isinstance(package, bytes):
        if len(package) > MAX_PACKAGE_BYTES:
            raise PackageError("package exceeds byte budget")
        try:
            package = package.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PackageError("package not UTF-8") from exc
    if isinstance(package, str):
        if len(package.encode("utf-8")) > MAX_PACKAGE_BYTES:
            raise PackageError("package exceeds byte budget")
        import json
        def unique_members(pairs: list[tuple[str, Any]]) -> dict:
            result: dict = {}
            for key, value in pairs:
                if key in result:
                    raise PackageError("duplicate package JSON member")
                result[key] = value
            return result
        def reject_nonfinite(value: str) -> None:
            raise PackageError("nonfinite package JSON number")
        try:
            package = json.loads(package, object_pairs_hook=unique_members,
                                 parse_constant=reject_nonfinite)
        except ValueError as exc:
            raise PackageError("invalid package JSON") from exc
    if not isinstance(package, dict) or set(package) != {"payload", "sha256"}:
        raise PackageError("invalid package envelope")
    payload = package["payload"]
    if not isinstance(payload, dict) or set(payload) != {"schema", "manifest", "world"}:
        raise PackageError("invalid package payload")
    if payload["schema"] != "ridge.rescue.package.v1" or digest(payload) != package["sha256"]:
        raise PackageError("package digest or schema mismatch")
    try:
        world = parse_world(payload["world"])
        validate_reachability(world)
    except (ValueError, TypeError) as exc:
        raise PackageError("invalid or unreachable package world") from exc
    expected = build_package(world)
    if canonical(expected) != canonical(package):
        raise PackageError("manifest does not match source")
    return {"world": world, "manifest": payload["manifest"]}

def play_package(package: dict, actions: list[dict]) -> dict:
    verified = verify_package(package)
    bundle = export_run(verified["world"], actions)
    verify_run(bundle)
    return bundle
