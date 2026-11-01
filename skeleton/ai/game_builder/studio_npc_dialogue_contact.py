"""Proximity-gated authored NPC dialogue previews, replayed against playable state.

This is a read-only conversation handoff: proximity, health, quest unlocks,
source identity and authored NPC identity must all agree before a player sees
a scene's original dialogue choices. It never claims speech or reward grants.
"""
from __future__ import annotations

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
from .studio_ecosystem_dialogue_choice_preview import preview_dialogue_choices
from .studio_npc_contact_handoff import compile_npc_contact_handoff
from .studio_waypoint_handoff import _bounded_walk_receipt

SCHEMA = "skeleton.game_builder.studio_npc_dialogue_contact.v1"
FILENAME = "studio_npc_dialogue_contact.json"
MAX_BYTES = 512 * 1024
MAX_ACTIONS = 64


def _actions(value: object) -> list[list[str]]:
    if type(value) is not list or len(value) > MAX_ACTIONS:
        raise StudioQuestError("invalid bounded NPC dialogue quest actions")
    output: list[list[str]] = []
    for pair in value:
        if (type(pair) is not list or len(pair) != 2
                or any(type(part) is not str or not 1 <= len(part) <= 256
                       or part.strip() != part
                       or any(ord(c) < 32 for c in part) for part in pair)):
            raise StudioQuestError("invalid NPC dialogue quest action")
        output.append(pair[:])
    if len(_canonical(output)) > 32768:
        raise StudioQuestError("NPC dialogue quest actions exceed budget")
    return output


def _scene(value: object) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 256
            or value.strip() != value or any(ord(c) < 32 for c in value)):
        raise StudioQuestError("invalid NPC dialogue scene ID")
    return value


def compile_npc_dialogue_contact(
    documents: Mapping[str, Any], walk_receipt: object, *, npc_id: str,
    scene_id: str, quest_actions: object, authorized: bool,
    expected_source_digest: str, expected_walk_digest: str,
    expected_quest_digest: str,
) -> dict[str, Any]:
    """Compile a playable NPC-to-quest dialogue handoff with no side effects."""
    if authorized is not True:
        raise PermissionError("NPC dialogue contact requires operator authorization")
    _lease(expected_source_digest, "NPC dialogue source")
    _lease(expected_walk_digest, "NPC dialogue walk")
    _lease(expected_quest_digest, "NPC dialogue quest")
    scene_id = _scene(scene_id)
    actions = _actions(quest_actions)
    # Preflight untrusted receipts before invoking any canonical replay engine.
    walk = json.loads(_bounded_walk_receipt(walk_receipt))
    contact = compile_npc_contact_handoff(
        documents, walk, npc_id=npc_id, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_walk_digest,
    )
    quest = replay_quest(documents, actions, authorized=True)
    if quest.digest != expected_quest_digest:
        raise StudioQuestError("stale NPC dialogue quest lease")
    if quest.project_id != contact["project_id"]:
        raise StudioQuestError("NPC dialogue quest and playable project diverged")
    preview = preview_dialogue_choices(
        documents, actions, authorized=True, scene_id=scene_id,
        expected_source_digest=expected_source_digest,
    )
    if (preview["source_digest"] != contact["source_digest"]
            or preview["project_id"] != contact["project_id"]
            or preview["session_digest"] != expected_quest_digest
            or preview["choice_committed"] is not False
            or preview["file_write_performed"] is not False):
        raise StudioQuestError("NPC dialogue source or quest replay diverged")
    cards = preview["cards"]
    if len(cards) != 1:
        raise StudioQuestError("NPC dialogue scene must identify exactly one card")
    card = cards[0]
    if card["npc_id"] != npc_id:
        raise StudioQuestError("NPC dialogue scene belongs to a different NPC")
    if card["status"] != "available":
        raise StudioQuestError("NPC dialogue scene is locked or already completed")
    cues = [cue for cue in card["authored_cues"]
            if cue["kind"] == "npc_knowledge"]
    if cues and (len(cues) != 1
                 or cues[0]["text"] != contact["authored_knowledge"]):
        raise StudioQuestError("NPC dialogue knowledge differs from contact source")
    choices = [item for item in preview["previews"]
               if item["npc_id"] == npc_id and item["scene_id"] == scene_id]
    if (not choices or len(choices) != len(card["authored_alternatives"])
            or {choice["alternative"] for choice in choices}
               != set(card["authored_alternatives"])
            or any(choice["choice_committed"] is not False for choice in choices)):
        raise StudioQuestError("NPC dialogue authored alternatives diverged")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": contact["project_id"],
        "source_digest": expected_source_digest,
        "walk_session_digest": expected_walk_digest,
        "quest_session_digest": expected_quest_digest,
        "walk_receipt": walk, "quest_actions": actions,
        "npc_id": npc_id, "scene_id": scene_id,
        "contact_proof": contact, "dialogue_card": card,
        "choice_previews": choices,
        "authored_alternative_count": len(choices),
        "playable_proximity_verified": True,
        "quest_unlock_replay_verified": True,
        "dialogue_spoken_verified": False,
        "quest_choice_committed": False,
        "file_write_performed": False,
        "external_evidence_verified": False,
        "native_runtime_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC dialogue contact exceeds receipt budget")
    result["receipt_digest"] = _digest(result)
    return result


def replay_npc_dialogue_contact(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str, expected_walk_digest: str,
    expected_quest_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC dialogue replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC dialogue contact receipt")
    verified = compile_npc_dialogue_contact(
        documents, receipt.get("walk_receipt"), npc_id=receipt.get("npc_id"),
        scene_id=receipt.get("scene_id"), quest_actions=receipt.get("quest_actions"),
        authorized=True, expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
    if verified != receipt:
        raise StudioQuestError("NPC dialogue contact failed canonical replay")
    return verified


def publish_npc_dialogue_contact(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool, expected_source_digest: str, expected_walk_digest: str,
    expected_quest_digest: str,
) -> dict[str, Any]:
    verified = replay_npc_dialogue_contact(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC dialogue publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".npc-dialogue-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=fd,
        )
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME), "bytes": len(raw),
            "receipt_digest": verified["receipt_digest"],
            "file_write_performed": True, "release_certified": False}


def restore_npc_dialogue_contact(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str, expected_walk_digest: str,
    expected_quest_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC dialogue restore requires authorization")
    _lease(expected_source_digest, "NPC dialogue restore source")
    _lease(expected_walk_digest, "NPC dialogue restore walk")
    _lease(expected_quest_digest, "NPC dialogue restore quest")
    fd = _open_directory(directory)
    try:
        handle = os.open(
            FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix" and
                        (info.st_uid != os.getuid() or info.st_mode & 0o077
                         or info.st_nlink != 1))):
                raise StudioQuestError("NPC dialogue receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC dialogue receipt size")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate NPC dialogue JSON key")
            result[key] = value
        return result

    try:
        receipt = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite NPC dialogue JSON")),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC dialogue JSON") from exc
    return replay_npc_dialogue_contact(
        documents, receipt, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
