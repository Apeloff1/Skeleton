"""Source-bound, append-only narrative context custody for original worlds.

This is a bounded author-visible note archive, not serialization of model
weights, private chain-of-thought, system prompts, or provider state. Hash
chaining detects accidental or malicious file edits but is not authentication.
"""
from __future__ import annotations

from hashlib import sha256
import os
from typing import Any

from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text, canonical, compile_html,
    digest, prove, strict_json,
)

SCHEMA = "jeeves.world.context_journal.v1"
ENTRY_SCHEMA = "jeeves.world.context_entry.v1"
HANDOFF_SCHEMA = "jeeves.world.context_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.context_receipt.v1"
GENESIS = "0" * 64
KINDS = frozenset({"author_note", "canon_rationale", "playtest_observation"})
MAX_ENTRIES = 128
MAX_ENTRY_TEXT = 2048
MAX_OUTPUT = 524288


def new_journal(world: Any) -> dict[str, Any]:
    proof = prove(world)
    return {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": proof.source_digest, "revision": 0,
        "entries": [], "head": GENESIS,
    }


def validate_journal(data: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "revision", "entries", "head",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("context_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("context_world_lease_mismatch")
    entries = _list(obj["entries"], "context.entries", MAX_ENTRIES)
    if type(obj["revision"]) is not int or obj["revision"] != len(entries):
        raise CanonError("context_revision_invalid")
    previous = GENESIS
    for seq, entry in enumerate(entries, 1):
        _keys(entry, {
            "schema", "seq", "kind", "text", "world_digest", "prev", "hash",
        })
        if entry["schema"] != ENTRY_SCHEMA or type(entry["seq"]) is not int or entry["seq"] != seq:
            raise CanonError("context_sequence_invalid")
        if type(entry["kind"]) is not str or entry["kind"] not in KINDS:
            raise CanonError("context_kind_invalid")
        _text(entry["text"], "context.text", MAX_ENTRY_TEXT)
        if entry["world_digest"] != proof.source_digest or entry["prev"] != previous:
            raise CanonError("context_chain_mismatch")
        body = {key: entry[key] for key in (
            "schema", "seq", "kind", "text", "world_digest", "prev",
        )}
        expected = digest(body)
        if type(entry["hash"]) is not str or entry["hash"] != expected:
            raise CanonError("context_hash_mismatch")
        previous = expected
    if type(obj["head"]) is not str or obj["head"] != previous:
        raise CanonError("context_head_mismatch")
    if len(canonical(obj)) > MAX_OUTPUT:
        raise CanonError("context_too_large")
    return obj


def append_entry(
    data: Any, world: Any, *, expected_head: str,
    kind: str, text: str,
) -> dict[str, Any]:
    validate_journal(data, world)
    if type(expected_head) is not str or data["head"] != expected_head:
        raise CanonError("stale_context_head")
    if len(data["entries"]) >= MAX_ENTRIES:
        raise CanonError("context_entry_budget")
    if type(kind) is not str or kind not in KINDS:
        raise CanonError("context_kind_invalid")
    _text(text, "context.text", MAX_ENTRY_TEXT)
    body = {
        "schema": ENTRY_SCHEMA, "seq": data["revision"] + 1,
        "kind": kind, "text": text, "world_digest": digest(world),
        "prev": data["head"],
    }
    entry = {**body, "hash": digest(body)}
    updated = strict_json(canonical(data))
    updated["entries"].append(entry)
    updated["revision"] += 1
    updated["head"] = entry["hash"]
    return validate_journal(updated, world)


def context_status(data: Any, world: Any) -> dict[str, Any]:
    validate_journal(data, world)
    return {
        "schema": "jeeves.world.context_status.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "revision": data["revision"], "head": data["head"],
        "journal_digest": digest(data),
        "kinds": sorted({entry["kind"] for entry in data["entries"]}),
        "note_text_exposed": False,
        "authenticity": "unkeyed_hash_chain_integrity_only",
    }


def compile_context(data: Any, world: Any) -> dict[str, Any]:
    validate_journal(data, world)
    return {
        "schema": HANDOFF_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "journal_digest": digest(data),
        "head": data["head"], "revision": data["revision"],
        "entries": [
            {"seq": item["seq"], "kind": item["kind"], "hash": item["hash"]}
            for item in data["entries"]
        ],
        "private_text_included": False,
        "authenticity": "unkeyed_hash_chain_integrity_only",
        "qualification": "source_replay_not_release_certified",
    }


class ContextStore:
    """Descriptor-held CAS custody and source-verified publication."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".context.json"

    @staticmethod
    def _artifacts(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".context.playable.html",
            world_id + ".context.handoff.json",
            world_id + ".context.receipt.json",
        )

    @staticmethod
    def _lock(fd: int, world_id: str) -> int:
        try:
            return os.open(world_id + ".lock",
                           os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        source = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(source)
        if source["id"] != world_id:
            raise CanonError("identity_mismatch")
        return source

    def _data(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        return validate_journal(
            strict_json(self.worlds._read(fd, self._name(world_id))), world)

    def read(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            return self._data(fd, world_id, world)
        finally:
            os.close(fd)

    def create(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                try:
                    self.worlds._read(fd, self._name(world_id))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                else:
                    raise CanonError("context_already_exists")
                data = new_journal(world)
                self.worlds._write(fd, self._name(world_id), canonical(data))
                return context_status(data, world)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def append(self, world_id: str, *, expected_head: str,
               kind: str, text: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._data(fd, world_id, world)
                updated = append_entry(
                    data, world, expected_head=expected_head,
                    kind=kind, text=text,
                )
                self.worlds._write(fd, self._name(world_id), canonical(updated))
                return context_status(updated, world)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def status(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            return context_status(self._data(fd, world_id, world), world)
        finally:
            os.close(fd)

    def _outputs(self, world: Any, data: Any):
        handoff = canonical(compile_context(data, world))
        html = compile_html(world).encode("utf-8")
        if max(len(html), len(handoff)) > MAX_OUTPUT:
            raise CanonError("context_artifact_too_large")
        names = self._artifacts(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "journal_digest": digest(data),
            "head": data["head"],
            "artifacts": {
                name: sha256(content).hexdigest()
                for name, content in zip(names[:2], (html, handoff))
            },
            "qualification": "source_replay_not_release_certified",
        }
        return receipt, (html, handoff)

    def compile(self, world_id: str, expected_head: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._data(fd, world_id, world)
                if data["head"] != expected_head:
                    raise CanonError("stale_context_head")
                receipt, contents = self._outputs(world, data)
                names = self._artifacts(world_id)
                for name, content in zip(names[:2], contents):
                    self.worlds._write(fd, name, content)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._data(fd, world_id, world)
                receipt, contents = self._outputs(world, data)
                names = self._artifacts(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("context_receipt_mismatch")
                for name, content in zip(names[:2], contents):
                    if self.worlds._read(fd, name) != content:
                        raise CanonError("context_artifact_mismatch", name)
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
