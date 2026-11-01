"""Deterministic what-if critical path for authored scenes and NPC scheduling.

This estimates editorial timing, not native movement, dialogue or wall-clock time.
All scene identity and consequence authority belongs to the canonical compilers.
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
    _canonical, _digest, _lease, _open_directory, _write_all, compile_scene_schedule,
)

SCHEMA = "skeleton.game_builder.studio_scene_rehearsal.v1"
FILENAME = "scene_rehearsal.json"
MAX_BYTES = 256 * 1024


def _dependency_proof(rows: list[dict[str, Any]], turnaround: int
                      ) -> tuple[list[dict[str, object]], list[str]]:
    seen: dict[str, dict[str, Any]] = {}
    proof: list[dict[str, object]] = []
    for row in rows:
        sid, start = row["scene_id"], row["start_tick"]
        if sid in seen:
            raise StudioQuestError("duplicate scene rehearsal identity")
        edges: list[dict[str, str]] = []
        for parent in row["prerequisite_scenes"]:
            prior = seen.get(parent["scene_id"])
            if prior is None or prior["end_tick"] != parent["end_tick"]:
                raise StudioQuestError("invalid rehearsal prerequisite evidence")
            if prior["end_tick"] == start:
                edges.append({"scene_id": parent["scene_id"], "kind": "quest"})
        prior_id = row["prior_npc_scene"]
        if prior_id is not None:
            prior = seen.get(prior_id)
            if prior is None or prior["npc_id"] != row["npc_id"]:
                raise StudioQuestError("invalid rehearsal NPC predecessor")
            if prior["end_tick"] + turnaround == start:
                edges.append({"scene_id": prior_id, "kind": "npc_turnaround"})
        edges.sort(key=lambda edge: (edge["scene_id"], edge["kind"]))
        proof.append({"scene_id": sid, "start_tick": start,
                      "end_tick": row["end_tick"], "binding_edges": edges,
                      "externally_anchored": not edges})
        seen[sid] = row
    last = max(rows, key=lambda row: (row["end_tick"], -row["scene_index"]))
    current = last["scene_id"]
    lookup = {item["scene_id"]: item for item in proof}
    chain: list[str] = []
    while current:
        if current in chain:
            raise StudioQuestError("cyclic rehearsal dependency")
        chain.append(current)
        edges = lookup[current]["binding_edges"]
        current = edges[0]["scene_id"] if edges else ""
    chain.reverse()
    return proof, chain


def compile_scene_rehearsal(
    documents: Mapping[str, Any], actions: list[list[str]],
    baseline: object, candidate: object, *, authorized: bool,
    expected_source_digest: str, expected_session_digest: str | None = None,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("scene rehearsal requires operator authorization")
    _lease(expected_source_digest, "rehearsal source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "rehearsal session")
    old = compile_scene_schedule(
        documents, actions, baseline, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    new = compile_scene_schedule(
        documents, actions, candidate, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=old["session_digest"])
    for key in ("project_id", "source_digest", "quest_source_digest",
                "session_digest", "scene_count"):
        if old[key] != new[key]:
            raise StudioQuestError("rehearsal source or session diverged")
    changes: list[dict[str, object]] = []
    for before, after in zip(old["timeline"], new["timeline"]):
        for key in ("scene_id", "quest_stage", "npc_id", "site", "status",
                    "selected_alternative", "authored_card_digest"):
            if before[key] != after[key]:
                raise StudioQuestError("rehearsal changed authored scene identity")
        if any(before[key] != after[key] for key in
               ("start_tick", "end_tick", "duration_ticks")):
            changes.append({
                "scene_id": before["scene_id"],
                "start_shift_ticks": after["start_tick"] - before["start_tick"],
                "end_shift_ticks": after["end_tick"] - before["end_tick"],
                "duration_delta_ticks": after["duration_ticks"] - before["duration_ticks"],
                "old_start_tick": before["start_tick"],
                "new_start_tick": after["start_tick"],
                "old_end_tick": before["end_tick"],
                "new_end_tick": after["end_tick"],
            })
    old_proof, old_chain = _dependency_proof(
        old["timeline"], old["schedule_request"]["npc_turnaround_ticks"])
    new_proof, new_chain = _dependency_proof(
        new["timeline"], new["schedule_request"]["npc_turnaround_ticks"])
    delta = new["critical_path_ticks"] - old["critical_path_ticks"]
    result: dict[str, object] = {
        "schema": SCHEMA, "project_id": old["project_id"],
        "source_digest": old["source_digest"],
        "quest_source_digest": old["quest_source_digest"],
        "session_digest": old["session_digest"],
        "baseline_schedule": old["schedule_request"],
        "candidate_schedule": new["schedule_request"],
        "baseline_schedule_digest": old["schedule_digest"],
        "candidate_schedule_digest": new["schedule_digest"],
        "baseline_critical_ticks": old["critical_path_ticks"],
        "candidate_critical_ticks": new["critical_path_ticks"],
        "critical_delta_ticks": delta, "candidate_is_shorter": delta < 0,
        "changed_scene_count": len(changes), "scene_changes": changes,
        "baseline_dependency_proof": old_proof,
        "candidate_dependency_proof": new_proof,
        "baseline_critical_chain": old_chain,
        "candidate_critical_chain": new_chain,
        "source_replay_verified": True, "source_unchanged": True,
        "model_inference_performed": False, "native_timing_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("rehearsal exceeds bounded receipt")
    result["rehearsal_digest"] = _digest(result)
    return result


def compile_rehearsed_playable(
    documents: Mapping[str, Any], actions: list[list[str]],
    report: Mapping[str, Any], assignments: object, *, authorized: bool,
    expected_visual_digest: str,
) -> tuple[dict[str, object], bytes]:
    if authorized is not True:
        raise PermissionError("playable rehearsal requires operator authorization")
    if type(report) is not dict or report.get("schema") != SCHEMA:
        raise StudioQuestError("invalid playable rehearsal")
    replay = compile_scene_rehearsal(
        documents, actions, report.get("baseline_schedule"),
        report.get("candidate_schedule"), authorized=True,
        expected_source_digest=report.get("source_digest"),
        expected_session_digest=report.get("session_digest"))
    if replay != report:
        raise StudioQuestError("rehearsal playable lacks source replay")
    from .studio_ecosystem_director_handoff import compile_director_handoff
    manifest, bundle = compile_director_handoff(
        documents, actions, report["candidate_schedule"], assignments,
        authorized=True, expected_source_digest=report["source_digest"],
        expected_visual_digest=expected_visual_digest,
        expected_session_digest=report["session_digest"])
    if (manifest["scene_schedule_digest"] != report["candidate_schedule_digest"]
            or manifest["project_id"] != report["project_id"]
            or manifest["canonical_html5_gameplay_replay_verified"] is not True):
        raise StudioQuestError("playable rehearsal diverged from source")
    return manifest, bundle


def publish_scene_rehearsal(
    report: Mapping[str, Any], directory: Path, *, authorized: bool,
    documents: Mapping[str, Any], actions: list[list[str]],
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("rehearsal publication requires authorization")
    if type(report) is not dict or report.get("schema") != SCHEMA:
        raise StudioQuestError("invalid rehearsal publication")
    replay = compile_scene_rehearsal(
        documents, actions, report.get("baseline_schedule"),
        report.get("candidate_schedule"), authorized=True,
        expected_source_digest=report.get("source_digest"),
        expected_session_digest=report.get("session_digest"))
    if report != replay:
        raise StudioQuestError("forged rehearsal publication")
    raw = _canonical(report) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("rehearsal publication too large")
    fd = _open_directory(directory)
    name = ".scene-rehearsal-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(name, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(name, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "rehearsal_digest": report["rehearsal_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def verify_scene_rehearsal(
    documents: Mapping[str, Any], actions: list[list[str]],
    directory: Path, *, authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("rehearsal restore requires authorization")
    _lease(expected_source_digest, "restored rehearsal source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "restored rehearsal session")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or
                    not 0 < info.st_size <= MAX_BYTES or
                    os.name == "posix" and
                    (info.st_uid != os.getuid() or info.st_mode & 0o077 or
                     info.st_nlink != 1)):
                raise StudioQuestError("rehearsal restore requires private file")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid rehearsal receipt size")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate rehearsal JSON key")
            result[key] = value
        return result
    try:
        stored = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite rehearsal JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid rehearsal receipt JSON") from exc
    if (type(stored) is not dict or stored.get("source_digest") != expected_source_digest
            or expected_session_digest is not None
            and stored.get("session_digest") != expected_session_digest):
        raise StudioQuestError("stale rehearsal source or session")
    replay = compile_scene_rehearsal(
        documents, actions, stored.get("baseline_schedule"),
        stored.get("candidate_schedule"), authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=stored.get("session_digest"))
    if stored != replay:
        raise StudioQuestError("rehearsal restore lacks canonical replay")
    return replay
