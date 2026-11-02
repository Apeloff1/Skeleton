"""Offline CSP-hashed counterfactual quest editor and source-leased import."""
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
from .studio_ecosystem_scene_schedule import _lease, _open_directory
from .studio_quest_consequence_diff import (
    compile_quest_consequence_diff, replay_quest_consequence_diff,
)

EXPORT_SCHEMA = "skeleton.game_builder.studio_quest_consequence_editor_export.v1"
MAX_EXPORT_BYTES = 32768
MAX_HTML_BYTES = 128 * 1024


def render_quest_consequence_editor(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> tuple[bytes, dict[str, Any]]:
    checked = replay_quest_consequence_diff(documents, receipt, authorized=authorized)
    meta = {
        "schema": EXPORT_SCHEMA, "project_id": checked["project_id"],
        "expected_source_digest": checked["source_digest"],
        "expected_initial_session_digest": checked["initial_session_digest"],
    }
    safe_meta = (json.dumps(meta, sort_keys=True, ensure_ascii=True)
                 .replace("<", "\\u003c").replace(">", "\\u003e")
                 .replace("&", "\\u0026"))
    script = (
        "const meta=" + safe_meta + ";"
        "const left=document.getElementById('baseline');"
        "const right=document.getElementById('candidate');"
        "const status=document.getElementById('status');"
        "document.getElementById('export').addEventListener('click',()=>{"
        "try{const a=JSON.parse(left.value),b=JSON.parse(right.value);"
        "const valid=x=>Array.isArray(x)&&x.length<=64&&x.every(p=>"
        "Array.isArray(p)&&p.length===2&&p.every(v=>"
        "typeof v==='string'&&v.length>=1&&v.length<=256));"
        "if(!valid(a)||!valid(b)||JSON.stringify(a)===JSON.stringify(b))"
        "throw Error('invalid choice histories');"
        "const raw=JSON.stringify({...meta,authoring:{"
        "baseline_actions:a,candidate_actions:b}});"
        "if(new TextEncoder().encode(raw).length>32768)"
        "throw Error('oversized editor export');"
        "const url=URL.createObjectURL(new Blob([raw],"
        "{type:'application/json'}));"
        "const anchor=document.createElement('a');anchor.href=url;"
        "anchor.download='quest_consequence_edit.json';anchor.click();"
        "setTimeout(()=>URL.revokeObjectURL(url),1000);"
        "status.textContent='Exported. Import requires source leases and replay.';"
        "}catch(e){status.textContent='Invalid choice edit; nothing exported';}"
        "});"
    )
    digest = b64encode(sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = (
        "default-src 'none'; script-src 'sha256-" + digest
        + "'; connect-src 'none'; base-uri 'none'; form-action 'none'; "
        "object-src 'none'; frame-ancestors 'none'"
    )
    left = escape(json.dumps(checked["authoring"]["baseline_actions"],
                             ensure_ascii=True), quote=True)
    right = escape(json.dumps(checked["authoring"]["candidate_actions"],
                              ensure_ascii=True), quote=True)
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\""
        + csp + "\"><title>Quest counterfactual editor</title></head><body><main>"
        "<h1>Source-bound quest consequence editor</h1><p>Project: "
        + escape(checked["project_id"], quote=True) + "</p>"
        "<p>Edit only actual authored stage and alternative pairs. "
        "The browser does not authorize or compile changes.</p>"
        "<label for='baseline'>Baseline JSON actions</label>"
        "<textarea id='baseline' rows='8' cols='70'>" + left + "</textarea>"
        "<label for='candidate'>Candidate JSON actions</label>"
        "<textarea id='candidate' rows='8' cols='70'>" + right + "</textarea>"
        "<button type='button' id='export'>Export typed edit</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "</main><script>" + script + "</script></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("quest consequence editor exceeds byte budget")
    return html, {
        "schema": "skeleton.game_builder.studio_quest_consequence_editor.v1",
        "project_id": checked["project_id"],
        "consequence_receipt_digest": checked["receipt_digest"],
        "html_sha256": sha256(html).hexdigest(),
        "html_bytes": len(html), "authoring_export_only": True,
        "file_write_performed": False, "release_certified": False,
    }


def import_quest_consequence_editor_export(
    documents: Mapping[str, Any], path: Path, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest consequence editor import requires authorization")
    _lease(expected_source_digest, "consequence editor source")
    _lease(expected_initial_session_digest, "consequence editor session")
    if (not isinstance(path, Path) or path.name in ("", ".", "..")
            or len(str(path).encode("utf-8", "strict")) > 4096):
        raise StudioQuestError("invalid consequence editor export path")
    fd = _open_directory(path.parent)
    try:
        inp = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                      dir_fd=fd)
        try:
            before = os.fstat(inp)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_EXPORT_BYTES
                    or (os.name == "posix" and
                        (before.st_uid != os.getuid() or before.st_mode & 0o077
                         or before.st_nlink != 1))):
                raise StudioQuestError("consequence editor export must be private")
            raw = os.read(inp, MAX_EXPORT_BYTES + 1)
            after = os.fstat(inp)
            if (len(raw) != before.st_size
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                        after.st_ino) !=
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                     before.st_ino)):
                raise StudioQuestError("consequence editor export changed during read")
        finally:
            os.close(inp)
    finally:
        os.close(fd)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate consequence editor JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite consequence editor JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid consequence editor JSON") from exc
    if (type(value) is not dict
            or set(value) != {"schema", "project_id", "expected_source_digest",
                              "expected_initial_session_digest", "authoring"}
            or value["schema"] != EXPORT_SCHEMA
            or value["project_id"] != compile_quest_program(documents).project_id
            or value["expected_source_digest"] != expected_source_digest
            or value["expected_initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale or forged consequence editor export")
    return compile_quest_consequence_diff(
        documents, value["authoring"], authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest,
    )
