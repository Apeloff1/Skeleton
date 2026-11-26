"""Bounded, source-leased ending witness search over the real authored quest engine.

An ending witness is a replayable sandbox quest history, not evidence of native
gameplay, cinematic delivery, physical travel or consumer release readiness.
"""
from __future__ import annotations

from collections import deque
from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)

SCHEMA = "skeleton.game_builder.studio_quest_ending_witness.v1"
FILENAME = "studio_quest_ending_witness.json"
MAX_BYTES = 256 * 1024
MAX_STATES = 2048
MAX_DEPTH = 64


def _actions(value: object) -> list[list[str]]:
    if type(value) is not list or len(value) > MAX_DEPTH:
        raise StudioQuestError("invalid bounded ending witness prefix")
    result: list[list[str]] = []
    for item in value:
        if (type(item) is not list or len(item) != 2
                or any(type(x) is not str or not 1 <= len(x) <= 256
                       or x.strip() != x or any(ord(c) < 32 for c in x)
                       for x in item)):
            raise StudioQuestError("invalid typed ending witness action")
        result.append(list(item))
    return result


def _limit(value: object, label: str, upper: int) -> int:
    if type(value) is not int or not 1 <= value <= upper:
        raise StudioQuestError("invalid ending witness " + label)
    return value


def compile_ending_witness(
    documents: Mapping[str, Any], *, target_ending: str,
    initial_actions: object, max_states: int, max_depth: int,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Search authored alternatives in canonical order; never invent facts.

    A bounded search reports inconclusive rather than claiming impossibility
    when its node or depth budget prevents exhaustive exploration.
    """
    if authorized is not True:
        raise PermissionError("ending witness requires operator authorization")
    _lease(expected_source_digest, "ending witness source")
    _lease(expected_initial_session_digest, "ending witness initial session")
    states = _limit(max_states, "state budget", MAX_STATES)
    depth = _limit(max_depth, "depth budget", MAX_DEPTH)
    actions = _actions(initial_actions)
    if len(actions) > depth:
        raise StudioQuestError("ending witness prefix exceeds depth budget")
    if (type(target_ending) is not str or not 1 <= len(target_ending) <= 256
            or target_ending.strip() != target_ending
            or any(ord(c) < 32 for c in target_ending)):
        raise StudioQuestError("invalid ending witness target")
    before = _canonical(documents)
    if len(before) > MAX_BYTES:
        raise StudioQuestError("ending witness source exceeds budget")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale ending witness source lease")
    if target_ending not in dict(program.endings):
        raise StudioQuestError("unknown authored ending target")
    initial = replay_quest(documents, actions, authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale ending witness session lease")

    queue: deque[list[list[str]]] = deque([actions])
    expanded = 0
    truncated = False
    found: list[list[str]] | None = None
    found_session = initial
    found_progress = quest_progress(initial, documents)
    by_stage = {stage.key: stage for stage in program.stages}
    while queue:
        if expanded >= states:
            truncated = True
            break
        current = queue.popleft()
        session = replay_quest(documents, current, authorized=True)
        progress = quest_progress(session, documents)
        expanded += 1
        if target_ending in progress["sandbox_endings_eligible"]:
            found = current
            found_session = session
            found_progress = progress
            break
        available = progress["available"]
        if len(current) >= depth:
            if available:
                truncated = True
            continue
        for stage_id in available:
            stage = by_stage[stage_id]
            for option in stage.alternatives:
                queue.append(current + [[stage_id, option]])
                if len(queue) > states * 8:
                    truncated = True
                    break
            if truncated:
                break
        if truncated:
            break
    if found is not None:
        status = "found"
    elif truncated:
        status = "inconclusive"
    else:
        status = "unreachable"
    if _canonical(documents) != before:
        raise StudioQuestError("ending witness source changed during search")
    payload: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": expected_source_digest,
        "target_ending": target_ending, "initial_actions": actions,
        "initial_session_digest": initial.digest,
        "max_states": states, "max_depth": depth,
        "status": status, "search_exhaustive": status == "unreachable",
        "expanded_states": expanded, "witness_actions": found or [],
        "witness_session_digest": (
            found_session.digest if found is not None else None),
        "witness_progress": found_progress if found is not None else None,
        "playable_quest_replay_verified": found is not None,
        "native_gameplay_verified": False,
        "external_evidence_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_BYTES - 128:
        raise StudioQuestError("ending witness result exceeds budget")
    payload["receipt_digest"] = _digest(payload)
    return payload


def replay_ending_witness(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("ending witness replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid ending witness receipt")
    checked = compile_ending_witness(
        documents, target_ending=receipt.get("target_ending"),
        initial_actions=receipt.get("initial_actions"),
        max_states=receipt.get("max_states"), max_depth=receipt.get("max_depth"),
        authorized=True, expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest,
    )
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("ending witness failed canonical replay")
    return checked


def render_ending_witness_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> bytes:
    checked = replay_ending_witness(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)
    rows = "".join(
        "<li>" + escape(stage, quote=True) + " → "
        + escape(option, quote=True) + "</li>"
        for stage, option in checked["witness_actions"]
    )
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "\'none\'; script-src \'none\'; style-src \'none\'; img-src \'none\'; "
        'form-action \'none\'; base-uri \'none\'">'
        '<title>Quest ending witness</title></head><body><main>'
        '<h1>Authored ending witness</h1><p>Target: '
        + escape(checked["target_ending"], quote=True)
        + '</p><p>Search: ' + escape(checked["status"])
        + '</p><ol>' + rows + '</ol>'
        '<p>Sandbox quest replay only; native gameplay and release not verified.'
        '</p></main></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_BYTES:
        raise StudioQuestError("ending witness HTML exceeds budget")
    return html


def publish_ending_witness(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    checked = replay_ending_witness(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)
    raw = _canonical(checked) + b"\n"
    fd = _open_directory(directory)
    temporary = ".ending-witness-" + secrets.token_hex(16) + ".tmp"
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
    return {
        "path": str(Path(directory) / FILENAME), "bytes": len(raw),
        "receipt_digest": checked["receipt_digest"],
        "file_write_performed": True, "release_certified": False,
    }


def restore_ending_witness(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("ending witness restore requires authorization")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_BYTES
                    or (os.name == "posix" and
                        (before.st_uid != os.getuid()
                         or before.st_mode & 0o077 or before.st_nlink != 1))):
                raise StudioQuestError("ending witness receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size or
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                     after.st_ino) !=
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                     before.st_ino)):
                raise StudioQuestError("ending witness receipt changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate ending witness JSON key")
            result[key] = value
        return result

    try:
        receipt = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite ending witness JSON")))
    except StudioQuestError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid ending witness JSON") from exc
    return replay_ending_witness(
        documents, receipt, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)
