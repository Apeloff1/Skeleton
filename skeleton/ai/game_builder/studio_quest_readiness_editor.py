"""CSP-hashed offline readiness-budget editor and source-leased JSON import.

The browser cannot authorize source edits or claim playable safety. It exports
a typed budget request that must be imported by the canonical quest compiler
under an out-of-band operator lease before any playable handoff.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError, compile_quest_program
from .studio_ecosystem_scene_schedule import _canonical, _lease, _open_directory
from .studio_quest_readiness import (
    compile_quest_readiness, replay_quest_readiness,
)

EXPORT_SCHEMA = "skeleton.game_builder.studio_quest_readiness_editor_export.v1"
MAX_EXPORT_BYTES = 32768
MAX_HTML_BYTES = 256 * 1024


def render_quest_readiness_editor(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> tuple[bytes, dict[str, Any]]:
    """Render an accessible offline budget editor bound to current source."""
    checked = replay_quest_readiness(documents, receipt, authorized=authorized)
    stage_count = len(compile_quest_program(documents).stages)
    meta = {
        "schema": EXPORT_SCHEMA,
        "project_id": checked["project_id"],
        "expected_source_digest": checked["source_digest"],
        "expected_initial_session_digest": checked["initial_session_digest"],
    }
    # JSON inside an inline script must not contain a literal '<' or '</script'.
    meta_js = (json.dumps(meta, sort_keys=True, ensure_ascii=True)
               .replace("<", "\\u003c").replace(">", "\\u003e")
               .replace("&", "\\u0026"))
    script = (
        "const meta=" + meta_js + ";"
        "const states=document.getElementById('states');"
        "const depth=document.getElementById('depth');"
        "const status=document.getElementById('status');"
        "document.getElementById('export').addEventListener('click',()=>{"
        "try{const s=Number(states.value),d=Number(depth.value);"
        "if(!Number.isInteger(s)||s<1||s>2048||"
        "!Number.isInteger(d)||d<1||d>" + str(stage_count) + ")"
        "throw Error('invalid bounded budget');"
        "const raw=JSON.stringify({...meta,authoring:{max_states:s,max_depth:d}});"
        "if(new TextEncoder().encode(raw).length>32768)"
        "throw Error('oversized export');"
        "const blob=new Blob([raw],{type:'application/json'});"
        "const url=URL.createObjectURL(blob);"
        "const a=document.createElement('a');"
        "a.href=url;a.download='quest_readiness_budget.json';a.click();"
        "setTimeout(()=>URL.revokeObjectURL(url),1000);"
        "status.textContent='Exported typed budget; import requires operator lease';"
        "}catch(e){status.textContent='Invalid budget; nothing exported';}"
        "});"
    )
    digest = b64encode(sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = (
        "default-src 'none'; script-src 'sha256-" + digest +
        "'; connect-src 'none'; base-uri 'none'; form-action 'none'; "
        "object-src 'none'; frame-ancestors 'none'"
    )
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\""
        + csp + "\"><title>Quest readiness editor</title></head><body><main>"
        "<h1>Source-bound quest readiness editor</h1>"
        "<p>Project: " + escape(checked["project_id"], quote=True) + "</p>"
        "<p>Current proof: " + escape(checked["status"], quote=True) + "</p>"
        "<p>This edits only exploration budgets. It cannot grant authorization, "
        "change canon or certify native gameplay. Reimport to recompile.</p>"
        "<label for='states'>Maximum explored states</label>"
        "<input id='states' type='number' min='1' max='2048' value='"
        + str(checked["authoring"]["max_states"]) + "'>"
        "<label for='depth'>Maximum quest depth</label>"
        "<input id='depth' type='number' min='1' max='"
        + str(stage_count) + "' value='"
        + str(checked["authoring"]["max_depth"]) + "'>"
        "<button type='button' id='export'>Export typed budget</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "</main><script>" + script + "</script></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("readiness editor exceeds HTML byte budget")
    return html, {
        "schema": "skeleton.game_builder.studio_quest_readiness_editor.v1",
        "project_id": checked["project_id"],
        "readiness_digest": checked["readiness_digest"],
        "html_sha256": sha256(html).hexdigest(),
        "html_bytes": len(html),
        "authoring_export_only": True,
        "file_write_performed": False,
        "release_certified": False,
    }


def import_quest_readiness_editor_export(
    documents: Mapping[str, Any], path: Path, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    """Import only private regular JSON, then recompile BOTH proof owners."""
    if authorized is not True:
        raise PermissionError("readiness editor import requires authorization")
    _lease(expected_source_digest, "readiness editor source")
    _lease(expected_initial_session_digest, "readiness editor session")
    if (not isinstance(path, Path) or path.name in ("", ".", "..")
            or len(str(path).encode("utf-8", "strict")) > 4096):
        raise StudioQuestError("invalid readiness editor export path")
    fd = _open_directory(path.parent)
    try:
        handle = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_EXPORT_BYTES
                    or (os.name == "posix" and
                        (before.st_uid != os.getuid() or before.st_mode & 0o077
                         or before.st_nlink != 1))):
                raise StudioQuestError("readiness editor export must be private")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                        after.st_ino) !=
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                     before.st_ino)):
                raise StudioQuestError("readiness editor export changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate readiness editor JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite readiness editor JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid readiness editor JSON") from exc
    if (type(value) is not dict
            or set(value) != {"schema", "project_id", "expected_source_digest",
                              "expected_initial_session_digest", "authoring"}
            or value["schema"] != EXPORT_SCHEMA
            or value["project_id"] != compile_quest_program(documents).project_id
            or value["expected_source_digest"] != expected_source_digest
            or value["expected_initial_session_digest"] !=
            expected_initial_session_digest):
        raise StudioQuestError("stale or forged readiness editor export")
    return compile_quest_readiness(
        documents, value["authoring"], authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest,
    )
