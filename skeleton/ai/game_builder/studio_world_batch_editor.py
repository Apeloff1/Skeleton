"""Offline CSP-hashed typed read-only workflow editor and strict import."""
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
from .studio_world_batch import replay_world_batch_plan

EXPORT_SCHEMA = "skeleton.jeeves.studio_world_batch_editor.v1"
FILENAME = "studio_world_batch_editor.html"
MAX_EXPORT_BYTES = 48 * 1024


def render_world_batch_editor(plan: object, *, authorized: bool) -> tuple[bytes, dict[str, Any]]:
    verified = replay_world_batch_plan(plan, authorized=authorized)
    meta = {
        "schema": EXPORT_SCHEMA,
        "catalog_digest": verified["catalog_digest"],
        "baseline_plan_digest": verified["plan_digest"],
    }
    requests = [row["request"] for row in verified["steps"]]
    provenance = verified["provenance"]
    sources = "".join(
        "<li>" + escape(item["project_id"], quote=True) +
        " — canonical source SHA-256 " + escape(item["source_digest"]) +
        "</li>" for item in provenance["projects"]
    )
    script = (
        "const meta=" + json.dumps(meta, sort_keys=True) + ";"
        "const edit=document.getElementById('requests');"
        "document.getElementById('export').addEventListener('click',()=>{"
        "try{const requests=JSON.parse(edit.value);"
        "if(!Array.isArray(requests)||requests.length<1||requests.length>8)"
        "throw Error('step budget');"
        "const raw=JSON.stringify({...meta,requests});"
        "if(new TextEncoder().encode(raw).length>49152)throw Error('byte budget');"
        "const blob=new Blob([raw],{type:'application/json'});"
        "const url=URL.createObjectURL(blob);const a=document.createElement('a');"
        "a.href=url;a.download='studio_world_batch_edit.json';a.click();"
        "setTimeout(()=>URL.revokeObjectURL(url),1000);"
        "document.getElementById('status').textContent='Exported for typed replay';"
        "}catch(e){document.getElementById('status').textContent='Invalid workflow JSON';}"
        "});"
    )
    hashed = b64encode(sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + hashed +
           "'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"" + csp + "\">"
        "<title>Typed world workflow editor</title></head><body><main>"
        "<h1>Read-only original world workflow</h1>"
        "<p>Only reviewed tool names and schema-checked arguments are accepted. "
        "This editor cannot grant authorization or release certification.</p>"
        "<h2>Source custody</h2><p>All edits must replay against these "
        "immutable authored source digests. Stale worlds are rejected.</p>"
        "<ul>" + sources + "</ul>"
        "<label for='requests'>Typed world-tool requests</label>"
        "<textarea id='requests' rows='24' cols='110'>" +
        escape(json.dumps(requests, indent=2, ensure_ascii=True)) + "</textarea>"
        "<button id='export' type='button'>Export typed workflow</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "</main><script>" + script + "</script></body></html>"
    ).encode("utf-8")
    if len(html) > 128 * 1024:
        raise StudioQuestError("world batch editor exceeds byte budget")
    return html, {
        "html_sha256": sha256(html).hexdigest(),
        "html_bytes": len(html), "baseline_plan_digest": verified["plan_digest"],
        "provenance_digest": provenance["manifest_digest"],
        "release_certified": False,
    }


def publish_world_batch_editor(
    plan: object, directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world batch editor publication requires authorization")
    html, proof = render_world_batch_editor(plan, authorized=True)
    fd = _open_directory(directory)
    temporary = ".world-batch-editor-" + secrets.token_hex(16) + ".tmp"
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


def load_world_batch_editor_export(
    path: Path, *, authorized: bool, expected_catalog_digest: str,
    expected_baseline_plan_digest: str,
) -> list[dict[str, Any]]:
    if authorized is not True:
        raise PermissionError("world batch import requires authorization")
    if not isinstance(path, Path):
        raise StudioQuestError("world batch import path required")
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
                raise StudioQuestError("world batch import must be private")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXPORT_BYTES:
        raise StudioQuestError("invalid world batch import size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate world batch import key")
            out[key] = value
        return out
    try:
        record = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite world batch import")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid world batch import JSON") from exc
    expected = {
        "schema": EXPORT_SCHEMA, "catalog_digest": expected_catalog_digest,
        "baseline_plan_digest": expected_baseline_plan_digest,
    }
    if (type(record) is not dict or set(record) != set(expected) | {"requests"}
            or any(record[key] != value for key, value in expected.items())
            or type(record["requests"]) is not list
            or len(_canonical(record["requests"])) > MAX_EXPORT_BYTES):
        raise StudioQuestError("stale or invalid world batch editor export")
    return record["requests"]
