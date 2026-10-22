"""Independent disk verifier for actual source-owned sprite asset ZIPs.

This module rereads the saved artifact, replays every decoded PNG, animation
resource, hitbox and palette map, and refuses unknown members or oversized ZIPs.
It is NOT the compiler: generator memory is never trusted for disk attestation.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any
import zipfile

from .studio_interaction_contract import digest
from .studio_sprite_verify import verify_published_sprite, SpriteVerificationError
from .studio_sprite_hitboxes import verify_exact_sprite_hitboxes, SpriteCollisionError
from .studio_sprite_godot_resources import (
    verify_godot_sprite_resources, SpriteResourceError,
)
from .studio_sprite_palette_variants import (
    verify_original_palette_variant, SpritePaletteVariantError,
)
from .studio_sprite_surface import (
    SpriteSurfaceError, verify_authored_normals, verify_normal_texture_bytes,
)
from .studio_sprite_frame_cues import (
    SpriteCueError, emit_godot_frame_cue_files, verify_godot_frame_cue_files,
)

MAX_ARCHIVE = 16 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
MAX_ASSETS = 128
PROOF = "jeeves_sprite_receipt.json"


class SpritePackageVerificationError(ValueError):
    """Saved sprite ZIP does not match its reviewed native asset sources."""


def verify_published_sprite_package(
    path: Path, *, project_id: str, source_head_sha256: str | None,
    expected_archive_sha256: str,
) -> dict[str, Any]:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or not path.is_file()):
        raise SpritePackageVerificationError("sprite export must be an existing absolute local file")
    if type(expected_archive_sha256) is not str or len(expected_archive_sha256) != 64:
        raise SpritePackageVerificationError("source ZIP needs a pinned SHA-256")
    stat = path.stat()
    if stat.st_size < 128 or stat.st_size > MAX_ARCHIVE:
        raise SpritePackageVerificationError("sprite archive exceeds publication budget")
    published = path.read_bytes()
    if len(published) != stat.st_size or sha256(published).hexdigest() != expected_archive_sha256:
        raise SpritePackageVerificationError("sprite bytes differ from expected source build")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            entries = archive.infolist()
            names = [item.filename for item in entries]
            if (not 6 <= len(names) <= 9 * MAX_ASSETS + 1
                    or len(names) != len(set(names))
                    or names != sorted(names)
                    or PROOF not in names):
                raise SpritePackageVerificationError("sprite ZIP has missing or duplicate source entries")
            expanded = 0
            for member in entries:
                name = member.filename
                rel = PurePosixPath(name)
                if (not name or rel.is_absolute() or ".." in rel.parts
                        or "\\" in name or rel.as_posix() != name
                        or name.endswith("/") or member.is_dir()
                        or member.file_size > MAX_FILE
                        or member.compress_type != zipfile.ZIP_DEFLATED
                        or (member.external_attr >> 16) & 0o170000 != 0o100000):
                    raise SpritePackageVerificationError("unsafe native sprite archive entry")
                expanded += member.file_size
                if expanded > MAX_ARCHIVE:
                    raise SpritePackageVerificationError("sprite ZIP expansion exceeds budget")
            receipt_bytes = archive.read(PROOF)
            if len(receipt_bytes) > MAX_ARCHIVE:
                raise SpritePackageVerificationError("sprite project receipt too large")
            proof = json.loads(receipt_bytes)
            if not isinstance(proof, dict):
                raise SpritePackageVerificationError("sprite source receipt not a canonical object")
            body = dict(proof)
            pinned = body.pop("receipt_sha256", None)
            if (digest(body) != pinned
                    or proof.get("schema_version") != "skeleton.jeeves.sprite_package.v1"
                    or proof.get("project_id") != project_id
                    or proof.get("source_head_sha256") != source_head_sha256
                    or proof.get("native_engine_sprite_binding_verified") is not False
                    or proof.get("artist_review_claimed") is not False):
                raise SpritePackageVerificationError(
                    "sprite archive metadata or ownership is not independently verified"
                )
            sprites = proof.get("sprites")
            if (not isinstance(sprites, list) or not 1 <= len(sprites) <= MAX_ASSETS
                    or proof.get("asset_count") != len(sprites)):
                raise SpritePackageVerificationError("original asset count lacks source receipts")
            expected: set[str] = {PROOF}
            by_name: dict[str, dict[str, Any]] = {}
            report: dict[str, Any] = {}
            for source in sprites:
                if not isinstance(source, dict):
                    raise SpritePackageVerificationError("sprite asset does not have metadata")
                name = source.get("asset_id")
                if (not isinstance(name, str)
                        or not name.isascii()
                        or not name.replace("-", "").replace("_", "").isalnum()
                        or name in by_name):
                    raise SpritePackageVerificationError("duplicate or unsafe original sprite ID")
                by_name[name] = source
                folder = "sprites/" + name
                paths = {folder + ext for ext in (
                    ".png", ".json", ".hitboxes.json", ".tres", ".tscn",
                )}
                expected |= paths
                png = archive.read(folder + ".png")
                metadata = json.loads(archive.read(folder + ".json"))
                boxes = json.loads(archive.read(folder + ".hitboxes.json"))
                if metadata != source:
                    raise SpritePackageVerificationError(
                        "saved sprite metadata differs from reviewed receipt"
                    )
                verify_published_sprite(png, source)
                checked_boxes = verify_exact_sprite_hitboxes(source, boxes)
                verify_godot_sprite_resources(source, {
                    folder + ".tres": archive.read(folder + ".tres").decode("utf-8"),
                    folder + ".tscn": archive.read(folder + ".tscn").decode("utf-8"),
                }, directory="sprites")
                # Every optional source-generated file is required exactly when
                # the original reviewed metadata calls for it. Ignore neither
                # an added file nor a missing one.
                cue_files = emit_godot_frame_cue_files(
                    source, directory="sprites",
                )
                expected.update(cue_files)
                verify_godot_frame_cue_files(source, {
                    file: archive.read(file).decode("utf-8")
                    for file in cue_files
                }, directory="sprites")
                if source.get("normal_map") is not None:
                    normal_name = folder + ".normal.png"
                    normal_source_name = folder + ".normal.source.json"
                    expected.update((normal_name, normal_source_name))
                    normal_png = archive.read(normal_name)
                    source_heights = json.loads(archive.read(normal_source_name))
                    proof_normal = verify_normal_texture_bytes(
                        png, normal_png, source["normal_map"],
                        width=source["sheet_width_px"],
                        height=source["sheet_height_px"],
                    )
                    replay_normal = verify_authored_normals(
                        source_heights, metadata=source, color_png=png,
                        normal_png=normal_png,
                        normal_receipt=source["normal_map"],
                    )
                    if (not proof_normal["pixel_alpha_preserved"]
                            or not replay_normal["height_map_replayed"]):
                        raise SpritePackageVerificationError(
                            "published normal source did not reconstruct")
                if (checked_boxes["receipt_sha256"]
                        != proof.get("collision_receipts", {}).get(name)
                        or sha256(png).hexdigest() != proof.get("atlas_hashes", {}).get(name)):
                    raise SpritePackageVerificationError(
                        "saved native sprite or hitbox differs from original package evidence"
                    )
                report[name] = {"metadata": source, "png": png}
            if set(names) != expected:
                raise SpritePackageVerificationError(
                    "sprite ZIP has undeclared, missing or substituted original files"
                )
            skins = proof.get("palette_variant_receipts", [])
            if not isinstance(skins, list) or len(skins) > MAX_ASSETS:
                raise SpritePackageVerificationError("invalid palette skin catalogue")
            seen: set[str] = set()
            for source in skins:
                if not isinstance(source, dict):
                    raise SpritePackageVerificationError("original palette receipt is not a document")
                parent, target = source.get("base_asset_id"), source.get("asset_id")
                if (parent not in report or target not in report or target in seen
                        or parent == target):
                    raise SpritePackageVerificationError("palette variant has ambiguous source")
                seen.add(target)
                verify_original_palette_variant(report[parent], report[target], source)
    except (
        zipfile.BadZipFile, OSError, RuntimeError, UnicodeError,
        ValueError, KeyError, TypeError,
        SpriteVerificationError, SpriteCollisionError,
        SpriteResourceError, SpritePaletteVariantError, SpriteSurfaceError,
        SpriteCueError,
    ) as exc:
        if isinstance(exc, SpritePackageVerificationError):
            raise
        raise SpritePackageVerificationError(
            "saved sprite archive failed independently reproduced art verification"
        ) from exc
    receipt = {
        "schema_version": "skeleton.jeeves.sprite_disk_verification.v1",
        "project_id": project_id,
        "source_head_sha256": source_head_sha256,
        "archive_sha256": expected_archive_sha256,
        "archive_bytes": stat.st_size,
        "asset_count": len(by_name),
        "palette_variants_replayed": len(skins),
        "actual_archive_bytes_verified": True,
        "all_rgba_hitbox_and_resource_bytes_replayed": True,
        "authored_normal_maps_replayed": sum(
            1 for source in sprites if source.get("normal_map") is not None
        ),
        "frame_cue_resources_replayed": sum(
            1 for source in sprites if source.get("frame_cues")
        ),
        "native_sprite_scene_binding_verified": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


__all__ = [
    "SpritePackageVerificationError", "verify_published_sprite_package",
]
