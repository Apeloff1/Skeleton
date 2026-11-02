"""Verified, source-bound, multi-plane playable publication for Jeeves worlds."""
from __future__ import annotations

from hashlib import sha256
import os
import stat
from typing import Any

from .asset_briefs import compile_assets, validate_briefs
from .timeline import compile_timeline, validate_timeline
from .world_canon import (
    CanonError, WorldStore, _id, canonical, compile_html, digest, prove,
    strict_json,
)

BUNDLE_SCHEMA = "jeeves.world.playable_bundle.v1"
RECEIPT_SCHEMA = "jeeves.world.bundle_receipt.v1"
MAX_ARTIFACT_BYTES = 1572864


def _artifact_read(fd: int, name: str) -> bytes:
    try:
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
    except FileNotFoundError:
        raise CanonError("artifact_missing", name) from None
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARTIFACT_BYTES:
            raise CanonError("unsafe_artifact", name)
        with os.fdopen(os.dup(handle), "rb") as stream:
            content = stream.read(MAX_ARTIFACT_BYTES + 1)
        if len(content) > MAX_ARTIFACT_BYTES:
            raise CanonError("artifact_too_large")
        return content
    finally:
        os.close(handle)


def _source_triplet(fd: int, store: WorldStore, world_id: str):
    _id(world_id, "world_id")
    world = strict_json(store._read(fd, world_id + ".json"))
    assets = strict_json(store._read(fd, world_id + ".assets.json"))
    timeline = strict_json(store._read(fd, world_id + ".timeline.json"))
    prove(world)
    validate_briefs(assets, world)
    validate_timeline(timeline, world)
    if world["id"] != world_id:
        raise CanonError("identity_mismatch")
    return world, assets, timeline


def _names(world_id: str) -> tuple[str, str, str]:
    _id(world_id, "world_id")
    return (world_id + ".bundle.html",
            world_id + ".bundle.manifest.json",
            world_id + ".bundle.receipt.json")


def _expected(world: Any, assets: Any, timeline: Any,
              world_digest: str, asset_digest: str, timeline_digest: str) -> None:
    if digest(world) != world_digest:
        raise CanonError("stale_world_source")
    if digest(assets) != asset_digest:
        raise CanonError("stale_asset_source")
    if digest(timeline) != timeline_digest:
        raise CanonError("stale_timeline")


def _manifest(world: Any, assets: Any, timeline: Any, era: str,
              html_digest: str) -> dict[str, Any]:
    return {
        "schema": BUNDLE_SCHEMA,
        "world_id": world["id"],
        "world_digest": digest(world),
        "asset_briefs_digest": digest(assets),
        "timeline_digest": digest(timeline),
        "engine_era": era,
        "playable_html_sha256": html_digest,
        "engine_assets": compile_assets(assets, world, era),
        "temporal_events": compile_timeline(timeline, world),
        "source_custody": "operator_reviewed_source_leased_not_signed",
    }


class PlayableBundleStore:
    """Publish HTML, engine manifest, then receipt as a commit marker.

    A crash may leave unreferenced partial files; only a receipt whose hashes
    match every file is accepted by verification. All operations use the same
    per-world exclusive lock as authored edits and engine handoffs.
    """
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    def compile(self, world_id: str, *, world_digest: str,
                asset_digest: str, timeline_digest: str,
                era: str) -> dict[str, Any]:
        html_name, manifest_name, receipt_name = _names(world_id)
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
                world, assets, timeline = _source_triplet(fd, self.worlds, world_id)
                _expected(world, assets, timeline, world_digest,
                          asset_digest, timeline_digest)
                html = compile_html(world).encode("utf-8")
                html_hash = sha256(html).hexdigest()
                manifest = _manifest(world, assets, timeline, era, html_hash)
                manifest_bytes = canonical(manifest)
                receipt = {
                    "schema": RECEIPT_SCHEMA,
                    "world_id": world_id,
                    "world_digest": world_digest,
                    "asset_briefs_digest": asset_digest,
                    "timeline_digest": timeline_digest,
                    "engine_era": era,
                    "html_file": html_name,
                    "html_sha256": html_hash,
                    "manifest_file": manifest_name,
                    "manifest_sha256": sha256(manifest_bytes).hexdigest(),
                    "publication_state": "complete_source_bound",
                }
                self.worlds._write(fd, html_name, html)
                self.worlds._write(fd, manifest_name, manifest_bytes)
                # The receipt is published last; stale/partial receipts cannot
                # pass verification against the exact source and artifact hashes.
                self.worlds._write(fd, receipt_name, canonical(receipt))
                return receipt
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        html_name, manifest_name, receipt_name = _names(world_id)
        fd = self.worlds._directory()
        try:
            receipt = strict_json(self.worlds._read(fd, receipt_name))
            if type(receipt) is not dict or set(receipt) != {
                "schema", "world_id", "world_digest", "asset_briefs_digest",
                "timeline_digest", "engine_era", "html_file", "html_sha256",
                "manifest_file", "manifest_sha256", "publication_state",
            }:
                raise CanonError("invalid_bundle_receipt")
            if (receipt["schema"] != RECEIPT_SCHEMA or
                receipt["world_id"] != world_id or
                receipt["html_file"] != html_name or
                receipt["manifest_file"] != manifest_name or
                receipt["publication_state"] != "complete_source_bound"):
                raise CanonError("invalid_bundle_receipt")
            world, assets, timeline = _source_triplet(fd, self.worlds, world_id)
            _expected(world, assets, timeline, receipt["world_digest"],
                      receipt["asset_briefs_digest"], receipt["timeline_digest"])
            html = _artifact_read(fd, html_name)
            manifest_bytes = _artifact_read(fd, manifest_name)
            if (sha256(html).hexdigest() != receipt["html_sha256"] or
                sha256(manifest_bytes).hexdigest() != receipt["manifest_sha256"]):
                raise CanonError("bundle_artifact_tampered")
            manifest = strict_json(manifest_bytes)
            if (type(manifest) is not dict or
                manifest.get("schema") != BUNDLE_SCHEMA or
                manifest.get("playable_html_sha256") != receipt["html_sha256"] or
                manifest.get("world_digest") != receipt["world_digest"] or
                manifest.get("asset_briefs_digest") != receipt["asset_briefs_digest"] or
                manifest.get("timeline_digest") != receipt["timeline_digest"] or
                manifest.get("engine_era") != receipt["engine_era"]):
                raise CanonError("bundle_manifest_mismatch")
            # A matching receipt alone is insufficient: recompile deterministically
            # and compare against actual source and engine policy at verification.
            expected_html = compile_html(world).encode("utf-8")
            expected_manifest = canonical(_manifest(
                world, assets, timeline, receipt["engine_era"],
                sha256(expected_html).hexdigest()))
            if html != expected_html or manifest_bytes != expected_manifest:
                raise CanonError("bundle_recompile_mismatch")
            return receipt
        finally:
            os.close(fd)
