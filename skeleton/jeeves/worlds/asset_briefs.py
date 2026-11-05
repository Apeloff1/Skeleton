"""Original asset briefs bound to reviewed world source and real era asset compiler."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from typing import Any

from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text, canonical, digest,
    prove, strict_json,
)

ASSET_SCHEMA = "jeeves.world.asset_briefs.v1"
MAX_ASSETS = 64
KINDS = frozenset({
    "primitive", "vector", "sprite", "tileset", "mesh", "texture",
    "material", "audio", "animation",
})


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CanonError("invalid_numeric_budget", field)
    return value


def validate_briefs(data: Any, world: Any) -> dict[str, Any]:
    obj = _keys(data, {"schema", "world_id", "world_digest", "assets"})
    if obj["schema"] != ASSET_SCHEMA:
        raise CanonError("asset_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != prove(world).source_digest:
        raise CanonError("asset_source_lease_mismatch")
    ids: set[str] = set()
    scene_ids = {s["id"] for s in world["scenes"]}
    for item in _list(obj["assets"], "assets", MAX_ASSETS):
        _keys(item, {"id", "scene", "kind", "description", "alt_text",
                     "originality_attested", "reviewed", "width", "height",
                     "colors", "triangles", "sample_rate", "channels", "frames"})
        asset_id = _id(item["id"], "asset.id")
        if asset_id in ids:
            raise CanonError("duplicate_asset", asset_id)
        ids.add(asset_id)
        if _id(item["scene"], "asset.scene") not in scene_ids:
            raise CanonError("unknown_asset_scene", asset_id)
        if item["kind"] not in KINDS:
            raise CanonError("invalid_asset_kind", asset_id)
        _text(item["description"], "asset.description", 2048)
        _text(item["alt_text"], "asset.alt_text", 512)
        if type(item["originality_attested"]) is not bool or type(item["reviewed"]) is not bool:
            raise CanonError("invalid_review_flag", asset_id)
        _integer(item["width"], "width", 1, 8192)
        _integer(item["height"], "height", 1, 8192)
        _integer(item["colors"], "colors", 1, 16777216)
        _integer(item["triangles"], "triangles", 0, 2000000)
        _integer(item["sample_rate"], "sample_rate", 0, 192000)
        _integer(item["channels"], "channels", 0, 32)
        _integer(item["frames"], "frames", 1, 65536)
    if len(canonical(obj)) > 524288:
        raise CanonError("source_too_large")
    return obj


def propose_asset(world: Any, *, asset_id: str, scene: str, kind: str,
                  description: str, alt_text: str, width: int = 16,
                  height: int = 16, colors: int = 4) -> dict[str, Any]:
    proof = prove(world)
    asset = {
        "id": _id(asset_id, "asset_id"),
        "scene": _id(scene, "scene"),
        "kind": kind,
        "description": _text(description, "description", 2048),
        "alt_text": _text(alt_text, "alt_text", 512),
        "originality_attested": False,
        "reviewed": False,
        "width": width, "height": height, "colors": colors,
        "triangles": 0, "sample_rate": 0, "channels": 0, "frames": 1,
    }
    validate_briefs({"schema": ASSET_SCHEMA, "world_id": world["id"],
                     "world_digest": proof.source_digest, "assets": [asset]}, world)
    return asset


def edit_briefs(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_briefs(data, world)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(data))
    action, value = op["action"], op["value"]
    if action == "add":
        _keys(value, {"id", "scene", "kind", "description", "alt_text",
                      "originality_attested", "reviewed", "width", "height",
                      "colors", "triangles", "sample_rate", "channels", "frames"})
        if value["reviewed"] or value["originality_attested"]:
            raise CanonError("review_cannot_be_imported")
        candidate["assets"].append(value)
    elif action == "replace":
        _keys(value, {"id", "scene", "kind", "description", "alt_text",
                      "originality_attested", "reviewed", "width", "height",
                      "colors", "triangles", "sample_rate", "channels", "frames"})
        if value["reviewed"] or value["originality_attested"]:
            raise CanonError("review_cannot_be_imported")
        indices = [i for i, asset in enumerate(candidate["assets"])
                   if asset["id"] == value["id"]]
        if len(indices) != 1:
            raise CanonError("unknown_asset")
        candidate["assets"][indices[0]] = value
    elif action == "review":
        _keys(value, {"id", "originality_attested"})
        if type(value["originality_attested"]) is not bool:
            raise CanonError("invalid_review_flag")
        found = [asset for asset in candidate["assets"] if asset["id"] == value["id"]]
        if len(found) != 1:
            raise CanonError("unknown_asset")
        found[0]["reviewed"] = True
        found[0]["originality_attested"] = value["originality_attested"]
    elif action == "remove":
        _keys(value, {"id"})
        before = len(candidate["assets"])
        candidate["assets"] = [asset for asset in candidate["assets"]
                               if asset["id"] != value["id"]]
        if len(candidate["assets"]) != before - 1:
            raise CanonError("unknown_asset")
    else:
        raise CanonError("unsupported_asset_edit", str(action))
    return validate_briefs(candidate, world)


def compile_assets(data: Any, world: Any, era: str) -> dict[str, Any]:
    """Compile actual engine-facing SourceAsset recipes, not catalog placeholders."""
    from skeleton.jeeves.game_engine_assets import (
        AssetKind, SourceAsset, compile_asset_build,
    )
    from skeleton.jeeves.game_engine_lab import GameEngineLabError
    validate_briefs(data, world)
    if not data["assets"]:
        raise CanonError("no_assets")
    for item in data["assets"]:
        if not item["reviewed"] or not item["originality_attested"]:
            raise CanonError("asset_review_required", item["id"])
    sources = tuple(
        SourceAsset(
            asset_id=item["id"], kind=AssetKind(item["kind"]),
            width=item["width"], height=item["height"], colors=item["colors"],
            triangles=item["triangles"], sample_rate=item["sample_rate"],
            channels=item["channels"], frames=item["frames"],
            metadata=(
                ("scene", item["scene"]),
                ("alt_text", item["alt_text"]),
                ("author_description", item["description"][:256]),
            ),
        )
        for item in data["assets"]
    )
    try:
        build = compile_asset_build(era, sources)
    except (GameEngineLabError, ValueError) as exc:
        raise CanonError("engine_asset_compile_rejected", str(exc)) from exc
    return {
        "schema": "jeeves.world.asset_handoff.v1",
        "world_id": world["id"],
        "world_digest": digest(world),
        "asset_briefs_digest": digest(data),
        "engine_era": era,
        "review_provenance": "operator_attestation_not_independent_rights_proof",
        "engine_manifest": build.manifest(),
    }


class AssetBriefStore:
    """Same descriptor-anchored root and world lease as the canon workbench."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _filename(world_id: str) -> str:
        return _id(world_id, "world_id") + ".assets.json"

    def read(self, world_id: str) -> dict[str, Any]:
        world = self.worlds.read(world_id)
        fd = self.worlds._directory()
        try:
            data = strict_json(self.worlds._read(fd, self._filename(world_id)))
            return validate_briefs(data, world)
        finally:
            os.close(fd)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        _id(world_id, "world_id")
        if create and expected_digest is not None:
            raise CanonError("invalid_lease")
        fd = self.worlds._directory()
        lock = world_id + ".lock"
        try:
            try:
                lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  os.O_NOFOLLOW, 0o600, dir_fd=fd)
            except FileExistsError:
                raise CanonError("lease_busy") from None
            try:
                os.close(lock_fd)
                world = strict_json(self.worlds._read(fd, world_id + ".json"))
                prove(world)
                validate_briefs(data, world)
                try:
                    existing = strict_json(self.worlds._read(fd, self._filename(world_id)))
                    old = digest(validate_briefs(existing, world))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None:
                        raise CanonError("already_exists")
                elif old is None or old != expected_digest:
                    raise CanonError("stale_asset_source")
                self.worlds._write(fd, self._filename(world_id), canonical(data))
                return digest(data)
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, expected_digest: str, era: str) -> dict[str, str]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        lock = world_id + ".lock"
        try:
            try:
                lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  os.O_NOFOLLOW, 0o600, dir_fd=fd)
            except FileExistsError:
                raise CanonError("lease_busy") from None
            try:
                os.close(lock_fd)
                world = strict_json(self.worlds._read(fd, world_id + ".json"))
                data = strict_json(self.worlds._read(fd, self._filename(world_id)))
                validate_briefs(data, world)
                if digest(data) != expected_digest:
                    raise CanonError("stale_asset_source")
                manifest = compile_assets(data, world, era)
                payload = canonical(manifest)
                self.worlds._write(fd, world_id + ".assets.compiled.json", payload)
                return {"world_id": world_id, "source_digest": digest(world),
                        "asset_briefs_digest": digest(data),
                        "manifest_sha256": sha256(payload).hexdigest(),
                        "compiled_file": world_id + ".assets.compiled.json"}
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)
