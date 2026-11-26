"""Chronological source-replayed NPC continuity journal across studio planes.

The journal is a deterministic *inspection* of canonical scenes, authored
transit, rendezvous and earned fact exchanges. It cannot alter quest outcomes.
"""
from __future__ import annotations

from hashlib import sha256
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
    compile_scene_schedule,
)
from .studio_ecosystem_npc_knowledge_exchange import (
    replay_npc_knowledge_exchange, compile_knowledge_exchange_playable,
)

SCHEMA = "skeleton.game_builder.studio_npc_continuity_journal.v1"
PROMPT = "audit source-bound npc continuity timeline"
FILENAME = "npc_continuity_journal.json"
MAX_NOTES = 64
MAX_BYTES = 512 * 1024


def _text(value: object) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 240
            or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise StudioQuestError("invalid NPC continuity annotation")
    return value


def _events(exchange: dict[str, Any], schedule: dict[str, Any]) -> list[dict[str, Any]]:
    meeting = exchange["rendezvous_receipt"]
    transit = meeting["transit_receipt"]
    result: list[dict[str, Any]] = []
    for row in schedule["timeline"]:
        result.append({
            "event_key": "scene:" + row["scene_id"],
            "kind": "authored_scene", "start_tick": row["start_tick"],
            "end_tick": row["end_tick"], "npc_ids": [row["npc_id"]],
            "site": row["site"], "source_scene_id": row["scene_id"],
            "source_proof_digest": row["scene_proof_digest"],
            "text": None,
        })
    for index, transition in enumerate(transit["transitions"]):
        result.append({
            "event_key": "transit:" + str(index),
            "kind": "npc_transit", "start_tick": transition["departure_tick"],
            "end_tick": transition["arrival_deadline_tick"],
            "npc_ids": [transition["npc_id"]],
            "site": transition["to_site"],
            "source_scene_id": transition["to_scene_id"],
            "source_proof_digest": transition["transition_digest"],
            "text": None,
        })
    for authored, outcome in zip(
            meeting["meetings"], meeting["outcomes"], strict=True):
        if outcome["status"] != "accepted":
            continue
        result.append({
            "event_key": "meeting:" + authored["id"],
            "kind": "npc_rendezvous", "start_tick": outcome["start_tick"],
            "end_tick": outcome["end_tick"], "npc_ids": authored["npc_ids"],
            "site": authored["site"], "source_scene_id": None,
            "source_proof_digest": outcome["meeting_digest"],
            "text": None,
        })
    for index, row in enumerate(exchange["exchanges"]):
        if row["status"] != "delivered_in_sandbox_replay":
            continue
        matching = [
            meeting_item for meeting_item in meeting["meetings"]
            if meeting_item["id"] == row["meeting_id"]
        ]
        if len(matching) != 1:
            raise StudioQuestError("NPC continuity exchange meeting missing")
        result.append({
            "event_key": "exchange:" + str(index),
            "kind": "earned_knowledge_exchange",
            "start_tick": row["meeting_start_tick"],
            "end_tick": row["meeting_end_tick"],
            "npc_ids": [row["source_npc_id"], row["recipient_npc_id"]],
            "site": matching[0]["site"],
            "source_scene_id": row["source_scene_id"],
            "source_proof_digest": row["exchange_proof_digest"],
            "text": row["source_text"],
        })
    result.sort(key=lambda row: (
        row["start_tick"], row["end_tick"], row["event_key"]))
    keys = [row["event_key"] for row in result]
    if len(set(keys)) != len(keys):
        raise StudioQuestError("duplicate NPC continuity event identity")
    return result


def compile_npc_continuity_journal(
    documents: Mapping[str, Any], exchange_receipt: object,
    authoring: object, *, authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC continuity journal requires authorization")
    _lease(expected_source_digest, "NPC continuity source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "NPC continuity session")
    exchange = replay_npc_knowledge_exchange(
        documents, exchange_receipt, authorized=True)
    if (exchange["source_digest"] != expected_source_digest
            or expected_session_digest is not None
            and exchange["session_digest"] != expected_session_digest):
        raise StudioQuestError("stale NPC continuity source or session")
    temporal = exchange["rendezvous_receipt"]["transit_receipt"]["temporal_receipt"]
    schedule = compile_scene_schedule(
        documents, temporal["actions"], temporal["authoring"]["schedule_request"],
        authorized=True, expected_source_digest=expected_source_digest,
        expected_session_digest=exchange["session_digest"])
    if schedule["schedule_digest"] != temporal["schedule_digest"]:
        raise StudioQuestError("NPC continuity schedule drift")
    if (type(authoring) is not dict or set(authoring) != {"notes"}
            or type(authoring["notes"]) is not list
            or len(authoring["notes"]) > MAX_NOTES
            or len(_canonical(authoring)) > 32768):
        raise StudioQuestError("invalid bounded NPC continuity annotations")
    events = _events(exchange, schedule)
    keys = {event["event_key"] for event in events}
    notes: dict[str, str] = {}
    for item in authoring["notes"]:
        if (type(item) is not dict or set(item) != {"event_key", "text"}
                or type(item["event_key"]) is not str
                or item["event_key"] not in keys or item["event_key"] in notes):
            raise StudioQuestError("duplicate or unknown NPC continuity note anchor")
        notes[item["event_key"]] = _text(item["text"])
    for event in events:
        event["operator_note"] = notes.get(event["event_key"])
        event["event_digest"] = _digest(event)
    payload: dict[str, Any] = {
        "schema": SCHEMA, "project_id": exchange["project_id"],
        "source_digest": exchange["source_digest"],
        "session_digest": exchange["session_digest"],
        "exchange_digest": exchange["exchange_digest"],
        "rendezvous_digest": exchange["rendezvous_digest"],
        "exchange_receipt": exchange,
        "authoring": authoring, "events": events,
        "event_count": len(events), "annotated_count": len(notes),
        "scene_count": sum(row["kind"] == "authored_scene" for row in events),
        "transit_count": sum(row["kind"] == "npc_transit" for row in events),
        "meeting_count": sum(row["kind"] == "npc_rendezvous" for row in events),
        "exchange_count": sum(row["kind"] == "earned_knowledge_exchange" for row in events),
        "playable_handoff_allowed": exchange["playable_handoff_allowed"],
        "source_replay_verified": True, "operator_estimates_only": True,
        "native_scene_timing_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC continuity journal exceeds receipt budget")
    payload["journal_digest"] = _digest(payload)
    return payload


def propose_npc_continuity_journal(
    documents: Mapping[str, Any], exchange_receipt: object,
    prompt: str, *, authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC continuity proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported NPC continuity prompt")
    return compile_npc_continuity_journal(
        documents, exchange_receipt, {"notes": []}, authorized=True,
        expected_source_digest=expected_source_digest)


def replay_npc_continuity_journal(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC continuity replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC continuity journal receipt")
    verified = compile_npc_continuity_journal(
        documents, receipt.get("exchange_receipt"), receipt.get("authoring"),
        authorized=True, expected_source_digest=receipt.get("source_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if verified != receipt:
        raise StudioQuestError("NPC continuity journal failed canonical replay")
    return verified


def render_npc_continuity_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    verified = replay_npc_continuity_journal(
        documents, receipt, authorized=authorized)
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "base-uri 'none'; form-action 'none'\">",
        "<title>NPC continuity journal</title></head><body><main>",
        "<h1>Canonical NPC continuity</h1>",
        "<p>Source replay only; physical timing and speech remain unverified.</p>",
        "<ol>",
    ]
    for row in verified["events"]:
        parts.append(
            "<li><strong>" + escape(row["event_key"], quote=True) + "</strong> " +
            escape(row["kind"], quote=True) + " [" +
            str(row["start_tick"]) + "–" + str(row["end_tick"]) + "] at " +
            escape(row["site"], quote=True))
        if row["text"] is not None:
            parts.append("<p>Authored fact: " + escape(row["text"], quote=True) + "</p>")
        if row["operator_note"] is not None:
            parts.append("<p>Operator note: " + escape(row["operator_note"], quote=True) + "</p>")
        parts.append("</li>")
    parts.extend(["</ol></main></body></html>"])
    html = "".join(parts).encode("utf-8")
    if len(html) > 256 * 1024:
        raise StudioQuestError("NPC continuity HTML exceeds budget")
    return html


def compile_continuity_playable(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_npc_continuity_journal(
        documents, receipt, authorized=authorized)
    if not verified["playable_handoff_allowed"]:
        raise StudioQuestError("NPC continuity blocked by upstream proof")
    manifest = compile_knowledge_exchange_playable(
        documents, verified["exchange_receipt"], authorized=True)
    html = render_npc_continuity_html(
        documents, verified, authorized=True)
    result = {
        "schema": "skeleton.game_builder.studio_npc_continuity_handoff.v1",
        "journal_digest": verified["journal_digest"],
        "bundle_sha256": manifest["bundle_sha256"],
        "canonical_html5_quest_included": manifest["canonical_html5_quest_included"],
        "companion_html_sha256": sha256(html).hexdigest(),
        "companion_html_bytes": len(html),
        "native_continuity_ui_integrated": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_npc_continuity_journal(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    verified = replay_npc_continuity_journal(
        documents, receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC continuity publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".npc-continuity-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "journal_digest": verified["journal_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_npc_continuity_journal(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC continuity restore requires authorization")
    _lease(expected_source_digest, "NPC continuity restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix"
                        and (info.st_uid != os.getuid() or info.st_mode & 0o077
                             or info.st_nlink != 1))):
                raise StudioQuestError("NPC continuity receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC continuity receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate NPC continuity JSON key")
            out[key] = value
        return out
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite NPC continuity JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC continuity JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale NPC continuity source lease")
    return replay_npc_continuity_journal(documents, receipt, authorized=True)
