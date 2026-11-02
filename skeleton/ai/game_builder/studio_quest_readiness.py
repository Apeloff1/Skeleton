"""Fail-closed joint proof of authored ending coverage and terminal-branch safety.

This is a canonical quest sandbox qualification, not native gameplay or release
certification. Each proof is independently replayed against the exact source.
A bounded/inconclusive audit is never promoted to a safe handoff.
"""
from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_ending_coverage import (
    compile_ending_coverage, compile_ending_coverage_handoff,
)
from .studio_quest_softlock_audit import (
    compile_quest_softlock_audit, compile_quest_softlock_handoff,
)

SCHEMA = "skeleton.game_builder.studio_quest_readiness.v1"
HANDOFF_SCHEMA = "skeleton.game_builder.studio_quest_readiness_handoff.v1"
PROMPT = "verify all authored quest endings and rule out terminal softlocks"
FILENAME = "studio_quest_readiness.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 512 * 1024
MAX_STATES = 2048
MAX_DEPTH = 64


def _plan(value: object, stage_count: int) -> dict[str, int]:
    if type(value) is not dict or set(value) != {"max_states", "max_depth"}:
        raise StudioQuestError("readiness requires exact typed exploration budget")
    states, depth = value["max_states"], value["max_depth"]
    if (type(states) is not int or not 1 <= states <= MAX_STATES
            or type(depth) is not int or not 1 <= depth <= MAX_DEPTH
            or depth > stage_count):
        raise StudioQuestError("invalid or excessive readiness exploration budget")
    return {"max_states": states, "max_depth": depth}


def compile_quest_readiness(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Require BOTH independently replayable proofs over the full quest origin.

    Never accept a caller-provided subset of endings or a nonempty prefix:
    either would let a caller hide a softlocked branch or unreachable ending.
    """
    if authorized is not True:
        raise PermissionError("quest readiness requires operator authorization")
    _lease(expected_source_digest, "readiness source")
    _lease(expected_initial_session_digest, "readiness initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("quest readiness source exceeds byte budget")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale quest readiness source lease")
    initial = start_quest(documents, authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale quest readiness initial session lease")
    if len(program.endings) > 16:
        raise StudioQuestError("too many authored endings for bounded readiness")
    plan = _plan(authoring, len(program.stages))
    proof_request = {
        "initial_actions": [],
        "target_endings": [name for name, _ in program.endings],
        "max_states": plan["max_states"],
        "max_depth": plan["max_depth"],
    }
    leases = {
        "authorized": True,
        "expected_source_digest": expected_source_digest,
        "expected_initial_session_digest": expected_initial_session_digest,
    }
    coverage = compile_ending_coverage(documents, proof_request, **leases)
    softlock = compile_quest_softlock_audit(documents, proof_request, **leases)
    if (_canonical(documents) != before
            or coverage["source_digest"] != softlock["source_digest"]
            or coverage["initial_session_digest"] != softlock["initial_session_digest"]):
        raise StudioQuestError("quest readiness evidence source drift")
    covered = (coverage["status"] == "all_targets_witnessed"
               and coverage["coverage_complete"] is True)
    no_softlock = (
        softlock["status"] == "no_softlock_in_exhaustive_search"
        and softlock["search_exhaustive"] is True
        and softlock["playable_handoff_allowed"] is True
    )
    allowed = bool(covered and no_softlock)
    status = ("canonical_sandbox_ready" if allowed else
              "terminal_softlock_proven" if softlock["status"] == "softlock_proven"
              else "unreachable_ending" if
              coverage["status"] == "unreachable_in_exhaustive_search"
              else "inconclusive_not_ready")
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": program.project_id,
        "source_digest": expected_source_digest,
        "initial_session_digest": initial.digest,
        "authoring": plan,
        "status": status,
        "all_endings_witnessed": covered,
        "terminal_softlocks_excluded": no_softlock,
        "playable_handoff_allowed": allowed,
        "ending_coverage": coverage,
        "softlock_audit": softlock,
        "canonical_quest_replay_verified": True,
        "external_evidence_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(receipt)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("quest readiness evidence exceeds byte budget")
    receipt["readiness_digest"] = _digest(receipt)
    return receipt


def propose_quest_readiness(
    documents: Mapping[str, Any], prompt: str, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported quest readiness prompt")
    program = compile_quest_program(documents)
    return compile_quest_readiness(
        documents, {"max_states": 512, "max_depth": len(program.stages)},
        authorized=authorized,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest,
    )


def replay_quest_readiness(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest readiness replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid typed quest readiness receipt")
    verified = compile_quest_readiness(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"),
    )
    if _canonical(verified) != _canonical(receipt):
        raise StudioQuestError("quest readiness receipt differs from canonical replay")
    return verified


def compile_quest_readiness_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_quest_readiness(documents, receipt, authorized=authorized)
    if verified["playable_handoff_allowed"] is not True:
        raise StudioQuestError("quest readiness does not authorize playable handoff")
    ending = compile_ending_coverage_handoff(
        documents, verified["ending_coverage"], authorized=True)
    safety = compile_quest_softlock_handoff(
        documents, verified["softlock_audit"], authorized=True)
    if (ending["quest_source_digest"] != verified["source_digest"]
            or safety["quest_source_digest"] != verified["source_digest"]):
        raise StudioQuestError("quest readiness handoff source mismatch")
    handoff: dict[str, Any] = {
        "schema": HANDOFF_SCHEMA,
        "project_id": verified["project_id"],
        "quest_source_digest": verified["source_digest"],
        "initial_session_digest": verified["initial_session_digest"],
        "readiness_digest": verified["readiness_digest"],
        "ending_coverage_handoff_digest": ending["handoff_digest"],
        "softlock_handoff_digest": safety["handoff_digest"],
        "ending_witnesses": ending["ending_witnesses"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    handoff["handoff_digest"] = _digest(handoff)
    return handoff


def render_quest_readiness_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_readiness(documents, receipt, authorized=authorized)
    witnesses = "".join(
        "<li>" + escape(row["ending_id"], quote=True) + " — "
        + str(len(row["actions"])) + " canonical steps</li>"
        for row in checked["ending_coverage"]["witnesses"]
    )
    uncovered = "".join(
        "<li>" + escape(name, quote=True) + "</li>"
        for name in checked["ending_coverage"]["uncovered_endings"]
    )
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'none'; style-src 'none'; form-action 'none'; "
        'base-uri \'none\'"><title>Quest readiness</title></head>'
        '<body><main><h1>Canonical quest readiness</h1><p>Status: '
        + escape(checked["status"], quote=True)
        + '</p><h2>Verified ending witnesses</h2><ol>' + witnesses
        + '</ol><h2>Uncovered endings</h2><ul>' + uncovered
        + '</ul><p>Terminal branch audit: '
        + escape(checked["softlock_audit"]["status"], quote=True)
        + '</p><p>Sandbox proof only. Native gameplay, external evidence, '
        'rights and release remain unverified.</p></main></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("quest readiness preview exceeds byte budget")
    return html


def publish_quest_readiness(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    verified = replay_quest_readiness(documents, receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("quest readiness publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".quest-readiness-" + secrets.token_hex(16) + ".tmp"
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
        "file": FILENAME, "readiness_digest": verified["readiness_digest"],
        "file_write_performed": True, "release_certified": False,
    }


def restore_quest_readiness(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest readiness restore requires authorization")
    _lease(expected_source_digest, "readiness restore source")
    fd = _open_directory(directory)
    try:
        inp = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                      dir_fd=fd)
        try:
            before = os.fstat(inp)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_RECEIPT_BYTES
                    or (os.name == "posix" and
                        (before.st_uid != os.getuid() or before.st_mode & 0o077
                         or before.st_nlink != 1))):
                raise StudioQuestError("quest readiness evidence must be private")
            raw = os.read(inp, MAX_RECEIPT_BYTES + 1)
            after = os.fstat(inp)
            if (len(raw) != before.st_size
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                        after.st_ino) !=
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                     before.st_ino)):
                raise StudioQuestError("quest readiness evidence changed during read")
        finally:
            os.close(inp)
    finally:
        os.close(fd)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate quest readiness JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite quest readiness JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid quest readiness evidence JSON") from exc
    if type(value) is not dict or value.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale or malformed quest readiness evidence")
    return replay_quest_readiness(documents, value, authorized=True)
