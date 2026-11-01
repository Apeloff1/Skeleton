"""Deterministic authored caption and audio cue rehearsal for studio scenes.

No samples are synthesized or played. Every cue binds an authored source layer
to an exact canonical quest replay and scene schedule; output is an accessible
caption plan for a playable director, not evidence of recorded or licensed audio.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory,
    compile_scene_schedule,
)

SCHEMA = "skeleton.game_builder.studio_audio_cue_plan.v1"
REQUEST_SCHEMA = "skeleton.game_builder.studio_audio_cue_authoring.v1"
FILENAME = "studio_audio_cues.json"
MAX_CUES = 256
MAX_SCENES = 64
MAX_BYTES = 256 * 1024
MAX_CAPTION = 280


def _text(value: object, label: str, *, maximum: int = MAX_CAPTION) -> str:
    if (type(value) is not str or not value or len(value) > maximum
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise StudioQuestError("invalid audio " + label)
    return value


def _number(value: object, label: str, *, minimum: int = 0,
            maximum: int = 1_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise StudioQuestError("invalid audio " + label)
    return value


def _layers(documents: Mapping[str, Any]) -> tuple[str, dict[str, dict[str, str]]]:
    audio = documents.get("audio")
    if type(audio) is not dict or audio.get("release_certified") is not False:
        raise StudioQuestError("missing canonical non-certified audio source")
    layers = audio.get("sound_layers")
    if type(layers) is not list or not 1 <= len(layers) <= 64:
        raise StudioQuestError("authored sound layer list required")
    accessibility = audio.get("audio_accessibility")
    if (type(accessibility) is not list
            or any(type(value) is not str for value in accessibility)
            or not {"complete_captions", "no_audio_only_navigation"}.issubset(
                set(accessibility))):
        raise StudioQuestError("authored caption and non-audio navigation obligations missing")
    mapped: dict[str, dict[str, str]] = {}
    for layer in layers:
        if type(layer) is not dict or not {"id", "source", "trigger", "ducking", "spatial"}.issubset(layer):
            raise StudioQuestError("invalid authored sound layer")
        key = _text(layer["id"], "layer ID", maximum=80)
        if key in mapped:
            raise StudioQuestError("duplicate sound layer ID")
        mapped[key] = {
            "source": _text(layer["source"], "source description", maximum=512),
            "trigger": _text(layer["trigger"], "trigger", maximum=256),
            "ducking": _text(layer["ducking"], "ducking", maximum=80),
            "spatial": _text(layer["spatial"], "spatial", maximum=80),
        }
    return _digest(audio), mapped


def _validate_request(request: object, scene_ids: set[str]) -> dict[str, Any]:
    if (type(request) is not dict or set(request) != {"schema", "scene_cues"}
            or request.get("schema") != REQUEST_SCHEMA):
        raise StudioQuestError("invalid typed audio cue authoring request")
    cues = request["scene_cues"]
    if type(cues) is not dict or set(cues) != scene_ids:
        raise StudioQuestError("audio cue scene identities differ from canonical schedule")
    if len(_canonical(request)) > 64 * 1024:
        raise StudioQuestError("audio cue authoring request exceeds budget")
    return request


def compile_audio_cues(
    documents: Mapping[str, Any], actions: list[list[str]], schedule: object,
    request: object, *, authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, Any]:
    """Compile a bounded timeline with source, schedule, and session custody."""
    if authorized is not True:
        raise PermissionError("audio cue compilation requires operator authorization")
    _lease(expected_source_digest, "audio source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "audio session")
    timing = compile_scene_schedule(
        documents, actions, schedule, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    audio_digest, layers = _layers(documents)
    rows = timing["timeline"]
    if not 1 <= len(rows) <= MAX_SCENES:
        raise StudioQuestError("invalid audio scene count")
    authored = _validate_request(request, {row["scene_id"] for row in rows})
    result_rows: list[dict[str, Any]] = []
    total = 0
    for scene in rows:
        scene_id = scene["scene_id"]
        authored_cues = authored["scene_cues"][scene_id]
        if type(authored_cues) is not list or not 1 <= len(authored_cues) <= 16:
            raise StudioQuestError("each scene requires 1-16 authored caption cues")
        used: dict[str, int] = {}
        cues: list[dict[str, Any]] = []
        for cue in authored_cues:
            if type(cue) is not dict or set(cue) != {
                    "layer_id", "start_offset", "duration_ticks", "caption"}:
                raise StudioQuestError("invalid audio cue fields")
            layer_id = _text(cue["layer_id"], "cue layer", maximum=80)
            if layer_id not in layers:
                raise StudioQuestError("audio cue references unregistered sound layer")
            offset = _number(cue["start_offset"], "cue offset")
            duration = _number(cue["duration_ticks"], "cue duration", minimum=1)
            if offset + duration > scene["duration_ticks"]:
                raise StudioQuestError("audio cue exceeds authored scene duration")
            if offset < used.get(layer_id, 0):
                raise StudioQuestError("same-layer audio cues overlap or are out of order")
            used[layer_id] = offset + duration
            caption = _text(cue["caption"], "caption")
            absolute_start = scene["start_tick"] + offset
            entry: dict[str, Any] = {
                "scene_id": scene_id, "layer_id": layer_id,
                "start_tick": absolute_start,
                "end_tick": absolute_start + duration,
                "caption": caption,
                "trigger": layers[layer_id]["trigger"],
                "ducking": layers[layer_id]["ducking"],
                "spatial": layers[layer_id]["spatial"],
                "authored_source": layers[layer_id]["source"],
                "audio_recording_verified": False,
                "caption_runtime_verified": False,
            }
            entry["cue_digest"] = _digest(entry)
            cues.append(entry)
            total += 1
            if total > MAX_CUES:
                raise StudioQuestError("audio cue budget exceeded")
        scene_row: dict[str, Any] = {
            "scene_id": scene_id, "scene_proof_digest": scene["scene_proof_digest"],
            "start_tick": scene["start_tick"], "end_tick": scene["end_tick"],
            "cues": cues,
        }
        scene_row["scene_audio_digest"] = _digest(scene_row)
        result_rows.append(scene_row)
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": timing["project_id"],
        "source_digest": timing["source_digest"],
        "quest_source_digest": timing["quest_source_digest"],
        "session_digest": timing["session_digest"],
        "schedule_digest": timing["schedule_digest"],
        "audio_source_digest": audio_digest,
        "request_digest": _digest(authored),
        "scene_count": len(result_rows), "cue_count": total,
        "scenes": result_rows, "source_replay_verified": True,
        "captions_authored": True, "captions_rendered_verified": False,
        "audio_recorded_verified": False, "native_audio_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES:
        raise StudioQuestError("audio cue receipt exceeds bounded size")
    result["plan_digest"] = _digest(result)
    return result


def _verify_plan(
    plan: Mapping[str, Any], documents: Mapping[str, Any],
    actions: list[list[str]], schedule: object, request: object,
) -> bytes:
    if type(plan) is not dict or plan.get("schema") != SCHEMA:
        raise StudioQuestError("invalid audio plan receipt")
    expected = compile_audio_cues(
        documents, actions, schedule, request, authorized=True,
        expected_source_digest=_lease(plan.get("source_digest"), "published audio source"),
        expected_session_digest=_lease(plan.get("session_digest"), "published audio session"))
    if _canonical(expected) != _canonical(plan):
        raise StudioQuestError("audio plan is not canonical source replay")
    return _canonical(plan) + b"\n"


def publish_audio_cues(
    plan: Mapping[str, Any], directory: Path, *, authorized: bool,
    documents: Mapping[str, Any], actions: list[list[str]],
    schedule: object, request: object,
) -> dict[str, Any]:
    """Create a private, exclusive receipt without following directory symlinks."""
    if authorized is not True:
        raise PermissionError("audio cue publication requires operator authorization")
    data = _verify_plan(plan, documents, actions, schedule, request)
    import secrets
    directory_fd = _open_directory(directory)
    fd: int | None = None
    temporary = ".studio_audio_" + secrets.token_hex(16) + ".tmp"
    temporary_created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        temporary_created = True
        offset = 0
        while offset < len(data):
            count = os.write(fd, data[offset:])
            if count <= 0:
                raise OSError("short audio cue write")
            offset += count
        os.fsync(fd)
        os.close(fd)
        fd = None
        # Publish only fully durable bytes; never overwrite an existing receipt.
        os.link(temporary, FILENAME, src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        if temporary_created:
            os.unlink(temporary, dir_fd=directory_fd)
        os.close(directory_fd)
    return {
        "schema": SCHEMA, "plan_digest": plan["plan_digest"],
        "filename": FILENAME, "bytes": len(data),
        "sha256": sha256(data).hexdigest(), "file_write_performed": True,
        "release_certified": False,
    }


def verify_published_audio_cues(
    directory: Path, *, documents: Mapping[str, Any],
    actions: list[list[str]], schedule: object, request: object,
    expected_source_digest: str, expected_session_digest: str | None = None,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("audio cue verification requires operator authorization")
    expected = compile_audio_cues(
        documents, actions, schedule, request, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    directory_fd = _open_directory(directory)
    try:
        fd = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES + 1:
                raise StudioQuestError("published audio plan exceeds byte budget")
            chunks: list[bytes] = []
            remaining = MAX_BYTES + 2
            while remaining:
                part = os.read(fd, min(remaining, 65536))
                if not part:
                    break
                chunks.append(part)
                remaining -= len(part)
            data = b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)
    if data != _canonical(expected) + b"\n":
        raise StudioQuestError("published audio cue plan failed exact replay")
    return expected


def render_caption_preview(plan: Mapping[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Accessible offline text timeline; not a sound player or caption QA pass.

    The caller must first compile the plan from canonical source. This renderer
    rejects a tampered digest, escapes all authored text and includes no scripts.
    """
    from html import escape

    if (type(plan) is not dict or plan.get("schema") != SCHEMA
            or type(plan.get("scenes")) is not list
            or len(plan["scenes"]) > MAX_SCENES):
        raise StudioQuestError("invalid caption preview plan")
    digest = _lease(plan.get("plan_digest"), "caption preview")
    if _digest({key: value for key, value in plan.items()
                if key != "plan_digest"}) != digest:
        raise StudioQuestError("caption preview plan digest mismatch")
    parts = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta http-equiv=\"Content-Security-Policy\" ",
        "content=\"default-src 'none'; base-uri 'none'; form-action 'none'\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Original scene caption rehearsal</title></head><body>",
        "<main><h1>Original scene caption rehearsal</h1>",
        "<p>Authored text only. No sound recorded, audio played, or native caption timing verified.</p>",
    ]
    count = 0
    for scene in plan["scenes"]:
        if (type(scene) is not dict or type(scene.get("scene_id")) is not str
                or type(scene.get("cues")) is not list
                or len(scene["cues"]) > 16):
            raise StudioQuestError("invalid caption preview scene")
        parts.append("<section aria-label=\"Scene captions\"><h2>" +
                     escape(scene["scene_id"], quote=True) + "</h2><ol>")
        for cue in scene["cues"]:
            if (type(cue) is not dict or type(cue.get("caption")) is not str
                    or type(cue.get("start_tick")) is not int
                    or type(cue.get("end_tick")) is not int):
                raise StudioQuestError("invalid caption preview cue")
            caption = _text(cue["caption"], "preview caption")
            start = _number(cue["start_tick"], "preview start")
            end = _number(cue["end_tick"], "preview end", minimum=start + 1)
            parts.append("<li><strong>Ticks " + str(start) + "–" + str(end) +
                         "</strong>: " + escape(caption, quote=True) + "</li>")
            count += 1
        parts.append("</ol></section>")
    if count != plan.get("cue_count"):
        raise StudioQuestError("caption preview cue count mismatch")
    parts.append("</main></body></html>")
    output = "".join(parts).encode("utf-8", "strict")
    if len(output) > MAX_BYTES:
        raise StudioQuestError("caption preview exceeds bounded size")
    return output, {
        "schema": "skeleton.game_builder.studio_audio_caption_preview.v1",
        "plan_digest": digest, "html_sha256": sha256(output).hexdigest(),
        "caption_count": count, "authored_text_only": True,
        "native_caption_runtime_verified": False,
        "audio_playback_verified": False, "release_certified": False,
    }


def render_audio_cue_editor(
    plan: Mapping[str, Any], documents: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    """Offline editable caption timeline exporting typed JSON for CLI replay.

    This browser is untrusted: it can propose edits but never signs or
    publishes receipts. The CLI/Jeeves compiler must independently revalidate.
    """
    import base64
    from html import escape

    if (type(plan) is not dict or plan.get("schema") != SCHEMA
            or type(plan.get("scenes")) is not list):
        raise StudioQuestError("invalid audio editor plan")
    digest = _lease(plan.get("plan_digest"), "audio editor")
    if _digest({key: value for key, value in plan.items()
                if key != "plan_digest"}) != digest:
        raise StudioQuestError("audio editor plan digest mismatch")
    audio_digest, layers = _layers(documents)
    if audio_digest != plan.get("audio_source_digest"):
        raise StudioQuestError("stale audio editor source lease")
    scenes: dict[str, list[dict[str, Any]]] = {}
    for row in plan["scenes"]:
        if type(row) is not dict or type(row.get("cues")) is not list:
            raise StudioQuestError("invalid audio editor scene")
        scene_id = _text(row.get("scene_id"), "editor scene", maximum=256)
        if scene_id in scenes:
            raise StudioQuestError("duplicate audio editor scene")
        start = _number(row.get("start_tick"), "editor scene start")
        cues: list[dict[str, Any]] = []
        for cue in row["cues"]:
            if type(cue) is not dict or cue.get("layer_id") not in layers:
                raise StudioQuestError("invalid audio editor cue")
            cue_start = _number(cue.get("start_tick"), "editor cue start")
            cue_end = _number(cue.get("end_tick"), "editor cue end",
                              minimum=cue_start + 1)
            if cue_start < start:
                raise StudioQuestError("audio editor cue starts before scene")
            cues.append({
                "layer_id": cue["layer_id"],
                "start_offset": cue_start - start,
                "duration_ticks": cue_end - cue_start,
                "caption": _text(cue.get("caption"), "editor caption"),
            })
        scenes[scene_id] = cues
    if len(scenes) != plan.get("scene_count"):
        raise StudioQuestError("audio editor scene count mismatch")
    seed = {
        "schema": REQUEST_SCHEMA, "scene_cues": scenes,
    }
    seed_json = _canonical(seed).decode("ascii").replace("<", "\\u003c")
    layer_json = _canonical(sorted(layers)).decode("ascii").replace("<", "\\u003c")
    script = """(function(){
"use strict";
const seed=JSON.parse(document.getElementById("audio-seed").textContent);
const layers=JSON.parse(document.getElementById("audio-layers").textContent);
const host=document.getElementById("audio-editor");
function node(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
function field(label,value,kind){const wrap=node("label",label+" ");const input=node("input");
 input.type=kind||"text";input.value=String(value);input.setAttribute("aria-label",label);
 if(kind==="number"){input.min="0";input.step="1";}wrap.appendChild(input);return [wrap,input];}
function addCue(list,cue){const item=node("li");item.className="audio-cue";
 const select=node("select");select.setAttribute("aria-label","Authored sound layer");
 for(const layer of layers){const opt=node("option",layer);opt.value=layer;select.appendChild(opt);}
 select.value=cue.layer_id;item.appendChild(select);
 const start=field("Start offset",cue.start_offset,"number");
 const duration=field("Duration ticks",cue.duration_ticks,"number");
 const caption=field("Accessible caption",cue.caption);
 item.appendChild(start[0]);item.appendChild(duration[0]);item.appendChild(caption[0]);
 const remove=node("button","Remove cue");remove.type="button";
 remove.addEventListener("click",function(){item.remove();});
 item.appendChild(remove);list.appendChild(item);
}
for(const sceneId of Object.keys(seed.scene_cues)){
 const section=node("section");section.dataset.sceneId=sceneId;
 section.appendChild(node("h2",sceneId));const list=node("ol");
 for(const cue of seed.scene_cues[sceneId])addCue(list,cue);
 section.appendChild(list);const add=node("button","Add cue");add.type="button";
 add.addEventListener("click",function(){
   addCue(list,{layer_id:layers[0],start_offset:0,duration_ticks:1,
     caption:"Describe original audible event"});
 });section.appendChild(add);host.appendChild(section);
}
document.getElementById("audio-export").addEventListener("click",function(){
 const result={schema:seed.schema,scene_cues:{}};
 for(const section of host.querySelectorAll("section")){
  const cues=[];for(const row of section.querySelectorAll("li.audio-cue")){
   const inputs=row.querySelectorAll("input");
   cues.push({layer_id:row.querySelector("select").value,
    start_offset:Number(inputs[0].value),duration_ticks:Number(inputs[1].value),
    caption:inputs[2].value});
  }result.scene_cues[section.dataset.sceneId]=cues;
 }
 const data=JSON.stringify(result,null,2)+"\\n";
 const blob=new Blob([data],{type:"application/json"});
 const url=URL.createObjectURL(blob);const link=node("a");
 link.href=url;link.download="studio_audio_cue_authoring.json";
 document.body.appendChild(link);link.click();link.remove();
 setTimeout(function(){URL.revokeObjectURL(url);},0);
});
})();"""
    script_hash = base64.b64encode(sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' +
        escape(csp, quote=True) + '">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Original audio cue editor</title></head><body><main>'
        '<h1>Original audio cue editor</h1>'
        '<p>Offline authoring only. Recompile exported JSON with the canonical CLI; '
        'browser exports do not prove audio playback or release readiness.</p>'
        '<div id="audio-editor"></div><button id="audio-export" type="button">'
        'Export typed cue edits</button></main>'
        '<script type="application/json" id="audio-seed">' + seed_json + '</script>'
        '<script type="application/json" id="audio-layers">' + layer_json + '</script>'
        '<script>' + script + '</script></body></html>'
    )
    html = page.encode("utf-8", "strict")
    if len(html) > MAX_BYTES:
        raise StudioQuestError("audio editor HTML exceeds byte budget")
    return html, {
        "schema": "skeleton.game_builder.studio_audio_cue_editor.v1",
        "plan_digest": digest, "audio_source_digest": audio_digest,
        "html_sha256": sha256(html).hexdigest(),
        "script_sha256": sha256(script.encode("utf-8")).hexdigest(),
        "export_schema": REQUEST_SCHEMA,
        "browser_export_authoritative": False, "file_write_performed": False,
        "native_audio_verified": False, "release_certified": False,
    }


__all__ = [
    "SCHEMA", "REQUEST_SCHEMA", "FILENAME", "compile_audio_cues",
    "publish_audio_cues", "verify_published_audio_cues", "render_caption_preview",
    "render_audio_cue_editor",
]
