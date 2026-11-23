"""Source-leased quest replay diagnostics and minimal failing-prefix witnesses.

This is authored sandbox evidence, not environmental, native, or release proof.
The first invalid action is localized by replaying only canonical quest steps.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, start_quest,
    step_quest, replay_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)

SCHEMA = "skeleton.game_builder.studio_quest_replay_diagnostic.v1"
PROMPT = "diagnose the first canonical quest replay divergence"
FILENAME = "studio_quest_replay_diagnostic.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 128 * 1024
MAX_ACTIONS = 64


def _plan(value: object, ending_ids: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
            "actions", "target_ending", "expected_final_session_digest"}:
        raise StudioQuestError("invalid replay diagnostic plan fields")
    actions = value["actions"]
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise StudioQuestError("invalid replay diagnostic action count")
    for pair in actions:
        if (type(pair) is not list or len(pair) != 2
                or any(type(item) is not str or not 1 <= len(item) <= 256
                       or item.strip() != item or any(ord(c) < 32 for c in item)
                       for item in pair)):
            raise StudioQuestError("invalid typed replay diagnostic action")
    ending = value["target_ending"]
    if type(ending) is not str or ending not in ending_ids:
        raise StudioQuestError("unknown authored diagnostic ending")
    final = value["expected_final_session_digest"]
    if final is not None:
        _lease(final, "expected final session")
    if len(_canonical(value)) > 32768:
        raise StudioQuestError("replay diagnostic plan exceeds byte budget")
    return {"actions": [list(pair) for pair in actions],
            "target_ending": ending,
            "expected_final_session_digest": final}


def propose_replay_diagnostic(
    documents: Mapping[str, Any], prompt: str, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported replay diagnostic prompt")
    program = compile_quest_program(documents)
    if not program.endings:
        raise StudioQuestError("no authored endings")
    return compile_replay_diagnostic(
        documents, {"actions": [], "target_ending": program.endings[0][0],
                    "expected_final_session_digest": None},
        authorized=authorized, expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)


def compile_replay_diagnostic(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Locate first illegal action, unmet ending or expected digest mismatch."""
    if authorized is not True:
        raise PermissionError("quest replay diagnostic requires authorization")
    _lease(expected_source_digest, "diagnostic source")
    _lease(expected_initial_session_digest, "diagnostic initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("diagnostic source exceeds byte budget")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale diagnostic source lease")
    session = start_quest(documents, authorized=True)
    if session.digest != expected_initial_session_digest:
        raise StudioQuestError("stale diagnostic initial session lease")
    plan = _plan(authoring, {name for name, _ in program.endings})
    by_stage = {stage.key: stage for stage in program.stages}
    prefix: list[list[str]] = []
    first_invalid: dict[str, object] | None = None
    for index, (stage_id, alternative) in enumerate(plan["actions"]):
        try:
            updated = step_quest(
                session, documents, stage=stage_id, alternative=alternative,
                authorized=True)
        except StudioQuestError:
            first_invalid = {
                "index": index, "action": [stage_id, alternative],
                "reason": ("unknown_stage" if stage_id not in by_stage else
                           "unknown_alternative" if alternative not in
                           by_stage[stage_id].alternatives else
                           "stage_locked_or_repeated"),
                "verified_prefix_digest": session.digest,
            }
            break
        prefix.append([stage_id, alternative])
        session = updated
    # Verify the actual accepted prefix from the immutable source, not a
    # client-provided receipt or an unverified cached session object.
    if replay_quest(documents, prefix, authorized=True) != session:
        raise StudioQuestError("replay diagnostic prefix divergence")
    progress = quest_progress(session, documents)
    ending = plan["target_ending"]
    expected = plan["expected_final_session_digest"]
    if first_invalid is not None:
        status = "invalid_action"
    elif ending not in progress["sandbox_endings_eligible"]:
        status = "ending_unmet"
    elif expected is not None and session.digest != expected:
        status = "final_session_digest_mismatch"
    else:
        status = "verified"
    available = progress["available"]
    next_actions = [
        [stage_id, option]
        for stage_id in available
        for option in by_stage[stage_id].alternatives
    ]
    if _canonical(documents) != before:
        raise StudioQuestError("diagnostic source changed during replay")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": expected_initial_session_digest,
        "authoring": plan, "status": status,
        "accepted_actions": prefix,
        "first_invalid_action": first_invalid,
        "verified_prefix_session_digest": session.digest,
        "target_ending": ending,
        "target_ending_eligible": ending in progress["sandbox_endings_eligible"],
        "unmet_target_predicates": progress["unmet_ending_predicates"].get(ending, []),
        "next_legal_actions": next_actions,
        "expected_final_session_digest_matched": (
            expected is None or expected == session.digest),
        "canonical_quest_replay_verified": True,
        "playable_handoff_allowed": status == "verified",
        "external_evidence_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("diagnostic receipt exceeds byte budget")
    result["diagnostic_digest"] = _digest(result)
    return result


def replay_replay_diagnostic(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("diagnostic replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid replay diagnostic receipt")
    checked = compile_replay_diagnostic(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("diagnostic receipt differs from canonical replay")
    return checked


def compile_replay_diagnostic_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_replay_diagnostic(documents, receipt, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("unverified quest replay blocks playable handoff")
    session = replay_quest(
        documents, checked["accepted_actions"], authorized=True)
    progress = quest_progress(session, documents)
    if (session.digest != checked["verified_prefix_session_digest"]
            or checked["target_ending"] not in
            progress["sandbox_endings_eligible"]):
        raise StudioQuestError("quest handoff ending witness diverged")
    payload: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_quest_replay_handoff.v1",
        "diagnostic_digest": checked["diagnostic_digest"],
        "quest_source_digest": checked["source_digest"],
        "quest_session_digest": session.digest,
        "target_ending": checked["target_ending"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False, "release_certified": False,
    }
    payload["handoff_digest"] = _digest(payload)
    return payload


def publish_replay_diagnostic(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_replay_diagnostic(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("diagnostic publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".replay-diagnostic-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "diagnostic_digest": checked["diagnostic_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_replay_diagnostic(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("diagnostic restore requires authorization")
    _lease(expected_source_digest, "restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_RECEIPT_BYTES
                    or (os.name == "posix" and (
                        before.st_uid != os.getuid() or before.st_mode & 0o077
                        or before.st_nlink != 1))):
                raise StudioQuestError("diagnostic receipt is not private")
            raw = os.read(handle, MAX_RECEIPT_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size
                    or (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                        before.st_ino) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                     after.st_ino)):
                raise StudioQuestError("diagnostic receipt changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise StudioQuestError("duplicate diagnostic receipt JSON key")
            obj[key] = value
        return obj
    try:
        receipt = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite diagnostic receipt JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid diagnostic receipt JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale diagnostic restore source")
    return replay_replay_diagnostic(documents, receipt, authorized=True)
