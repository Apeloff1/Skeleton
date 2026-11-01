"""Accessible CSP-hashed offline what-if editor with source-bound import."""
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
from .studio_ecosystem_scene_rehearsal import (
    SCHEMA as REHEARSAL_SCHEMA, _canonical, _digest, _lease,
    _open_directory, _write_all, compile_scene_rehearsal,
)

SCHEMA = "skeleton.game_builder.studio_scene_rehearsal_editor.v1"
EXPORT_SCHEMA = "skeleton.game_builder.studio_scene_rehearsal_export.v1"
FILENAME = "scene_rehearsal_editor.html"
MAX_HTML_BYTES = 256 * 1024
MAX_EXPORT_BYTES = 32768

_CSS = """
:root{color-scheme:dark;background:#10242c;color:#e5f7fb;font:16px/1.5 system-ui,sans-serif}
body{max-width:900px;margin:auto;padding:1.5rem}
section{border:1px solid #6a909c;border-radius:.5rem;padding:1rem;margin:1rem 0}
label{display:block;margin:.6rem 0}input,button{font:inherit;padding:.4rem;color:inherit;background:#204451}
input{max-width:9rem}button{cursor:pointer;border:1px solid #9bd9e8;padding:.7rem}
:focus-visible{outline:3px solid #ffdc87;outline-offset:2px}
"""
_JS = """
"use strict";
const model=JSON.parse(document.getElementById("source").textContent);
const fields=document.getElementById("scenes");
const rows=[];
for(const scene of model.scenes){
  const label=document.createElement("label");
  label.textContent=scene.scene_id+" — "+scene.npc_id+" (ticks) ";
  const input=document.createElement("input");
  input.type="number";input.min="1";input.max="100000";input.step="1";
  input.value=String(scene.duration_ticks);
  input.dataset.scene=scene.scene_id;
  label.appendChild(input);fields.appendChild(label);
  rows.push(input);
}
const status=document.getElementById("status");
document.getElementById("export").addEventListener("click",()=>{
  const schedule=JSON.parse(JSON.stringify(model.candidate_schedule));
  for(const input of rows){
    const raw=input.value.trim();const ticks=Number(raw);
    if(!/^[0-9]+$/.test(raw)||!Number.isSafeInteger(ticks)||
       ticks<1||ticks>100000){
      status.textContent="Invalid duration. Use integer ticks 1 through 100000.";
      input.focus();return;
    }
    schedule.scene_ticks[input.dataset.scene]=ticks;
  }
  const payload={
    schema:"skeleton.game_builder.studio_scene_rehearsal_export.v1",
    project_id:model.project_id,source_digest:model.source_digest,
    session_digest:model.session_digest,
    baseline_schedule_digest:model.baseline_schedule_digest,
    candidate_schedule:schedule
  };
  const blob=new Blob([JSON.stringify(payload,null,2)+"\\n"],
                      {type:"application/json"});
  const url=URL.createObjectURL(blob);
  try{
    const link=document.createElement("a");link.href=url;
    link.download="scene_rehearsal_candidate.json";
    document.body.appendChild(link);link.click();link.remove();
  }finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
  status.textContent="Exported. Operator CLI source replay is required before publication.";
});
"""


def _hash_script(text: str) -> str:
    return "'sha256-" + b64encode(sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def render_scene_rehearsal_editor(
    documents: Mapping[str, Any], actions: list[list[str]],
    report: Mapping[str, Any], *, authorized: bool,
) -> tuple[bytes, dict[str, object]]:
    if authorized is not True:
        raise PermissionError("rehearsal editor requires operator authorization")
    if type(report) is not dict or report.get("schema") != REHEARSAL_SCHEMA:
        raise StudioQuestError("invalid rehearsal editor input")
    replay = compile_scene_rehearsal(
        documents, actions, report.get("baseline_schedule"),
        report.get("candidate_schedule"), authorized=True,
        expected_source_digest=report.get("source_digest"),
        expected_session_digest=report.get("session_digest"))
    if replay != report:
        raise StudioQuestError("rehearsal editor lacks canonical source proof")
    from .studio_ecosystem_scene_schedule import compile_scene_schedule
    candidate = compile_scene_schedule(
        documents, actions, report["candidate_schedule"], authorized=True,
        expected_source_digest=report["source_digest"],
        expected_session_digest=report["session_digest"])
    model = {
        "schema": SCHEMA, "project_id": report["project_id"],
        "source_digest": report["source_digest"],
        "session_digest": report["session_digest"],
        "baseline_schedule_digest": report["baseline_schedule_digest"],
        "candidate_schedule": report["candidate_schedule"],
        "scenes": [{"scene_id": row["scene_id"], "npc_id": row["npc_id"],
                    "duration_ticks": row["duration_ticks"]}
                   for row in candidate["timeline"]],
    }
    raw = _canonical(model).decode("ascii")
    raw = raw.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")
    csp = ("default-src 'none'; script-src " + _hash_script(raw) + " " +
           _hash_script(_JS) + "; style-src " + _hash_script(_CSS) +
           "; base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"" + csp + "\">"
        "<title>Original scene timing editor</title><style>" + _CSS + "</style>"
        "</head><body><main><h1>Original scene timing editor</h1>"
        "<p>Offline estimated ticks only. No native NPC travel or execution claim.</p>"
        "<p>Project: " + escape(report["project_id"], quote=True) + "</p>"
        "<section id='scenes' aria-label='Authored scene durations'></section>"
        "<button type='button' id='export'>Export source-bound candidate</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "<script type='application/json' id='source'>" + raw + "</script>"
        "<script>" + _JS + "</script></main></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("rehearsal editor exceeds byte budget")
    receipt: dict[str, object] = {
        "schema": SCHEMA, "project_id": report["project_id"],
        "source_digest": report["source_digest"],
        "session_digest": report["session_digest"],
        "rehearsal_digest": report["rehearsal_digest"],
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "source_replay_verified": True, "authoring_export_only": True,
        "file_write_performed": False, "release_certified": False,
    }
    receipt["editor_digest"] = _digest(receipt)
    return html, receipt


def load_scene_rehearsal_export(
    path: Path, *, authorized: bool, expected_project_id: str,
    expected_source_digest: str, expected_session_digest: str,
    expected_baseline_digest: str,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("rehearsal editor import requires authorization")
    for name, value in (("source", expected_source_digest),
                        ("session", expected_session_digest),
                        ("baseline", expected_baseline_digest)):
        _lease(value, "editor " + name)
    fd = _open_directory(Path(path).parent)
    try:
        handle = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or
                    not 0 < info.st_size <= MAX_EXPORT_BYTES or
                    os.name == "posix" and
                    (info.st_uid != os.getuid() or info.st_mode & 0o077 or
                     info.st_nlink != 1)):
                raise StudioQuestError("editor import requires private regular file")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXPORT_BYTES:
        raise StudioQuestError("editor import exceeds byte budget")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate editor JSON key")
            result[key] = value
        return result
    try:
        record = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite editor JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid rehearsal editor JSON") from exc
    if (type(record) is not dict or set(record) != {
            "schema", "project_id", "source_digest", "session_digest",
            "baseline_schedule_digest", "candidate_schedule"} or
            record["schema"] != EXPORT_SCHEMA or
            record["project_id"] != expected_project_id or
            record["source_digest"] != expected_source_digest or
            record["session_digest"] != expected_session_digest or
            record["baseline_schedule_digest"] != expected_baseline_digest or
            type(record["candidate_schedule"]) is not dict):
        raise StudioQuestError("stale or forged rehearsal editor source")
    return record["candidate_schedule"]


def publish_scene_rehearsal_editor(
    html: bytes, receipt: Mapping[str, Any], directory: Path, *,
    authorized: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("editor publication requires authorization")
    if (type(html) is not bytes or not 0 < len(html) <= MAX_HTML_BYTES
            or type(receipt) is not dict or receipt.get("schema") != SCHEMA
            or receipt.get("html_sha256") != sha256(html).hexdigest()
            or receipt.get("html_bytes") != len(html)
            or receipt.get("editor_digest") != _digest({
                k: v for k, v in receipt.items() if k != "editor_digest"})):
        raise StudioQuestError("invalid editor publication evidence")
    fd = _open_directory(directory)
    name = ".scene-editor-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(handle, html)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(name, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(name, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "html_sha256": receipt["html_sha256"],
            "file_write_performed": True, "release_certified": False}
