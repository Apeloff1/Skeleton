"""CSP-bound offline NPC itinerary editor with review-reset JSON export."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .npc_schedule import validate_schedule
from .world_canon import CanonError, canonical, digest

EDITOR_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("editor-data").textContent);
let draft = JSON.parse(JSON.stringify(model.schedule));
const $ = id => document.getElementById(id);
const status = $("status");
const list = $("appointments");
const source = $("source-json");
const ids = /^[a-z][a-z0-9_-]{0,47}$/;
function node(tag, text) {
  const item = document.createElement(tag);
  item.textContent = text;
  return item;
}
function show() {
  list.replaceChildren();
  for (const item of draft.appointments) {
    list.append(node("li", item.id + " — " + item.actor + " in " +
      item.scene + " at ticks " + item.first_tick + "–" +
      item.last_tick + ": " + item.label));
  }
  source.value = JSON.stringify(draft, null, 2);
  status.textContent = "Unapproved source; operator CLI validation required.";
}
function unapprove() {
  draft.approved = false;
  draft.review_note = "Edited schedule requires renewed author review.";
}
$("add-appointment").addEventListener("click", () => {
  const id = $("appointment-id").value;
  const actor = $("actor").value;
  const scene = $("scene").value;
  const first = Number($("first-tick").value);
  const last = Number($("last-tick").value);
  const label = $("label").value;
  const flags = $("requires-flags").value.split(",")
    .map(value => value.trim()).filter(Boolean).sort();
  if (!ids.test(id) || draft.appointments.some(a => a.id === id) ||
      !model.cast.characters.some(a => a.id === actor) ||
      !model.world.scenes.some(s => s.id === scene) ||
      !Number.isInteger(first) || !Number.isInteger(last) ||
      first < 0 || first > last || last > 64 || !label ||
      label.length > 400 || flags.some(f => !ids.test(f)) ||
      new Set(flags).size !== flags.length ||
      draft.appointments.length >= 128) {
    status.textContent = "Invalid appointment; no edit applied.";
    return;
  }
  draft.appointments.push({
    id, actor, scene, first_tick: first, last_tick: last,
    label, requires_flags: flags
  });
  draft.appointments.sort((a, b) => a.id.localeCompare(b.id));
  unapprove(); show();
});
$("remove-appointment").addEventListener("click", () => {
  const id = $("appointment-id").value;
  const count = draft.appointments.length;
  if (count <= 1 || !draft.appointments.some(a => a.id === id)) {
    status.textContent = "Cannot remove the last or unknown appointment.";
    return;
  }
  draft.appointments = draft.appointments.filter(a => a.id !== id);
  unapprove(); show();
});
$("load-json").addEventListener("click", () => {
  try {
    if (source.value.length > 524288) throw Error("oversized");
    const candidate = JSON.parse(source.value);
    if (!candidate || typeof candidate !== "object" ||
        candidate.schema !== model.schedule.schema ||
        candidate.world_id !== model.schedule.world_id ||
        candidate.world_digest !== model.schedule.world_digest ||
        candidate.cast_digest !== model.schedule.cast_digest ||
        !Array.isArray(candidate.appointments) ||
        candidate.appointments.length < 1 ||
        candidate.appointments.length > 128) throw Error("invalid lease");
    draft = candidate;
    unapprove(); show();
  } catch (_) {
    status.textContent = "Invalid or stale JSON; original draft preserved.";
  }
});
$("export-json").addEventListener("click", () => {
  unapprove();
  show();
  source.focus();
  source.select();
  status.textContent = "Copy typed JSON to world-npc-schedule save; review required.";
});
$("source-digest").textContent = model.source_digest;
$("cast-ids").textContent = model.cast.characters.map(a => a.id).join(", ");
$("scene-ids").textContent = model.world.scenes.map(s => s.id).join(", ");
show();
""".strip()


def render_editor(data: Any, world: Any, cast: Any) -> bytes:
    validate_schedule(data, world, cast)
    embedded = canonical({
        "schedule": data, "world": world, "cast": cast,
        "source_digest": digest(data),
    }).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(EDITOR_JS.encode()).digest()).decode()
    title = html.escape(world["id"], quote=True)
    output = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'\">"
        "<title>Original NPC itinerary editor: " + title + "</title></head><body>"
        "<main><h1>Reviewed original NPC itinerary editor</h1>"
        "<p>Offline JSON edits require operator review and source-bound CLI proof.</p>"
        '<p>Schedule digest: <code id="source-digest"></code></p>'
        '<p>Cast actors: <span id="cast-ids"></span></p>'
        '<p>Scenes: <span id="scene-ids"></span></p>'
        '<h2>Appointments</h2><ul id="appointments"></ul>'
        '<label>Appointment ID <input id="appointment-id" maxlength="48"></label>'
        '<label>Actor <input id="actor" maxlength="48"></label>'
        '<label>Scene <input id="scene" maxlength="48"></label>'
        '<label>First tick <input id="first-tick" type="number" min="0" max="64"></label>'
        '<label>Last tick <input id="last-tick" type="number" min="0" max="64"></label>'
        '<label>Encounter label <input id="label" maxlength="400"></label>'
        '<label>Required flags, comma separated <input id="requires-flags"></label>'
        '<button type="button" id="add-appointment">Add appointment</button>'
        '<button type="button" id="remove-appointment">Remove by ID</button>'
        '<h2>Typed source JSON</h2>'
        '<label>Source <textarea id="source-json" rows="24" cols="90"></textarea></label>'
        '<button type="button" id="load-json">Load JSON edits</button>'
        '<button type="button" id="export-json">Export unapproved JSON</button>'
        '<p id="status" role="status" aria-live="polite"></p></main>'
        '<script id="editor-data" type="application/json">' + embedded +
        "</script><script>" + EDITOR_JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(output) > 1572864:
        raise CanonError("npc_schedule_editor_too_large")
    return output
