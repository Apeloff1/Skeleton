"""Source-replayed NPC knowledge relay across original authored rendezvous.

The original fact is never inferred. Every additional recipient requires an
explicit, ordered meeting and a later authored scene. This is a deterministic
sandbox planning proof, not evidence of real dialogue or native NPC cognition.
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
from .studio_ecosystem_npc_knowledge_exchange import (
    replay_npc_knowledge_exchange, compile_knowledge_exchange_playable,
)

SCHEMA = "skeleton.game_builder.studio_npc_knowledge_relay.v1"
PROMPT = "plan source-bound npc knowledge relay"
FILENAME = "npc_knowledge_relay.json"
MAX_ROUTES = 32
MAX_HOPS = 8
MAX_BYTES = 512 * 1024


def _context(documents: Mapping[str, Any], exchange_receipt: object,
             expected_source_digest: str, expected_session_digest: str | None):
    _lease(expected_source_digest, "NPC relay source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "NPC relay session")
    exchange = replay_npc_knowledge_exchange(
        documents, exchange_receipt, authorized=True)
    if (exchange["source_digest"] != expected_source_digest
            or expected_session_digest is not None
            and exchange["session_digest"] != expected_session_digest):
        raise StudioQuestError("stale NPC relay source or session")
    meeting = exchange["rendezvous_receipt"]
    temporal = meeting["transit_receipt"]["temporal_receipt"]
    schedule = compile_scene_schedule(
        documents, temporal["actions"], temporal["authoring"]["schedule_request"],
        authorized=True, expected_source_digest=expected_source_digest,
        expected_session_digest=exchange["session_digest"])
    if schedule["schedule_digest"] != temporal["schedule_digest"]:
        raise StudioQuestError("NPC relay schedule differs from canonical replay")
    return exchange, meeting, schedule


def _authoring(value: object) -> list[dict[str, Any]]:
    if (type(value) is not dict or set(value) != {"routes"}
            or type(value["routes"]) is not list
            or len(value["routes"]) > MAX_ROUTES
            or len(_canonical(value)) > 32768):
        raise StudioQuestError("invalid bounded NPC relay authoring")
    keys: set[tuple[str, str, str]] = set()
    rows = []
    for route in value["routes"]:
        if type(route) is not dict or set(route) != {
                "fact_id", "recipient_scene_id", "target_scene_id", "hops"}:
            raise StudioQuestError("invalid NPC relay route fields")
        key = (route["fact_id"], route["recipient_scene_id"],
               route["target_scene_id"])
        hops = route["hops"]
        if (any(type(x) is not str or not x for x in key)
                or key in keys or type(hops) is not list
                or not 1 <= len(hops) <= MAX_HOPS):
            raise StudioQuestError("invalid NPC relay route identity or hops")
        keys.add(key)
        seen: set[str] = set()
        for hop in hops:
            if (type(hop) is not dict
                    or set(hop) != {"meeting_id", "to_npc_id"}
                    or any(type(v) is not str or not v for v in hop.values())
                    or hop["meeting_id"] in seen):
                raise StudioQuestError("invalid or repeated NPC relay hop")
            seen.add(hop["meeting_id"])
        rows.append(route)
    return rows


def compile_npc_knowledge_relay(
    documents: Mapping[str, Any], exchange_receipt: object, authoring: object,
    *, authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC knowledge relay requires authorization")
    exchange, meeting, schedule = _context(
        documents, exchange_receipt, expected_source_digest,
        expected_session_digest)
    routes = _authoring(authoring)
    sources = {(row["fact_id"], row["recipient_scene_id"]): row
               for row in exchange["exchanges"]}
    meetings = {item["id"]: (item, outcome) for item, outcome in
                zip(meeting["meetings"], meeting["outcomes"], strict=True)}
    scenes = {row["scene_id"]: row for row in schedule["timeline"]}
    cast = {row["npc_id"] for row in schedule["timeline"]}
    result_rows: list[dict[str, Any]] = []
    for route in routes:
        key = (route["fact_id"], route["recipient_scene_id"])
        original = sources.get(key)
        target = scenes.get(route["target_scene_id"])
        if original is None or target is None:
            raise StudioQuestError("NPC relay fact or destination not source-bound")
        current = original["recipient_npc_id"]
        visited = {original["source_npc_id"], current}
        previous_end = original["meeting_end_tick"]
        causal = (original["status"] == "delivered_in_sandbox_replay"
                  and type(previous_end) is int)
        proofs: list[dict[str, Any]] = []
        for hop in route["hops"]:
            to_npc = hop["to_npc_id"]
            match = meetings.get(hop["meeting_id"])
            if (match is None or to_npc not in cast or to_npc in visited
                    or set(match[0]["npc_ids"]) != {current, to_npc}):
                raise StudioQuestError("NPC relay has unknown, cyclic or mismatched meeting")
            authored, outcome = match
            valid = (outcome["status"] == "accepted"
                     and type(previous_end) is int
                     and type(outcome["start_tick"]) is int
                     and type(outcome["end_tick"]) is int
                     and previous_end <= outcome["start_tick"]
                     and outcome["start_tick"] < outcome["end_tick"])
            causal = causal and valid
            proofs.append({
                "meeting_id": authored["id"], "from_npc_id": current,
                "to_npc_id": to_npc, "site": authored["site"],
                "start_tick": outcome["start_tick"] if valid else None,
                "end_tick": outcome["end_tick"] if valid else None,
                "causal": valid,
            })
            previous_end = outcome["end_tick"] if valid else None
            visited.add(to_npc)
            current = to_npc
        if current != target["npc_id"]:
            raise StudioQuestError("NPC relay final recipient differs from authored scene")
        causal = (causal and type(previous_end) is int
                  and previous_end <= target["start_tick"])
        status = ("delivered_in_sandbox_replay" if causal
                  else "blocked_causal_relay")
        row: dict[str, Any] = {
            "fact_id": key[0], "origin_scene_id": original["source_scene_id"],
            "recipient_scene_id": key[1], "target_scene_id": target["scene_id"],
            "target_npc_id": current, "hops": proofs,
            "source_ref": original["source_ref"],
            "source_text_digest": original["source_text_digest"],
            "source_text": original["source_text"] if causal else None,
            "status": status, "npc_speech_verified": False,
        }
        row["relay_proof_digest"] = _digest(row)
        result_rows.append(row)
    delivered = sum(row["status"] == "delivered_in_sandbox_replay"
                    for row in result_rows)
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": exchange["project_id"],
        "source_digest": exchange["source_digest"],
        "session_digest": exchange["session_digest"],
        "exchange_digest": exchange["exchange_digest"],
        "rendezvous_digest": exchange["rendezvous_digest"],
        "exchange_receipt": exchange, "authoring": authoring,
        "routes": result_rows, "delivered_count": delivered,
        "blocked_count": len(result_rows) - delivered,
        "playable_handoff_allowed": bool(result_rows)
            and delivered == len(result_rows)
            and exchange["playable_handoff_allowed"],
        "source_replay_verified": True, "npc_speech_verified": False,
        "native_npc_memory_verified": False,
        "model_inference_performed": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC relay receipt exceeds byte budget")
    result["relay_digest"] = _digest(result)
    return result


def propose_npc_knowledge_relay(
    documents: Mapping[str, Any], exchange_receipt: object, prompt: str,
    *, authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relay proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported NPC relay prompt")
    exchange, meeting, schedule = _context(
        documents, exchange_receipt, expected_source_digest, None)
    routes: list[dict[str, Any]] = []
    used: set[tuple[str, str, str]] = set()
    for original in exchange["exchanges"]:
        if original["status"] != "delivered_in_sandbox_replay":
            continue
        for scene in schedule["timeline"]:
            key = (original["fact_id"], original["recipient_scene_id"],
                   scene["scene_id"])
            if (key in used or scene["npc_id"] in {
                    original["source_npc_id"], original["recipient_npc_id"]}):
                continue
            for item, outcome in zip(meeting["meetings"],
                                     meeting["outcomes"], strict=True):
                if (outcome["status"] == "accepted"
                        and set(item["npc_ids"]) == {
                            original["recipient_npc_id"], scene["npc_id"]}
                        and original["meeting_end_tick"] <= outcome["start_tick"]
                        and outcome["end_tick"] <= scene["start_tick"]):
                    routes.append({
                        "fact_id": key[0], "recipient_scene_id": key[1],
                        "target_scene_id": key[2],
                        "hops": [{"meeting_id": item["id"],
                                  "to_npc_id": scene["npc_id"]}],
                    })
                    used.add(key)
                    break
            if len(routes) == MAX_ROUTES:
                break
        if len(routes) == MAX_ROUTES:
            break
    return compile_npc_knowledge_relay(
        documents, exchange, {"routes": routes}, authorized=True,
        expected_source_digest=expected_source_digest)


def replay_npc_knowledge_relay(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relay replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC relay receipt")
    checked = compile_npc_knowledge_relay(
        documents, receipt.get("exchange_receipt"), receipt.get("authoring"),
        authorized=True, expected_source_digest=receipt.get("source_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("NPC relay receipt differs from canonical replay")
    return checked


def compile_npc_relay_playable(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_npc_knowledge_relay(
        documents, receipt, authorized=authorized)
    if not verified["playable_handoff_allowed"]:
        raise StudioQuestError("unproved NPC relay blocks playable handoff")
    original = compile_knowledge_exchange_playable(
        documents, verified["exchange_receipt"], authorized=True)
    result = {
        "schema": "skeleton.game_builder.studio_npc_relay_handoff.v1",
        "relay_digest": verified["relay_digest"],
        "exchange_digest": verified["exchange_digest"],
        "bundle_sha256": original["bundle_sha256"],
        "canonical_html5_quest_included": original["canonical_html5_quest_included"],
        "native_npc_memory_integrated": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_npc_knowledge_relay(
    documents: Mapping[str, Any], receipt: object, directory: Path,
    *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_npc_knowledge_relay(
        documents, receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC relay publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".npc-relay-" + secrets.token_hex(16) + ".tmp"
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
            "relay_digest": verified["relay_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_npc_knowledge_relay(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relay restore requires authorization")
    _lease(expected_source_digest, "NPC relay restore source")
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
                raise StudioQuestError("NPC relay receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC relay receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate NPC relay JSON key")
            out[key] = value
        return out
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite NPC relay JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC relay JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale NPC relay source lease")
    return replay_npc_knowledge_relay(documents, receipt, authorized=True)
