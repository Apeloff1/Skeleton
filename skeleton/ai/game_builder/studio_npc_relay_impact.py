"""Replay-verified counterfactual review of original NPC knowledge relay edits.

Compares two independently source-verified authored relays without inferring
NPC cognition, speech, or native game integration. No model-generated facts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease, _open_directory, _write_all
from .studio_ecosystem_npc_knowledge_relay import (
    replay_npc_knowledge_relay, compile_npc_relay_playable,
)

SCHEMA = "skeleton.game_builder.studio_npc_relay_impact.v1"
PROMPT = "compare source-bound npc knowledge relay revisions"
FILENAME = "npc_relay_impact.json"
MAX_BYTES = 896 * 1024
MAX_ROUTES = 32


def _identity(row: object) -> tuple[str, str, str]:
    if type(row) is not dict:
        raise StudioQuestError("malformed NPC relay impact route")
    key = (row.get("fact_id"), row.get("recipient_scene_id"),
           row.get("target_scene_id"))
    if any(type(item) is not str or not item for item in key):
        raise StudioQuestError("invalid NPC relay impact route identity")
    return key


def _index(receipt: Mapping[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    rows = receipt.get("routes")
    if type(rows) is not list or len(rows) > MAX_ROUTES:
        raise StudioQuestError("invalid NPC relay impact route budget")
    result = {}
    for row in rows:
        key = _identity(row)
        if key in result:
            raise StudioQuestError("duplicate NPC relay impact route")
        result[key] = row
    return result


def compile_npc_relay_impact(
    documents: Mapping[str, Any], baseline: object, candidate: object, *,
    authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    """Prove changed delivery, route causality and affected authored scenes."""
    if authorized is not True:
        raise PermissionError("NPC relay impact requires operator authorization")
    _lease(expected_source_digest, "NPC relay impact source")
    original = replay_npc_knowledge_relay(documents, baseline, authorized=True)
    revised = replay_npc_knowledge_relay(documents, candidate, authorized=True)
    if (original["source_digest"] != expected_source_digest
            or revised["source_digest"] != expected_source_digest
            or original["project_id"] != revised["project_id"]
            or original["session_digest"] != revised["session_digest"]
            or original["exchange_digest"] != revised["exchange_digest"]
            or original["rendezvous_digest"] != revised["rendezvous_digest"]):
        raise StudioQuestError("NPC relay impact source, session or exchange drift")
    old = _index(original)
    new = _index(revised)
    changes: list[dict[str, Any]] = []
    affected_scenes: set[str] = set()
    regressions = 0
    for key in sorted(set(old) | set(new)):
        before = old.get(key)
        after = new.get(key)
        if before is not None and after is not None and _canonical(before) == _canonical(after):
            continue
        before_status = before["status"] if before is not None else "absent"
        after_status = after["status"] if after is not None else "absent"
        before_delivered = before_status == "delivered_in_sandbox_replay"
        after_delivered = after_status == "delivered_in_sandbox_replay"
        if before_delivered and not after_delivered:
            regressions += 1
        affected_scenes.add(key[2])
        changes.append({
            "fact_id": key[0], "recipient_scene_id": key[1],
            "target_scene_id": key[2],
            "baseline_status": before_status,
            "candidate_status": after_status,
            "baseline_proof_digest": before["relay_proof_digest"] if before else None,
            "candidate_proof_digest": after["relay_proof_digest"] if after else None,
            "baseline_delivered": before_delivered,
            "candidate_delivered": after_delivered,
            "delivery_regressed": before_delivered and not after_delivered,
            "source_text_in_impact_row": False,
        })
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": original["project_id"],
        "source_digest": expected_source_digest,
        "session_digest": original["session_digest"],
        "exchange_digest": original["exchange_digest"],
        "baseline_relay_digest": original["relay_digest"],
        "candidate_relay_digest": revised["relay_digest"],
        "baseline_receipt": original, "candidate_receipt": revised,
        "changes": changes, "changed_route_count": len(changes),
        "affected_scene_ids": sorted(affected_scenes),
        "delivery_regressions": regressions,
        "playable_handoff_allowed": (
            regressions == 0 and original["playable_handoff_allowed"]
            and revised["playable_handoff_allowed"]),
        "source_replay_verified": True, "npc_speech_verified": False,
        "native_npc_memory_verified": False, "model_inference_performed": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC relay impact receipt exceeds bounded bytes")
    result["impact_digest"] = _digest(result)
    return result


def propose_npc_relay_impact(
    documents: Mapping[str, Any], baseline: object, candidate: object,
    prompt: str, *, authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported NPC relay impact prompt")
    return compile_npc_relay_impact(
        documents, baseline, candidate, authorized=authorized,
        expected_source_digest=expected_source_digest)


def replay_npc_relay_impact(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relay impact replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC relay impact receipt")
    checked = compile_npc_relay_impact(
        documents, receipt.get("baseline_receipt"),
        receipt.get("candidate_receipt"), authorized=True,
        expected_source_digest=receipt.get("source_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("NPC relay impact differs from canonical replay")
    return checked


def compile_npc_relay_impact_playable(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_npc_relay_impact(documents, receipt, authorized=authorized)
    if not verified["playable_handoff_allowed"]:
        raise StudioQuestError("NPC relay impact has unproved or regressed delivery")
    before = compile_npc_relay_playable(
        documents, verified["baseline_receipt"], authorized=True)
    after = compile_npc_relay_playable(
        documents, verified["candidate_receipt"], authorized=True)
    if before["bundle_sha256"] != after["bundle_sha256"]:
        raise StudioQuestError("NPC relay impact playable bundle drift")
    result = {
        "schema": "skeleton.game_builder.studio_npc_relay_impact_handoff.v1",
        "impact_digest": verified["impact_digest"],
        "bundle_sha256": after["bundle_sha256"],
        "baseline_handoff_digest": before["handoff_digest"],
        "candidate_handoff_digest": after["handoff_digest"],
        "canonical_html5_quest_included": after["canonical_html5_quest_included"],
        "native_npc_memory_integrated": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_npc_relay_impact(
    documents: Mapping[str, Any], receipt: object, directory: Path,
    *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_npc_relay_impact(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC relay impact publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".npc-impact-" + secrets.token_hex(16) + ".tmp"
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
            "impact_digest": checked["impact_digest"], "bytes": len(raw),
            "file_write_performed": True, "release_certified": False}


def restore_npc_relay_impact(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relay impact restore requires authorization")
    _lease(expected_source_digest, "NPC relay impact restore source")
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
                raise StudioQuestError("NPC relay impact receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC relay impact receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate NPC relay impact JSON key")
            result[key] = value
        return result
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite NPC relay impact JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC relay impact JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale NPC relay impact source lease")
    return replay_npc_relay_impact(documents, receipt, authorized=True)
