"""Offline CSP-hashed original quest structural editor with source-bound import.

The browser edits a typed JSON batch, never executes it. Import revalidates the
exact baseline, private file custody, schema and full quest graph compilation.
"""
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

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical, _lease, _open_directory, _write_all
from .studio_prompt_quest_plan import replay_prompt_quest_plan
from .studio_quest_structural_edit import compile_quest_structural_edit

EXPORT_SCHEMA = "skeleton.game_builder.studio_quest_structural_editor.v1"
FILENAME = "studio_quest_structural_editor.html"
MAX_EXPORT_BYTES = 64 * 1024
MAX_HTML_BYTES = 256 * 1024


def _baseline(value: object, expected_digest: str, authorized: bool) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("quest structural editor requires authorization")
    _lease(expected_digest, "structural editor baseline")
    checked = replay_prompt_quest_plan(value, authorized=True)
    if (_canonical(checked) != _canonical(value)
            or checked["receipt_digest"] != expected_digest):
        raise StudioQuestError("stale or noncanonical structural editor baseline")
    return checked


def render_quest_structural_editor(
    baseline: object, *, authorized: bool, expected_baseline_digest: str,
) -> tuple[bytes, dict[str, Any]]:
    checked = _baseline(baseline, expected_baseline_digest, authorized)
    meta = {
        "schema": EXPORT_SCHEMA, "project_id": checked["project_id"],
        "baseline_digest": checked["receipt_digest"],
    }
    initial = [{"op": "replace_prompt", "id": "prompt",
                "value": checked["plan"]["prompt"]}]
    script = (
        "const meta=" + json.dumps(meta, sort_keys=True, ensure_ascii=True) + ";"
        "const box=document.getElementById('edits');"
        "document.getElementById('export').addEventListener('click',()=>{"
        "try{const edits=JSON.parse(box.value);"
        "if(!Array.isArray(edits)||edits.length<1||edits.length>32)"
        "throw Error('edit count');"
        "const allowed=new Set(['add_stage','replace_stage','remove_stage',"
        "'reorder_stages','add_ending','replace_ending','remove_ending',"
        "'replace_prompt']);"
        "for(const e of edits){if(!e||typeof e!=='object'||Array.isArray(e)"
        "||Object.keys(e).sort().join(',')!=='id,op,value'"
        "||!allowed.has(e.op)||typeof e.id!=='string'||!e.id.length)"
        "throw Error('typed edit');}"
        "const raw=JSON.stringify({...meta,edits});"
        "if(new TextEncoder().encode(raw).length>65536)throw Error('byte limit');"
        "const blob=new Blob([raw],{type:'application/json'});"
        "const url=URL.createObjectURL(blob);const a=document.createElement('a');"
        "a.href=url;a.download='quest_structural_edit.json';a.click();"
        "setTimeout(()=>URL.revokeObjectURL(url),1000);"
        "document.getElementById('status').textContent="
        "'Exported; import with source lease for full graph validation';"
        "}catch(e){document.getElementById('status').textContent="
        "'Invalid typed edit batch; no export';}"
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
        "<meta http-equiv='Content-Security-Policy' content=\"" + csp + "\">"
        "<title>Original quest structural editor</title></head><body><main>"
        "<h1>Source-leased original quest structural editor</h1>"
        "<p>Edits are proposals. Export does not compile or save game state. "
        "Import through the CLI to verify graph, source and persistence.</p>"
        "<p>Project: " + escape(checked["project_id"], quote=True) + "</p>"
        "<label for='edits'>Typed structural edit batch (JSON)</label>"
        "<textarea id='edits' rows='24' cols='110'>"
        + escape(json.dumps(initial, indent=2, ensure_ascii=True))
        + "</textarea><button type='button' id='export'>Export typed edits</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "</main><script>" + script + "</script></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("structural editor HTML exceeds budget")
    return html, {
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "baseline_digest": checked["receipt_digest"],
        "file_write_performed": False, "release_certified": False,
    }


def publish_quest_structural_editor(
    baseline: object, directory: Path, *, authorized: bool,
    expected_baseline_digest: str,
) -> dict[str, Any]:
    html, proof = render_quest_structural_editor(
        baseline, authorized=authorized,
        expected_baseline_digest=expected_baseline_digest)
    fd = _open_directory(directory)
    temporary = ".quest-structural-editor-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=fd)
        created = True
        try:
            _write_all(handle, html)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        try:
            os.fsync(fd)
        except OSError:
            os.unlink(FILENAME, dir_fd=fd)
            raise
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {**proof, "path": str(Path(directory) / FILENAME),
            "file_write_performed": True}


def import_quest_structural_editor_export(
    baseline: object, path: Path, *, authorized: bool,
    expected_baseline_digest: str,
) -> dict[str, Any]:
    checked = _baseline(baseline, expected_baseline_digest, authorized)
    if not isinstance(path, Path):
        raise StudioQuestError("structural editor import requires a file path")
    fd = _open_directory(path.parent)
    try:
        handle = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_EXPORT_BYTES
                    or (os.name == "posix" and (
                        before.st_uid != os.getuid() or before.st_mode & 0o077
                        or before.st_nlink != 1))):
                raise StudioQuestError("structural editor import must be private")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                        after.st_ino) !=
                       (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                        before.st_ino)):
                raise StudioQuestError("structural editor import changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise StudioQuestError("duplicate structural editor JSON key")
            output[key] = value
        return output

    try:
        data = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite structural editor JSON")),
        )
    except StudioQuestError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid structural editor export") from exc
    if (type(data) is not dict
            or set(data) != {"schema", "project_id", "baseline_digest", "edits"}
            or data["schema"] != EXPORT_SCHEMA
            or data["project_id"] != checked["project_id"]
            or data["baseline_digest"] != expected_baseline_digest):
        raise StudioQuestError("stale or forged structural editor export")
    return compile_quest_structural_edit(
        checked, data["edits"], authorized=True,
        expected_baseline_digest=expected_baseline_digest)
