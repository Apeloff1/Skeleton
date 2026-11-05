"""Canonical original-world player session with durable, replay-verified choices.

Actual player decisions, unlike route plans, are persisted as a source-leased
event trace. Every read independently replays the full trace from the
canonical world and refuses forged scene, flags or ending state.
"""
from __future__ import annotations

from hashlib import sha256
import os
from typing import Any, Callable

from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, canonical, digest, prove,
    strict_json,
)

SCHEMA = "jeeves.world.session.v1"
EXPORT_SCHEMA = "jeeves.world.session_export.v1"
MAX_CHOICES = 512
SourceGuard = Callable[[int, str], None]


def replay_choices(world: Any, choices: Any) -> dict[str, Any]:
    prove(world)
    trace = _list(choices, "choices", MAX_CHOICES)
    by_id = {item["id"]: item for item in world["choices"]}
    endings = {item["scene"]: item["label"] for item in world["endings"]}
    scene = world["start"]
    flags: set[str] = set()
    steps = [{"scene": scene, "flags": [], "choice": None}]
    for choice_id in trace:
        _id(choice_id, "choice_id")
        choice = by_id.get(choice_id)
        if scene in endings:
            raise CanonError("session_after_ending")
        if choice is None or choice["from"] != scene:
            raise CanonError("session_invalid_transition", choice_id)
        if not set(choice["requires"]) <= flags:
            raise CanonError("session_unearned_choice", choice_id)
        flags.update(choice["grants"])
        scene = choice["to"]
        steps.append({
            "scene": scene, "flags": sorted(flags), "choice": choice_id,
        })
    return {
        "scene": scene, "flags": sorted(flags),
        "ending": endings.get(scene), "steps": steps,
    }


def _source_session(world: Any, choices: list[str]) -> dict[str, Any]:
    replay = replay_choices(world, choices)
    return {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "choices": list(choices),
        "scene": replay["scene"], "flags": replay["flags"],
        "ending": replay["ending"], "revision": len(choices),
    }


def new_session(world: Any) -> dict[str, Any]:
    return _source_session(world, [])


def validate_session(data: Any, world: Any) -> dict[str, Any]:
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "choices", "scene",
        "flags", "ending", "revision",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("session_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != digest(world):
        raise CanonError("session_world_lease_mismatch")
    expected = _source_session(world, obj["choices"])
    if obj != expected:
        raise CanonError("session_replay_mismatch")
    if len(canonical(obj)) > 524288:
        raise CanonError("session_too_large")
    return obj


def apply_choice(data: Any, world: Any, choice_id: str) -> dict[str, Any]:
    validate_session(data, world)
    _id(choice_id, "choice_id")
    if data["ending"] is not None:
        raise CanonError("session_already_ended")
    if len(data["choices"]) >= MAX_CHOICES:
        raise CanonError("session_choice_budget")
    return _source_session(world, data["choices"] + [choice_id])


def player_view(data: Any, world: Any) -> dict[str, Any]:
    validate_session(data, world)
    scene = next(item for item in world["scenes"] if item["id"] == data["scene"])
    available = sorted([
        {"id": choice["id"], "label": choice["label"], "to": choice["to"]}
        for choice in world["choices"]
        if choice["from"] == data["scene"]
        and set(choice["requires"]) <= set(data["flags"])
    ], key=lambda item: item["id"])
    return {
        "world_id": world["id"], "world_digest": digest(world),
        "scene": scene, "flags": data["flags"], "ending": data["ending"],
        "available_choices": available,
        "session_digest": digest(data), "revision": data["revision"],
        "playable": True, "qualification": "source_replay_not_device_certified",
    }


def export_session(data: Any, world: Any) -> dict[str, Any]:
    validate_session(data, world)
    payload = {"schema": EXPORT_SCHEMA, "session": data}
    return {**payload, "checksum_sha256": digest(payload)}


def import_session(payload: Any, world: Any) -> dict[str, Any]:
    obj = _keys(payload, {"schema", "session", "checksum_sha256"})
    if obj["schema"] != EXPORT_SCHEMA:
        raise CanonError("session_export_schema_mismatch")
    checksum = obj["checksum_sha256"]
    if type(checksum) is not str or len(checksum) != 64:
        raise CanonError("session_checksum_invalid")
    if checksum != digest({"schema": EXPORT_SCHEMA, "session": obj["session"]}):
        raise CanonError("session_checksum_mismatch")
    return validate_session(obj["session"], world)


class SessionStore:
    """One world lock serializes edits and all player slots for a world."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str, slot: str) -> str:
        return _id(world_id, "world_id") + "." + _id(slot, "slot") + ".session.json"

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _session(self, fd: int, world_id: str, slot: str,
                 world: Any) -> dict[str, Any]:
        return validate_session(
            strict_json(self.worlds._read(fd, self._name(world_id, slot))), world)

    def _lock(self, fd: int, world_id: str) -> int:
        _id(world_id, "world_id")
        try:
            return os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                           os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        except OSError as exc:
            # A failed acquisition never grants ownership of the lock. Surface
            # filesystem custody failures as typed session errors rather than
            # misclassifying them as CLI input-file permission problems.
            raise CanonError("lease_unavailable") from exc

    @staticmethod
    def _require_world_lease(world: Any, expected_world_digest: str | None) -> None:
        """Reject revisions made between laptop artifact proof and session I/O.

        The check for mutating operations occurs under the world writer lock,
        preventing a source edit from silently reauthorizing a player session.
        """
        if expected_world_digest is not None and digest(world) != expected_world_digest:
            raise CanonError("session_world_lease_mismatch")

    def read(self, world_id: str, slot: str) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            return self._session(fd, world_id, slot, world)
        finally:
            os.close(fd)

    def create(self, world_id: str, slot: str, *,
               imported: Any = None,
               expected_world_digest: str | None = None,
               source_guard: SourceGuard | None = None) -> dict[str, Any]:
        _id(world_id, "world_id")
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                self._require_world_lease(world, expected_world_digest)
                if source_guard is not None:
                    source_guard(fd, world_id)
                data = (import_session(imported, world) if imported is not None
                        else new_session(world))
                try:
                    self.worlds._read(fd, self._name(world_id, slot))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                else:
                    raise CanonError("session_already_exists")
                self.worlds._write(fd, self._name(world_id, slot),
                                   canonical(data))
                return player_view(data, world)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def choose(self, world_id: str, slot: str, choice_id: str,
               expected_digest: str, *,
               expected_world_digest: str | None = None,
               source_guard: SourceGuard | None = None) -> dict[str, Any]:
        _id(world_id, "world_id")
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                self._require_world_lease(world, expected_world_digest)
                if source_guard is not None:
                    source_guard(fd, world_id)
                data = self._session(fd, world_id, slot, world)
                if digest(data) != expected_digest:
                    raise CanonError("stale_session")
                updated = apply_choice(data, world, choice_id)
                self.worlds._write(fd, self._name(world_id, slot),
                                   canonical(updated))
                return player_view(updated, world)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _read_guarded(self, fd: int, world_id: str,
                      source_guard: SourceGuard | None,
                      operation: Callable[[], Any]) -> Any:
        """Pin approved artifacts and player reads to one writer lease."""
        if source_guard is None:
            return operation()
        lock_fd = self._lock(fd, world_id)
        try:
            os.close(lock_fd)
            source_guard(fd, world_id)
            return operation()
        finally:
            os.unlink(world_id + ".lock", dir_fd=fd)

    def inspect(self, world_id: str, slot: str, *,
                expected_world_digest: str | None = None,
                source_guard: SourceGuard | None = None) -> dict[str, Any]:
        _id(world_id, "world_id")
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            def operation() -> dict[str, Any]:
                world = self._world(fd, world_id)
                self._require_world_lease(world, expected_world_digest)
                return player_view(self._session(fd, world_id, slot, world), world)
            return self._read_guarded(fd, world_id, source_guard, operation)
        finally:
            os.close(fd)

    def export(self, world_id: str, slot: str, *,
               expected_world_digest: str | None = None,
               source_guard: SourceGuard | None = None) -> dict[str, Any]:
        _id(world_id, "world_id")
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            def operation() -> dict[str, Any]:
                world = self._world(fd, world_id)
                self._require_world_lease(world, expected_world_digest)
                return export_session(self._session(fd, world_id, slot, world), world)
            return self._read_guarded(fd, world_id, source_guard, operation)
        finally:
            os.close(fd)

    def preflight_import(self, world_id: str, imported: Any, *,
                         expected_world_digest: str | None = None,
                         source_guard: SourceGuard | None = None) -> dict[str, Any]:
        """Verify portable save without creating a slot or approving canon."""
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            def operation() -> dict[str, Any]:
                world = self._world(fd, world_id)
                self._require_world_lease(world, expected_world_digest)
                data = import_session(imported, world)
                view = player_view(data, world)
                return {
                    "world_id": world_id,
                    "world_digest": view["world_digest"],
                    "session_digest": view["session_digest"],
                    "revision": view["revision"],
                    "scene": view["scene"]["id"],
                    "ending": view["ending"],
                    "restorable": True,
                    "qualification": "verified_preview_not_persisted",
                }
            return self._read_guarded(fd, world_id, source_guard, operation)
        finally:
            os.close(fd)
