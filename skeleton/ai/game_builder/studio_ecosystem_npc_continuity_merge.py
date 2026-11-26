"""Source-replayed, operator-resolved NPC continuity branch reconciliation.

This reconciles *annotations* only. It cannot create source events, earned
knowledge, temporal authority, quest state, or native-game qualification.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease, _open_directory, _write_all
from .studio_ecosystem_npc_continuity_journal import (
    compile_npc_continuity_journal, replay_npc_continuity_journal,
    compile_continuity_playable,
)

SCHEMA = "skeleton.game_builder.studio_npc_continuity_merge.v1"
PROMPT = "reconcile source-bound npc continuity annotations"
FILENAME = "npc_continuity_merge.json"
MAX_RECEIPT_BYTES = 768 * 1024
MAX_DECISIONS = 64
TAKES = frozenset(("baseline", "candidate", "drop"))


def _verified_pair(
    documents: Mapping[str, Any], baseline: object, candidate: object,
    expected_source_digest: str, expected_session_digest: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _lease(expected_source_digest, "continuity merge source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "continuity merge session")
    left = replay_npc_continuity_journal(documents, baseline, authorized=True)
    right = replay_npc_continuity_journal(documents, candidate, authorized=True)
    for field in ("project_id", "source_digest", "session_digest",
                  "exchange_digest", "rendezvous_digest"):
        if left[field] != right[field]:
            raise StudioQuestError("continuity branches have different canonical ancestry")
    if left["source_digest"] != expected_source_digest:
        raise StudioQuestError("stale continuity merge source lease")
    if (expected_session_digest is not None
            and left["session_digest"] != expected_session_digest):
        raise StudioQuestError("stale continuity merge session lease")
    if len(left["events"]) != len(right["events"]):
        raise StudioQuestError("continuity branches have different event counts")
    for a, b in zip(left["events"], right["events"], strict=True):
        for field in ("event_key", "kind", "start_tick", "end_tick",
                      "npc_ids", "site", "source_scene_id",
                      "source_proof_digest", "text"):
            if a[field] != b[field]:
                raise StudioQuestError("continuity branches changed canonical event facts")
    return left, right


def _merge_notes(
    left: dict[str, Any], right: dict[str, Any], decisions: object,
) -> tuple[list[dict[str, str]], list[dict[str, object]], list[str]]:
    if (type(decisions) is not dict or set(decisions) != {"decisions"}
            or type(decisions["decisions"]) is not list
            or len(decisions["decisions"]) > MAX_DECISIONS
            or len(_canonical(decisions)) > 16384):
        raise StudioQuestError("invalid bounded continuity merge decisions")
    conflicting = {
        a["event_key"] for a, b in zip(left["events"], right["events"], strict=True)
        if a["operator_note"] is not None and b["operator_note"] is not None
        and a["operator_note"] != b["operator_note"]
    }
    choices: dict[str, str] = {}
    for item in decisions["decisions"]:
        if (type(item) is not dict or set(item) != {"event_key", "take"}
                or type(item["event_key"]) is not str
                or type(item["take"]) is not str
                or item["event_key"] not in conflicting
                or item["take"] not in TAKES
                or item["event_key"] in choices):
            raise StudioQuestError("invalid or duplicate continuity conflict decision")
        choices[item["event_key"]] = item["take"]
    notes: list[dict[str, str]] = []
    conflicts: list[dict[str, object]] = []
    unresolved: list[str] = []
    for a, b in zip(left["events"], right["events"], strict=True):
        key = a["event_key"]
        lnote, rnote = a["operator_note"], b["operator_note"]
        if key in conflicting:
            selected = choices.get(key)
            conflicts.append({
                "event_key": key, "baseline_note_digest": _digest(lnote),
                "candidate_note_digest": _digest(rnote),
                "decision": selected,
                "resolved": selected is not None,
            })
            if selected is None:
                unresolved.append(key)
                continue
            note = lnote if selected == "baseline" else (
                rnote if selected == "candidate" else None)
        else:
            note = lnote if lnote is not None else rnote
        if note is not None:
            notes.append({"event_key": key, "text": note})
    if len(notes) > MAX_DECISIONS:
        raise StudioQuestError("merged continuity annotation count exceeds budget")
    return notes, conflicts, unresolved


def compile_npc_continuity_merge(
    documents: Mapping[str, Any], baseline: object, candidate: object,
    authoring: object, *, authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC continuity reconciliation requires authorization")
    left, right = _verified_pair(
        documents, baseline, candidate, expected_source_digest,
        expected_session_digest)
    notes, conflicts, unresolved = _merge_notes(left, right, authoring)
    merged = None
    if not unresolved:
        merged = compile_npc_continuity_journal(
            documents, left["exchange_receipt"], {"notes": notes},
            authorized=True, expected_source_digest=expected_source_digest,
            expected_session_digest=left["session_digest"])
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": left["project_id"],
        "source_digest": left["source_digest"],
        "session_digest": left["session_digest"],
        "exchange_digest": left["exchange_digest"],
        "baseline_digest": left["journal_digest"],
        "candidate_digest": right["journal_digest"],
        "baseline_receipt": left, "candidate_receipt": right,
        "authoring": authoring, "conflicts": conflicts,
        "conflict_count": len(conflicts), "unresolved_keys": unresolved,
        "unresolved_count": len(unresolved), "merged_journal": merged,
        "merged_note_count": len(notes) if merged is not None else None,
        "playable_handoff_allowed": bool(merged is not None and
                                        merged["playable_handoff_allowed"]),
        "source_replay_verified": True, "operator_decisions_required": bool(unresolved),
        "file_write_performed": False, "native_scene_timing_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("continuity merge receipt exceeds byte budget")
    result["merge_digest"] = _digest(result)
    return result


def propose_npc_continuity_merge(
    documents: Mapping[str, Any], baseline: object, candidate: object,
    prompt: str, *, authorized: bool, expected_source_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported continuity merge prompt")
    return compile_npc_continuity_merge(
        documents, baseline, candidate, {"decisions": []},
        authorized=authorized, expected_source_digest=expected_source_digest)


def replay_npc_continuity_merge(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC continuity merge replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid continuity merge receipt")
    verified = compile_npc_continuity_merge(
        documents, receipt.get("baseline_receipt"),
        receipt.get("candidate_receipt"), receipt.get("authoring"),
        authorized=True, expected_source_digest=receipt.get("source_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if verified != receipt:
        raise StudioQuestError("continuity merge failed canonical source replay")
    return verified


def render_npc_continuity_merge_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    verified = replay_npc_continuity_merge(
        documents, receipt, authorized=authorized)
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; ",
        "base-uri 'none'; form-action 'none'\">",
        "<title>NPC continuity branch review</title></head><body><main>",
        "<h1>Source-replayed NPC annotation reconciliation</h1>",
        "<p>Only operator notes may change. Canonical events and quest state are immutable.</p>",
        "<p>Unresolved conflicts: " + str(verified["unresolved_count"]) + "</p><ol>",
    ]
    for row in verified["conflicts"]:
        parts.append("<li><strong>" + escape(row["event_key"], quote=True) +
                     "</strong> — " + escape(row["decision"] or "unresolved", quote=True) +
                     "</li>")
    parts.append("</ol></main></body></html>")
    data = "".join(parts).encode("utf-8")
    if len(data) > 128 * 1024:
        raise StudioQuestError("continuity merge HTML exceeds budget")
    return data


def compile_npc_continuity_merge_playable(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_npc_continuity_merge(
        documents, receipt, authorized=authorized)
    if verified["unresolved_count"] or not verified["playable_handoff_allowed"]:
        raise StudioQuestError("unresolved continuity merge blocks playable handoff")
    manifest = compile_continuity_playable(
        documents, verified["merged_journal"], authorized=True)
    html = render_npc_continuity_merge_html(
        documents, verified, authorized=True)
    result = {
        "schema": "skeleton.game_builder.studio_npc_continuity_merge_handoff.v1",
        "merge_digest": verified["merge_digest"],
        "merged_journal_digest": verified["merged_journal"]["journal_digest"],
        "bundle_sha256": manifest["bundle_sha256"],
        "canonical_html5_quest_included": manifest["canonical_html5_quest_included"],
        "companion_html_sha256": sha256(html).hexdigest(),
        "companion_html_bytes": len(html),
        "native_continuity_ui_integrated": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_npc_continuity_merge(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    verified = replay_npc_continuity_merge(
        documents, receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("continuity merge publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".npc-continuity-merge-" + secrets.token_hex(16) + ".tmp"
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
            "merge_digest": verified["merge_digest"], "bytes": len(raw),
            "file_write_performed": True, "release_certified": False}


def restore_npc_continuity_merge(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC continuity merge restore requires authorization")
    _lease(expected_source_digest, "continuity merge restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_RECEIPT_BYTES
                    or (os.name == "posix" and (info.st_uid != os.getuid()
                        or info.st_mode & 0o077 or info.st_nlink != 1))):
                raise StudioQuestError("continuity merge receipt must be private")
            raw = os.read(handle, MAX_RECEIPT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("invalid continuity merge receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate continuity merge JSON key")
            out[key] = value
        return out
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite continuity merge JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid continuity merge JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale continuity merge source lease")
    return replay_npc_continuity_merge(documents, receipt, authorized=True)
