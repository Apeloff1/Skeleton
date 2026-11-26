"""Canonical NPC conversation eligibility from an actual source-bound walk state.

This verifies contact proximity against the authored patrol clock and rejects
defeated or forged sessions. It does not synthesize dialogue or mutate canon.
"""
from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_ecosystem_walk_replay import restore_walk_receipt
from .studio_ecosystem_encounters import replay_hazard_health
from .studio_ecosystem_npc_patrol import cast_patrols, inspect_npc_contact
from .studio_waypoint_handoff import _bounded_walk_receipt

SCHEMA = "skeleton.game_builder.studio_npc_contact_handoff.v1"
FILENAME = "studio_npc_contact_handoff.json"
MAX_BYTES = 256 * 1024


def compile_npc_contact_handoff(
    documents: Mapping[str, Any], session_receipt: object, *,
    npc_id: str, authorized: bool, expected_source_digest: str,
    expected_session_digest: str,
) -> dict[str, Any]:
    """Prove source-authored proximity without making a dialogue choice."""
    if authorized is not True:
        raise PermissionError("NPC contact handoff requires operator authorization")
    _lease(expected_source_digest, "NPC contact source")
    _lease(expected_session_digest, "NPC contact session")
    if (type(npc_id) is not str or not 1 <= len(npc_id) <= 256
            or npc_id.strip() != npc_id
            or any(ord(char) < 32 for char in npc_id)):
        raise StudioQuestError("invalid authored NPC identity")
    raw = _bounded_walk_receipt(session_receipt)
    session = restore_walk_receipt(documents, raw, authorized=True)
    if (session.source_digest != expected_source_digest
            or session.digest != expected_session_digest):
        raise StudioQuestError("stale NPC contact source or session lease")
    health = replay_hazard_health(documents, session.events, authorized=True)
    if health["character_defeated"] or health["remaining_health"] <= 0:
        raise StudioQuestError("defeated player cannot contact an NPC")
    cast = cast_patrols(documents)
    if (cast.get("source_digest") != expected_source_digest
            or cast.get("project_id") != session.project_id):
        raise StudioQuestError("NPC cast and playable source custody diverged")
    contact = inspect_npc_contact(
        documents, npc_id=npc_id, player_position=session.position,
        accepted_moves=session.accepted_moves, scene_index=session.scene_index,
        authorized=True,
    )
    actor = next((item for item in cast["actors"] if item["id"] == npc_id), None)
    if actor is None:
        raise StudioQuestError("NPC missing from source-bound cast snapshot")
    expected_position = actor["patrol_by_stage"][session.scene_index][
        session.accepted_moves % 2]
    if (contact["project_id"] != session.project_id
            or contact["npc_id"] != npc_id
            or contact["local_contact_available"] is not True
            or contact["real_dialogue_performed"] is not False
            or contact["patrol_position"] != expected_position
            or contact["authored_knowledge"] != actor["knows"]):
        raise StudioQuestError("NPC contact evidence diverged from authored source")
    payload: dict[str, Any] = {
        "schema": SCHEMA, "project_id": session.project_id,
        "source_digest": expected_source_digest,
        "session_digest": session.digest,
        "npc_id": npc_id, "walk_receipt": session.receipt(),
        "scene_index": session.scene_index,
        "player_position": list(session.position),
        "accepted_moves": session.accepted_moves,
        "remaining_health": health["remaining_health"],
        "npc_patrol_position": contact["patrol_position"],
        "authored_knowledge": contact["authored_knowledge"],
        "contact_proof": contact,
        "source_replay_verified": True,
        "playable_contact_eligible": True,
        "npc_conversation_performed": False,
        "external_dialogue_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC contact handoff exceeds byte budget")
    payload["contact_digest"] = _digest(payload)
    return payload


def replay_npc_contact_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str, expected_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC contact replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC contact handoff receipt")
    verified = compile_npc_contact_handoff(
        documents, receipt.get("walk_receipt"), npc_id=receipt.get("npc_id"),
        authorized=True, expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest,
    )
    if verified != receipt:
        raise StudioQuestError("NPC contact handoff failed canonical replay")
    return verified


def render_npc_contact_handoff_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str, expected_session_digest: str,
) -> bytes:
    proof = replay_npc_contact_handoff(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest,
    )
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "base-uri 'none'; form-action 'none'; object-src 'none'\">"
        "<title>Source-verified NPC contact</title></head><body><main>"
        "<h1>Original-world NPC conversation eligibility</h1>"
        "<p>Local proximity verified. No conversation or external dialogue occurred.</p>"
        "<h2>Authored NPC: " + escape(proof["npc_id"], quote=True) + "</h2>"
        "<p>Authored knowledge: " + escape(proof["authored_knowledge"], quote=True) +
        "</p><p>Remaining health: " + str(proof["remaining_health"]) +
        "</p><p>Proof SHA-256: " + escape(proof["contact_digest"]) +
        "</p></main></body></html>"
    ).encode("utf-8")
    if len(html) > 32 * 1024:
        raise StudioQuestError("NPC contact preview exceeds budget")
    return html


def publish_npc_contact_handoff(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str,
) -> dict[str, Any]:
    verified = replay_npc_contact_handoff(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest,
    )
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC contact publication exceeds budget")
    fd = _open_directory(directory)
    temp = ".npc-contact-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=fd)
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME), "bytes": len(raw),
            "contact_digest": verified["contact_digest"],
            "file_write_performed": True, "release_certified": False}


def restore_npc_contact_handoff(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str, expected_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC contact restore requires authorization")
    _lease(expected_source_digest, "NPC restore source")
    _lease(expected_session_digest, "NPC restore session")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix" and (
                        info.st_uid != os.getuid() or info.st_mode & 0o077
                        or info.st_nlink != 1))):
                raise StudioQuestError("NPC contact receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC contact receipt size")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        record: dict[str, Any] = {}
        for key, value in pairs:
            if key in record:
                raise StudioQuestError("duplicate NPC contact JSON key")
            record[key] = value
        return record

    try:
        receipt = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite NPC contact JSON")),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC contact JSON") from exc
    return replay_npc_contact_handoff(
        documents, receipt, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest,
    )
