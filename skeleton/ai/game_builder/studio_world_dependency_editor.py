"""CSP-hashed offline dependency graph editor with source-leased strict import."""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _open_directory, _write_all,
)
from skeleton.ai.game_builder.studio_world_dependency import (
    SCHEMA, MAX_GRAPH_BYTES, replay_dependency_world_batch,
)

EXPORT_SCHEMA = "skeleton.jeeves.studio_world_dependency_editor.v1"
FILENAME = "studio_world_dependency_editor.html"
MAX_EXPORT_BYTES = 48 * 1024


def render_dependency_editor(proof: object, *, authorized: bool) -> tuple[bytes, dict[str, Any]]:
    verified = replay_dependency_world_batch(proof, authorized=authorized)
    meta = {
        "schema": EXPORT_SCHEMA,
        "catalog_digest": verified["catalog_digest"],
        "baseline_proof_digest": verified["proof_digest"],
        "baseline_graph_digest": verified["graph_digest"],
    }
    script = (
        "const meta=" + json.dumps(meta, sort_keys=True) + ";"
        "const edit=document.getElementById('graph');"
        "document.getElementById('export').addEventListener('click',()=>{"
        "try{const graph=JSON.parse(edit.value);"
        "if(!graph||typeof graph!=='object'||Array.isArray(graph)"
        "||!Array.isArray(graph.steps)||graph.steps.length<1||graph.steps.length>8)"
        "throw Error('step budget');"
        "const raw=JSON.stringify({...meta,graph});"
        "if(new TextEncoder().encode(raw).length>49152)throw Error('byte budget');"
        "const blob=new Blob([raw],{type:'application/json'});"
        "const url=URL.createObjectURL(blob);const a=document.createElement('a');"
        "a.href=url;a.download='studio_world_dependency_edit.json';a.click();"
        "setTimeout(()=>URL.revokeObjectURL(url),1000);"
        "document.getElementById('status').textContent='Exported; canonical replay required';"
        "}catch(e){document.getElementById('status').textContent='Invalid dependency JSON';}"
        "});"
    )
    hashed = b64encode(sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + hashed +
           "'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
    sources = "".join(
        "<li>" + escape(source["project_id"], quote=True) +
        " — SHA-256 " + escape(source["source_digest"], quote=True) + "</li>"
        for source in verified["source_projects"]
    )
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"" + csp + "\">"
        "<title>Original world dependency editor</title></head><body><main>"
        "<h1>Typed original world dependency editor</h1>"
        "<p>Modify step requests and dependency edges. Export is not execution, "
        "authorization or native gameplay proof. CLI recompilation rechecks "
        "every canonical source and catalog lease.</p>"
        "<h2>Canonical source custody</h2><ul>" + sources + "</ul>"
        "<label for='graph'>Dependency graph JSON</label>"
        "<textarea id='graph' rows='28' cols='110'>" +
        escape(json.dumps(verified["graph"], indent=2, ensure_ascii=True)) +
        "</textarea><button id='export' type='button'>Export graph</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "</main><script>" + script + "</script></body></html>"
    ).encode("utf-8")
    if len(html) > 128 * 1024:
        raise StudioQuestError("world dependency editor exceeds budget")
    return html, {
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "baseline_proof_digest": verified["proof_digest"],
        "baseline_graph_digest": verified["graph_digest"],
        "release_certified": False,
    }


def publish_dependency_editor(
    proof: object, directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("dependency editor publication requires authorization")
    html, attestation = render_dependency_editor(proof, authorized=True)
    fd = _open_directory(directory)
    temp = ".world-dependency-editor-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
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
    return {
        **attestation, "path": str(Path(directory) / FILENAME),
        "file_write_performed": True,
    }


def load_dependency_editor_export(
    path: Path, *, authorized: bool, expected_catalog_digest: str,
    baseline_proof: object,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("dependency editor import requires authorization")
    baseline = replay_dependency_world_batch(baseline_proof, authorized=True)
    if baseline["catalog_digest"] != expected_catalog_digest:
        raise StudioQuestError("stale dependency editor catalog lease")
    if type(path) is not Path:
        # pathlib subclasses are accepted (PosixPath/WindowsPath), but never
        # accept an untrusted string as a path without explicit CLI parsing.
        if not isinstance(path, Path):
            raise StudioQuestError("dependency editor import path required")
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
                raise StudioQuestError("dependency editor import must be private")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXPORT_BYTES:
        raise StudioQuestError("invalid dependency editor import size")
    def unique(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise StudioQuestError("duplicate dependency editor JSON key")
            output[key] = value
        return output
    try:
        record = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite dependency editor JSON")),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid dependency editor JSON") from exc
    expected = {
        "schema": EXPORT_SCHEMA,
        "catalog_digest": baseline["catalog_digest"],
        "baseline_proof_digest": baseline["proof_digest"],
        "baseline_graph_digest": baseline["graph_digest"],
    }
    if (type(record) is not dict or set(record) != set(expected) | {"graph"}
            or any(record[key] != value for key, value in expected.items())
            or type(record["graph"]) is not dict
            or len(_canonical(record["graph"])) > MAX_GRAPH_BYTES):
        raise StudioQuestError("stale or invalid dependency editor export")
    if record["graph"].get("schema") != SCHEMA:
        raise StudioQuestError("invalid dependency editor graph schema")
    return record["graph"]
