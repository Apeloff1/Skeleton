"""Offline CSP-bound region atlas editor; all publication remains operator-owned.

Browser edits are proposals. The canonical CLI revalidates the entire JSON
against the current world lease before persisting or compiling anything.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .atlas import MAX_PLAYABLE_BYTES, validate_atlas
from .world_canon import CanonError, canonical, digest, prove

EDITOR_JS = r"""
"use strict";
const envelope = JSON.parse(document.getElementById("atlas-data").textContent);
const world = envelope.world;
let atlas = envelope.atlas;
const sceneById = new Map(world.scenes.map(s => [s.id, s]));
const choiceById = new Map(world.choices.map(c => [c.id, c]));
const $ = id => document.getElementById(id);
function node(tag, value) {
  const element = document.createElement(tag);
  element.textContent = value;
  return element;
}
function option(select, value, label) {
  const item = node("option", label);
  item.value = value;
  select.append(item);
}
function sync() {
  $("source-json").value = JSON.stringify(atlas, null, 2);
  $("regions").replaceChildren();
  for (const region of atlas.regions) {
    $("regions").append(node("li", region.id + ": " + region.name +
      " — " + region.description));
  }
  $("placements").replaceChildren();
  $("scene").replaceChildren();
  $("region").replaceChildren();
  for (const region of atlas.regions) {
    option($("region"), region.id, region.name);
  }
  for (const placement of atlas.placements) {
    option($("scene"), placement.scene, sceneById.get(placement.scene).title);
    $("placements").append(node("li", placement.scene + " → " + placement.region));
  }
  $("choice").replaceChildren();
  $("passages").replaceChildren();
  for (const choice of world.choices) {
    option($("choice"), choice.id, choice.label);
  }
  for (const passage of atlas.passages) {
    $("passages").append(node("li", passage.id + ": " +
      passage.from_region + " → " + passage.to_region + " via " + passage.choice));
  }
  $("status").textContent = "Draft only. Review and save with the source-leased CLI.";
}
function error(message) { $("status").textContent = message; }
function validId(value) { return /^[a-z][a-z0-9_-]{0,47}$/.test(value); }
function place(scene) {
  const placement = atlas.placements.find(p => p.scene === scene);
  if (!placement) throw new Error("Missing scene placement");
  return placement.region;
}
$("add-region").addEventListener("click", () => {
  try {
    const id = $("region-id").value.trim();
    const name = $("region-name").value.trim();
    const description = $("region-description").value.trim();
    if (!validId(id) || !name || !description ||
        name.length > 400 || description.length > 4096 ||
        atlas.regions.some(r => r.id === id) || atlas.regions.length >= 64) {
      throw new Error("Invalid or duplicate region");
    }
    atlas.regions.push({id, name, description});
    atlas.regions.sort((a,b) => a.id.localeCompare(b.id, "en"));
    sync();
  } catch (e) { error(e.message); }
});
$("place-scene").addEventListener("click", () => {
  try {
    const scene = $("scene").value;
    const region = $("region").value;
    const item = atlas.placements.find(p => p.scene === scene);
    if (!item || !atlas.regions.some(r => r.id === region)) {
      throw new Error("Unknown scene or region");
    }
    item.region = region;
    sync();
  } catch (e) { error(e.message); }
});
$("add-passage").addEventListener("click", () => {
  try {
    const id = $("passage-id").value.trim();
    const description = $("passage-description").value.trim();
    const choice = choiceById.get($("choice").value);
    if (!choice || !validId(id) || !description || description.length > 1024 ||
        atlas.passages.length >= 512 ||
        atlas.passages.some(p => p.id === id || p.choice === choice.id)) {
      throw new Error("Invalid or duplicate passage");
    }
    const from_region = place(choice.from);
    const to_region = place(choice.to);
    if (from_region === to_region) throw new Error("Choice is not a region crossing");
    atlas.passages.push({id, choice: choice.id, from_region, to_region, description});
    atlas.passages.sort((a,b) => a.id.localeCompare(b.id, "en"));
    sync();
  } catch (e) { error(e.message); }
});
$("remove-passage").addEventListener("click", () => {
  const choice = $("choice").value;
  atlas.passages = atlas.passages.filter(p => p.choice !== choice);
  sync();
});
function parseDraft() {
  const candidate = JSON.parse($("source-json").value);
  if (!candidate || candidate.schema !== "jeeves.world.atlas.v1" ||
      candidate.world_id !== world.id ||
      candidate.world_digest !== envelope.world_digest ||
      candidate.approved !== false) {
    throw new Error("Invalid, stale or already-approved draft");
  }
  if (!Array.isArray(candidate.regions) || !Array.isArray(candidate.placements) ||
      !Array.isArray(candidate.passages)) throw new Error("Invalid atlas arrays");
  return candidate;
}
$("load-json").addEventListener("click", () => {
  try { atlas = parseDraft(); sync(); }
  catch (e) { error(e.message); }
});
$("export-json").addEventListener("click", () => {
  try {
    atlas = parseDraft();
    const text = JSON.stringify(atlas, null, 2) + "\n";
    if (new TextEncoder().encode(text).length > 524288) {
      throw new Error("Atlas exceeds source budget");
    }
    const url = URL.createObjectURL(new Blob([text], {type:"application/json"}));
    const a = document.createElement("a");
    a.href = url;
    a.download = world.id + ".atlas.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    error("Draft exported. Run world-atlas save, approve, compile and verify.");
  } catch (e) { error(e.message); }
});
sync();
""".strip()


def render_editor(atlas: Any, world: Any) -> bytes:
    validate_atlas(atlas, world)
    if atlas["approved"]:
        raise CanonError("atlas_editor_requires_draft")
    envelope = {
        "world": world, "atlas": atlas,
        "world_digest": prove(world).source_digest,
        "atlas_digest": digest(atlas),
    }
    embedded = canonical(envelope).decode("utf-8").replace("<", "\\u003c")
    policy_hash = base64.b64encode(sha256(EDITOR_JS.encode()).digest()).decode()
    title = html.escape(world["id"], quote=True)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + policy_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        'base-uri \'none\'; form-action \'none\'">'
        '<title>Original atlas editor: ' + title + '</title></head><body>'
        '<main><h1>Original region atlas editor</h1>'
        '<p>Offline authoring only. CLI review and proof are required.</p>'
        '<h2>Regions</h2><ul id="regions"></ul>'
        '<label>Region ID <input id="region-id" maxlength="48"></label>'
        '<label>Name <input id="region-name" maxlength="400"></label>'
        '<label>Description <textarea id="region-description" maxlength="4096"></textarea></label>'
        '<button type="button" id="add-region">Add region</button>'
        '<h2>Scene placement</h2><ul id="placements"></ul>'
        '<label>Scene <select id="scene"></select></label>'
        '<label>Region <select id="region"></select></label>'
        '<button type="button" id="place-scene">Place scene</button>'
        '<h2>Choice-bound passages</h2><ul id="passages"></ul>'
        '<label>Choice <select id="choice"></select></label>'
        '<label>Passage ID <input id="passage-id" maxlength="48"></label>'
        '<label>Description <textarea id="passage-description" maxlength="1024"></textarea></label>'
        '<button type="button" id="add-passage">Add passage</button>'
        '<button type="button" id="remove-passage">Remove selected passage</button>'
        '<h2>Editable typed JSON</h2>'
        '<label>Atlas source <textarea id="source-json" rows="24" cols="90"></textarea></label>'
        '<button type="button" id="load-json">Load JSON edits</button>'
        '<button type="button" id="export-json">Export source JSON</button>'
        '<p id="status" role="status" aria-live="polite"></p></main>'
        '<script id="atlas-data" type="application/json">' + embedded + '</script>'
        '<script>' + EDITOR_JS + '</script></body></html>\n'
    )
    output = page.encode("utf-8")
    if len(output) > MAX_PLAYABLE_BYTES:
        raise CanonError("atlas_editor_too_large")
    return output
