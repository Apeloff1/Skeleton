"""Source-bound clue visibility and consequence-safe quest handoff.

Clues are editorial annotations; no evidence, native gameplay or model output is
claimed. Every result is recomputed from the immutable authored quest source.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping
from zipfile import ZipFile, ZipInfo, ZIP_STORED

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import StudioQuestError, compile_quest_program, replay_quest
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease, _open_directory, _write_all
from .studio_ecosystem_story_html import render_story_html, story_source

SCHEMA = "skeleton.game_builder.studio_clue_visibility.v1"
FILENAME = "clue_visibility.json"
MAX_RECEIPT = 128 * 1024
MAX_CLUES = 64


def _text(value: object, label: str, limit: int = 240) -> str:
    if (type(value) is not str or not 1 <= len(value) <= limit
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise StudioQuestError("invalid " + label)
    return value


def _context(documents: Mapping[str, Any], actions: list[list[str]], *,
             expected_source_digest: str, expected_session_digest: str | None):
    _lease(expected_source_digest, "clue source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "clue session")
    if type(actions) is not list or len(actions) > 64 or len(_canonical(actions)) > 16384:
        raise StudioQuestError("invalid bounded clue replay")
    canon = audit_canon_source(documents, authorized=True)
    if not canon["canon_consistent"] or canon["source_digest"] != expected_source_digest:
        raise StudioQuestError("clue source not canon-consistent or lease stale")
    session = replay_quest(documents, actions, authorized=True)
    if expected_session_digest is not None and session.digest != expected_session_digest:
        raise StudioQuestError("stale clue session")
    story = story_source(documents)
    program = compile_quest_program(documents)
    if (story["project_id"] != session.project_id
            or program.source_digest != session.source_digest
            or story["source_digest"] != program.source_digest):
        raise StudioQuestError("clue story/quest replay mismatch")
    return canon, session, story, program


def compile_clue_visibility(documents: Mapping[str, Any], actions: list[list[str]],
                            authoring: object, *, authorized: bool,
                            expected_source_digest: str,
                            expected_session_digest: str | None = None) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("clue visibility requires operator authorization")
    canon, session, story, program = _context(
        documents, actions, expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    if type(authoring) is not dict or set(authoring) != {"clues"}:
        raise StudioQuestError("clue authoring requires exact typed fields")
    clues = authoring["clues"]
    if type(clues) is not list or not 1 <= len(clues) <= min(MAX_CLUES, len(story["stages"])):
        raise StudioQuestError("invalid bounded clue count")
    stages = {stage["id"]: (i, stage) for i, stage in enumerate(story["stages"])}
    scenes = {stage["scene_id"]: stage["id"] for stage in story["stages"]}
    completed = set(session.completed)
    seen: set[str] = set()
    rows: list[dict[str, object]] = []
    for clue in clues:
        if type(clue) is not dict or set(clue) != {
                "id", "scene_id", "visible_after_stage", "spoils_stage", "text"}:
            raise StudioQuestError("invalid typed clue record")
        ident = _text(clue["id"], "clue ID", 80)
        scene_id = _text(clue["scene_id"], "clue scene ID", 256)
        reveal = _text(clue["visible_after_stage"], "clue reveal stage", 256)
        spoiler = clue["spoils_stage"]
        if spoiler is not None:
            spoiler = _text(spoiler, "clue spoiler stage", 256)
        caption = _text(clue["text"], "clue text")
        if ident in seen or scene_id not in scenes or reveal not in stages:
            raise StudioQuestError("duplicate or unknown clue binding")
        if scenes[scene_id] != reveal:
            raise StudioQuestError("clue must reveal at its authored scene stage")
        if spoiler is not None and (spoiler not in stages
                                   or stages[spoiler][0] > stages[reveal][0]):
            raise StudioQuestError("clue would reveal future spoiler prematurely")
        seen.add(ident)
        visible = reveal in completed
        row: dict[str, object] = {
            "id": ident, "scene_id": scene_id, "visible_after_stage": reveal,
            "spoils_stage": spoiler, "visible": visible,
            "text": caption if visible else None,
            "text_sha256": sha256(caption.encode("utf-8")).hexdigest(),
            "source_stage_index": stages[reveal][0],
        }
        rows.append(row)
    rows.sort(key=lambda row: (row["source_stage_index"], row["id"]))
    result: dict[str, object] = {
        "schema": SCHEMA, "project_id": story["project_id"],
        "source_digest": canon["source_digest"],
        "quest_source_digest": program.source_digest,
        "session_digest": session.digest,
        "actions": [list(action) for action in session.choices],
        "authoring": authoring, "clues": rows,
        "visible_count": sum(row["visible"] for row in rows),
        "hidden_count": sum(not row["visible"] for row in rows),
        "source_replay_verified": True, "spoiler_guard_verified": True,
        "model_inference_performed": False, "file_write_performed": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT - 128:
        raise StudioQuestError("clue visibility receipt exceeds byte budget")
    result["clue_digest"] = _digest(result)
    return result


def propose_clue_visibility(documents: Mapping[str, Any], actions: list[list[str]],
                            prompt: str, *, authorized: bool,
                            expected_source_digest: str,
                            expected_session_digest: str | None = None) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("clue proposal requires operator authorization")
    if _text(prompt, "clue prompt", 512).casefold() != "build a source-bound clue trail":
        raise StudioQuestError("unsupported clue prompt; no provider inference claimed")
    _, session, story, _ = _context(
        documents, actions, expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    clues = [{
        "id": "clue_%03d" % (i + 1), "scene_id": stage["scene_id"],
        "visible_after_stage": stage["id"], "spoils_stage": None,
        "text": _text(stage["authored_goal"][:240].strip(), "source-authored clue text"),
    } for i, stage in enumerate(story["stages"])]
    authoring = {"clues": clues}
    report = compile_clue_visibility(
        documents, actions, authoring, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=session.digest)
    result = {"schema": "skeleton.game_builder.studio_clue_prompt.v1",
              "prompt": prompt, "authoring": authoring, "detail": report,
              "model_inference_performed": False, "release_certified": False}
    result["proposal_digest"] = _digest(result)
    return result


def _replay(documents: Mapping[str, Any], report: Mapping[str, Any],
            *, authorized: bool) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("clue replay requires authorization")
    if type(report) is not dict or report.get("schema") != SCHEMA:
        raise StudioQuestError("invalid clue receipt")
    result = compile_clue_visibility(
        documents, report.get("actions"), report.get("authoring"),
        authorized=True, expected_source_digest=report.get("source_digest"),
        expected_session_digest=report.get("session_digest"))
    if result != report:
        raise StudioQuestError("clue receipt fails canonical source replay")
    return result


def compile_clue_playable(documents: Mapping[str, Any], report: Mapping[str, Any],
                          *, authorized: bool) -> tuple[dict[str, object], bytes]:
    """Handoff a playable canonical HTML quest plus separately typed clue data.

    The canonical HTML remains the actual playable; clue ingestion by native
    engines is NOT asserted. Hidden clue text is omitted from the public data.
    """
    replay = _replay(documents, report, authorized=authorized)
    html = render_story_html(documents)
    if len(html) > 512 * 1024:
        raise StudioQuestError("playable HTML exceeds clue bundle budget")
    public = {"schema": "skeleton.game_builder.studio_clue_handoff.v1",
              "project_id": replay["project_id"],
              "source_digest": replay["source_digest"],
              "session_digest": replay["session_digest"],
              "clue_digest": replay["clue_digest"],
              "visible_clues": [row for row in replay["clues"] if row["visible"]],
              "hidden_count": replay["hidden_count"],
              "native_clue_ui_integrated": False, "release_certified": False}
    files = {"index.html": html, "clues.json": _canonical(public) + b"\n"}
    out = BytesIO()
    with ZipFile(out, "w", compression=ZIP_STORED) as archive:
        for name in sorted(files):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, files[name])
    payload = out.getvalue()
    manifest: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_clue_playable.v1",
        "project_id": replay["project_id"], "clue_digest": replay["clue_digest"],
        "files": {name: sha256(content).hexdigest() for name, content in sorted(files.items())},
        "bundle_sha256": sha256(payload).hexdigest(), "bundle_bytes": len(payload),
        "canonical_html5_quest_included": True, "native_clue_ui_integrated": False,
        "release_certified": False}
    return manifest, payload


def publish_clue_visibility(documents: Mapping[str, Any], report: Mapping[str, Any],
                            directory: Path, *, authorized: bool) -> dict[str, object]:
    replay = _replay(documents, report, authorized=authorized)
    raw = _canonical(replay) + b"\n"
    if len(raw) > MAX_RECEIPT:
        raise StudioQuestError("clue publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".clue-" + secrets.token_hex(16) + ".tmp"
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
            "clue_digest": replay["clue_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_clue_visibility(documents: Mapping[str, Any], directory: Path, *,
                            authorized: bool, expected_source_digest: str,
                            expected_session_digest: str | None = None) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("clue restore requires authorization")
    _lease(expected_source_digest, "clue restore source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "clue restore session")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_RECEIPT
                    or os.name == "posix" and
                    (info.st_uid != os.getuid() or info.st_mode & 0o077
                     or info.st_nlink != 1)):
                raise StudioQuestError("clue restore requires private regular file")
            raw = os.read(handle, MAX_RECEIPT + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate clue JSON key")
            result[key] = value
        return result
    try:
        stored = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite clue JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid clue JSON") from exc
    if (type(stored) is not dict
            or stored.get("source_digest") != expected_source_digest
            or expected_session_digest is not None
            and stored.get("session_digest") != expected_session_digest):
        raise StudioQuestError("clue restore source/session mismatch")
    return _replay(documents, stored, authorized=True)
