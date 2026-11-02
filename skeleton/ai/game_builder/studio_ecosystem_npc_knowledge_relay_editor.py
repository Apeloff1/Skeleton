"""Accessible offline NPC relay editor with source-leased typed JSON export."""
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
from .studio_ecosystem_npc_knowledge_relay import replay_npc_knowledge_relay

EXPORT_SCHEMA = "skeleton.game_builder.studio_npc_relay_editor_export.v1"
FILENAME = "npc_knowledge_relay_editor.html"
MAX_EXPORT_BYTES = 32768


def _record(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": EXPORT_SCHEMA, "project_id": receipt["project_id"],
        "source_digest": receipt["source_digest"],
        "session_digest": receipt["session_digest"],
        "exchange_digest": receipt["exchange_digest"],
        "baseline_relay_digest": receipt["relay_digest"],
        "authoring": receipt["authoring"],
    }


def render_npc_relay_editor(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> tuple[bytes, dict[str, Any]]:
    verified = replay_npc_knowledge_relay(
        documents, receipt, authorized=authorized)
    record = _record(verified)
    text = json.dumps(record["authoring"], indent=2, ensure_ascii=True)
    script = (
        "const meta=" + json.dumps({k: v for k, v in record.items()
                                   if k != "authoring"}, sort_keys=True) + ";"
        "const edit=document.getElementById('authoring');"
        "document.getElementById('export').addEventListener('click',()=>{"
        "try{const authoring=JSON.parse(edit.value);"
        "if(!authoring||!Array.isArray(authoring.routes)||"
        "authoring.routes.length>32)throw Error('invalid route count');"
        "const raw=JSON.stringify({...meta,authoring});"
        "if(new TextEncoder().encode(raw).length>32768)throw Error('byte budget');"
        "const blob=new Blob([raw],{type:'application/json'});"
        "const url=URL.createObjectURL(blob);const a=document.createElement('a');"
        "a.href=url;a.download='npc_relay_edit.json';a.click();"
        "setTimeout(()=>URL.revokeObjectURL(url),1000);"
        "document.getElementById('status').textContent='Exported for source replay';"
        "}catch(e){document.getElementById('status').textContent='Invalid typed relay JSON';}"
        "});"
    )
    script_hash = b64encode(sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; style-src 'unsafe-inline'; connect-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"" + csp + "\">"
        "<title>NPC knowledge relay editor</title></head><body>"
        "<main><h1>Source-bound NPC knowledge relay</h1>"
        "<p>Each fact requires earned original source and ordered meetings. "
        "No native NPC memory or speech verification is claimed.</p>"
        "<label for='authoring'>Typed relay routes and meetings</label>"
        "<textarea id='authoring' rows='20' cols='100'>" + escape(text) + "</textarea>"
        "<button id='export' type='button'>Export typed NPC relay edits</button>"
        "<p id='status' role='status' aria-live='polite'></p></main>"
        "<script>" + script + "</script></body></html>"
    ).encode("utf-8")
    if len(html) > 65536:
        raise StudioQuestError("NPC relay editor exceeds byte budget")
    return html, {
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "baseline_relay_digest": verified["relay_digest"],
        "release_certified": False,
    }


def publish_npc_relay_editor(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relay editor publication requires authorization")
    html, proof = render_npc_relay_editor(
        documents, receipt, authorized=True)
    fd = _open_directory(directory)
    temp = ".npc-relay-editor-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, html)
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
    return {**proof, "path": str(Path(directory) / FILENAME),
            "file_write_performed": True}


def load_npc_relay_editor_export(
    path: Path, *, authorized: bool,
    expected_project_id: str, expected_source_digest: str,
    expected_session_digest: str, expected_exchange_digest: str,
    expected_baseline_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relay editor import requires authorization")
    if not isinstance(path, Path):
        raise StudioQuestError("NPC relay editor path required")
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
                raise StudioQuestError("NPC relay editor import must be private")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXPORT_BYTES:
        raise StudioQuestError("invalid NPC relay editor export size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate NPC relay editor JSON key")
            out[key] = value
        return out
    try:
        record = json.loads(raw.decode("utf-8", "strict"),
                            object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite NPC relay editor export")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC relay editor JSON") from exc
    expected = {
        "schema": EXPORT_SCHEMA, "project_id": expected_project_id,
        "source_digest": expected_source_digest,
        "session_digest": expected_session_digest,
        "exchange_digest": expected_exchange_digest,
        "baseline_relay_digest": expected_baseline_digest,
    }
    if (type(record) is not dict or set(record) != set(expected) | {"authoring"}
            or any(record[key] != value for key, value in expected.items())
            or type(record["authoring"]) is not dict
            or len(_canonical(record["authoring"])) > MAX_EXPORT_BYTES):
        raise StudioQuestError("stale or invalid NPC relay editor export")
    return record["authoring"]
