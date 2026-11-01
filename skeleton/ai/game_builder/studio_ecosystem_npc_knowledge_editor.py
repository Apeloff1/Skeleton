"""Accessible offline NPC knowledge editor with exact source/session export custody."""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_npc_knowledge import (
    REQUEST_SCHEMA, _canonical, _digest, _lease, compile_npc_knowledge,
    source_knowledge_facts,
)
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _open_directory

SCHEMA = "skeleton.game_builder.studio_npc_knowledge_editor.v1"
EXPORT_SCHEMA = "skeleton.game_builder.studio_npc_knowledge_editor_export.v1"
MAX_EDITOR_BYTES = 256 * 1024
MAX_EXPORT_BYTES = 65536

_CSS = """
:root{font:16px/1.5 system-ui,sans-serif;color-scheme:dark;background:#10232e;color:#eef9fa}
body{max-width:900px;margin:auto;padding:1.5rem}
section{border:1px solid #63818c;border-radius:.5rem;padding:1rem;margin:1rem 0}
label{display:block;margin:.8rem 0}select,button{font:inherit;padding:.6rem;color:#fff;background:#204154}
select{max-width:100%}button{cursor:pointer;margin:.3rem;border:1px solid #9bd9e8}
button:focus-visible,select:focus-visible{outline:3px solid #ffdc87;outline-offset:2px}
code{overflow-wrap:anywhere}
"""

_JS = """
"use strict";
const model=JSON.parse(document.getElementById("knowledge-data").textContent);
const facts=new Map(model.facts.map(f=>[f.fact_id,f]));
const scenes=model.scenes;
const reveals=model.authoring.reveals.map(row=>({...row}));
const sourceSelect=document.getElementById("fact");
const recipientSelect=document.getElementById("recipient");
const alternativeSelect=document.getElementById("alternative");
const list=document.getElementById("reveals");
const status=document.getElementById("status");
function node(tag,text,parent){
  const item=document.createElement(tag);
  if(text!==null)item.textContent=text;
  if(parent)parent.appendChild(item);
  return item;
}
function option(select,value,label){
  const item=node("option",label,select);item.value=value;return item;
}
for(const fact of model.facts){
  option(sourceSelect,fact.fact_id,fact.fact_id+" — "+fact.source_text);
}
function refreshTargets(){
  recipientSelect.replaceChildren();alternativeSelect.replaceChildren();
  const fact=facts.get(sourceSelect.value);
  if(!fact)return;
  const start=scenes.findIndex(s=>s.scene_id===fact.scene_id);
  for(let i=start+1;i<scenes.length;i++){
    option(recipientSelect,scenes[i].scene_id,
           scenes[i].scene_id+" — "+scenes[i].npc_id);
  }
  option(alternativeSelect,"","Any completed authored source choice");
  const source=scenes[start];
  for(const alternative of source.alternatives){
    option(alternativeSelect,alternative,alternative);
  }
}
function refreshList(){
  list.replaceChildren();
  for(let i=0;i<reveals.length;i++){
    const row=reveals[i];const item=node("li",null,list);
    node("span",row.fact_id+" → "+row.recipient_scene_id+
         (row.required_alternative===null?"":" [choice: "+row.required_alternative+"]"),item);
    const remove=node("button","Remove",item);
    remove.type="button";
    remove.addEventListener("click",()=>{
      reveals.splice(i,1);refreshList();status.textContent="Local edits only.";
    });
  }
}
sourceSelect.addEventListener("change",refreshTargets);
document.getElementById("add").addEventListener("click",()=>{
  if(!facts.has(sourceSelect.value)||!recipientSelect.value||reveals.length>=128){
    status.textContent="Select a valid later scene; maximum 128 reveals.";return;
  }
  if(reveals.some(row=>row.fact_id===sourceSelect.value&&
                     row.recipient_scene_id===recipientSelect.value)){
    status.textContent="Duplicate knowledge reveal refused.";return;
  }
  reveals.push({fact_id:sourceSelect.value,
                recipient_scene_id:recipientSelect.value,
                required_alternative:alternativeSelect.value||null});
  refreshList();status.textContent="Local edits only; export to compile.";
});
document.getElementById("export").addEventListener("click",()=>{
  const payload={schema:"skeleton.game_builder.studio_npc_knowledge_editor_export.v1",
    project_id:model.project_id,source_digest:model.source_digest,
    session_digest:model.session_digest,
    authoring:{schema:"skeleton.game_builder.studio_npc_knowledge_authoring.v1",
               reveals:reveals.map(row=>({...row}))}};
  const blob=new Blob([JSON.stringify(payload,null,2)+"\\n"],
                      {type:"application/json"});
  const url=URL.createObjectURL(blob);
  try{
    const link=node("a",null,document.body);
    link.href=url;link.download="studio_npc_knowledge_authoring.json";
    link.click();link.remove();
  }finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
  status.textContent="Source-bound JSON exported. CLI replay verification is required.";
});
refreshTargets();refreshList();
"""


def _hash_js(text: str) -> str:
    return "'sha256-" + b64encode(sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def render_npc_knowledge_editor(
    documents: Mapping[str, Any], actions: list[list[str]],
    knowledge: Mapping[str, Any], *, authorized: bool,
) -> tuple[bytes, dict[str, object]]:
    if authorized is not True:
        raise PermissionError("NPC knowledge editor requires operator authorization")
    if type(knowledge) is not dict:
        raise StudioQuestError("invalid NPC knowledge editor input")
    compiled = compile_npc_knowledge(
        documents, actions, knowledge.get("authoring"), authorized=True,
        expected_source_digest=knowledge.get("source_digest"),
        expected_session_digest=knowledge.get("session_digest"))
    if compiled != knowledge:
        raise StudioQuestError("NPC knowledge editor lacks canonical source replay")
    staging = compile_dialogue_staging(
        documents, actions, authorized=True,
        expected_source_digest=compiled["source_digest"])
    facts = source_knowledge_facts(
        documents, actions, authorized=True,
        expected_source_digest=compiled["source_digest"],
        expected_session_digest=compiled["session_digest"])
    scenes = [{
        "scene_id": card["scene_id"], "npc_id": card["npc_id"],
        "alternatives": card["authored_alternatives"],
    } for card in staging["cards"]]
    model = {
        "schema": SCHEMA, "project_id": compiled["project_id"],
        "source_digest": compiled["source_digest"],
        "session_digest": compiled["session_digest"],
        "authoring": compiled["authoring"],
        "facts": facts["facts"], "scenes": scenes,
    }
    raw = _canonical(model).decode("ascii")
    raw = raw.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")
    policy = ("default-src 'none'; script-src " + _hash_js(raw) + " " +
              _hash_js(_JS) + "; style-src " + _hash_js(_CSS) +
              "; base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"" + policy + "\">"
        "<title>Original NPC knowledge editor</title><style>" + _CSS + "</style>"
        "</head><body><main><h1>Original NPC knowledge editor</h1>"
        "<p>Source-bound authored cues only. No new facts, speech or runtime authority.</p>"
        "<p>Project: " + escape(compiled["project_id"], quote=True) + "</p>"
        "<section><label>Source fact <select id='fact'></select></label>"
        "<label>Later recipient scene <select id='recipient'></select></label>"
        "<label>Required authored choice <select id='alternative'></select></label>"
        "<button type='button' id='add'>Add knowledge handoff</button></section>"
        "<section><h2>Edited handoffs</h2><ol id='reveals'></ol>"
        "<button type='button' id='export'>Export source-bound JSON</button>"
        "<p id='status' role='status' aria-live='polite'></p></section>"
        "<script type='application/json' id='knowledge-data'>" + raw + "</script>"
        "<script>" + _JS + "</script></main></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_EDITOR_BYTES:
        raise StudioQuestError("NPC knowledge editor exceeds byte budget")
    receipt: dict[str, object] = {
        "schema": SCHEMA, "project_id": compiled["project_id"],
        "source_digest": compiled["source_digest"],
        "session_digest": compiled["session_digest"],
        "knowledge_digest": compiled["knowledge_digest"],
        "html_sha256": sha256(html).hexdigest(),
        "html_bytes": len(html), "source_replay_verified": True,
        "authoring_export_only": True, "file_write_performed": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    receipt["editor_digest"] = _digest(receipt)
    return html, receipt


def load_npc_knowledge_editor_export(path: Path, *, authorized: bool,
                                     expected_project_id: str,
                                     expected_source_digest: str,
                                     expected_session_digest: str) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("NPC knowledge editor import requires operator authorization")
    _lease(expected_source_digest, "editor import source")
    _lease(expected_session_digest, "editor import session")
    directory = _open_directory(Path(path).parent)
    try:
        handle = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or
                    not 0 < info.st_size <= MAX_EXPORT_BYTES or
                    os.name == "posix" and
                    (info.st_uid != os.getuid() or info.st_mode & 0o077 or
                     info.st_nlink != 1)):
                raise StudioQuestError("NPC knowledge editor import must be private regular file")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(directory)
    if not raw or len(raw) > MAX_EXPORT_BYTES:
        raise StudioQuestError("invalid NPC knowledge editor import size")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate NPC knowledge editor JSON key")
            result[key] = value
        return result
    try:
        record = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite NPC knowledge editor JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC knowledge editor JSON") from exc
    if (type(record) is not dict or set(record) != {
            "schema", "project_id", "source_digest", "session_digest", "authoring"} or
            record["schema"] != EXPORT_SCHEMA or
            record["project_id"] != expected_project_id or
            record["source_digest"] != expected_source_digest or
            record["session_digest"] != expected_session_digest or
            type(record["authoring"]) is not dict or
            record["authoring"].get("schema") != REQUEST_SCHEMA):
        raise StudioQuestError("stale or forged NPC knowledge editor source")
    return record["authoring"]
