"""Accessible offline HTML editor for canonical scene timings and asset recipes.

The browser edits explicit typed JSON, never a project file or privileged
source. Only the CLI/Jeeves compiler may validate the exported authoring data.
All untrusted source labels enter text nodes; no dynamic code evaluation.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from html import escape
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical, _digest

EDITOR_SCHEMA = "skeleton.game_builder.studio_director_editor.v1"
MAX_EDITOR_BYTES = 512 * 1024

_CSS = """
:root{font:16px/1.5 system-ui,sans-serif;color-scheme:dark;background:#10232e;color:#eef9fa}
body{margin:0 auto;max-width:1000px;padding:1.25rem}
h1,h2{line-height:1.25}p{max-width:72ch}
a{color:#a2e8ff}section{border:1px solid #49727e;padding:1rem;margin:1rem 0;border-radius:.6rem}
fieldset{border:1px solid #456675;margin:.8rem 0;padding:.8rem}
legend{font-weight:700}label{display:block;margin:.5rem 0}
input,select,button{font:inherit;background:#1c3b4c;color:#fff;border:1px solid #83a8b7;padding:.35rem}
input{width:9rem}select{max-width:100%}button{padding:.6rem 1rem;cursor:pointer}
button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #ffe399;outline-offset:2px}
code{overflow-wrap:anywhere}small{color:#c9dfe5}
.warning{border-left:4px solid #ffce82;padding-left:.75rem}
"""

_JS = """
"use strict";
const model=JSON.parse(document.getElementById("director-data").textContent);
const root=document.getElementById("editor");
const status=document.getElementById("status");
const schedule=structuredClone(model.schedule);
const assignments=structuredClone(model.assignments);
function element(tag,text,parent){
  const node=document.createElement(tag);
  if(text!==null)node.textContent=text;
  if(parent)parent.appendChild(node);
  return node;
}
function numeric(parent,label,value,min,max,apply){
  const wrap=element("label",null,parent);
  element("span",label+" ",wrap);
  const input=element("input",null,wrap);
  input.type="number";input.min=String(min);input.max=String(max);
  input.step="1";input.value=String(value);input.required=true;
  input.addEventListener("input",()=>{
    const n=Number(input.value);
    if(!Number.isSafeInteger(n)||n<min||n>max){
      input.setCustomValidity("Enter an integer from "+min+" to "+max);
      status.textContent="Invalid editor input; export disabled.";
    }else{
      input.setCustomValidity("");
      apply(n);status.textContent="Unsaved local edits.";
    }
  });
}
numeric(root,"NPC turnaround ticks",schedule.npc_turnaround_ticks,0,100000,
  n=>{schedule.npc_turnaround_ticks=n;});
for(const scene of model.scenes){
  const group=element("fieldset",null,root);
  element("legend",scene.scene_id+" — "+scene.quest_stage,group);
  element("p","NPC "+scene.npc_id+"; quest status "+scene.status,group);
  numeric(group,"Scene duration ticks",schedule.scene_ticks[scene.scene_id],1,100000,
    n=>{schedule.scene_ticks[scene.scene_id]=n;});
  numeric(group,"Earliest start tick",schedule.min_start_ticks[scene.scene_id]??0,
    0,1000000,n=>{schedule.min_start_ticks[scene.scene_id]=n;});
  for(const asset of scene.bindings){
    const wrap=element("label",null,group);
    element("span","Original asset "+asset.asset_id+" → ",wrap);
    const select=element("select",null,wrap);
    for(const recipe of model.recipes){
      const option=element("option",recipe.recipe_id+" ("+recipe.recipe_kind+")",select);
      option.value=recipe.recipe_id;
    }
    select.value=assignments[scene.scene_id][asset.asset_id];
    select.addEventListener("change",()=>{
      assignments[scene.scene_id][asset.asset_id]=select.value;
      status.textContent="Unsaved local edits.";
    });
  }
}
function download(name,data){
  const blob=new Blob([JSON.stringify(data,null,2)+"\n"],{type:"application/json"});
  const url=URL.createObjectURL(blob);
  try{
    const anchor=document.createElement("a");
    anchor.href=url;anchor.download=name;
    document.body.appendChild(anchor);anchor.click();anchor.remove();
  }finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
}
const save=element("button","Export both authoring JSON files",root);
save.type="button";
save.addEventListener("click",()=>{
  if(!root.querySelectorAll("input:invalid").length){
    download("studio_scene_schedule.json",schedule);
    download("studio_scene_assignments.json",assignments);
    status.textContent="JSON exported. Recompile with source-bound CLI; no game changed.";
  }else{status.textContent="Correct invalid fields before export.";}
});
"""

def _hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _csp_hash(source: str) -> str:
    return "'sha256-" + base64.b64encode(sha256(source.encode("utf-8")).digest()).decode("ascii") + "'"


def render_director_editor(
    schedule: Mapping[str, Any], assets: Mapping[str, Any],
) -> tuple[bytes, dict[str, object]]:
    """Render local editable form with exact source/quest lease provenance."""
    if (type(schedule) is not dict or type(assets) is not dict
            or schedule.get("source_digest") != assets.get("source_digest")
            or schedule.get("session_digest") != assets.get("session_digest")
            or schedule.get("scene_count") != assets.get("scene_count")
            or schedule.get("scene_count", 0) > 64):
        raise StudioQuestError("director editor source or session identity mismatch")
    scenes = schedule.get("timeline")
    bound = assets.get("scenes")
    if (type(scenes) is not list or type(bound) is not list
            or len(scenes) != len(bound)
            or [row.get("scene_id") for row in scenes] != [
                row.get("scene_id") for row in bound]):
        raise StudioQuestError("director editor scene order mismatch")
    # Editing must offer *every* source-authorized recipe, not only recipes
    # already selected in the current binding work orders.
    recipes = assets.get("available_recipes")
    if type(recipes) is not list or not recipes:
        raise StudioQuestError("director editor has no original asset recipes")
    model = {
        "schema": EDITOR_SCHEMA,
        "source_digest": schedule["source_digest"],
        "visual_digest": assets["visual_digest"],
        "session_digest": schedule["session_digest"],
        "schedule": schedule["schedule_request"],
        "assignments": assets["assignments"],
        "scenes": [{
            "scene_id": row["scene_id"], "quest_stage": row["quest_stage"],
            "npc_id": row["npc_id"], "status": row["status"],
            "bindings": [
                {"asset_id": item["asset_id"]} for item in bound[index]["bindings"]
            ],
        } for index, row in enumerate(scenes)],
        "recipes": [{"recipe_id": item["recipe_id"], "recipe_kind": item["recipe_kind"]}
                    for item in recipes],
        "native_assets_verified": False, "release_certified": False,
    }
    raw = _canonical(model)
    if len(raw) > 128 * 1024:
        raise StudioQuestError("director editor input exceeds byte budget")
    # An HTML parser terminates any script element at a literal </script>,
    # even when its type is application/json. Escape ALL '<' before embedding.
    data = raw.decode("ascii").replace("<", "\\u003c")
    csp = ("default-src 'none'; base-uri 'none'; connect-src 'none'; "
           "img-src data:; form-action 'none'; "
           "script-src " + _csp_hash(_JS) + "; style-src " + _csp_hash(_CSS))
    html = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"" + escape(csp, quote=True) + "\">"
        "<title>Original world director editor</title><style>" + _CSS + "</style>"
        "</head><body><header><h1>Original world director editor</h1>"
        "<p>Source-bound local scene timing and asset recipe authoring.</p>"
        "<p class=\"warning\">Preview geometry is playable, but NPC speech, "
        "native asset binding and release are not verified.</p>"
        "<p><a href=\"index.html\">Open verified offline HTML5 game</a></p>"
        "<small>Source digest: <code>" + escape(schedule["source_digest"]) + "</code></small>"
        "</header><main><section><h2>Authoring controls</h2><div id=\"editor\"></div>"
        "<p id=\"status\" role=\"status\" aria-live=\"polite\">No edits made.</p>"
        "</section></main><script type=\"application/json\" id=\"director-data\">"
        + data + "</script><script>" + _JS + "</script></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_EDITOR_BYTES:
        raise StudioQuestError("director editor HTML exceeds byte budget")
    receipt: dict[str, object] = {
        "schema": EDITOR_SCHEMA, "source_digest": schedule["source_digest"],
        "visual_digest": assets["visual_digest"],
        "session_digest": schedule["session_digest"],
        "html_sha256": _hash(html),
        "model_digest": _digest(model),
        "offline": True, "authoring_export_only": True,
        "native_asset_binding_verified": False,
        "release_certified": False,
    }
    receipt["receipt_digest"] = _digest(receipt)
    return html, receipt
