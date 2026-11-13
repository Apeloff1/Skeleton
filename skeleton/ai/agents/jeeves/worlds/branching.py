"""Reviewed alternate-playthrough forks with replay-proven parentage.

A fork is a native SessionStore session: the existing player, engines, and
HTML5 handoff consume it without an alternate game-state implementation.
The sidecar is evidence, not authority; every read recomputes both histories.
"""
from __future__ import annotations

import os
import secrets
from typing import Any

from .session import SessionStore, _source_session, apply_choice, player_view
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _text, canonical, digest, prove,
    strict_json,
)

PROPOSAL_SCHEMA = "jeeves.world.fork_proposal.v1"
RECEIPT_SCHEMA = "jeeves.world.fork_receipt.v1"
MAX_FORK_PROMPT = 1000


def propose_fork(world: Any, parent: Any, *, parent_slot: str,
                 target_slot: str, prompt: str, at_revision: int,
                 choice_id: str) -> dict[str, Any]:
    """Preview one explicit divergent choice from a replay-verified checkpoint."""
    prove(world)
    _id(parent_slot, "parent_slot")
    _id(target_slot, "target_slot")
    _id(choice_id, "choice_id")
    _text(prompt, "prompt", MAX_FORK_PROMPT)
    if parent_slot == target_slot:
        raise CanonError("fork_same_slot")
    from .session import validate_session
    validate_session(parent, world)
    if type(at_revision) is not int or not 0 <= at_revision <= parent["revision"]:
        raise CanonError("fork_revision_invalid")
    prefix = parent["choices"][:at_revision]
    ancestor = _source_session(world, prefix)
    descendant = apply_choice(ancestor, world, choice_id)
    return {
        "schema": PROPOSAL_SCHEMA,
        "world_id": world["id"], "world_digest": digest(world),
        "parent_slot": parent_slot, "target_slot": target_slot,
        "parent_digest": digest(parent), "parent_choices": parent["choices"],
        "at_revision": at_revision, "choice_id": choice_id,
        "prompt": prompt, "initial_session_digest": digest(descendant),
        "preview": player_view(descendant, world),
    }


def _receipt(proposal: Any) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA, "world_id": proposal["world_id"],
        "world_digest": proposal["world_digest"],
        "parent_slot": proposal["parent_slot"],
        "target_slot": proposal["target_slot"],
        "parent_digest": proposal["parent_digest"],
        "parent_choices": proposal["parent_choices"],
        "at_revision": proposal["at_revision"],
        "choice_id": proposal["choice_id"],
        "prompt": proposal["prompt"],
        "prompt_digest": digest(proposal["prompt"]),
        "proposal_digest": digest(proposal),
        "initial_session_digest": proposal["initial_session_digest"],
    }


def compare_sessions(world: Any, left: Any, right: Any) -> dict[str, Any]:
    """Deterministic, read-only comparison, not an inferred causal claim."""
    from .session import validate_session
    validate_session(left, world)
    validate_session(right, world)
    common = 0
    for a, b in zip(left["choices"], right["choices"]):
        if a != b:
            break
        common += 1
    return {
        "schema": "jeeves.world.fork_comparison.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "common_revision": common,
        "left_digest": digest(left), "right_digest": digest(right),
        "left_suffix": left["choices"][common:],
        "right_suffix": right["choices"][common:],
        "left_scene": left["scene"], "right_scene": right["scene"],
        "left_ending": left["ending"], "right_ending": right["ending"],
        "left_only_flags": sorted(set(left["flags"]) - set(right["flags"])),
        "right_only_flags": sorted(set(right["flags"]) - set(left["flags"])),
        "qualification": "replay_proven_not_device_certified",
    }


def _publish_once(fd: int, name: str, data: bytes) -> None:
    """Atomically publish a new file without replacing a racing name.

    Hard-linking a private, fsynced temporary file is a no-clobber publish;
    an attacker cannot swap a symlink into the destination after the check.
    """
    if len(data) > 524288:
        raise CanonError("fork_output_too_large")
    temp = "." + secrets.token_hex(16) + ".fork.tmp"
    handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        with os.fdopen(handle, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, name, src_dir_fd=fd, dst_dir_fd=fd,
                    follow_symlinks=False)
        except FileExistsError:
            raise CanonError("fork_slot_exists") from None
        os.fsync(fd)
    finally:
        os.close(handle)
        os.unlink(temp, dir_fd=fd)


class ForkStore:
    """One descriptor-anchored world lease serializes fork and session writes."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.sessions = SessionStore(root)
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str, slot: str) -> str:
        return _id(world_id, "world_id") + "." + _id(slot, "slot") + ".fork.json"

    def _read_source(self, fd: int, world_id: str) -> dict[str, Any]:
        return self.sessions._world(fd, world_id)

    def preview(self, world_id: str, *, parent_slot: str, target_slot: str,
                prompt: str, at_revision: int, choice_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._read_source(fd, world_id)
            parent = self.sessions._session(fd, world_id, parent_slot, world)
            return propose_fork(
                world, parent, parent_slot=parent_slot, target_slot=target_slot,
                prompt=prompt, at_revision=at_revision, choice_id=choice_id,
            )
        finally:
            os.close(fd)

    def publish(self, world_id: str, proposal: Any,
                expected_parent_digest: str) -> dict[str, Any]:
        """Operator-reviewed proposal + optimistic parent lease; never overwrite."""
        _id(world_id, "world_id")
        obj = _keys(proposal, {
            "schema", "world_id", "world_digest", "parent_slot", "target_slot",
            "parent_digest", "parent_choices", "at_revision", "choice_id",
            "prompt", "initial_session_digest", "preview",
        })
        if obj["schema"] != PROPOSAL_SCHEMA or obj["world_id"] != world_id:
            raise CanonError("fork_proposal_schema_mismatch")
        if type(expected_parent_digest) is not str or len(expected_parent_digest) != 64:
            raise CanonError("fork_invalid_lease")
        fd = self.worlds._directory()
        try:
            lock_fd = self.sessions._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._read_source(fd, world_id)
                parent = self.sessions._session(
                    fd, world_id, obj["parent_slot"], world)
                if digest(parent) != expected_parent_digest:
                    raise CanonError("fork_stale_parent")
                expected = propose_fork(
                    world, parent, parent_slot=obj["parent_slot"],
                    target_slot=obj["target_slot"], prompt=obj["prompt"],
                    at_revision=obj["at_revision"], choice_id=obj["choice_id"],
                )
                if obj != expected or expected_parent_digest != obj["parent_digest"]:
                    raise CanonError("fork_proposal_mismatch")
                session_name = SessionStore._name(world_id, obj["target_slot"])
                receipt_name = self._name(world_id, obj["target_slot"])
                for name in (session_name, receipt_name):
                    try:
                        self.worlds._read(fd, name)
                    except CanonError as exc:
                        if exc.code != "not_found":
                            raise
                    else:
                        raise CanonError("fork_slot_exists")
                seed = _source_session(
                    world, parent["choices"][:obj["at_revision"]])
                child = apply_choice(seed, world, obj["choice_id"])
                # The native session is published first. A crash before the
                # receipt leaves an ordinary playable session, not false proof.
                _publish_once(fd, session_name, canonical(child))
                receipt = _receipt(obj)
                _publish_once(fd, receipt_name, canonical(receipt))
                return {"receipt": receipt, "player": player_view(child, world)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _verified(self, fd: int, world_id: str, target_slot: str
                  ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        world = self._read_source(fd, world_id)
        child = self.sessions._session(fd, world_id, target_slot, world)
        receipt = _keys(strict_json(self.worlds._read(
            fd, self._name(world_id, target_slot))), {
                "schema", "world_id", "world_digest", "parent_slot",
                "target_slot", "parent_digest", "parent_choices",
                "at_revision", "choice_id", "prompt", "prompt_digest",
                "proposal_digest", "initial_session_digest",
            })
        if (receipt["schema"] != RECEIPT_SCHEMA
                or receipt["world_id"] != world_id
                or receipt["target_slot"] != target_slot
                or receipt["world_digest"] != digest(world)):
            raise CanonError("fork_receipt_lease_mismatch")
        parent = self.sessions._session(
            fd, world_id, receipt["parent_slot"], world)
        old_parent = _source_session(world, receipt["parent_choices"])
        if (digest(old_parent) != receipt["parent_digest"]
                or parent["choices"][:len(old_parent["choices"])] != old_parent["choices"]):
            raise CanonError("fork_parent_history_mismatch")
        revision = receipt["at_revision"]
        if type(revision) is not int or not 0 <= revision <= len(old_parent["choices"]):
            raise CanonError("fork_receipt_revision_invalid")
        expected_proposal = propose_fork(
            world, old_parent, parent_slot=receipt["parent_slot"],
            target_slot=target_slot, prompt=receipt["prompt"],
            at_revision=revision, choice_id=receipt["choice_id"])
        if _receipt(expected_proposal) != receipt:
            raise CanonError("fork_receipt_mismatch")
        seed = _source_session(world, old_parent["choices"][:revision])
        genesis = apply_choice(seed, world, receipt["choice_id"])
        if (digest(genesis) != receipt["initial_session_digest"]
                or child["choices"][:len(genesis["choices"])] != genesis["choices"]):
            raise CanonError("fork_history_mismatch")
        return world, child, receipt

    def inspect(self, world_id: str, target_slot: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, child, receipt = self._verified(fd, world_id, target_slot)
            return {
                "schema": "jeeves.world.fork_inspection.v1",
                "receipt": receipt, "player": player_view(child, world),
                "history_proven": True,
            }
        finally:
            os.close(fd)

    def compare(self, world_id: str, target_slot: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, child, receipt = self._verified(fd, world_id, target_slot)
            parent = self.sessions._session(
                fd, world_id, receipt["parent_slot"], world)
            return {"receipt_digest": digest(receipt),
                    **compare_sessions(world, parent, child)}
        finally:
            os.close(fd)

    def editor(self, world_id: str, parent_slot: str,
               expected_parent_digest: str) -> dict[str, Any]:
        """Compile a private offline editor from the current native save lease."""
        from .branching_editor import render_fork_editor
        _id(world_id, "world_id")
        _id(parent_slot, "parent_slot")
        fd = self.worlds._directory()
        try:
            lock_fd = self.sessions._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._read_source(fd, world_id)
                parent = self.sessions._session(fd, world_id, parent_slot, world)
                if digest(parent) != expected_parent_digest:
                    raise CanonError("fork_stale_parent")
                page = render_fork_editor(world, parent, parent_slot)
                name = world_id + "." + parent_slot + ".fork-editor.html"
                self.worlds._write(fd, name, page)
                return {
                    "schema": "jeeves.world.fork_editor.v1",
                    "html_file": name, "html_sha256": __import__("hashlib").sha256(page).hexdigest(),
                    "world_digest": digest(world), "parent_digest": digest(parent),
                    "review_required": True,
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, target_slot: str,
                expected_world_digest: str) -> dict[str, Any]:
        inspected = self.inspect(world_id, target_slot)
        if inspected["receipt"]["world_digest"] != expected_world_digest:
            raise CanonError("fork_stale_source")
        artifact = self.worlds.compile(world_id, expected_world_digest)
        # Revalidate fork after compile: source and branch must remain leased.
        verified = self.inspect(world_id, target_slot)
        return {
            "schema": "jeeves.world.fork_playable_handoff.v1",
            "artifact": artifact, "fork_receipt_digest": digest(verified["receipt"]),
            "session_digest": verified["player"]["session_digest"],
            "qualification": "source_verified_not_release_certified",
        }
