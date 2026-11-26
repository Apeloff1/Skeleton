"""Deterministic source-leased what-if comparisons for authored scene timelines.

A scenario is a proposed *editor* revision, never native timing evidence.
Rejected scenarios cannot be selected, published as playable, or silently
substituted for the baseline. All accepted variants are canonically replayed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_ecosystem_temporal_windows import (
    MAX_TOTAL_TICKS, compile_temporal_windows, compile_temporal_playable,
)

SCHEMA = "skeleton.game_builder.studio_temporal_scenarios.v1"
PROMPT = "compare source-bound scene timing alternatives"
FILENAME = "temporal_scenarios.json"
MAX_SCENARIOS = 12
MAX_REQUEST_BYTES = 64 * 1024
MAX_RECEIPT_BYTES = 256 * 1024
_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")


def _validate_candidates(candidates: object) -> list[dict[str, object]]:
    if type(candidates) is not list or not 1 <= len(candidates) <= MAX_SCENARIOS:
        raise StudioQuestError("temporal scenarios require 1..12 candidates")
    if len(_canonical(candidates)) > MAX_REQUEST_BYTES:
        raise StudioQuestError("temporal scenarios exceed request budget")
    seen: set[str] = set()
    for item in candidates:
        if (type(item) is not dict or set(item) != {"id", "authoring"}
                or type(item["id"]) is not str or not _ID.fullmatch(item["id"])
                or item["id"] in seen or type(item["authoring"]) is not dict):
            raise StudioQuestError("invalid or duplicate temporal scenario")
        seen.add(item["id"])
    return candidates


def compile_temporal_scenarios(
    documents: Mapping[str, Any], actions: list[list[str]],
    baseline_authoring: object, candidates: object, *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    """Evaluate typed variants against the *same* source and quest replay lease."""
    if authorized is not True:
        raise PermissionError("temporal scenario compilation requires authorization")
    _lease(expected_source_digest, "temporal scenario source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "temporal scenario session")
    checked = _validate_candidates(candidates)
    baseline = compile_temporal_windows(
        documents, actions, baseline_authoring, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    base_rows = {row["scene_id"]: row for row in baseline["window_proofs"]}
    outcomes: list[dict[str, object]] = []
    for candidate in checked:
        try:
            proof = compile_temporal_windows(
                documents, actions, candidate["authoring"], authorized=True,
                expected_source_digest=expected_source_digest,
                expected_session_digest=baseline["session_digest"])
        except StudioQuestError:
            outcome: dict[str, object] = {
                "id": candidate["id"], "status": "rejected",
                "reason": "authored-temporal-constraint-unsatisfied",
                "playable_handoff_allowed": False,
            }
        else:
            if (proof["source_digest"] != baseline["source_digest"]
                    or proof["session_digest"] != baseline["session_digest"]
                    or proof["quest_source_digest"] != baseline["quest_source_digest"]
                    or proof["scene_count"] != baseline["scene_count"]):
                raise StudioQuestError("temporal scenario changed source identity")
            changes = []
            for row in proof["window_proofs"]:
                prior = base_rows[row["scene_id"]]
                changes.append({
                    "scene_id": row["scene_id"],
                    "start_tick_delta": row["start_tick"] - prior["start_tick"],
                    "end_tick_delta": row["end_tick"] - prior["end_tick"],
                    "deadline_slack_delta": row["deadline_slack"] - prior["deadline_slack"],
                    "window_changed": (row["earliest"], row["latest"]) !=
                                      (prior["earliest"], prior["latest"]),
                })
            outcome = {
                "id": candidate["id"], "status": "accepted",
                "temporal_digest": proof["temporal_digest"],
                "critical_path_ticks": proof["critical_path_ticks"],
                "critical_path_delta": proof["critical_path_ticks"] -
                                       baseline["critical_path_ticks"],
                "scene_changes": changes,
                "playable_handoff_allowed": True,
            }
        outcome["outcome_digest"] = _digest(outcome)
        outcomes.append(outcome)
    receipt: dict[str, object] = {
        "schema": SCHEMA, "project_id": baseline["project_id"],
        "source_digest": baseline["source_digest"],
        "quest_source_digest": baseline["quest_source_digest"],
        "session_digest": baseline["session_digest"],
        "baseline_authoring": baseline_authoring,
        "baseline_temporal_digest": baseline["temporal_digest"],
        "actions": [list(action) for action in actions],
        "candidates": checked, "outcomes": outcomes,
        "accepted_count": sum(x["status"] == "accepted" for x in outcomes),
        "rejected_count": sum(x["status"] == "rejected" for x in outcomes),
        "source_replay_verified": True, "model_inference_performed": False,
        "native_time_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(receipt)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("temporal scenario receipt exceeds byte budget")
    receipt["scenario_digest"] = _digest(receipt)
    return receipt


def propose_temporal_scenarios(
    documents: Mapping[str, Any], actions: list[list[str]],
    baseline_authoring: object, prompt: str, *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    """Deterministic authored-window alternatives; no provider call is implied."""
    if authorized is not True:
        raise PermissionError("temporal scenario proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported temporal scenario prompt")
    baseline = compile_temporal_windows(
        documents, actions, baseline_authoring, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    tight = json.loads(_canonical(baseline_authoring))
    buffered = json.loads(_canonical(baseline_authoring))
    for row in baseline["window_proofs"]:
        scene = row["scene_id"]
        tight["windows"][scene]["latest"] = row["end_tick"]
        buffered["windows"][scene]["latest"] = min(
            MAX_TOTAL_TICKS, max(row["latest"], row["end_tick"] + 30))
    candidates = [
        {"id": "tight-deadlines", "authoring": tight},
        {"id": "buffered-deadlines", "authoring": buffered},
    ]
    return compile_temporal_scenarios(
        documents, actions, baseline_authoring, candidates, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)


def replay_temporal_scenarios(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("temporal scenario replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid temporal scenario receipt")
    replay = compile_temporal_scenarios(
        documents, receipt.get("actions"), receipt.get("baseline_authoring"),
        receipt.get("candidates"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if replay != receipt:
        raise StudioQuestError("temporal scenario receipt failed canonical replay")
    return replay


def select_temporal_scenario(
    documents: Mapping[str, Any], receipt: object, scenario_id: str, *,
    authorized: bool, playable: bool = False,
) -> dict[str, object]:
    """Return a canonically recompiled variant; optionally prove HTML5 handoff."""
    replay = replay_temporal_scenarios(documents, receipt, authorized=authorized)
    if type(scenario_id) is not str or not _ID.fullmatch(scenario_id):
        raise StudioQuestError("invalid temporal scenario selection")
    matched = [x for x in replay["outcomes"] if x["id"] == scenario_id]
    if len(matched) != 1 or matched[0]["status"] != "accepted":
        raise StudioQuestError("cannot select rejected or unknown scenario")
    authoring = next(x["authoring"] for x in replay["candidates"]
                     if x["id"] == scenario_id)
    selected = compile_temporal_windows(
        documents, replay["actions"], authoring, authorized=True,
        expected_source_digest=replay["source_digest"],
        expected_session_digest=replay["session_digest"])
    if selected["temporal_digest"] != matched[0]["temporal_digest"]:
        raise StudioQuestError("selected scenario changed since proof")
    result: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_temporal_selection.v1",
        "scenario_id": scenario_id, "scenario_digest": replay["scenario_digest"],
        "temporal": selected, "source_replay_verified": True,
        "release_certified": False,
    }
    if playable is True:
        result["playable_manifest"], _ = compile_temporal_playable(
            documents, selected, authorized=True)
    elif playable is not False:
        raise StudioQuestError("playable selection must be boolean")
    result["selection_digest"] = _digest(result)
    return result


def publish_temporal_scenarios(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, object]:
    replay = replay_temporal_scenarios(documents, receipt, authorized=authorized)
    raw = _canonical(replay) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("temporal scenario publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".temporal-scenarios-" + secrets.token_hex(16) + ".tmp"
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
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "scenario_digest": replay["scenario_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_temporal_scenarios(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("temporal scenario restore requires authorization")
    _lease(expected_source_digest, "temporal scenario restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode)
                    or not 0 < info.st_size <= MAX_RECEIPT_BYTES
                    or (os.name == "posix" and
                        (info.st_uid != os.getuid() or info.st_mode & 0o077
                         or info.st_nlink != 1))):
                raise StudioQuestError("temporal scenario receipt must be private")
            raw = os.read(handle, MAX_RECEIPT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("invalid temporal scenario receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate temporal scenario receipt key")
            result[key] = value
        return result
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite scenario receipt")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid temporal scenario receipt JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale temporal scenario source lease")
    return replay_temporal_scenarios(documents, receipt, authorized=True)
