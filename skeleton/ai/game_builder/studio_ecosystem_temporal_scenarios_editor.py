"""Offline, CSP-hashed temporal scenario editor and source-leased JSON reimport."""
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
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease, _open_directory, _write_all
from .studio_ecosystem_temporal_scenarios import (
    MAX_REQUEST_BYTES, replay_temporal_scenarios,
)

SCHEMA = "skeleton.game_builder.studio_temporal_scenarios_editor.v1"
EXPORT_SCHEMA = "skeleton.game_builder.studio_temporal_scenarios_editor_export.v1"
FILENAME = "temporal_scenarios_editor.html"
MAX_HTML = 256 * 1024
MAX_EXPORT = MAX_REQUEST_BYTES + 4096

_CSS = """
:root{color-scheme:dark;background:#102134;color:#eff8ff;font:16px/1.5 system-ui}
body{max-width:64rem;margin:auto;padding:1.5rem}
fieldset{border:1px solid #81a8c2;border-radius:.4rem;margin:1rem 0}
label{display:block;margin:.5rem 0}input,button{font:inherit;padding:.4rem}
input{color:#fff;background:#214358;border:1px solid #9dc5df}
button{background:#1f5674;color:#fff;border:2px solid #addbfb}
:focus-visible{outline:3px solid #ffd777;outline-offset:2px}
"""
_JS = r"""
"use strict";
const model=JSON.parse(document.getElementById("source").textContent);
const host=document.getElementById("candidates");
const status=document.getElementById("status");
const fields=[];
for(const candidate of model.candidates){
  const section=document.createElement("fieldset");
  const title=document.createElement("legend");
  title.textContent="Scenario: "+candidate.id;section.append(title);
  for(const [id,window] of Object.entries(candidate.authoring.windows)){
    const group=document.createElement("fieldset");
    const legend=document.createElement("legend");legend.textContent=id;group.append(legend);
    const pair=[];
    for(const key of ["earliest","latest"]){
      const label=document.createElement("label");label.textContent=key+" (operator ticks)";
      const input=document.createElement("input");input.type="number";input.min="0";
      input.max="1000000";input.step="1";input.required=true;
      input.value=String(window[key]);label.append(input);group.append(label);
      pair.push(input);
    }
    fields.push([candidate.id,id,pair[0],pair[1]]);
    section.append(group);
  }
  host.append(section);
}
function readInt(input){
  if(!/^(0|[1-9][0-9]*)$/.test(input.value))return null;
  const n=Number(input.value);
  return Number.isSafeInteger(n)&&n<=1000000?n:null;
}
document.getElementById("export").addEventListener("click",()=>{
  const candidates=JSON.parse(JSON.stringify(model.candidates));
  const byId=new Map(candidates.map(x=>[x.id,x]));
  for(const [scenario,scene,first,last] of fields){
    const earliest=readInt(first),latest=readInt(last);
    if(earliest===null||latest===null||latest<=earliest){
      status.textContent="Invalid authored window: "+scenario+" / "+scene;
      first.focus();return;
    }
    byId.get(scenario).authoring.windows[scene]={earliest,latest};
  }
  const record={
    schema:"skeleton.game_builder.studio_temporal_scenarios_editor_export.v1",
    project_id:model.project_id,source_digest:model.source_digest,
    session_digest:model.session_digest,
    baseline_scenario_digest:model.baseline_scenario_digest,candidates
  };
  const blob=new Blob([JSON.stringify(record,null,2)+"\n"],{type:"application/json"});
  const url=URL.createObjectURL(blob);
  try{
    const link=document.createElement("a");link.href=url;
    link.download="temporal_scenario_edits.json";document.body.append(link);
    link.click();link.remove();
  }finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
  status.textContent="Exported. Run the source-bound CLI to validate and persist edits.";
});
"""


def _hash(text: str) -> str:
    return "'sha256-" + b64encode(sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def render_temporal_scenarios_editor(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> tuple[bytes, dict[str, object]]:
    replay = replay_temporal_scenarios(documents, receipt, authorized=authorized)
    model = {
        "schema": SCHEMA, "project_id": replay["project_id"],
        "source_digest": replay["source_digest"],
        "session_digest": replay["session_digest"],
        "baseline_scenario_digest": replay["scenario_digest"],
        "candidates": replay["candidates"],
    }
    raw = _canonical(model).decode("ascii")
    raw = raw.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")
    csp = ("default-src 'none'; script-src " + _hash(raw) + " " + _hash(_JS)
           + "; style-src " + _hash(_CSS)
           + "; base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        "<title>Temporal scenario editor</title><style>" + _CSS + "</style></head>"
        "<body><main><h1>Source-bound temporal scenario editor</h1>"
        "<p>Offline operator estimates only. Changes require canonical replay.</p>"
        "<p>Project: " + escape(replay["project_id"], quote=True) + "</p>"
        "<div id='candidates' aria-label='Editable timing alternatives'></div>"
        "<button type='button' id='export'>Export typed scenario edits</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "<script type='application/json' id='source'>" + raw + "</script>"
        "<script>" + _JS + "</script></main></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("temporal scenario editor exceeds HTML budget")
    proof: dict[str, object] = {
        "schema": SCHEMA, "project_id": replay["project_id"],
        "source_digest": replay["source_digest"],
        "session_digest": replay["session_digest"],
        "baseline_scenario_digest": replay["scenario_digest"],
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "source_replay_verified": True, "export_only": True,
        "file_write_performed": False, "release_certified": False,
    }
    proof["editor_digest"] = _digest(proof)
    return html, proof


def load_temporal_scenarios_editor_export(
    path: Path, *, authorized: bool, expected_project_id: str,
    expected_source_digest: str, expected_session_digest: str,
    expected_baseline_digest: str,
) -> list[dict[str, object]]:
    if authorized is not True:
        raise PermissionError("temporal scenario editor import requires authorization")
    for label, digest in (
        ("source", expected_source_digest), ("session", expected_session_digest),
        ("baseline", expected_baseline_digest),
    ):
        _lease(digest, "temporal scenario editor " + label)
    fd = _open_directory(Path(path).parent)
    try:
        handle = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_EXPORT
                    or (os.name == "posix" and
                        (info.st_uid != os.getuid() or info.st_mode & 0o077
                         or info.st_nlink != 1))):
                raise StudioQuestError("temporal scenario export must be private")
            raw = os.read(handle, MAX_EXPORT + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXPORT:
        raise StudioQuestError("temporal scenario export exceeds byte budget")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate temporal scenario export key")
            result[key] = value
        return result
    try:
        record = json.loads(raw.decode("utf-8", "strict"),
                            object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite temporal scenario export")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid temporal scenario editor export") from exc
    if (type(record) is not dict or set(record) != {
            "schema", "project_id", "source_digest", "session_digest",
            "baseline_scenario_digest", "candidates"}
            or record["schema"] != EXPORT_SCHEMA
            or record["project_id"] != expected_project_id
            or record["source_digest"] != expected_source_digest
            or record["session_digest"] != expected_session_digest
            or record["baseline_scenario_digest"] != expected_baseline_digest
            or type(record["candidates"]) is not list):
        raise StudioQuestError("temporal scenario editor export lease mismatch")
    return record["candidates"]


def publish_temporal_scenarios_editor(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, object]:
    html, proof = render_temporal_scenarios_editor(
        documents, receipt, authorized=authorized)
    fd = _open_directory(directory)
    temporary = ".temporal-scenarios-editor-" + secrets.token_hex(16) + ".tmp"
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
            "html_sha256": proof["html_sha256"],
            "file_write_performed": True, "release_certified": False}
