"""Hash-chained, source-leased NPC conversation progress and atomic handoff.

A transcript is private, bounded and tied to an unchanged canonical session.
Only the final reviewed conversation response can advance the world session.
"""
from __future__ import annotations

import os
from typing import Any

from .dialogue_graph import DialogueStore, replay_dialogue
from .session import SessionStore, apply_choice, validate_session
from .world_canon import (
    CanonError, _id, _keys, _list, canonical, digest, strict_json,
)

SCHEMA = "jeeves.world.dialogue_transcript.v1"
RECEIPT_SCHEMA = "jeeves.world.dialogue_transcript_receipt.v1"
MAX_STEPS = 128


def _seed(data: Any) -> str:
    return digest({
        "world_digest": data["world_digest"],
        "cast_digest": data["cast_digest"],
        "dialogue_digest": data["dialogue_digest"],
        "session_digest": data["session_digest"],
        "conversation": data["conversation"], "slot": data["slot"],
    })


def _chain(data: Any) -> list[dict[str, Any]]:
    previous = _seed(data)
    chain = []
    for index, response in enumerate(data["responses"]):
        previous = digest({
            "previous": previous, "response": response, "index": index,
        })
        chain.append({"response": response, "sha256": previous})
    return chain


def validate_transcript(data: Any, world: Any, cast: Any, dialogue: Any,
                        session: Any) -> dict[str, Any]:
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "cast_digest",
        "dialogue_digest", "session_digest", "slot", "conversation",
        "responses", "chain", "revision",
    })
    if obj["schema"] != SCHEMA or obj["world_id"] != world["id"]:
        raise CanonError("dialogue_transcript_schema_mismatch")
    if (obj["world_digest"] != digest(world) or
            obj["cast_digest"] != digest(cast) or
            obj["dialogue_digest"] != digest(dialogue) or
            obj["session_digest"] != digest(session)):
        raise CanonError("dialogue_transcript_stale_source")
    _id(obj["slot"], "slot")
    _id(obj["conversation"], "conversation")
    responses = _list(obj["responses"], "responses", MAX_STEPS)
    for response in responses:
        _id(response, "response")
    if type(obj["revision"]) is not int or obj["revision"] != len(responses):
        raise CanonError("dialogue_transcript_revision_mismatch")
    if obj["chain"] != _chain(obj):
        raise CanonError("dialogue_transcript_chain_mismatch")
    replay = replay_dialogue(
        dialogue, world, cast, obj["conversation"], responses)
    if replay["scene"] != session["scene"]:
        raise CanonError("dialogue_transcript_wrong_scene")
    if len(canonical(obj)) > 524288:
        raise CanonError("dialogue_transcript_too_large")
    return obj


class DialogueTranscriptStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.dialogue = DialogueStore(root)

    @staticmethod
    def _name(world_id: str, slot: str) -> str:
        return _id(world_id, "world_id") + "." + _id(slot, "slot") + ".dialogue.transcript.json"

    @staticmethod
    def _receipt_name(world_id: str, slot: str) -> str:
        return _id(world_id, "world_id") + "." + _id(slot, "slot") + ".dialogue.transcript.receipt.json"

    def _sources(self, fd: int, world_id: str, slot: str):
        world, cast = self.dialogue._sources(fd, world_id)
        dialogue = self.dialogue._source(fd, world_id, world, cast)
        if dialogue["approved"] is not True or cast["approved"] is not True:
            raise CanonError("dialogue_review_required")
        session = validate_session(strict_json(self.dialogue.worlds._read(
            fd, SessionStore._name(world_id, slot))), world)
        return world, cast, dialogue, session

    def _read(self, fd: int, world_id: str, slot: str, sources: Any):
        data = strict_json(self.dialogue.worlds._read(
            fd, self._name(world_id, slot)))
        if data.get("slot") != slot:
            raise CanonError("dialogue_transcript_slot_mismatch")
        return validate_transcript(data, *sources)

    def begin(self, world_id: str, slot: str, conversation: str, *,
              expected_session_digest: str,
              expected_dialogue_digest: str) -> dict[str, Any]:
        _id(conversation, "conversation")
        fd = self.dialogue.worlds._directory()
        try:
            self.dialogue._lock(fd, world_id)
            try:
                world, cast, dialogue, session = sources = self._sources(
                    fd, world_id, slot)
                if (digest(session) != expected_session_digest or
                        digest(dialogue) != expected_dialogue_digest):
                    raise CanonError("dialogue_transcript_stale_lease")
                replay = replay_dialogue(dialogue, world, cast, conversation, [])
                if replay["scene"] != session["scene"]:
                    raise CanonError("dialogue_transcript_wrong_scene")
                try:
                    self.dialogue.worlds._read(fd, self._name(world_id, slot))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                else:
                    raise CanonError("dialogue_transcript_already_exists")
                data = {
                    "schema": SCHEMA, "world_id": world_id,
                    "world_digest": digest(world), "cast_digest": digest(cast),
                    "dialogue_digest": digest(dialogue),
                    "session_digest": digest(session), "slot": slot,
                    "conversation": conversation, "responses": [],
                    "chain": [], "revision": 0,
                }
                validate_transcript(data, *sources)
                self.dialogue.worlds._write(
                    fd, self._name(world_id, slot), canonical(data))
                return {"transcript": data, "transcript_digest": digest(data),
                        "replay": replay}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def inspect(self, world_id: str, slot: str) -> dict[str, Any]:
        fd = self.dialogue.worlds._directory()
        try:
            self.dialogue._lock(fd, world_id)
            try:
                sources = self._sources(fd, world_id, slot)
                data = self._read(fd, world_id, slot, sources)
                return {"transcript": data, "transcript_digest": digest(data),
                        "replay": replay_dialogue(
                            sources[2], sources[0], sources[1],
                            data["conversation"], data["responses"])}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def append(self, world_id: str, slot: str, response_id: str,
               expected_digest: str) -> dict[str, Any]:
        _id(response_id, "response_id")
        fd = self.dialogue.worlds._directory()
        try:
            self.dialogue._lock(fd, world_id)
            try:
                sources = self._sources(fd, world_id, slot)
                data = self._read(fd, world_id, slot, sources)
                if digest(data) != expected_digest:
                    raise CanonError("dialogue_transcript_stale_edit")
                if len(data["responses"]) >= MAX_STEPS:
                    raise CanonError("dialogue_transcript_step_budget")
                prior = replay_dialogue(
                    sources[2], sources[0], sources[1],
                    data["conversation"], data["responses"])
                if prior["world_choice"] is not None:
                    raise CanonError("dialogue_transcript_already_complete")
                updated = strict_json(canonical(data))
                updated["responses"].append(response_id)
                updated["revision"] += 1
                updated["chain"] = _chain(updated)
                validate_transcript(updated, *sources)
                self.dialogue.worlds._write(
                    fd, self._name(world_id, slot), canonical(updated))
                return {"transcript_digest": digest(updated),
                        "replay": replay_dialogue(
                            sources[2], sources[0], sources[1],
                            updated["conversation"], updated["responses"])}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def commit(self, world_id: str, slot: str, expected_digest: str) -> dict[str, Any]:
        fd = self.dialogue.worlds._directory()
        try:
            self.dialogue._lock(fd, world_id)
            try:
                world, cast, dialogue, session = sources = self._sources(
                    fd, world_id, slot)
                data = self._read(fd, world_id, slot, sources)
                if digest(data) != expected_digest:
                    raise CanonError("dialogue_transcript_stale_edit")
                replay = replay_dialogue(
                    dialogue, world, cast,
                    data["conversation"], data["responses"])
                if replay["world_choice"] is None:
                    raise CanonError("dialogue_transcript_incomplete")
                updated = apply_choice(session, world, replay["world_choice"])
                receipt = {
                    "schema": RECEIPT_SCHEMA, "world_id": world_id,
                    "slot": slot, "conversation": data["conversation"],
                    "world_digest": digest(world), "cast_digest": digest(cast),
                    "dialogue_digest": digest(dialogue),
                    "session_before": digest(session),
                    "session_after": digest(updated),
                    "transcript_digest": digest(data),
                    "chain_head": (data["chain"][-1]["sha256"]
                                   if data["chain"] else _seed(data)),
                    "responses": data["responses"],
                    "world_choice": replay["world_choice"],
                }
                # Session write first: a crash before receipt publication fails
                # closed on the stale transcript instead of double-committing.
                self.dialogue.worlds._write(
                    fd, SessionStore._name(world_id, slot), canonical(updated))
                self.dialogue.worlds._write(
                    fd, self._receipt_name(world_id, slot), canonical(receipt))
                os.unlink(self._name(world_id, slot), dir_fd=fd)
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def cancel(self, world_id: str, slot: str, expected_digest: str) -> None:
        fd = self.dialogue.worlds._directory()
        try:
            self.dialogue._lock(fd, world_id)
            try:
                sources = self._sources(fd, world_id, slot)
                data = self._read(fd, world_id, slot, sources)
                if digest(data) != expected_digest:
                    raise CanonError("dialogue_transcript_stale_edit")
                os.unlink(self._name(world_id, slot), dir_fd=fd)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify_receipt(self, world_id: str, slot: str) -> dict[str, Any]:
        fd = self.dialogue.worlds._directory()
        try:
            self.dialogue._lock(fd, world_id)
            try:
                world, cast, dialogue, session = self._sources(fd, world_id, slot)
                receipt = strict_json(self.dialogue.worlds._read(
                    fd, self._receipt_name(world_id, slot)))
                if type(receipt) is not dict or receipt.get("schema") != RECEIPT_SCHEMA:
                    raise CanonError("dialogue_transcript_receipt_invalid")
                if receipt.get("session_after") != digest(session):
                    raise CanonError("dialogue_transcript_receipt_stale")
                if (receipt.get("world_digest") != digest(world) or
                        receipt.get("cast_digest") != digest(cast) or
                        receipt.get("dialogue_digest") != digest(dialogue)):
                    raise CanonError("dialogue_transcript_receipt_source_mismatch")
                # Reconstruct the exact archived transcript and hash chain.
                candidate = {
                    "schema": SCHEMA, "world_id": world_id,
                    "world_digest": digest(world), "cast_digest": digest(cast),
                    "dialogue_digest": digest(dialogue),
                    "session_digest": receipt["session_before"],
                    "slot": slot, "conversation": receipt["conversation"],
                    "responses": receipt["responses"],
                    "chain": [], "revision": len(receipt["responses"]),
                }
                candidate["chain"] = _chain(candidate)
                if (digest(candidate) != receipt["transcript_digest"] or
                        (candidate["chain"][-1]["sha256"] if candidate["chain"]
                         else _seed(candidate)) != receipt["chain_head"]):
                    raise CanonError("dialogue_transcript_receipt_chain_mismatch")
                from .session import _source_session
                if not session["choices"] or digest(_source_session(
                        world, session["choices"][:-1])) != receipt["session_before"]:
                    raise CanonError("dialogue_transcript_receipt_session_mismatch")
                replay = replay_dialogue(
                    dialogue, world, cast, receipt["conversation"],
                    receipt["responses"])
                if (replay["world_choice"] != receipt["world_choice"] or
                        not session["choices"] or
                        session["choices"][-1] != receipt["world_choice"]):
                    raise CanonError("dialogue_transcript_receipt_replay_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
