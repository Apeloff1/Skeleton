"""Sequential source-leased NPC contacts and authored quest choices.

A chain is a deterministic multi-scene quest transition, not native dialogue
execution. Every step re-verifies playable contact against the unchanged walk
receipt and the newly advanced canonical quest session.
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
from .studio_npc_dialogue_contact import compile_npc_dialogue_contact
from .studio_npc_dialogue_choice_commit import (
    compile_npc_dialogue_choice_commit,
)

SCHEMA = "skeleton.game_builder.studio_npc_dialogue_chain.v1"
FILENAME = "studio_npc_dialogue_chain.json"
MAX_BYTES = 512 * 1024
MAX_STEPS = 8
MAX_INITIAL_ACTIONS = 64
_STEP_KEYS = frozenset({"npc_id", "scene_id", "alternative"})


def _step(value: object) -> dict[str, str]:
    if type(value) is not dict or set(value) != _STEP_KEYS:
        raise StudioQuestError("invalid typed NPC dialogue chain step")
    result: dict[str, str] = {}
    for key in sorted(_STEP_KEYS):
        item = value[key]
        if (type(item) is not str or not 1 <= len(item) <= 256
                or item.strip() != item
                or any(ord(char) < 32 for char in item)):
            raise StudioQuestError("invalid NPC dialogue chain " + key)
        try:
            if len(item.encode("utf-8", "strict")) > 1024:
                raise StudioQuestError("NPC dialogue chain step exceeds budget")
        except UnicodeError as exc:
            raise StudioQuestError("noncanonical NPC dialogue chain step") from exc
        result[key] = item
    return result


def _actions(value: object) -> list[list[str]]:
    if type(value) is not list or len(value) > MAX_INITIAL_ACTIONS:
        raise StudioQuestError("invalid NPC dialogue chain initial history")
    output: list[list[str]] = []
    for action in value:
        if type(action) is not list or len(action) != 2:
            raise StudioQuestError("invalid NPC dialogue chain initial action")
        left = _step({"npc_id": action[0], "scene_id": action[1],
                      "alternative": "initial"})
        output.append([left["npc_id"], left["scene_id"]])
    return output


def compile_npc_dialogue_chain(
    documents: Mapping[str, Any], walk_receipt: object, *,
    initial_quest_actions: object, steps: object, authorized: bool,
    expected_source_digest: str, expected_walk_digest: str,
    expected_quest_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC dialogue chain requires operator authorization")
    for label, value in (
        ("source", expected_source_digest), ("walk", expected_walk_digest),
        ("quest", expected_quest_digest),
    ):
        _lease(value, "NPC dialogue chain " + label)
    if type(steps) is not list or not 1 <= len(steps) <= MAX_STEPS:
        raise StudioQuestError("NPC dialogue chain requires 1..8 authored steps")
    checked_steps = [_step(step) for step in steps]
    actions = _actions(initial_quest_actions)
    source_before = _canonical(documents)
    if len(source_before) > MAX_BYTES:
        raise StudioQuestError("NPC dialogue chain source exceeds budget")
    initial = replay_quest(documents, actions, authorized=True)
    if (initial.source_digest != expected_source_digest
            or initial.digest != expected_quest_digest):
        raise StudioQuestError("stale NPC dialogue chain initial quest lease")
    current_digest = initial.digest
    receipts: list[dict[str, Any]] = []
    for index, step in enumerate(checked_steps):
        contact = compile_npc_dialogue_contact(
            documents, walk_receipt,
            npc_id=step["npc_id"], scene_id=step["scene_id"],
            quest_actions=actions, authorized=True,
            expected_source_digest=expected_source_digest,
            expected_walk_digest=expected_walk_digest,
            expected_quest_digest=current_digest,
        )
        choice = compile_npc_dialogue_choice_commit(
            documents, contact, alternative=step["alternative"],
            authorized=True, expected_contact_digest=contact["receipt_digest"],
            expected_source_digest=expected_source_digest,
            expected_walk_digest=expected_walk_digest,
            expected_quest_digest=current_digest,
        )
        if (choice["previous_quest_session_digest"] != current_digest
                or choice["quest_actions"][:-1] != actions
                or choice["quest_actions"][-1] != [
                    contact["dialogue_card"]["quest_stage"], step["alternative"]]
                or choice["source_digest"] != expected_source_digest
                or choice["walk_session_digest"] != expected_walk_digest
                or choice["playable_proximity_verified"] is not True
                or choice["quest_choice_replayed"] is not True
                or choice["dialogue_spoken_verified"] is not False
                or choice["native_runtime_verified"] is not False
                or choice["release_certified"] is not False):
            raise StudioQuestError("NPC dialogue chain step replay diverged")
        current_digest = choice["next_quest_session_digest"]
        actions = choice["quest_actions"]
        receipts.append({
            "step_index": index, "npc_id": step["npc_id"],
            "scene_id": step["scene_id"],
            "authored_alternative": step["alternative"],
            "contact_digest": contact["receipt_digest"],
            "choice_receipt_digest": choice["receipt_digest"],
            "previous_quest_digest": choice["previous_quest_session_digest"],
            "next_quest_digest": current_digest,
        })
    final = replay_quest(documents, actions, authorized=True)
    if (final.digest != current_digest
            or final.source_digest != expected_source_digest
            or len(final.choices) != len(actions)
            or _canonical(documents) != source_before):
        raise StudioQuestError("NPC dialogue chain final replay diverged")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": initial.project_id,
        "source_digest": expected_source_digest,
        "walk_session_digest": expected_walk_digest,
        "initial_quest_session_digest": expected_quest_digest,
        "final_quest_session_digest": current_digest,
        "initial_quest_actions": _actions(initial_quest_actions),
        "final_quest_actions": actions,
        "walk_receipt": walk_receipt, "steps": checked_steps,
        "step_receipts": receipts, "step_count": len(receipts),
        "source_replay_verified": True,
        "sequential_quest_replay_verified": True,
        "playable_contact_verified_per_step": True,
        "choice_receipts_committed": True,
        "dialogue_spoken_verified": False,
        "native_runtime_verified": False,
        "external_evidence_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC dialogue chain receipt exceeds budget")
    result["receipt_digest"] = _digest(result)
    return result


def replay_npc_dialogue_chain(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str, expected_walk_digest: str,
    expected_quest_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC dialogue chain replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC dialogue chain receipt")
    verified = compile_npc_dialogue_chain(
        documents, receipt.get("walk_receipt"),
        initial_quest_actions=receipt.get("initial_quest_actions"),
        steps=receipt.get("steps"), authorized=True,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
    if verified != receipt:
        raise StudioQuestError("NPC dialogue chain failed canonical replay")
    return verified


def render_npc_dialogue_chain_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str, expected_walk_digest: str,
    expected_quest_digest: str,
) -> bytes:
    verified = replay_npc_dialogue_chain(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
    items = "".join(
        "<li><strong>" + escape(step["npc_id"], quote=True) + "</strong> "
        + escape(step["scene_id"], quote=True) + " → "
        + escape(step["authored_alternative"], quote=True) + "</li>"
        for step in verified["step_receipts"]
    )
    page = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta http-equiv=\"Content-Security-Policy\" "
        "content=\"default-src 'none'; script-src 'none'; style-src 'none'; "
        "img-src 'none'; form-action 'none'; base-uri 'none'\">"
        "<title>NPC dialogue chain replay</title></head><body>"
        "<main><h1>NPC dialogue chain replay</h1>"
        "<p>Authored quest choices only. No spoken dialogue, native runtime "
        "execution, external evidence or release certification.</p><ol>"
        + items + "</ol><p>Final quest digest: "
        + escape(verified["final_quest_session_digest"]) + "</p></main>"
        "</body></html>"
    ).encode("utf-8", "strict")
    if len(page) > MAX_BYTES:
        raise StudioQuestError("NPC dialogue chain HTML exceeds budget")
    return page


def publish_npc_dialogue_chain(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool, expected_source_digest: str,
    expected_walk_digest: str, expected_quest_digest: str,
) -> dict[str, Any]:
    verified = replay_npc_dialogue_chain(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC dialogue chain publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".npc-chain-" + secrets.token_hex(16) + ".tmp"
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
    return {"path": str(Path(directory) / FILENAME), "bytes": len(raw),
            "receipt_digest": verified["receipt_digest"],
            "file_write_performed": True, "release_certified": False}


def restore_npc_dialogue_chain(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str, expected_walk_digest: str,
    expected_quest_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC dialogue chain restore requires authorization")
    for label, value in (
        ("source", expected_source_digest), ("walk", expected_walk_digest),
        ("quest", expected_quest_digest),
    ):
        _lease(value, "NPC dialogue chain restore " + label)
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
                raise StudioQuestError("NPC dialogue chain receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != info.st_size or after.st_size != info.st_size
                    or after.st_mtime_ns != info.st_mtime_ns
                    or after.st_ctime_ns != info.st_ctime_ns
                    or after.st_ino != info.st_ino):
                raise StudioQuestError("NPC dialogue chain receipt changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate NPC dialogue chain JSON key")
            result[key] = value
        return result

    try:
        receipt = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite NPC dialogue chain JSON")),
        )
    except StudioQuestError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC dialogue chain JSON") from exc
    return replay_npc_dialogue_chain(
        documents, receipt, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_walk_digest=expected_walk_digest,
        expected_quest_digest=expected_quest_digest,
    )
