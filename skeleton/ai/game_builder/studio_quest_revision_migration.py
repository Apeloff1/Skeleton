"""Fail-closed migration of authored quest saves across reviewed prose revisions.

No action is silently rewritten: an operator must explicitly lease every
changed selected alternative. The old and revised quest are both replayed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_author_revision import preview_canon_revision
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)

SCHEMA = "skeleton.game_builder.studio_quest_revision_migration.v1"
FILENAME = "studio_quest_revision_migration.json"
MAX_SOURCE_BYTES = 512 * 1024
MAX_PLAN_BYTES = 32768
MAX_RECEIPT_BYTES = 128 * 1024


def _plan(value: object) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != {
            "revision_request", "actions", "remaps", "target_ending"}
            or len(_canonical(value)) > MAX_PLAN_BYTES):
        raise StudioQuestError("invalid bounded quest migration plan")
    revision = value["revision_request"]
    if type(revision) is not dict:
        raise StudioQuestError("migration revision request must be typed")
    actions = value["actions"]
    if type(actions) is not list or len(actions) > 64:
        raise StudioQuestError("invalid bounded migration actions")
    for pair in actions:
        if (type(pair) is not list or len(pair) != 2
                or any(type(x) is not str or not 1 <= len(x) <= 256
                       or x.strip() != x or any(ord(c) < 32 for c in x)
                       for x in pair)):
            raise StudioQuestError("invalid migration action")
    remaps = value["remaps"]
    if type(remaps) is not list or len(remaps) > 64:
        raise StudioQuestError("invalid migration remap count")
    seen: set[str] = set()
    for item in remaps:
        if (type(item) is not dict or set(item) != {
                "stage_id", "from_choice", "to_choice"}
                or any(type(x) is not str or not 1 <= len(x) <= 256
                       or x.strip() != x or any(ord(c) < 32 for c in x)
                       for x in item.values())):
            raise StudioQuestError("invalid explicit migration remap")
        if item["stage_id"] in seen:
            raise StudioQuestError("duplicate migration remap stage")
        seen.add(item["stage_id"])
    target = value["target_ending"]
    if type(target) is not str or not 1 <= len(target) <= 256:
        raise StudioQuestError("invalid migration ending")
    return {"revision_request": revision,
            "actions": [list(x) for x in actions],
            "remaps": [dict(x) for x in remaps],
            "target_ending": target}


def compile_quest_revision_migration(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Recompile a reviewed authored revision and migrate the longest safe prefix."""
    if authorized is not True:
        raise PermissionError("quest migration requires operator authorization")
    _lease(expected_source_digest, "migration old quest source")
    _lease(expected_initial_session_digest, "migration initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE_BYTES:
        raise StudioQuestError("migration source exceeds byte budget")
    old_program = compile_quest_program(documents)
    if old_program.source_digest != expected_source_digest:
        raise StudioQuestError("stale migration quest source lease")
    initial = replay_quest(documents, [], authorized=True)
    if initial.digest != expected_initial_session_digest:
        raise StudioQuestError("stale migration initial session lease")
    plan = _plan(authoring)
    old_session = replay_quest(documents, plan["actions"], authorized=True)
    old_progress = quest_progress(old_session, documents)
    revised, html, revision_receipt = preview_canon_revision(
        documents, plan["revision_request"], authorized=True)
    new_program = compile_quest_program(revised)
    if (new_program.project_id != old_program.project_id
            or old_program.stage_ids != new_program.stage_ids
            or old_program.endings != new_program.endings):
        raise StudioQuestError("revision changed protected quest structure")
    by_old = {stage.key: stage for stage in old_program.stages}
    by_new = {stage.key: stage for stage in new_program.stages}
    for key in old_program.stage_ids:
        original, updated = by_old[key], by_new[key]
        if (original.prerequisites != updated.prerequisites
                or original.reward != updated.reward
                or len(original.alternatives) != len(updated.alternatives)):
            raise StudioQuestError("revision changed protected quest semantics")
    target = plan["target_ending"]
    if target not in dict(old_program.endings):
        raise StudioQuestError("migration target ending is not authored")
    maps = {row["stage_id"]: row for row in plan["remaps"]}
    selected = {stage: choice for stage, choice in plan["actions"]}
    if not set(maps).issubset(selected):
        raise StudioQuestError("migration remap does not target a selected action")
    migrated: list[list[str]] = []
    first_unmigrated: int | None = None
    for index, (stage_id, old_choice) in enumerate(plan["actions"]):
        original, updated = by_old[stage_id], by_new[stage_id]
        position = original.alternatives.index(old_choice)
        new_choice = updated.alternatives[position]
        row = maps.get(stage_id)
        if new_choice != old_choice:
            if row is None:
                first_unmigrated = index
                break
            if (row["from_choice"] != old_choice
                    or row["to_choice"] != new_choice):
                raise StudioQuestError("migration remap differs from revised source")
        elif row is not None:
            raise StudioQuestError("redundant migration remap of unchanged choice")
        migrated.append([stage_id, new_choice])
    if first_unmigrated is not None:
        if any(stage in maps for stage, _ in plan["actions"][first_unmigrated + 1:]):
            raise StudioQuestError("remap after unmigrated prefix is ambiguous")
    new_session = replay_quest(revised, migrated, authorized=True)
    new_progress = quest_progress(new_session, revised)
    old_eligible = target in old_progress["sandbox_endings_eligible"]
    new_eligible = target in new_progress["sandbox_endings_eligible"]
    status = ("requires_explicit_remap" if first_unmigrated is not None else
              "ending_unmet" if not old_eligible or not new_eligible else
              "migrated")
    if _canonical(documents) != before:
        raise StudioQuestError("migration source changed during replay")
    report: dict[str, Any] = {
        "schema": SCHEMA, "project_id": old_program.project_id,
        "old_quest_source_digest": old_program.source_digest,
        "new_quest_source_digest": new_program.source_digest,
        "initial_session_digest": initial.digest,
        "old_session_digest": old_session.digest,
        "new_session_digest": new_session.digest,
        "authoring": plan, "revision_receipt": revision_receipt,
        "revised_html_sha256": revision_receipt["playable_html_sha256"],
        "revised_html_bytes": len(html),
        "status": status, "migrated_actions": migrated,
        "first_unmigrated_index": first_unmigrated,
        "dropped_old_actions": plan["actions"][len(migrated):],
        "old_target_ending_eligible": old_eligible,
        "new_target_ending_eligible": new_eligible,
        "unmet_new_ending_predicates": new_progress[
            "unmet_ending_predicates"].get(target, []),
        "playable_handoff_allowed": status == "migrated",
        "canonical_old_replay_verified": True,
        "canonical_revised_replay_verified": True,
        "native_gameplay_verified": False,
        "external_authorship_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(report)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("migration receipt exceeds byte budget")
    report["migration_digest"] = _digest(report)
    return report


def replay_quest_revision_migration(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("migration replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid migration receipt")
    checked = compile_quest_revision_migration(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("old_quest_source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("migration receipt differs from canonical replay")
    return checked


def compile_quest_migration_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_revision_migration(
        documents, receipt, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("incomplete or ineligible migration blocks handoff")
    revised, html, revision_receipt = preview_canon_revision(
        documents, checked["authoring"]["revision_request"], authorized=True)
    session = replay_quest(revised, checked["migrated_actions"], authorized=True)
    progress = quest_progress(session, revised)
    if (session.digest != checked["new_session_digest"]
            or checked["authoring"]["target_ending"] not in
            progress["sandbox_endings_eligible"]
            or revision_receipt["playable_html_sha256"] !=
            checked["revised_html_sha256"]):
        raise StudioQuestError("migration playable handoff drift")
    result: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_quest_migration_handoff.v1",
        "migration_digest": checked["migration_digest"],
        "revised_quest_source_digest": checked["new_quest_source_digest"],
        "revised_quest_session_digest": session.digest,
        "revised_playable_html_sha256": checked["revised_html_sha256"],
        "revised_playable_html_bytes": len(html),
        "canonical_replay_verified": True,
        "native_gameplay_verified": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_revision_migration(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_revision_migration(
        documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    fd = _open_directory(directory)
    temp = ".quest-migration-" + secrets.token_hex(16) + ".tmp"
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
            "migration_digest": checked["migration_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_quest_revision_migration(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("migration restore requires authorization")
    _lease(expected_source_digest, "migration restore source")
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
                raise StudioQuestError("migration receipt must be private")
            raw = os.read(handle, MAX_RECEIPT_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size
                    or (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                        before.st_ino) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                     after.st_ino)):
                raise StudioQuestError("migration receipt changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate migration JSON key")
            result[key] = value
        return result
    try:
        receipt = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite migration JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid migration receipt JSON") from exc
    if type(receipt) is not dict or receipt.get("old_quest_source_digest") != expected_source_digest:
        raise StudioQuestError("stale migration restore source")
    return replay_quest_revision_migration(documents, receipt, authorized=True)
