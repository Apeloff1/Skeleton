"""Offline, CSP-hashed authoring UI for a typed playable waypoint request.

The browser edits request JSON only. Python/Jeeves perform all authoritative
source checks and gameplay compilation after explicit operator submission.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
import os
from pathlib import Path
import secrets

from .studio_ecosystem_scene_schedule import _open_directory, _write_all

FILENAME = "studio_waypoint_handoff_editor.html"
REQUEST_SCHEMA = "skeleton.jeeves.studio_waypoint_handoff_request.v1"
_SCRIPT = r"""
"use strict";
const field=id=>document.getElementById(id);
field("compile").addEventListener("click",()=>{
  const status=field("status");
  status.textContent="";
  field("output").value="";
  try{
    const session=JSON.parse(field("session").value);
    const waypoints=JSON.parse(field("waypoints").value);
    const budget=Number(field("budget").value);
    const source=field("source").value.trim();
    const lease=field("lease").value.trim();
    const project=field("project").value.trim();
    if(!/^[0-9a-f]{64}$/.test(source)||!/^[0-9a-f]{64}$/.test(lease))
      throw Error("SHA-256 source and session leases are required");
    if(!project||project.length>128)throw Error("Invalid project id");
    if(!Array.isArray(waypoints)||waypoints.length>8)
      throw Error("At most eight waypoints are allowed");
    for(const point of waypoints){
      if(!Array.isArray(point)||point.length!==2||
         !point.every(Number.isInteger))throw Error("Waypoint coordinates must be integers");
    }
    if(!Number.isInteger(budget)||budget<0||budget>16)
      throw Error("Invalid hazard budget");
    if(!session||typeof session!=="object"||Array.isArray(session)||
       session.session_digest!==lease||session.source_digest!==source)
      throw Error("Pasted walk session does not match source/session leases");
    const request={
      schema:"skeleton.jeeves.studio_waypoint_handoff_request.v1",
      project_id:project,expected_source_digest:source,
      expected_session_digest:lease,session_receipt:session,
      waypoints:waypoints,max_hazard_contacts:budget
    };
    const encoded=JSON.stringify(request);
    if(new TextEncoder().encode(encoded).length>32768)
      throw Error("Editor request exceeds bounded CLI/Jeeves input");
    field("output").value=encoded;
    status.textContent="Typed request ready. Copy JSON to --request-json; only the Python replay can verify gameplay.";
  }catch(error){status.textContent="Blocked: "+String(error.message||error);}
});
"""
_CSS = """
:root{color-scheme:dark;background:#101d2a;color:#eef5fb;font:16px system-ui}
body{max-width:850px;margin:2rem auto;padding:1rem}
label{display:block;margin:1rem 0}input,textarea{display:block;width:100%;
box-sizing:border-box;padding:.6rem;background:#1b3445;color:#fff;
border:2px solid #91b6c6;font:inherit}
textarea{min-height:6rem}#session{min-height:12rem}
button{padding:.8rem;background:#125675;color:white;border:2px solid #99cddc}
:focus-visible{outline:3px solid #f7ce67}
"""


def _hash(text: str) -> str:
    return "'sha256-" + b64encode(sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def render_waypoint_handoff_editor_html() -> bytes:
    policy = ("default-src 'none'; script-src " + _hash(_SCRIPT) +
              "; style-src " + _hash(_CSS) +
              "; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"" + policy + "\">"
        "<title>Original-world waypoint playable handoff editor</title>"
        "<style>" + _CSS + "</style></head><body><main>"
        "<h1>Playable waypoint handoff editor</h1>"
        "<p>Offline authoring only. No network or implicit game action.</p>"
        "<label>Project id<input id='project' maxlength='128' autocomplete='off'></label>"
        "<label>Expected source SHA-256<input id='source' maxlength='64'></label>"
        "<label>Expected session SHA-256<input id='lease' maxlength='64'></label>"
        "<label>Authoritative walk session JSON<textarea id='session'></textarea></label>"
        "<label>Waypoints JSON<textarea id='waypoints'>[]</textarea></label>"
        "<label>Maximum hazard contacts (must preserve health)"
        "<input id='budget' type='number' min='0' max='16' value='0'></label>"
        "<button id='compile' type='button'>Export typed request</button>"
        "<p id='status' role='status' aria-live='polite'></p>"
        "<label>Copy into CLI --request-json<textarea id='output' readonly></textarea></label>"
        "</main><script>" + _SCRIPT + "</script></body></html>"
    ).encode("utf-8")
    if len(html) > 32 * 1024:
        raise ValueError("offline editor exceeds byte budget")
    return html


def publish_waypoint_handoff_editor(directory: Path, *, authorized: bool) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("offline waypoint editor requires authorization")
    raw = render_waypoint_handoff_editor_html()
    fd = _open_directory(directory)
    temp = ".waypoint-editor-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=fd)
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "sha256": sha256(raw).hexdigest(), "bytes": len(raw),
            "file_write_performed": True, "release_certified": False}
