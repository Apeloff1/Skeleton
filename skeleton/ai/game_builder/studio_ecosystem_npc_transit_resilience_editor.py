"""Offline source-leased route-disruption editor with bounded, private typed import."""
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
from .studio_ecosystem_npc_transit_resilience import replay_npc_transit_resilience

SCHEMA = "skeleton.game_builder.studio_npc_resilience_editor.v1"
EXPORT_SCHEMA = "skeleton.game_builder.studio_npc_resilience_editor_export.v1"
FILENAME = "npc_transit_resilience_editor.html"
MAX_HTML = 128 * 1024
MAX_EXPORT = 32768

_CSS = """
:root{color-scheme:dark;background:#102134;color:#eff8ff;font:16px/1.5 system-ui}
body{max-width:60rem;margin:auto;padding:1.5rem}
textarea{box-sizing:border-box;width:100%;min-height:22rem;color:#fff;background:#214358;
border:2px solid #9dc5df;font:14px/1.4 monospace;padding:.7rem}
button{font:inherit;background:#1f5674;color:#fff;border:2px solid #addbfb;
padding:.6rem 1rem;margin:1rem 0}
:focus-visible{outline:3px solid #ffd777;outline-offset:2px}
"""
_JS = r"""
"use strict";
const model=JSON.parse(document.getElementById("source").textContent);
const input=document.getElementById("variants");
const status=document.getElementById("status");
input.value=JSON.stringify(model.variants,null,2);
document.getElementById("export").addEventListener("click",()=>{
  let variants;
  try{variants=JSON.parse(input.value);}catch(_){
    status.textContent="Invalid JSON; correct the variants before exporting.";return;
  }
  if(!Array.isArray(variants)||variants.length<1||variants.length>12){
    status.textContent="Provide between one and twelve variants.";return;
  }
  const seen=new Set(),edges=new Set(model.edges.map(e=>JSON.stringify([e.from_site,e.to_site])));
  for(const item of variants){
    if(!item||typeof item!=="object"||Array.isArray(item)
       ||Object.keys(item).sort().join(",")!=="closed_edges,id"
       ||typeof item.id!=="string"||!/^[a-z][a-z0-9_-]{0,47}$/.test(item.id)
       ||seen.has(item.id)||!Array.isArray(item.closed_edges)
       ||item.closed_edges.length>32){
      status.textContent="Invalid variant identity or closure list.";return;
    }
    seen.add(item.id);
    const closed=new Set();
    for(const edge of item.closed_edges){
      if(!edge||typeof edge!=="object"||Array.isArray(edge)
         ||Object.keys(edge).sort().join(",")!=="from_site,to_site"
         ||typeof edge.from_site!=="string"||typeof edge.to_site!=="string"){
        status.textContent="Invalid directed edge closure.";return;
      }
      const key=JSON.stringify([edge.from_site,edge.to_site]);
      if(!edges.has(key)||closed.has(key)){
        status.textContent="Unknown or duplicate directed route closure.";return;
      }
      closed.add(key);
    }
  }
  const exportRecord={
    schema:"skeleton.game_builder.studio_npc_resilience_editor_export.v1",
    project_id:model.project_id,source_digest:model.source_digest,
    session_digest:model.session_digest,temporal_digest:model.temporal_digest,
    baseline_transit_digest:model.baseline_transit_digest,
    baseline_resilience_digest:model.baseline_resilience_digest,variants
  };
  const bytes=JSON.stringify(exportRecord,null,2)+"\n";
  if(new TextEncoder().encode(bytes).length>32768){
    status.textContent="Export exceeds 32 KiB budget.";return;
  }
  const blob=new Blob([bytes],{type:"application/json"});
  const url=URL.createObjectURL(blob);
  try{
    const link=document.createElement("a");link.href=url;
    link.download="npc_resilience_variants.json";document.body.append(link);
    link.click();link.remove();
  }finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
  status.textContent="Exported. Protect the file as private (0600), then recompile with the CLI.";
});
"""


def _hash(value: str) -> str:
    return "'sha256-" + b64encode(sha256(value.encode("utf-8")).digest()).decode("ascii") + "'"


def render_npc_resilience_editor(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> tuple[bytes, dict[str, Any]]:
    replay = replay_npc_transit_resilience(documents, receipt, authorized=authorized)
    baseline = replay["baseline_receipt"]
    model = {
        "schema": SCHEMA, "project_id": replay["project_id"],
        "source_digest": replay["source_digest"],
        "session_digest": replay["session_digest"],
        "temporal_digest": replay["temporal_digest"],
        "baseline_transit_digest": baseline["transit_digest"],
        "baseline_resilience_digest": replay["resilience_digest"],
        "edges": baseline["graph"]["edges"], "variants": replay["variants"],
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
        "<title>NPC route disruption editor</title><style>" + _CSS + "</style></head>"
        "<body><main><h1>NPC route disruption editor</h1>"
        "<p>Offline operator-estimated routes. A closed edge must exist in the source "
        "transit graph. This editor does not simulate native travel.</p>"
        "<p>Project: " + escape(replay["project_id"], quote=True) + "</p>"
        "<label for='variants'>Typed disruption variants (JSON)</label>"
        "<textarea id='variants' spellcheck='false' aria-describedby='status'></textarea>"
        "<button type='button' id='export'>Export typed NPC disruption edits</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "<script type='application/json' id='source'>" + raw + "</script>"
        "<script>" + _JS + "</script></main></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("NPC disruption editor exceeds HTML budget")
    proof: dict[str, Any] = {
        "schema": SCHEMA, "project_id": replay["project_id"],
        "source_digest": replay["source_digest"],
        "session_digest": replay["session_digest"],
        "baseline_transit_digest": baseline["transit_digest"],
        "baseline_resilience_digest": replay["resilience_digest"],
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "source_replay_verified": True, "export_only": True,
        "file_write_performed": False, "release_certified": False,
    }
    proof["editor_digest"] = _digest(proof)
    return html, proof


def load_npc_resilience_editor_export(
    path: Path, *, authorized: bool, expected_project_id: str,
    expected_source_digest: str, expected_session_digest: str,
    expected_temporal_digest: str, expected_transit_digest: str,
    expected_resilience_digest: str,
) -> list[dict[str, Any]]:
    if authorized is not True:
        raise PermissionError("NPC disruption import requires authorization")
    for label, digest in (
        ("source", expected_source_digest), ("session", expected_session_digest),
        ("temporal", expected_temporal_digest), ("transit", expected_transit_digest),
        ("resilience", expected_resilience_digest),
    ):
        _lease(digest, "NPC disruption editor " + label)
    fd = _open_directory(Path(path).parent)
    try:
        handle = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_EXPORT
                    or (os.name == "posix"
                        and (info.st_uid != os.getuid() or info.st_mode & 0o077
                             or info.st_nlink != 1))):
                raise StudioQuestError("NPC disruption editor export must be private")
            raw = os.read(handle, MAX_EXPORT + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXPORT:
        raise StudioQuestError("NPC disruption export exceeds byte budget")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise StudioQuestError("duplicate NPC disruption export key")
            output[key] = value
        return output
    try:
        record = json.loads(raw.decode("utf-8", "strict"),
                            object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite NPC disruption export")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC disruption export JSON") from exc
    if (type(record) is not dict or set(record) != {
            "schema", "project_id", "source_digest", "session_digest",
            "temporal_digest", "baseline_transit_digest",
            "baseline_resilience_digest", "variants"}
            or record["schema"] != EXPORT_SCHEMA
            or record["project_id"] != expected_project_id
            or record["source_digest"] != expected_source_digest
            or record["session_digest"] != expected_session_digest
            or record["temporal_digest"] != expected_temporal_digest
            or record["baseline_transit_digest"] != expected_transit_digest
            or record["baseline_resilience_digest"] != expected_resilience_digest
            or type(record["variants"]) is not list):
        raise StudioQuestError("NPC disruption export lease mismatch")
    return record["variants"]


def publish_npc_resilience_editor(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    html, proof = render_npc_resilience_editor(
        documents, receipt, authorized=authorized)
    fd = _open_directory(directory)
    temporary = ".npc-resilience-editor-" + secrets.token_hex(16) + ".tmp"
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
    return {**proof, "path": str(Path(directory) / FILENAME),
            "file_write_performed": True}
