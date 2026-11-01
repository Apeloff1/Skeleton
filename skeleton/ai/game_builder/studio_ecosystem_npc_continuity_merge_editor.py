"""Offline CSP-hashed merge-decision editor and descriptor-anchored import."""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical, _open_directory, _write_all
from .studio_ecosystem_npc_continuity_merge import replay_npc_continuity_merge

EXPORT_SCHEMA = "skeleton.game_builder.studio_npc_continuity_merge_editor.v1"
FILENAME = "npc_continuity_merge_editor.html"
MAX_EXPORT_BYTES = 32768


def _meta(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": EXPORT_SCHEMA, "project_id": receipt["project_id"],
        "source_digest": receipt["source_digest"],
        "session_digest": receipt["session_digest"],
        "baseline_digest": receipt["baseline_digest"],
        "candidate_digest": receipt["candidate_digest"],
        "baseline_merge_digest": receipt["merge_digest"],
    }


def render_npc_continuity_merge_editor(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> tuple[bytes, dict[str, Any]]:
    verified = replay_npc_continuity_merge(documents, receipt, authorized=authorized)
    meta = _meta(verified)
    decisions = json.dumps(verified["authoring"], indent=2, ensure_ascii=True)
    script = (
        "const meta=" + json.dumps(meta, sort_keys=True) + ";"
        "const edit=document.getElementById('decisions');"
        "document.getElementById('export').addEventListener('click',()=>{"
        "try{const authoring=JSON.parse(edit.value);"
        "if(!authoring||!Array.isArray(authoring.decisions)||"
        "authoring.decisions.length>64)throw Error('decision budget');"
        "const raw=JSON.stringify({...meta,authoring});"
        "if(new TextEncoder().encode(raw).length>32768)throw Error('byte budget');"
        "const blob=new Blob([raw],{type:'application/json'});"
        "const url=URL.createObjectURL(blob);const a=document.createElement('a');"
        "a.href=url;a.download='npc_continuity_merge_edit.json';a.click();"
        "setTimeout(()=>URL.revokeObjectURL(url),1000);"
        "document.getElementById('status').textContent='Exported for source replay';"
        "}catch(e){document.getElementById('status').textContent='Invalid typed decision JSON';}"
        "});"
    )
    hashed = b64encode(sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + hashed +
           "'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
    rows = "".join(
        "<li><strong>" + escape(row["event_key"], quote=True) +
        "</strong> — " + escape(row["decision"] or "unresolved", quote=True) +
        "</li>" for row in verified["conflicts"])
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"" + csp + "\">"
        "<title>NPC continuity merge editor</title></head><body><main>"
        "<h1>Reconcile original NPC annotations</h1>"
        "<p>Choose baseline, candidate or drop for each conflict. "
        "Only canonical source replay can accept these decisions.</p>"
        "<label for='decisions'>Typed conflict decisions</label>"
        "<textarea id='decisions' rows='18' cols='100'>" +
        escape(decisions) + "</textarea>"
        "<button id='export' type='button'>Export merge decisions</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "<h2>Conflict anchors</h2><ol>" + rows + "</ol>"
        "</main><script>" + script + "</script></body></html>"
    ).encode("utf-8")
    if len(html) > 65536:
        raise StudioQuestError("continuity merge editor exceeds byte budget")
    return html, {
        "html_sha256": sha256(html).hexdigest(),
        "html_bytes": len(html), "merge_digest": verified["merge_digest"],
        "release_certified": False,
    }


def publish_npc_continuity_merge_editor(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("continuity merge editor requires authorization")
    html, proof = render_npc_continuity_merge_editor(
        documents, receipt, authorized=True)
    fd = _open_directory(directory)
    temporary = ".npc-continuity-merge-editor-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, html)
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
    return {**proof, "path": str(Path(directory) / FILENAME),
            "file_write_performed": True}


def load_npc_continuity_merge_editor_export(
    path: Path, *, authorized: bool,
    expected_project_id: str, expected_source_digest: str,
    expected_session_digest: str, expected_baseline_digest: str,
    expected_candidate_digest: str, expected_merge_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("continuity merge import requires authorization")
    if not isinstance(path, Path):
        raise StudioQuestError("continuity merge import path required")
    fd = _open_directory(path.parent)
    try:
        handle = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode)
                    or not 0 < info.st_size <= MAX_EXPORT_BYTES
                    or (os.name == "posix"
                        and (info.st_uid != os.getuid() or info.st_mode & 0o077
                             or info.st_nlink != 1))):
                raise StudioQuestError("continuity merge editor import must be private")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXPORT_BYTES:
        raise StudioQuestError("invalid continuity merge editor export size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate continuity merge editor JSON key")
            out[key] = value
        return out
    try:
        record = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite continuity merge editor JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid continuity merge editor JSON") from exc
    expected = {
        "schema": EXPORT_SCHEMA, "project_id": expected_project_id,
        "source_digest": expected_source_digest,
        "session_digest": expected_session_digest,
        "baseline_digest": expected_baseline_digest,
        "candidate_digest": expected_candidate_digest,
        "baseline_merge_digest": expected_merge_digest,
    }
    if (type(record) is not dict or set(record) != set(expected) | {"authoring"}
            or any(record[key] != value for key, value in expected.items())
            or type(record["authoring"]) is not dict
            or len(_canonical(record["authoring"])) > MAX_EXPORT_BYTES):
        raise StudioQuestError("stale or invalid continuity merge editor export")
    return record["authoring"]
