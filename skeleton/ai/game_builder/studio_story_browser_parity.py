"""Canonical parity between authored browser choices and source-replayed quest endings.

This checks the exact browser projection, not actual JavaScript execution, real
environmental evidence, or device certification. All replay inputs are bounded
and leased to an immutable source digest. Publication never overwrites a file.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress,
    replay_quest, start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_ecosystem_story_html import render_story_html, story_source

SCHEMA = "skeleton.game_builder.studio_story_browser_parity.v1"
PROMPT = "rehearse source-authored browser quest endings"
FILENAME = "story_browser_parity.json"
MAX_BYTES = 256 * 1024
MAX_ACTION_BYTES = 16 * 1024


def _actions(value: object, limit: int) -> list[list[str]]:
    if type(value) is not list or len(value) > limit:
        raise StudioQuestError("invalid bounded browser choice history")
    if len(_canonical(value)) > MAX_ACTION_BYTES:
        raise StudioQuestError("browser choice history exceeds byte budget")
    for pair in value:
        if (type(pair) is not list or len(pair) != 2
                or type(pair[0]) is not str or type(pair[1]) is not str):
            raise StudioQuestError("browser choices require exact string pairs")
    return value


def compile_story_browser_parity(
    documents: Mapping[str, Any], actions: object, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, object]:
    """Compare browser-earned predicates with the canonical quest engine."""
    if authorized is not True:
        raise PermissionError("browser parity requires operator authorization")
    _lease(expected_source_digest, "browser source")
    _lease(expected_initial_session_digest, "initial browser session")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale browser source lease")
    initial = start_quest(documents, authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale initial browser session lease")
    choices = _actions(actions, len(program.stages))
    browser = story_source(documents)
    if (browser["source_digest"] != program.source_digest
            or len(browser["stages"]) != len(program.stages)):
        raise StudioQuestError("browser projection diverged from quest source")
    session = replay_quest(documents, choices, authorized=True)
    progress = quest_progress(session, documents)
    by_id = {stage["id"]: stage for stage in browser["stages"]}
    earned = set(session.completed)
    earned.update(by_id[stage_id]["reward"] for stage_id in session.completed)
    applied: list[dict[str, object]] = []
    for stage_id, option in choices:
        stage = by_id[stage_id]
        tokens = stage["choice_effects"].get(option, [])
        if type(tokens) is not list or any(type(t) is not str for t in tokens):
            raise StudioQuestError("browser projection has malformed choice effects")
        earned.update(tokens)
        applied.append({
            "stage_id": stage_id, "alternative": option,
            "earned_choice_effects": list(tokens),
        })
    endings: list[dict[str, object]] = []
    eligible: list[str] = []
    missing: dict[str, list[str]] = {}
    for ending in browser["endings"]:
        absent = sorted(set(ending["requires"]) - earned)
        endings.append({"ending_id": ending["id"], "eligible": not absent,
                        "unmet_predicates": absent})
        if absent:
            missing[ending["id"]] = absent
        else:
            eligible.append(ending["id"])
    if (eligible != progress["sandbox_endings_eligible"]
            or missing != progress["unmet_ending_predicates"]):
        raise StudioQuestError("browser ending eligibility differs from canonical replay")
    html = render_story_html(documents)
    receipt: dict[str, object] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest, "actions": choices,
        "applied_choice_effects": applied, "browser_endings": endings,
        "canonical_eligible_endings": eligible,
        "canonical_unmet_predicates": missing,
        "playable_html_sha256": sha256(html).hexdigest(),
        "browser_projection_parity_verified": True,
        "javascript_runtime_executed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(receipt)) > MAX_BYTES - 128:
        raise StudioQuestError("browser parity receipt exceeds byte budget")
    receipt["receipt_digest"] = _digest(receipt)
    return receipt


def propose_story_browser_parity(
    documents: Mapping[str, Any], prompt: str, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, object]:
    """Deterministic authored-first-choice proposal, never model inference."""
    if authorized is not True:
        raise PermissionError("browser parity proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported browser parity prompt")
    program = compile_quest_program(documents)
    actions = [[stage.key, stage.alternatives[0]] for stage in program.stages]
    receipt = compile_story_browser_parity(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)
    return {"schema": "skeleton.game_builder.studio_story_browser_prompt.v1",
            "prompt": prompt, "actions": actions, "detail": receipt,
            "model_inference_performed": False, "release_certified": False}


def replay_story_browser_parity(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("browser parity replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid browser parity receipt")
    result = compile_story_browser_parity(
        documents, receipt.get("actions"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if receipt != result:
        raise StudioQuestError("browser parity receipt failed canonical replay")
    return result


def compile_story_browser_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> tuple[dict[str, object], bytes]:
    """Return the actual CSP-bound playable HTML, plus its replayed digest."""
    verified = replay_story_browser_parity(documents, receipt, authorized=authorized)
    html = render_story_html(documents)
    if sha256(html).hexdigest() != verified["playable_html_sha256"]:
        raise StudioQuestError("browser playable HTML changed after replay")
    return ({
        "schema": "skeleton.game_builder.studio_story_browser_handoff.v1",
        "project_id": verified["project_id"],
        "source_digest": verified["source_digest"],
        "receipt_digest": verified["receipt_digest"],
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "canonical_quest_replay_verified": True,
        "javascript_runtime_executed": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }, html)


def publish_story_browser_parity(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, object]:
    verified = replay_story_browser_parity(documents, receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("browser parity publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".browser-parity-" + secrets.token_hex(16) + ".tmp"
    created = False
    linked = False
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
        linked = True
        os.fsync(fd)
    except BaseException:
        if linked:
            os.unlink(FILENAME, dir_fd=fd)
        raise
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {"file": FILENAME, "bytes": len(raw),
            "receipt_digest": verified["receipt_digest"],
            "file_write_performed": True, "release_certified": False}


def restore_story_browser_parity(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("browser parity restore requires authorization")
    _lease(expected_source_digest, "restored browser source")
    _lease(expected_initial_session_digest, "restored initial session")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW |
                         getattr(os, "O_NONBLOCK", 0), dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix" and
                        (info.st_uid != os.getuid() or info.st_mode & 0o077
                         or info.st_nlink != 1))):
                raise StudioQuestError("browser parity receipt is not private regular file")
            raw = os.read(handle, MAX_BYTES + 1)
            after = os.fstat(handle)
            if (after.st_ino != info.st_ino or after.st_dev != info.st_dev
                    or after.st_size != info.st_size
                    or after.st_mtime_ns != info.st_mtime_ns):
                raise StudioQuestError("browser parity receipt mutated during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid bounded browser parity receipt")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise StudioQuestError("duplicate browser parity JSON key")
            value[key] = item
        return value
    try:
        stored = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite browser parity receipt")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid browser parity receipt JSON") from exc
    if (type(stored) is not dict
            or stored.get("source_digest") != expected_source_digest
            or stored.get("initial_session_digest") != expected_initial_session_digest
            or raw != _canonical(stored) + b"\n"):
        raise StudioQuestError("stale or noncanonical browser parity receipt")
    return replay_story_browser_parity(documents, stored, authorized=True)
