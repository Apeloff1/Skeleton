"""Offline NPC transit graph editor with CSP, strict import and exact replay leases."""
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
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
    compile_scene_schedule,
)
from .studio_ecosystem_npc_transit import replay_npc_transit

SCHEMA = "skeleton.game_builder.studio_npc_transit_editor.v1"
EXPORT_SCHEMA = "skeleton.game_builder.studio_npc_transit_editor_export.v1"
FILENAME = "npc_transit_editor.html"
MAX_HTML = 256 * 1024
MAX_EXPORT = 32768

_CSS = """
:root{color-scheme:dark;background:#102134;color:#eff8ff;font:16px/1.5 system-ui}
body{max-width:64rem;margin:auto;padding:1.5rem}
fieldset{border:1px solid #81a8c2;border-radius:.4rem;margin:1rem 0}
label{display:block;margin:.5rem 0}select,input,button{font:inherit;padding:.4rem}
select,input{color:#fff;background:#214358;border:1px solid #9dc5df}
button{background:#1f5674;color:#fff;border:2px solid #addbfb;margin:.2rem}
:focus-visible{outline:3px solid #ffd777;outline-offset:2px}
"""
_JS = r"""
"use strict";
const model=JSON.parse(document.getElementById("source").textContent);
const host=document.getElementById("edges");
const status=document.getElementById("status");
const rows=[];
function field(labelText,kind){
  const label=document.createElement("label");label.textContent=labelText;
  const input=document.createElement(kind);
  if(kind==="select"){
    for(const site of model.sites){
      const option=document.createElement("option");
      option.value=site;option.textContent=site;input.append(option);
    }
  }else{
    input.type="number";input.min="0";input.max="1000000";
    input.step="1";input.required=true;
  }
  label.append(input);return [label,input];
}
function addEdge(edge){
  if(rows.length>=256){status.textContent="Maximum 256 directed edges.";return;}
  const group=document.createElement("fieldset");
  const legend=document.createElement("legend");
  legend.textContent="Directed site transit "+String(rows.length+1);group.append(legend);
  const [fromLabel,from]=field("From site","select");
  const [toLabel,to]=field("To site","select");
  const [tickLabel,ticks]=field("Estimated travel ticks","input");
  from.value=edge.from_site||model.sites[0]||"";
  to.value=edge.to_site||model.sites[1]||model.sites[0]||"";
  ticks.value=String(edge.ticks===undefined?0:edge.ticks);
  group.append(fromLabel,toLabel,tickLabel);
  host.append(group);rows.push([from,to,ticks]);
}
for(const edge of model.graph.edges)addEdge(edge);
document.getElementById("add").addEventListener("click",()=>addEdge({}));
function readTicks(input){
  if(!/^(0|[1-9][0-9]*)$/.test(input.value))return null;
  const n=Number(input.value);
  return Number.isSafeInteger(n)&&n<=1000000?n:null;
}
document.getElementById("export").addEventListener("click",()=>{
  const edges=[],seen=new Set();
  for(const [from,to,ticks] of rows){
    const n=readTicks(ticks),key=JSON.stringify([from.value,to.value]);
    if(n===null||from.value===to.value||seen.has(key)){
      status.textContent="Invalid directed site edge, duplicate, or tick estimate.";
      ticks.focus();return;
    }
    seen.add(key);
    edges.push({from_site:from.value,to_site:to.value,ticks:n});
  }
  const record={
    schema:"skeleton.game_builder.studio_npc_transit_editor_export.v1",
    project_id:model.project_id,source_digest:model.source_digest,
    session_digest:model.session_digest,temporal_digest:model.temporal_digest,
    baseline_transit_digest:model.baseline_transit_digest,graph:{edges}
  };
  const blob=new Blob([JSON.stringify(record,null,2)+"\n"],{type:"application/json"});
  const url=URL.createObjectURL(blob);
  try{
    const link=document.createElement("a");link.href=url;
    link.download="npc_transit_edges.json";document.body.append(link);
    link.click();link.remove();
  }finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
  status.textContent="Exported. Validate the graph using the source-bound CLI.";
});
"""


def _hash(text: str) -> str:
    return "'sha256-" + b64encode(sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def render_npc_transit_editor(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> tuple[bytes, dict[str, object]]:
    replay = replay_npc_transit(documents, receipt, authorized=authorized)
    temporal = replay["temporal_receipt"]
    schedule = compile_scene_schedule(
        documents, temporal["actions"],
        temporal["authoring"]["schedule_request"], authorized=True,
        expected_source_digest=temporal["source_digest"],
        expected_session_digest=temporal["session_digest"])
    if schedule["schedule_digest"] != temporal["schedule_digest"]:
        raise StudioQuestError("NPC transit editor source schedule drift")
    sites = sorted({row["site"] for row in schedule["timeline"]})
    model = {
        "schema": SCHEMA, "project_id": replay["project_id"],
        "source_digest": replay["source_digest"],
        "session_digest": replay["session_digest"],
        "temporal_digest": replay["temporal_digest"],
        "baseline_transit_digest": replay["transit_digest"],
        "sites": sites, "graph": replay["graph"],
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
        "<title>NPC transit editor</title><style>" + _CSS + "</style></head>"
        "<body><main><h1>Source-bound NPC transit editor</h1>"
        "<p>Operator-estimated directed site travel. No physical measurements.</p>"
        "<p>Project: " + escape(replay["project_id"], quote=True) + "</p>"
        "<div id='edges' aria-label='Editable directed travel edges'></div>"
        "<button type='button' id='add'>Add directed site edge</button>"
        "<button type='button' id='export'>Export typed NPC transit edits</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "<script type='application/json' id='source'>" + raw + "</script>"
        "<script>" + _JS + "</script></main></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("NPC transit editor exceeds HTML budget")
    proof: dict[str, object] = {
        "schema": SCHEMA, "project_id": replay["project_id"],
        "source_digest": replay["source_digest"],
        "session_digest": replay["session_digest"],
        "temporal_digest": replay["temporal_digest"],
        "baseline_transit_digest": replay["transit_digest"],
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "source_replay_verified": True, "export_only": True,
        "file_write_performed": False, "release_certified": False,
    }
    proof["editor_digest"] = _digest(proof)
    return html, proof


def load_npc_transit_editor_export(
    path: Path, *, authorized: bool, expected_project_id: str,
    expected_source_digest: str, expected_session_digest: str,
    expected_temporal_digest: str, expected_baseline_digest: str,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("NPC transit editor import requires authorization")
    for label, digest in (
        ("source", expected_source_digest), ("session", expected_session_digest),
        ("temporal", expected_temporal_digest), ("baseline", expected_baseline_digest),
    ):
        _lease(digest, "NPC transit editor " + label)
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
                raise StudioQuestError("NPC transit editor export must be private")
            raw = os.read(handle, MAX_EXPORT + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXPORT:
        raise StudioQuestError("NPC transit editor export exceeds byte budget")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate NPC transit export key")
            result[key] = value
        return result
    try:
        record = json.loads(raw.decode("utf-8", "strict"),
                            object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite NPC transit export")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC transit editor export") from exc
    if (type(record) is not dict or set(record) != {
            "schema", "project_id", "source_digest", "session_digest",
            "temporal_digest", "baseline_transit_digest", "graph"}
            or record["schema"] != EXPORT_SCHEMA
            or record["project_id"] != expected_project_id
            or record["source_digest"] != expected_source_digest
            or record["session_digest"] != expected_session_digest
            or record["temporal_digest"] != expected_temporal_digest
            or record["baseline_transit_digest"] != expected_baseline_digest
            or type(record["graph"]) is not dict):
        raise StudioQuestError("NPC transit editor export lease mismatch")
    return record["graph"]


def publish_npc_transit_editor(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, object]:
    html, proof = render_npc_transit_editor(
        documents, receipt, authorized=authorized)
    fd = _open_directory(directory)
    temporary = ".npc-transit-editor-" + secrets.token_hex(16) + ".tmp"
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
