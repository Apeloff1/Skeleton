"""Deterministic source-leased ending regression review for authored quest revisions.

Compares actual bounded sandbox ending witnesses for two independently compiled
original plans. An inconclusive search is NEVER reported as unreachable or safe.
This is a review aid, not native gameplay or rights qualification.
"""
from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_prompt_quest_plan import replay_prompt_quest_plan
from .studio_quest_ending_witness import (
    compile_ending_witness, replay_ending_witness,
)

SCHEMA = "skeleton.game_builder.studio_quest_regression_matrix.v1"
FILENAME = "studio_quest_regression_matrix.json"
MAX_BYTES = 512 * 1024
MAX_ENDINGS = 16


def _checked(value: object, digest: str, label: str) -> dict[str, Any]:
    _lease(digest, label)
    receipt = replay_prompt_quest_plan(value, authorized=True)
    if _canonical(value) != _canonical(receipt):
        raise StudioQuestError("noncanonical " + label + " payload")
    if receipt["receipt_digest"] != digest:
        raise StudioQuestError("stale " + label + " lease")
    return receipt


def _witness(compilation: dict[str, Any], ending: str,
             max_states: int, max_depth: int) -> dict[str, Any]:
    result = compile_ending_witness(
        compilation["documents"], target_ending=ending, initial_actions=[],
        max_states=max_states, max_depth=max_depth, authorized=True,
        expected_source_digest=compilation["quest_source_digest"],
        expected_initial_session_digest=compilation["initial_quest_session_digest"],
    )
    checked = replay_ending_witness(
        compilation["documents"], result, authorized=True,
        expected_source_digest=compilation["quest_source_digest"],
        expected_initial_session_digest=compilation["initial_quest_session_digest"],
    )
    if _canonical(result) != _canonical(checked):
        raise StudioQuestError("ending witness replay diverged")
    return result


def _first_divergence(before: list[list[str]], after: list[list[str]]) -> int | None:
    for index in range(min(len(before), len(after))):
        if before[index] != after[index]:
            return index
    return min(len(before), len(after)) if len(before) != len(after) else None


def compile_quest_regression_matrix(
    baseline: object, candidate: object, *, authorized: bool,
    expected_baseline_digest: str, expected_candidate_digest: str,
    max_states: int, max_depth: int,
) -> dict[str, Any]:
    """Recompile both source revisions, then compare bounded ending witnesses."""
    if authorized is not True:
        raise PermissionError("quest regression comparison requires authorization")
    if type(max_states) is not int or not 1 <= max_states <= 2048:
        raise StudioQuestError("invalid regression state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= 64:
        raise StudioQuestError("invalid regression depth budget")
    old = _checked(baseline, expected_baseline_digest, "baseline compilation")
    new = _checked(candidate, expected_candidate_digest, "candidate compilation")
    if old["project_id"] != new["project_id"]:
        raise StudioQuestError("cross-project quest regression comparison forbidden")
    if len(_canonical(old)) + len(_canonical(new)) > MAX_BYTES // 2:
        raise StudioQuestError("quest regression sources exceed budget")
    old_ids = {e["id"] for e in old["plan"]["endings"]}
    new_ids = {e["id"] for e in new["plan"]["endings"]}
    names = sorted(old_ids | new_ids)
    if len(names) > MAX_ENDINGS:
        raise StudioQuestError("too many ending identities for regression comparison")
    rows: list[dict[str, Any]] = []
    for name in names:
        prior = _witness(old, name, max_states, max_depth) if name in old_ids else None
        next_ = _witness(new, name, max_states, max_depth) if name in new_ids else None
        before_status = prior["status"] if prior is not None else "absent"
        after_status = next_["status"] if next_ is not None else "absent"
        before_actions = prior["witness_actions"] if prior is not None else []
        after_actions = next_["witness_actions"] if next_ is not None else []
        # Never classify an exhausted budget as a proven loss of reachability.
        uncertainty = "inconclusive" in (before_status, after_status)
        lost = before_status == "found" and after_status in ("unreachable", "absent")
        gained = after_status == "found" and before_status in ("unreachable", "absent")
        changed_route = (
            before_status == after_status == "found"
            and before_actions != after_actions
        )
        changed_source = old["quest_source_digest"] != new["quest_source_digest"]
        rows.append({
            "ending_id": name,
            "baseline_status": before_status,
            "candidate_status": after_status,
            "baseline_witness": prior,
            "candidate_witness": next_,
            "baseline_actions": before_actions,
            "candidate_actions": after_actions,
            "first_divergence_index": (
                _first_divergence(before_actions, after_actions)
                if before_status == after_status == "found" else None
            ),
            "regression_proven": lost,
            "newly_reachable": gained,
            "route_changed": changed_route,
            "search_inconclusive": uncertainty,
            "requires_review": (
                changed_source or before_status != after_status or changed_route
            ),
        })
    source_changed = old["quest_source_digest"] != new["quest_source_digest"]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": old["project_id"],
        "baseline_compilation": old,
        "candidate_compilation": new,
        "baseline_compilation_digest": expected_baseline_digest,
        "candidate_compilation_digest": expected_candidate_digest,
        "baseline_source_digest": old["quest_source_digest"],
        "candidate_source_digest": new["quest_source_digest"],
        "max_states": max_states, "max_depth": max_depth,
        "rows": rows, "ending_count": len(rows),
        "proven_regressions": sorted(r["ending_id"] for r in rows if r["regression_proven"]),
        "uncertain_endings": sorted(r["ending_id"] for r in rows if r["search_inconclusive"]),
        "review_required": source_changed or any(r["requires_review"] for r in rows),
        "sandbox_replay_verified": True,
        "native_gameplay_verified": False,
        "external_evidence_verified": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_BYTES - 128:
        raise StudioQuestError("quest regression matrix exceeds byte budget")
    payload["receipt_digest"] = _digest(payload)
    return payload


def replay_quest_regression_matrix(
    receipt: object, *, authorized: bool,
    expected_baseline_digest: str, expected_candidate_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest regression replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid quest regression matrix")
    checked = compile_quest_regression_matrix(
        receipt.get("baseline_compilation"), receipt.get("candidate_compilation"),
        authorized=True, expected_baseline_digest=expected_baseline_digest,
        expected_candidate_digest=expected_candidate_digest,
        max_states=receipt.get("max_states"), max_depth=receipt.get("max_depth"),
    )
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("quest regression matrix failed canonical replay")
    return checked


def render_quest_regression_html(
    receipt: object, *, authorized: bool,
    expected_baseline_digest: str, expected_candidate_digest: str,
) -> bytes:
    checked = replay_quest_regression_matrix(
        receipt, authorized=authorized,
        expected_baseline_digest=expected_baseline_digest,
        expected_candidate_digest=expected_candidate_digest,
    )
    rows = "".join(
        "<tr><th scope='row'>" + escape(r["ending_id"], quote=True)
        + "</th><td>" + escape(r["baseline_status"])
        + "</td><td>" + escape(r["candidate_status"])
        + "</td><td>" + ("REVIEW" if r["requires_review"] else "unchanged")
        + "</td></tr>" for r in checked["rows"]
    )
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "script-src 'none'; style-src 'none'; base-uri 'none'; form-action 'none'\">"
        "<title>Original quest ending regression</title></head><body><main>"
        "<h1>Sandbox ending regression review</h1><p>Bounded searches can be "
        "inconclusive. No native gameplay, rights or release qualification.</p>"
        "<table><thead><tr><th>Ending</th><th>Before</th><th>After</th>"
        "<th>Review</th></tr></thead><tbody>" + rows + "</tbody></table>"
        "<p>Receipt: " + escape(checked["receipt_digest"]) + "</p>"
        "</main></body></html>"
    ).encode("utf-8")
    if len(html) > 64 * 1024:
        raise StudioQuestError("quest regression HTML exceeds budget")
    return html


def publish_quest_regression_matrix(
    receipt: object, directory: Path, *, authorized: bool,
    expected_baseline_digest: str, expected_candidate_digest: str,
) -> dict[str, Any]:
    checked = replay_quest_regression_matrix(
        receipt, authorized=authorized,
        expected_baseline_digest=expected_baseline_digest,
        expected_candidate_digest=expected_candidate_digest,
    )
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("quest regression publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".quest-regression-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=fd,
        )
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
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
        "path": str(Path(directory) / FILENAME),
        "receipt_digest": checked["receipt_digest"],
        "bytes": len(raw), "file_write_performed": True,
        "release_certified": False,
    }


def restore_quest_regression_matrix(
    directory: Path, *, authorized: bool,
    expected_baseline_digest: str, expected_candidate_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest regression restore requires authorization")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_BYTES
                    or (os.name == "posix" and (
                        before.st_uid != os.getuid()
                        or before.st_mode & 0o077 or before.st_nlink != 1))):
                raise StudioQuestError("quest regression receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                        after.st_ino) !=
                       (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                        before.st_ino)):
                raise StudioQuestError("quest regression receipt changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise StudioQuestError("duplicate quest regression JSON key")
            output[key] = value
        return output

    try:
        parsed = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite quest regression JSON")),
        )
    except StudioQuestError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid quest regression JSON") from exc
    return replay_quest_regression_matrix(
        parsed, authorized=True,
        expected_baseline_digest=expected_baseline_digest,
        expected_candidate_digest=expected_candidate_digest,
    )
