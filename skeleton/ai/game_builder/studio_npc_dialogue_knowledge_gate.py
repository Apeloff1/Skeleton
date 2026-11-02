"""Source-replayed dialogue knowledge gate for original NPC scene disclosures.

A relay receipt alone never grants a dialogue cue. The authored quest scene must
be available and the exact fact's causal relay must be delivered to its NPC.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_ecosystem_npc_knowledge_relay import (
    replay_npc_knowledge_relay, compile_npc_relay_playable,
)

SCHEMA = "skeleton.game_builder.studio_npc_dialogue_knowledge_gate.v1"
PROMPT = "gate authored npc dialogue by replayed knowledge"
FILENAME = "npc_dialogue_knowledge_gate.json"
MAX_GATES = 32
MAX_BYTES = 768 * 1024


def _request(value: object) -> list[dict[str, str]]:
    if (type(value) is not dict or set(value) != {"gates"}
            or type(value["gates"]) is not list
            or len(value["gates"]) > MAX_GATES
            or len(_canonical(value)) > 32768):
        raise StudioQuestError("invalid bounded NPC dialogue gate authoring")
    seen: set[tuple[str, str, str]] = set()
    result = []
    for row in value["gates"]:
        if type(row) is not dict or set(row) != {
                "fact_id", "recipient_scene_id", "target_scene_id",
                "expected_relay_proof_digest"}:
            raise StudioQuestError("invalid NPC dialogue gate fields")
        key = (row["fact_id"], row["recipient_scene_id"],
               row["target_scene_id"])
        if (any(type(item) is not str or not 1 <= len(item) <= 256
                or item != item.strip() or any(ord(ch) < 32 for ch in item)
                for item in key) or key in seen):
            raise StudioQuestError("invalid or duplicate NPC dialogue gate identity")
        _lease(row["expected_relay_proof_digest"], "dialogue relay proof")
        seen.add(key)
        result.append(row)
    return result


def compile_npc_dialogue_knowledge_gate(
    documents: Mapping[str, Any], relay_receipt: object, authoring: object, *,
    authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC dialogue knowledge gate requires authorization")
    _lease(expected_source_digest, "NPC dialogue gate source")
    relay = replay_npc_knowledge_relay(
        documents, relay_receipt, authorized=True)
    if relay["source_digest"] != expected_source_digest:
        raise StudioQuestError("NPC dialogue gate source drift")
    temporal = relay["exchange_receipt"]["rendezvous_receipt"]["transit_receipt"]["temporal_receipt"]
    actions = temporal["actions"]
    staging = compile_dialogue_staging(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest)
    if (staging["session_digest"] != relay["session_digest"]
            or staging["project_id"] != relay["project_id"]):
        raise StudioQuestError("NPC dialogue gate quest replay drift")
    scenes = {card["scene_id"]: card for card in staging["cards"]}
    routes = {
        (route["fact_id"], route["recipient_scene_id"], route["target_scene_id"]): route
        for route in relay["routes"]
    }
    if len(routes) != len(relay["routes"]):
        raise StudioQuestError("ambiguous NPC dialogue relay routes")
    rows = []
    for gate in _request(authoring):
        key = (gate["fact_id"], gate["recipient_scene_id"],
               gate["target_scene_id"])
        route = routes.get(key)
        card = scenes.get(key[2])
        if route is None or card is None or route["target_npc_id"] != card["npc_id"]:
            raise StudioQuestError("NPC dialogue gate has no source-bound route or scene")
        if route["relay_proof_digest"] != gate["expected_relay_proof_digest"]:
            raise StudioQuestError("stale NPC dialogue gate proof lease")
        delivered = route["status"] == "delivered_in_sandbox_replay"
        available = card["status"] == "available"
        status = ("allowed_for_sandbox_preview" if delivered and available
                  else "blocked_knowledge_relay" if not delivered
                  else "blocked_quest_scene")
        row = {
            "fact_id": key[0], "recipient_scene_id": key[1],
            "target_scene_id": key[2], "target_npc_id": card["npc_id"],
            "relay_proof_digest": route["relay_proof_digest"],
            "dialogue_card_digest": card["card_digest"],
            "source_text_digest": route["source_text_digest"],
            "status": status, "npc_speech_verified": False,
            "source_text_disclosed": False,
        }
        row["gate_proof_digest"] = _digest(row)
        rows.append(row)
    allowed = sum(row["status"] == "allowed_for_sandbox_preview" for row in rows)
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": relay["project_id"],
        "source_digest": relay["source_digest"],
        "session_digest": relay["session_digest"],
        "relay_digest": relay["relay_digest"],
        "relay_receipt": relay, "authoring": authoring,
        "gates": rows, "allowed_count": allowed,
        "blocked_count": len(rows) - allowed,
        "playable_handoff_allowed": bool(rows)
            and allowed == len(rows) and relay["playable_handoff_allowed"],
        "source_replay_verified": True, "dialogue_spoken_verified": False,
        "native_npc_memory_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC dialogue gate receipt exceeds byte budget")
    result["gate_digest"] = _digest(result)
    return result


def propose_npc_dialogue_knowledge_gate(
    documents: Mapping[str, Any], relay_receipt: object, prompt: str, *,
    authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported NPC dialogue gate prompt")
    relay = replay_npc_knowledge_relay(
        documents, relay_receipt, authorized=authorized)
    authoring = {"gates": [{
        "fact_id": route["fact_id"],
        "recipient_scene_id": route["recipient_scene_id"],
        "target_scene_id": route["target_scene_id"],
        "expected_relay_proof_digest": route["relay_proof_digest"],
    } for route in relay["routes"][:MAX_GATES]]}
    return compile_npc_dialogue_knowledge_gate(
        documents, relay, authoring, authorized=authorized,
        expected_source_digest=expected_source_digest)


def replay_npc_dialogue_knowledge_gate(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC dialogue gate replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC dialogue gate receipt")
    checked = compile_npc_dialogue_knowledge_gate(
        documents, receipt.get("relay_receipt"), receipt.get("authoring"),
        authorized=True, expected_source_digest=receipt.get("source_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("NPC dialogue gate differs from canonical replay")
    return checked


def compile_npc_dialogue_gate_playable(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_npc_dialogue_knowledge_gate(
        documents, receipt, authorized=authorized)
    if not verified["playable_handoff_allowed"]:
        raise StudioQuestError("unproved NPC knowledge gate blocks playable handoff")
    original = compile_npc_relay_playable(
        documents, verified["relay_receipt"], authorized=True)
    result = {
        "schema": "skeleton.game_builder.studio_npc_dialogue_gate_handoff.v1",
        "gate_digest": verified["gate_digest"],
        "relay_digest": verified["relay_digest"],
        "bundle_sha256": original["bundle_sha256"],
        "canonical_html5_quest_included": original["canonical_html5_quest_included"],
        "native_npc_memory_integrated": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_npc_dialogue_knowledge_gate(
    documents: Mapping[str, Any], receipt: object, directory: Path,
    *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_npc_dialogue_knowledge_gate(
        documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC dialogue gate publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".npc-dialogue-gate-" + secrets.token_hex(16) + ".tmp"
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
    return {
        "path": str(Path(directory) / FILENAME),
        "gate_digest": checked["gate_digest"], "bytes": len(raw),
        "file_write_performed": True, "release_certified": False,
    }


def restore_npc_dialogue_knowledge_gate(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC dialogue gate restore requires authorization")
    _lease(expected_source_digest, "NPC dialogue gate restore source")
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
                raise StudioQuestError("NPC dialogue gate receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC dialogue gate receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate NPC dialogue gate JSON key")
            result[key] = value
        return result
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite NPC dialogue gate JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC dialogue gate JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale NPC dialogue gate source lease")
    return replay_npc_dialogue_knowledge_gate(documents, receipt, authorized=True)
