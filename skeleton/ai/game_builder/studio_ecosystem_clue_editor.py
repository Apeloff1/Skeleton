"""Private source-replayed offline clue editor and strict JSON reimport."""
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

from .studio_ecosystem_clue_visibility import (
    SCHEMA as CLUE_SCHEMA, _replay, compile_clue_visibility,
)
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)

SCHEMA = "skeleton.game_builder.studio_clue_editor.v1"
EXPORT_SCHEMA = "skeleton.game_builder.studio_clue_editor_export.v1"
FILENAME = "clue_editor.html"
MAX_HTML = 256 * 1024
MAX_EXPORT = 32768

_CSS = """
:root{color-scheme:dark;background:#0f2030;color:#eef7ff;font:16px/1.5 system-ui}
body{max-width:900px;margin:auto;padding:1.5rem}
section{border:1px solid #678ba3;border-radius:.5rem;padding:1rem;margin:1rem 0}
label{display:block;margin:.6rem 0}textarea,button{font:inherit;padding:.5rem}
textarea{display:block;width:95%;min-height:5rem;color:#fff;background:#183b50}
button{color:#fff;background:#1e5672;border:1px solid #b6e3ff;cursor:pointer}
:focus-visible{outline:3px solid #ffda75;outline-offset:2px}
"""
_JS = """
"use strict";
const model=JSON.parse(document.getElementById("source").textContent);
const host=document.getElementById("clues");
const status=document.getElementById("status");
const fields=[];
for(const clue of model.authoring.clues){
  const box=document.createElement("section");
  const label=document.createElement("label");
  label.textContent=clue.id+" — "+clue.scene_id+" (reveals after "+clue.visible_after_stage+")";
  const input=document.createElement("textarea");
  input.maxLength=240;input.value=clue.text;
  label.appendChild(input);box.appendChild(label);host.appendChild(box);
  fields.push(input);
}
document.getElementById("export").addEventListener("click",()=>{
  const authoring=JSON.parse(JSON.stringify(model.authoring));
  for(let i=0;i<fields.length;i++){
    const text=fields[i].value;
    if(text.length<1||text.length>240||text.trim()!==text||/[\\x00-\\x1f\\x7f]/.test(text)){
      status.textContent="Invalid clue text; 1–240 printable characters required.";
      fields[i].focus();return;
    }
    authoring.clues[i].text=text;
  }
  const payload={
    schema:"skeleton.game_builder.studio_clue_editor_export.v1",
    project_id:model.project_id,source_digest:model.source_digest,
    session_digest:model.session_digest,baseline_clue_digest:model.baseline_clue_digest,
    authoring
  };
  const blob=new Blob([JSON.stringify(payload,null,2)+"\\n"],{type:"application/json"});
  const url=URL.createObjectURL(blob);
  try{
    const link=document.createElement("a");
    link.href=url;link.download="clue_authoring.json";
    document.body.appendChild(link);link.click();link.remove();
  }finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
  status.textContent="Exported. CLI replay and authorization required before publication.";
});
"""


def _hash(text: str) -> str:
    return "'sha256-" + b64encode(sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def render_clue_editor(documents: Mapping[str, Any], report: Mapping[str, Any], *,
                       authorized: bool) -> tuple[bytes, dict[str, object]]:
    replay = _replay(documents, report, authorized=authorized)
    model = {
        "schema": SCHEMA, "project_id": replay["project_id"],
        "source_digest": replay["source_digest"],
        "session_digest": replay["session_digest"],
        "baseline_clue_digest": replay["clue_digest"],
        "authoring": replay["authoring"],
    }
    raw = _canonical(model).decode("ascii")
    raw = raw.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")
    csp = ("default-src 'none'; script-src " + _hash(raw) + " " + _hash(_JS)
           + "; style-src " + _hash(_CSS)
           + "; base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"" + csp + "\">"
        "<title>Original clue editor</title><style>" + _CSS + "</style></head>"
        "<body><main><h1>Original clue editor</h1>"
        "<p>Private offline authoring; hidden clue text is visible to the operator only.</p>"
        "<p>Project: " + escape(replay["project_id"], quote=True) + "</p>"
        "<div id='clues' aria-label='Editable clue text'></div>"
        "<button type='button' id='export'>Export typed clue edits</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "<script type='application/json' id='source'>" + raw + "</script>"
        "<script>" + _JS + "</script></main></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("clue editor exceeds bounded HTML budget")
    receipt: dict[str, object] = {
        "schema": SCHEMA, "project_id": replay["project_id"],
        "source_digest": replay["source_digest"],
        "session_digest": replay["session_digest"],
        "baseline_clue_digest": replay["clue_digest"],
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "source_replay_verified": True, "export_only": True,
        "file_write_performed": False, "release_certified": False,
    }
    receipt["editor_digest"] = _digest(receipt)
    return html, receipt


def load_clue_editor_export(path: Path, *, authorized: bool,
                            expected_project_id: str,
                            expected_source_digest: str,
                            expected_session_digest: str,
                            expected_baseline_digest: str) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("clue editor import requires authorization")
    for label, digest in (("source", expected_source_digest),
                          ("session", expected_session_digest),
                          ("baseline", expected_baseline_digest)):
        _lease(digest, "clue editor " + label)
    fd = _open_directory(Path(path).parent)
    try:
        handle = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_EXPORT
                    or os.name == "posix" and
                    (info.st_uid != os.getuid() or info.st_mode & 0o077
                     or info.st_nlink != 1)):
                raise StudioQuestError("clue import requires private regular file")
            raw = os.read(handle, MAX_EXPORT + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXPORT:
        raise StudioQuestError("clue export exceeds byte budget")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate clue export key")
            result[key] = value
        return result
    try:
        record = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite clue export JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid clue editor export") from exc
    if (type(record) is not dict or set(record) != {
            "schema", "project_id", "source_digest", "session_digest",
            "baseline_clue_digest", "authoring"}
            or record["schema"] != EXPORT_SCHEMA
            or record["project_id"] != expected_project_id
            or record["source_digest"] != expected_source_digest
            or record["session_digest"] != expected_session_digest
            or record["baseline_clue_digest"] != expected_baseline_digest
            or type(record["authoring"]) is not dict):
        raise StudioQuestError("clue export source/session/baseline mismatch")
    return record["authoring"]


def publish_clue_editor(documents: Mapping[str, Any],
                        report: Mapping[str, Any], directory: Path, *,
                        authorized: bool) -> dict[str, object]:
    html, receipt = render_clue_editor(documents, report, authorized=authorized)
    fd = _open_directory(directory)
    temporary = ".clue-editor-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(handle, html)
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
            "html_sha256": receipt["html_sha256"],
            "file_write_performed": True, "release_certified": False}
