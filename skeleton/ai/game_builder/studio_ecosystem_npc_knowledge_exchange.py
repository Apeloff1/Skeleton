"""Source-replayed NPC knowledge exchange gated by an actual authored meeting.

A reveal is never invented: only a canonical knowledge cue can be transferred.
An accepted logical rendezvous is necessary but not proof of spoken dialogue.
"""
from __future__ import annotations

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
from .studio_ecosystem_npc_knowledge import compile_npc_knowledge
from .studio_ecosystem_npc_rendezvous import (
    replay_npc_rendezvous, compile_rendezvous_playable,
)

SCHEMA = "skeleton.game_builder.studio_npc_knowledge_exchange.v1"
PROMPT = "plan source-bound npc knowledge exchange"
FILENAME = "npc_knowledge_exchange.json"
MAX_BINDINGS = 64
MAX_BYTES = 384 * 1024


def _context(documents: Mapping[str, Any], rendezvous_receipt: object,
             knowledge_receipt: object, expected_source_digest: str,
             expected_session_digest: str | None):
    _lease(expected_source_digest, "knowledge exchange source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "knowledge exchange session")
    meeting = replay_npc_rendezvous(
        documents, rendezvous_receipt, authorized=True)
    temporal = meeting["transit_receipt"]["temporal_receipt"]
    actions = temporal["actions"]
    if (meeting["source_digest"] != expected_source_digest
            or expected_session_digest is not None
            and meeting["session_digest"] != expected_session_digest):
        raise StudioQuestError("stale knowledge exchange source or session")
    if type(knowledge_receipt) is not dict:
        raise StudioQuestError("missing NPC knowledge receipt")
    knowledge = compile_npc_knowledge(
        documents, actions, knowledge_receipt.get("authoring"),
        authorized=True, expected_source_digest=expected_source_digest,
        expected_session_digest=meeting["session_digest"])
    if knowledge != knowledge_receipt:
        raise StudioQuestError("NPC knowledge exchange source replay mismatch")
    schedule = compile_scene_schedule(
        documents, actions, temporal["authoring"]["schedule_request"],
        authorized=True, expected_source_digest=expected_source_digest,
        expected_session_digest=meeting["session_digest"])
    if schedule["schedule_digest"] != temporal["schedule_digest"]:
        raise StudioQuestError("NPC knowledge exchange temporal drift")
    return meeting, knowledge, schedule


def compile_npc_knowledge_exchange(
    documents: Mapping[str, Any], rendezvous_receipt: object,
    knowledge_receipt: object, authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_session_digest: str | None = None,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC knowledge exchange requires authorization")
    meeting, knowledge, schedule = _context(
        documents, rendezvous_receipt, knowledge_receipt,
        expected_source_digest, expected_session_digest)
    if (type(authoring) is not dict or set(authoring) != {"bindings"}
            or type(authoring["bindings"]) is not list
            or len(authoring["bindings"]) > MAX_BINDINGS
            or len(_canonical(authoring)) > 32768):
        raise StudioQuestError("invalid bounded NPC knowledge exchange authoring")
    reveals = {(row["fact_id"], row["recipient_scene_id"]): row
               for row in knowledge["reveals"]}
    meetings = {row["id"]: (row, outcome) for row, outcome in
                zip(meeting["meetings"], meeting["outcomes"], strict=True)}
    scenes = {row["scene_id"]: row for row in schedule["timeline"]}
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for binding in authoring["bindings"]:
        if type(binding) is not dict or set(binding) != {
                "fact_id", "recipient_scene_id", "meeting_id"}:
            raise StudioQuestError("invalid NPC knowledge exchange binding")
        key = (binding["fact_id"], binding["recipient_scene_id"])
        meeting_id = binding["meeting_id"]
        if (any(type(x) is not str for x in (*key, meeting_id))
                or key in seen or key not in reveals or meeting_id not in meetings):
            raise StudioQuestError("duplicate or unknown NPC knowledge exchange source")
        seen.add(key)
        reveal = reveals[key]
        authored, outcome = meetings[meeting_id]
        if set(authored["npc_ids"]) != {
                reveal["source_npc_id"], reveal["recipient_npc_id"]}:
            raise StudioQuestError("knowledge exchange NPCs differ from meeting cast")
        source = scenes.get(reveal["source_scene_id"])
        recipient = scenes.get(reveal["recipient_scene_id"])
        if source is None or recipient is None:
            raise StudioQuestError("knowledge exchange scene not source-bound")
        causal = (
            outcome["status"] == "accepted"
            and source["end_tick"] <= outcome["start_tick"]
            and outcome["end_tick"] <= recipient["start_tick"]
        )
        earned = reveal["status"] == "earned_in_sandbox_replay"
        status = "delivered_in_sandbox_replay" if causal and earned else (
            "pending_quest_replay" if causal else "blocked_temporal_causality")
        row: dict[str, Any] = {
            "fact_id": key[0], "recipient_scene_id": key[1],
            "meeting_id": meeting_id, "source_scene_id": source["scene_id"],
            "source_npc_id": reveal["source_npc_id"],
            "recipient_npc_id": reveal["recipient_npc_id"],
            "source_ref": reveal["source_ref"],
            "source_text_digest": reveal["source_text_digest"],
            "source_text": reveal["source_text"] if status ==
                           "delivered_in_sandbox_replay" else None,
            "meeting_start_tick": outcome["start_tick"] if causal else None,
            "meeting_end_tick": outcome["end_tick"] if causal else None,
            "status": status, "npc_speech_verified": False,
        }
        row["exchange_proof_digest"] = _digest(row)
        rows.append(row)
    delivered = sum(row["status"] == "delivered_in_sandbox_replay" for row in rows)
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": meeting["project_id"],
        "source_digest": meeting["source_digest"],
        "session_digest": meeting["session_digest"],
        "rendezvous_digest": meeting["rendezvous_digest"],
        "knowledge_digest": knowledge["knowledge_digest"],
        "rendezvous_receipt": meeting, "knowledge_receipt": knowledge,
        "authoring": authoring, "exchanges": rows,
        "delivered_count": delivered,
        "pending_count": sum(row["status"] == "pending_quest_replay" for row in rows),
        "blocked_count": sum(row["status"] == "blocked_temporal_causality" for row in rows),
        "playable_handoff_allowed": bool(rows) and delivered == len(rows)
                                    and meeting["playable_handoff_allowed"],
        "source_replay_verified": True, "npc_speech_verified": False,
        "model_inference_performed": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC knowledge exchange receipt exceeds budget")
    result["exchange_digest"] = _digest(result)
    return result


def propose_npc_knowledge_exchange(
    documents: Mapping[str, Any], rendezvous_receipt: object,
    knowledge_receipt: object, prompt: str, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC knowledge exchange proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported NPC knowledge exchange prompt")
    meeting, knowledge, _ = _context(
        documents, rendezvous_receipt, knowledge_receipt,
        expected_source_digest, None)
    bindings = []
    for reveal in knowledge["reveals"]:
        compatible = [
            item["id"] for item in meeting["meetings"]
            if set(item["npc_ids"]) == {
                reveal["source_npc_id"], reveal["recipient_npc_id"]}
        ]
        if compatible:
            bindings.append({
                "fact_id": reveal["fact_id"],
                "recipient_scene_id": reveal["recipient_scene_id"],
                "meeting_id": compatible[0],
            })
        if len(bindings) == MAX_BINDINGS:
            break
    return compile_npc_knowledge_exchange(
        documents, meeting, knowledge, {"bindings": bindings},
        authorized=True, expected_source_digest=expected_source_digest)


def replay_npc_knowledge_exchange(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC knowledge exchange replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC knowledge exchange receipt")
    verified = compile_npc_knowledge_exchange(
        documents, receipt.get("rendezvous_receipt"),
        receipt.get("knowledge_receipt"), receipt.get("authoring"),
        authorized=True, expected_source_digest=receipt.get("source_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if verified != receipt:
        raise StudioQuestError("NPC knowledge exchange failed canonical replay")
    return verified


def compile_knowledge_exchange_playable(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_npc_knowledge_exchange(
        documents, receipt, authorized=authorized)
    if not verified["playable_handoff_allowed"]:
        raise StudioQuestError("unearned or unproved knowledge exchange blocks handoff")
    manifest = compile_rendezvous_playable(
        documents, verified["rendezvous_receipt"], authorized=True)
    result = {
        "schema": "skeleton.game_builder.studio_npc_knowledge_exchange_handoff.v1",
        "exchange_digest": verified["exchange_digest"],
        "rendezvous_digest": verified["rendezvous_digest"],
        "bundle_sha256": manifest["bundle_sha256"],
        "canonical_html5_quest_included": manifest["canonical_html5_quest_included"],
        "native_npc_speech_integrated": False,
        "native_knowledge_transfer_integrated": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_npc_knowledge_exchange(
    documents: Mapping[str, Any], receipt: object,
    directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_npc_knowledge_exchange(
        documents, receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC knowledge exchange publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".npc-exchange-" + secrets.token_hex(16) + ".tmp"
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
            "exchange_digest": verified["exchange_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_npc_knowledge_exchange(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC knowledge exchange restore requires authorization")
    _lease(expected_source_digest, "NPC knowledge exchange restore source")
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
                raise StudioQuestError("NPC knowledge exchange receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC knowledge exchange receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate NPC knowledge exchange JSON key")
            out[key] = value
        return out
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite NPC knowledge exchange JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC knowledge exchange JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale NPC knowledge exchange source lease")
    return replay_npc_knowledge_exchange(documents, receipt, authorized=True)
