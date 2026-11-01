"""Source-bound offline quest-choice rehearsal for the playable director handoff.

This is an interactive original-authoring companion, not a replacement for the
canonical HTML5 game. Browser decisions are untrusted until Python replays the
complete exported history against the exact authored quest and canon.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
)
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease, _open_directory

SCHEMA = "skeleton.game_builder.studio_choice_rehearsal.v1"
EXPORT_SCHEMA = "skeleton.game_builder.studio_choice_rehearsal_export.v1"
EXPORT_FILENAME = "studio_choice_rehearsal.json"
MAX_EXPORT_BYTES = 16 * 1024
MAX_HTML_BYTES = 256 * 1024
_EXPORT_FIELDS = frozenset({
    "schema", "project_id", "source_digest", "quest_source_digest",
    "base_session_digest", "base_actions", "actions",
})

_CSS = """
:root{font:16px/1.5 system-ui,sans-serif;color-scheme:dark;background:#10232e;color:#f2faff}
body{margin:0 auto;max-width:64rem;padding:1.25rem}
section{border:1px solid #6e929d;border-radius:.5rem;padding:1rem;margin:1rem 0}
button{font:inherit;padding:.55rem .8rem;margin:.25rem;background:#1d4c61;color:#fff;border:1px solid #b1d8e5;border-radius:.25rem}
button:focus-visible,a:focus-visible{outline:3px solid #ffe399;outline-offset:2px}
a{color:#a9eaff}code{overflow-wrap:anywhere}
.warning{border-left:4px solid #ffcd80;padding:.5rem}
li{margin:.35rem 0}small{color:#cce2eb}
"""

_JS = r"""
"use strict";
const model=JSON.parse(document.getElementById("choice-data").textContent);
const baseline=model.history.length;
let history=model.history.map(pair=>pair.slice());
const root=document.getElementById("choices");
const endings=document.getElementById("endings");
const status=document.getElementById("status");
function element(tag,text,parent){
  const node=document.createElement(tag);
  if(text!==null)node.textContent=text;
  if(parent)parent.appendChild(node);
  return node;
}
function state(){
  const completed=new Set();
  const facts=new Set();
  for(const pair of history){
    const stage=model.stages.find(row=>row.id===pair[0]);
    if(!stage||completed.has(stage.id)||!stage.alternatives.includes(pair[1])
       ||!stage.prerequisites.every(dep=>completed.has(dep))){
      throw Error("Invalid rehearsal history");
    }
    completed.add(stage.id);
    facts.add(stage.id);
    facts.add(stage.reward);
    for(const token of (stage.choice_effects[pair[1]]||[]))facts.add(token);
  }
  return {completed,facts};
}
function redraw(){
  root.replaceChildren();endings.replaceChildren();
  const {completed,facts}=state();
  for(const stage of model.stages){
    const group=element("section",null,root);
    element("h2",stage.id+" — "+stage.scene_id,group);
    element("p","NPC "+stage.npc_id+" · "+stage.site+" · ticks "+
      stage.start_tick+"–"+stage.end_tick,group);
    const chosen=history.find(pair=>pair[0]===stage.id);
    if(chosen){element("p","Selected: "+chosen[1],group);continue;}
    if(!stage.prerequisites.every(dep=>completed.has(dep))){
      element("p","Locked: requires "+stage.prerequisites.filter(dep=>!completed.has(dep)).join(", "),group);
      continue;
    }
    for(const alternative of stage.alternatives){
      const button=element("button","Choose "+alternative,group);
      button.type="button";
      button.addEventListener("click",()=>{
        history.push([stage.id,alternative]);redraw();
        status.textContent="Local rehearsal changed. Export to verify against canonical source.";
      });
    }
  }
  element("h2","Authored ending predicates (sandbox only)",endings);
  const list=element("ul",null,endings);
  for(const ending of model.endings){
    const missing=ending.requires.filter(token=>!facts.has(token));
    element("li",ending.id+": "+(missing.length?"Unmet: "+missing.join(", "):"Eligible in rehearsal"),list);
  }
  document.getElementById("undo").disabled=history.length<=baseline;
  document.getElementById("export").disabled=history.length>64;
}
function download(value){
  const blob=new Blob([JSON.stringify(value,null,2)+"\n"],{type:"application/json"});
  const url=URL.createObjectURL(blob);
  try{
    const a=document.createElement("a");a.href=url;
    a.download="studio_choice_rehearsal.json";
    document.body.appendChild(a);a.click();a.remove();
  }finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
}
document.getElementById("undo").addEventListener("click",()=>{
  if(history.length>baseline){history.pop();redraw();status.textContent="Last local choice undone.";}
});
document.getElementById("export").addEventListener("click",()=>{
  state();
  download({
    schema:"skeleton.game_builder.studio_choice_rehearsal_export.v1",
    project_id:model.project_id,source_digest:model.source_digest,
    quest_source_digest:model.quest_source_digest,
    base_session_digest:model.base_session_digest,
    base_actions:model.history,actions:history
  });
  status.textContent="Untrusted choice JSON exported. Verify using the Python CLI.";
});
redraw();
"""

def _csp_hash(source: str) -> str:
    return "'sha256-" + base64.b64encode(sha256(source.encode("utf-8")).digest()).decode("ascii") + "'"


def render_choice_rehearsal(
    documents: Mapping[str, Any], actions: list[list[str]],
    schedule: Mapping[str, Any], *, authorized: bool,
    expected_source_digest: str,
) -> tuple[bytes, dict[str, object]]:
    """Produce an interactive choice authoring page from verified canonical source."""
    if authorized is not True:
        raise PermissionError("choice rehearsal requires operator authorization")
    _lease(expected_source_digest, "choice rehearsal source")
    proof = audit_canon_source(documents, authorized=True)
    program = compile_quest_program(documents)
    session = replay_quest(documents, actions, authorized=True)
    if proof.get("canon_consistent") is not True or proof.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale or contradictory choice rehearsal canon")
    if type(schedule) is not dict:
        raise StudioQuestError("choice rehearsal requires canonical schedule")
    digest = schedule.get("schedule_digest")
    if (type(digest) is not str or _digest({k: v for k, v in schedule.items()
                                           if k != "schedule_digest"}) != digest
            or schedule.get("source_digest") != expected_source_digest
            or schedule.get("quest_source_digest") != program.source_digest
            or schedule.get("session_digest") != session.digest
            or schedule.get("project_id") != program.project_id
            or schedule.get("replay_verified") is not True):
        raise StudioQuestError("choice rehearsal schedule lease mismatch")
    rows = schedule.get("timeline")
    if type(rows) is not list or len(rows) != len(program.stages) or len(rows) > 64:
        raise StudioQuestError("choice rehearsal scene inventory mismatch")
    by_stage: dict[str, dict[str, Any]] = {}
    scene_ids: set[str] = set()
    for row in rows:
        if type(row) is not dict or type(row.get("quest_stage")) is not str:
            raise StudioQuestError("invalid choice rehearsal timeline row")
        stage_id, scene_id = row["quest_stage"], row.get("scene_id")
        if (stage_id in by_stage or type(scene_id) is not str or scene_id in scene_ids
                or type(row.get("start_tick")) is not int
                or type(row.get("end_tick")) is not int
                or row["end_tick"] <= row["start_tick"]):
            raise StudioQuestError("invalid choice rehearsal scene timing or identity")
        by_stage[stage_id] = row
        scene_ids.add(scene_id)
    if set(by_stage) != set(program.stage_ids):
        raise StudioQuestError("choice rehearsal stages diverge from authored source")
    stages: list[dict[str, Any]] = []
    for stage in program.stages:
        row = by_stage[stage.key]
        stages.append({
            "id": stage.key, "prerequisites": list(stage.prerequisites),
            "alternatives": list(stage.alternatives), "reward": stage.reward,
            "choice_effects": {key: list(tokens) for key, tokens in stage.choice_effects},
            "scene_id": row["scene_id"], "npc_id": row["npc_id"],
            "site": row["site"], "start_tick": row["start_tick"],
            "end_tick": row["end_tick"],
        })
    model = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": expected_source_digest,
        "quest_source_digest": program.source_digest,
        "base_session_digest": session.digest,
        "history": [list(pair) for pair in session.choices],
        "stages": stages,
        "endings": [{"id": key, "requires": list(reqs)} for key, reqs in program.endings],
    }
    raw = _canonical(model)
    if len(raw) > 64 * 1024:
        raise StudioQuestError("choice rehearsal model exceeds byte budget")
    # Escaping '<' is mandatory even in an application/json script element.
    encoded = raw.decode("ascii").replace("<", "\\u003c")
    csp = ("default-src 'none'; base-uri 'none'; connect-src 'none'; "
           "img-src data:; form-action 'none'; script-src " + _csp_hash(_JS)
           + "; style-src " + _csp_hash(_CSS))
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">'
        '<title>Original quest choice rehearsal</title><style>' + _CSS + '</style></head>'
        '<body><header><h1>Original quest choice rehearsal</h1>'
        '<p class="warning">This is an offline authored-choice rehearsal, not verified NPC '
        'dialogue execution or native gameplay. Browser exports are untrusted.</p>'
        '<p><a href="index.html">Playable HTML5 geometry</a> · '
        '<a href="director_editor.html">Director timing editor</a></p>'
        '<small>Canon: <code>' + escape(expected_source_digest) + '</code></small></header>'
        '<main><div id="choices"></div><section id="endings"></section>'
        '<section><button id="undo" type="button">Undo local choice</button>'
        '<button id="export" type="button">Export source-bound choices</button>'
        '<p id="status" role="status" aria-live="polite">No local edits.</p></section></main>'
        '<script type="application/json" id="choice-data">' + encoded + '</script>'
        '<script>' + _JS + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("choice rehearsal HTML exceeds byte budget")
    receipt: dict[str, object] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": expected_source_digest,
        "quest_source_digest": program.source_digest,
        "base_session_digest": session.digest,
        "model_digest": _digest(model), "html_sha256": sha256(html).hexdigest(),
        "authored_choice_rehearsal": True,
        "browser_export_trusted": False, "npc_dialogue_executed_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    receipt["receipt_digest"] = _digest(receipt)
    return html, receipt


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StudioQuestError("duplicate choice rehearsal JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise StudioQuestError("nonfinite choice rehearsal JSON")


def load_choice_export(path: Path) -> dict[str, Any]:
    """Read only a bounded regular leaf through symlink-safe directory descriptors."""
    if not isinstance(path, Path) or path.name != EXPORT_FILENAME or ".." in path.parts:
        raise StudioQuestError("choice export requires canonical filename")
    if not all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_NONBLOCK", "O_DIRECTORY")):
        raise StudioQuestError("secure choice import unavailable")
    directory_fd = _open_directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory_fd)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_EXPORT_BYTES:
                raise StudioQuestError("choice export must be a bounded regular file")
            chunks: list[bytes] = []
            total = 0
            while total <= MAX_EXPORT_BYTES:
                block = os.read(fd, min(4096, MAX_EXPORT_BYTES + 1 - total))
                if not block:
                    break
                chunks.append(block)
                total += len(block)
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise StudioQuestError("choice export changed during read")
            raw = b"".join(chunks)
            if len(raw) != before.st_size or len(raw) > MAX_EXPORT_BYTES:
                raise StudioQuestError("choice export changed or exceeds byte budget")
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)
    try:
        value = json.loads(raw.decode("utf-8", "strict"),
                           object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid choice export JSON") from exc
    if type(value) is not dict or set(value) != _EXPORT_FIELDS:
        raise StudioQuestError("choice export fields mismatch")
    return value


def replay_choice_export(
    documents: Mapping[str, Any], export: Mapping[str, Any], *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str,
) -> dict[str, object]:
    """Re-run every browser action through the authoritative quest engine."""
    if authorized is not True:
        raise PermissionError("choice export replay requires operator authorization")
    _lease(expected_source_digest, "choice export canon")
    _lease(expected_session_digest, "choice export baseline")
    if type(export) is not dict or set(export) != _EXPORT_FIELDS:
        raise StudioQuestError("choice export has unexpected fields")
    program = compile_quest_program(documents)
    proof = audit_canon_source(documents, authorized=True)
    if (export.get("schema") != EXPORT_SCHEMA
            or export.get("project_id") != program.project_id
            or export.get("source_digest") != expected_source_digest
            or proof.get("source_digest") != expected_source_digest
            or proof.get("canon_consistent") is not True
            or export.get("quest_source_digest") != program.source_digest
            or export.get("base_session_digest") != expected_session_digest):
        raise StudioQuestError("choice export source or session lease mismatch")
    baseline, actions = export["base_actions"], export["actions"]
    if (type(baseline) is not list or type(actions) is not list
            or len(baseline) > 64 or len(actions) > 64
            or len(_canonical(export)) > MAX_EXPORT_BYTES
            or actions[:len(baseline)] != baseline):
        raise StudioQuestError("choice export history is not an append-only rehearsal")
    previous = replay_quest(documents, baseline, authorized=True)
    if previous.digest != expected_session_digest:
        raise StudioQuestError("choice export baseline replay mismatch")
    current = replay_quest(documents, actions, authorized=True)
    progress = quest_progress(current, documents)
    result: dict[str, object] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": expected_source_digest,
        "quest_source_digest": program.source_digest,
        "base_session_digest": previous.digest,
        "result_session_digest": current.digest,
        "verified_actions": [list(pair) for pair in current.choices],
        "progress": progress, "replay_verified": True,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    result["result_digest"] = _digest(result)
    return result
