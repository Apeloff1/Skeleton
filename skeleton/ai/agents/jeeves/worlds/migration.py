"""Explicit, replay-proven migration of an offline save across a world revision.

A checksum is an integrity check, never an author signature. The operator must
supply the old canonical world and its checkpoint; the new canonical world is
read from private custody under an exclusive lease. This module never silently
reinterprets earned choices, flags, scenes or endings.
"""
from __future__ import annotations

from typing import Any

from .session import (
    SessionStore, _source_session, import_session, player_view, replay_choices,
)
from .world_canon import (
    CanonError, WorldStore, _id, _text, canonical, digest, prove,
)

SCHEMA = "jeeves.world.migration_preview.v1"
RECEIPT_SCHEMA = "jeeves.world.migration_receipt.v1"
MAX_REMAPS = 512


def _choice_mapping(value: Any, used: set[str]) -> dict[str, str]:
    if type(value) is not dict or len(value) > MAX_REMAPS:
        raise CanonError("migration_invalid_mapping")
    result: dict[str, str] = {}
    for old_id, new_id in value.items():
        _id(old_id, "old_choice_id")
        _id(new_id, "new_choice_id")
        if old_id not in used:
            raise CanonError("migration_unused_mapping", old_id)
        result[old_id] = new_id
    mapped = [result.get(choice_id, choice_id) for choice_id in sorted(used)]
    if len(set(mapped)) != len(mapped):
        raise CanonError("migration_mapping_collision")
    return result


def preview_migration(
    old_world: Any, checkpoint: Any, target_world: Any,
    choice_map: Any,
) -> dict[str, Any]:
    """Pure, bounded proof of a save migration; never mutates a store."""
    old_proof = prove(old_world)
    new_proof = prove(target_world)
    if old_world["id"] != target_world["id"]:
        raise CanonError("migration_world_identity_mismatch")
    if old_proof.source_digest == new_proof.source_digest:
        raise CanonError("migration_revision_unchanged")
    old_session = import_session(checkpoint, old_world)
    used = set(old_session["choices"])
    mapping = _choice_mapping(choice_map, used)
    old_by_id = {item["id"]: item for item in old_world["choices"]}
    new_by_id = {item["id"]: item for item in target_world["choices"]}
    for old_id in sorted(used):
        new_id = mapping.get(old_id, old_id)
        old_edge = old_by_id[old_id]
        new_edge = new_by_id.get(new_id)
        if new_edge is None:
            raise CanonError("migration_choice_missing", new_id)
        # A renamed choice is acceptable; its actual causal effect may not
        # change. Labels are presentation, not earned state.
        for key in ("from", "to", "requires", "grants"):
            if old_edge[key] != new_edge[key]:
                raise CanonError("migration_choice_semantics_changed", old_id)
    new_trace = [mapping.get(item, item) for item in old_session["choices"]]
    new_replay = replay_choices(target_world, new_trace)
    old_replay = replay_choices(old_world, old_session["choices"])
    for key in ("scene", "flags", "ending"):
        if new_replay[key] != old_replay[key]:
            raise CanonError("migration_replay_diverged", key)
    new_session = _source_session(target_world, new_trace)
    # Never include private story prose or the full checkpoint in the receipt.
    return {
        "schema": SCHEMA,
        "world_id": target_world["id"],
        "old_world_digest": old_proof.source_digest,
        "target_world_digest": new_proof.source_digest,
        "old_session_digest": digest(old_session),
        "target_session_digest": digest(new_session),
        "choice_map": {key: mapping[key] for key in sorted(mapping)},
        "old_choices": list(old_session["choices"]),
        "new_choices": new_trace,
        "scene": new_replay["scene"],
        "flags": new_replay["flags"],
        "ending": new_replay["ending"],
        "revision": new_session["revision"],
        "playable_proof_digest": digest(new_proof.as_dict()),
        "qualification": "replay_proven_not_device_or_release_certified",
    }


class MigrationStore:
    """Apply an operator-reviewed migration to a NEW slot, never overwrite."""
    def __init__(self, root: str) -> None:
        self.sessions = SessionStore(root)
        self.worlds = WorldStore(root)

    def preview(self, world_id: str, old_world: Any, checkpoint: Any,
                choice_map: Any) -> dict[str, Any]:
        _id(world_id, "world_id")
        target = self.worlds.read(world_id)
        return preview_migration(old_world, checkpoint, target, choice_map)

    def apply(self, world_id: str, slot: str, old_world: Any,
              checkpoint: Any, choice_map: Any, *,
              expected_preview_digest: str, review_note: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        _id(slot, "slot")
        _text(review_note, "review_note", 512)
        if type(expected_preview_digest) is not str or len(expected_preview_digest) != 64:
            raise CanonError("migration_invalid_lease")
        fd = self.worlds._directory()
        try:
            lock_fd = self.sessions._lock(fd, world_id)
            try:
                import os
                os.close(lock_fd)
                target = self.sessions._world(fd, world_id)
                preview = preview_migration(
                    old_world, checkpoint, target, choice_map)
                if digest(preview) != expected_preview_digest:
                    raise CanonError("migration_stale_preview")
                name = self.sessions._name(world_id, slot)
                try:
                    self.worlds._read(fd, name)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                else:
                    raise CanonError("session_already_exists")
                migrated = _source_session(target, preview["new_choices"])
                if digest(migrated) != preview["target_session_digest"]:
                    raise CanonError("migration_replay_diverged")
                # Session is the sole published object: no half-written
                # multi-file migration receipt can masquerade as a commit.
                self.worlds._write(fd, name, canonical(migrated))
                return {
                    "schema": RECEIPT_SCHEMA,
                    "world_id": world_id, "slot": slot,
                    "preview_digest": expected_preview_digest,
                    "review_note": review_note,
                    "player": player_view(migrated, target),
                    "qualification": "operator_reviewed_source_replay_only",
                }
            finally:
                import os
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            import os
            os.close(fd)
