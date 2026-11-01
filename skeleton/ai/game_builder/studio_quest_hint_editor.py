"""CSP-hashed offline quest hint editor with source/session-leased import."""
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
from .studio_quest_hint_deck import replay_quest_hint_deck

EXPORT_SCHEMA = "skeleton.game_builder.studio_quest_hint_editor.v1"
FILENAME = "quest_hint_editor.html"
MAX_EXPORT_BYTES = 32768


def render_quest_hint_editor(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> tuple[bytes, dict[str, Any]]:
    verified = replay_quest_hint_deck(documents, receipt, authorized=authorized)
    meta = {
        "schema": EXPORT_SCHEMA, "project_id": verified["project_id"],
        "source_digest": verified["source_digest"],
        "session_digest": verified["session_digest"],
        "baseline_hint_deck_digest": verified["hint_deck_digest"],
    }
    script = (
        "const meta=" + json.dumps(meta, sort_keys=True) + ";"
        "const edit=document.getElementById('hints');"
        "document.getElementById('export').addEventListener('click',()=>{"
        "try{const authoring=JSON.parse(edit.value);"
        "if(!authoring||!Array.isArray(authoring.hints)||authoring.hints.length>64)"
        "throw Error('hint budget');"
        "const raw=JSON.stringify({...meta,authoring});"
        "if(new TextEncoder().encode(raw).length>32768)throw Error('byte budget');"
        "const blob=new Blob([raw],{type:'application/json'});"
        "const url=URL.createObjectURL(blob);const a=document.createElement('a');"
        "a.href=url;a.download='quest_hint_edit.json';a.click();"
        "setTimeout(()=>URL.revokeObjectURL(url),1000);"
        "document.getElementById('status').textContent='Exported for source replay';"
        "}catch(e){document.getElementById('status').textContent='Invalid typed hint JSON';}"
        "});"
    )
    hashed = b64encode(sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + hashed +
           "'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"" + csp + "\">"
        "<title>Quest accessibility hint editor</title></head><body><main>"
        "<h1>Original quest accessibility hints</h1>"
        "<p>Only already available or completed stages may be annotated.</p>"
        "<label for='hints'>Typed source-bound hints</label>"
        "<textarea id='hints' rows='20' cols='110'>" +
        escape(json.dumps(verified["authoring"], indent=2, ensure_ascii=True)) +
        "</textarea>"
        "<button id='export' type='button'>Export typed hints</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "</main><script>" + script + "</script></body></html>"
    ).encode("utf-8")
    if len(html) > 65536:
        raise StudioQuestError("quest hint editor exceeds byte budget")
    return html, {
        "html_sha256": sha256(html).hexdigest(),
        "html_bytes": len(html),
        "baseline_hint_deck_digest": verified["hint_deck_digest"],
        "release_certified": False,
    }


def publish_quest_hint_editor(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest hint editor publication requires authorization")
    html, proof = render_quest_hint_editor(documents, receipt, authorized=True)
    fd = _open_directory(directory)
    temporary = ".quest-hint-editor-" + secrets.token_hex(16) + ".tmp"
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


def load_quest_hint_editor_export(
    path: Path, *, authorized: bool, expected_project_id: str,
    expected_source_digest: str, expected_session_digest: str,
    expected_baseline_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest hint import requires authorization")
    if not isinstance(path, Path):
        raise StudioQuestError("quest hint import path required")
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
                raise StudioQuestError("quest hint import must be private")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXPORT_BYTES:
        raise StudioQuestError("invalid quest hint export size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate quest hint JSON key")
            out[key] = value
        return out
    try:
        record = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite quest hint export")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid quest hint export JSON") from exc
    expected = {
        "schema": EXPORT_SCHEMA, "project_id": expected_project_id,
        "source_digest": expected_source_digest,
        "session_digest": expected_session_digest,
        "baseline_hint_deck_digest": expected_baseline_digest,
    }
    if (type(record) is not dict or set(record) != set(expected) | {"authoring"}
            or any(record[key] != value for key, value in expected.items())
            or type(record["authoring"]) is not dict
            or len(_canonical(record["authoring"])) > MAX_EXPORT_BYTES):
        raise StudioQuestError("stale or invalid quest hint editor export")
    return record["authoring"]
