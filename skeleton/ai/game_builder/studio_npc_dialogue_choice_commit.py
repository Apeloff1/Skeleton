"""Replay-verified NPC dialogue choice commitment from playable contact proof.

A committed choice here is a canonical quest receipt, not proof of spoken
dialogue, a native game-engine transition, or a durable write until published.
"""
from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError, replay_quest
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_npc_dialogue_contact import (
    replay_npc_dialogue_contact,
)

SCHEMA = "skeleton.game_builder.studio_npc_dialogue_choice_commit.v1"
FILENAME = "studio_npc_dialogue_choice_commit.json"
MAX_BYTES = 512 * 1024


def _alternative(value: object) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 256
            or value != value.strip() or any(ord(char) < 32 for char in value)):
        raise StudioQuestError("invalid authored NPC dialogue alternative")
    try:
        if len(value.encode("utf-8", "strict")) > 1024:
            raise StudioQuestError("authored NPC dialogue alternative exceeds budget")
    except UnicodeError as exc:
        raise StudioQuestError("noncanonical NPC dialogue alternative") from exc
    return value


def compile_npc_dialogue_choice_commit(
    documents: Mapping[str, Any], contact_receipt: object, *, alternative: str,
    authorized: bool, expected_contact_digest: str,
    expected_source_digest: str, expected_walk_digest: str,
    expected_quest_digest: str,
) -> dict[str, Any]:
    """Commit exactly one unlocked authored alternative to a replayable receipt."""
    if authorized is not True:
        raise PermissionError("NPC dialogue choice requires operator authorization")
    for name, value in (
        ("contact", expected_contact_digest), ("source", expected_source_digest),
        ("walk", expected_walk_digest), ("quest", expected_quest_digest),
    ):
        _lease(value, "NPC dialogue choice " + name)
    alternative = _alternative(alternative)
    source_before = _canonical(documents)
    if len(source_before) > MAX_BYTES:
        raise StudioQuestError("NPC dialogue choice source exceeds budget")
    contact = replay_npc_dialogue_contact(
        documents, contact_receipt, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
    if contact["receipt_digest"] != expected_contact_digest:
        raise StudioQuestError("stale NPC dialogue contact lease")
    if (contact["playable_proximity_verified"] is not True
            or contact["quest_unlock_replay_verified"] is not True
            or contact["quest_choice_committed"] is not False
            or contact["dialogue_spoken_verified"] is not False
            or contact["file_write_performed"] is not False):
        raise StudioQuestError("NPC dialogue contact lacks uncommitted proof")
    card = contact["dialogue_card"]
    if (card["status"] != "available"
            or card["npc_id"] != contact["npc_id"]
            or card["scene_id"] != contact["scene_id"]):
        raise StudioQuestError("NPC dialogue choice scene is not available")
    selected = [
        item for item in contact["choice_previews"]
        if item["alternative"] == alternative
    ]
    if len(selected) != 1:
        raise StudioQuestError("NPC dialogue choice is not uniquely authored")
    preview = selected[0]
    if (preview["npc_id"] != contact["npc_id"]
            or preview["scene_id"] != contact["scene_id"]
            or preview["quest_stage"] != card["quest_stage"]
            or preview["card_digest"] != card["card_digest"]
            or preview["before_session_digest"] != expected_quest_digest
            or preview["choice_committed"] is not False
            or preview["external_evidence_verified"] is not False):
        raise StudioQuestError("NPC dialogue choice preview proof diverged")
    next_actions = contact["quest_actions"] + [[card["quest_stage"], alternative]]
    next_session = replay_quest(documents, next_actions, authorized=True)
    if (next_session.digest != preview["after_session_digest"]
            or next_session.project_id != contact["project_id"]
            or next_session.source_digest != expected_source_digest
            or len(next_session.choices) != len(next_actions)):
        raise StudioQuestError("NPC dialogue choice replay consequence drift")
    if _canonical(documents) != source_before:
        raise StudioQuestError("NPC dialogue source changed during commitment")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": contact["project_id"],
        "source_digest": expected_source_digest,
        "walk_session_digest": expected_walk_digest,
        "previous_quest_session_digest": expected_quest_digest,
        "next_quest_session_digest": next_session.digest,
        "contact_digest": expected_contact_digest,
        "contact_receipt": contact, "quest_actions": next_actions,
        "npc_id": contact["npc_id"], "scene_id": contact["scene_id"],
        "quest_stage": card["quest_stage"], "authored_alternative": alternative,
        "selected_preview_digest": preview["preview_digest"],
        "playable_proximity_verified": True,
        "quest_choice_replayed": True, "choice_receipt_committed": True,
        "dialogue_spoken_verified": False,
        "external_evidence_verified": False,
        "native_runtime_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC dialogue choice receipt exceeds budget")
    result["receipt_digest"] = _digest(result)
    return result


def replay_npc_dialogue_choice_commit(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_contact_digest: str, expected_source_digest: str,
    expected_walk_digest: str, expected_quest_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC dialogue choice replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC dialogue choice receipt")
    verified = compile_npc_dialogue_choice_commit(
        documents, receipt.get("contact_receipt"),
        alternative=receipt.get("authored_alternative"),
        authorized=True, expected_contact_digest=expected_contact_digest,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
    if verified != receipt:
        raise StudioQuestError("NPC dialogue choice failed canonical replay")
    return verified


def render_npc_dialogue_choice_commit_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_contact_digest: str, expected_source_digest: str,
    expected_walk_digest: str, expected_quest_digest: str,
) -> bytes:
    """CSP-restricted, escaped, read-only operator proof for the next quest choice."""
    verified = replay_npc_dialogue_choice_commit(
        documents, receipt, authorized=authorized,
        expected_contact_digest=expected_contact_digest,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
    def field(value: str) -> str:
        return escape(value, quote=True)

    title = "NPC dialogue choice — canonical quest replay"
    rows = (
        ("Project", verified["project_id"]),
        ("NPC", verified["npc_id"]),
        ("Scene", verified["scene_id"]),
        ("Quest stage", verified["quest_stage"]),
        ("Authored alternative", verified["authored_alternative"]),
        ("Previous quest digest", verified["previous_quest_session_digest"]),
        ("Next quest digest", verified["next_quest_session_digest"]),
        ("Source digest", verified["source_digest"]),
        ("Contact proof digest", verified["contact_digest"]),
        ("Receipt digest", verified["receipt_digest"]),
    )
    items = "".join(
        "<dt>" + field(label) + "</dt><dd>" + field(value) + "</dd>"
        for label, value in rows
    )
    page = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta http-equiv=\"Content-Security-Policy\" "
        "content=\"default-src 'none'; script-src 'none'; style-src 'none'; "
        "img-src 'none'; form-action 'none'; base-uri 'none'\">"
        "<title>" + field(title) + "</title></head><body>"
        "<main><h1>" + field(title) + "</h1>"
        "<p>Canonical quest choice replay verified; not spoken dialogue, "
        "native execution, external evidence or release certification.</p>"
        "<dl>" + items + "</dl></main></body></html>"
    ).encode("utf-8", "strict")
    if len(page) > MAX_BYTES:
        raise StudioQuestError("NPC dialogue choice HTML exceeds byte budget")
    return page


def publish_npc_dialogue_choice_commit(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool, expected_contact_digest: str,
    expected_source_digest: str, expected_walk_digest: str,
    expected_quest_digest: str,
) -> dict[str, Any]:
    verified = replay_npc_dialogue_choice_commit(
        documents, receipt, authorized=authorized,
        expected_contact_digest=expected_contact_digest,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC dialogue choice publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".npc-choice-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        try:
            os.fsync(fd)
        except OSError:
            os.unlink(FILENAME, dir_fd=fd)
            raise
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {
        "path": str(Path(directory) / FILENAME), "bytes": len(raw),
        "receipt_digest": verified["receipt_digest"],
        "file_write_performed": True, "release_certified": False,
    }


def restore_npc_dialogue_choice_commit(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_contact_digest: str, expected_source_digest: str,
    expected_walk_digest: str, expected_quest_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC dialogue choice restore requires authorization")
    for name, value in (
        ("contact", expected_contact_digest), ("source", expected_source_digest),
        ("walk", expected_walk_digest), ("quest", expected_quest_digest),
    ):
        _lease(value, "NPC dialogue choice restore " + name)
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW |
                         os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode)
                    or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix" and
                        (info.st_uid != os.getuid() or info.st_mode & 0o077
                         or info.st_nlink != 1))):
                raise StudioQuestError("NPC dialogue choice receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != info.st_size or after.st_size != info.st_size
                    or after.st_mtime_ns != info.st_mtime_ns
                    or after.st_ctime_ns != info.st_ctime_ns
                    or after.st_ino != info.st_ino):
                raise StudioQuestError("NPC dialogue choice receipt changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC dialogue choice receipt size")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate NPC dialogue choice JSON key")
            result[key] = value
        return result

    try:
        receipt = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite NPC dialogue choice JSON")),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC dialogue choice JSON") from exc
    return replay_npc_dialogue_choice_commit(
        documents, receipt, authorized=True,
        expected_contact_digest=expected_contact_digest,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
