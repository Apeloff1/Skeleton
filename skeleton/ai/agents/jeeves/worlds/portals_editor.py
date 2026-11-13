"""Offline CSP-bound original multi-world portal editor with JSON export.

Browser state is an untrusted proposal; the operator CLI owns validation,
explicit review, optimistic source leases and compiled artifact custody.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .portals import MAX_HTML_BYTES, validate_network
from .world_canon import CanonError, canonical, digest

EDITOR_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("portal-data").textContent);
const worlds = model.worlds;
let network = model.network;
const $ = id => document.getElementById(id);
function node(tag, text) {
  const item = document.createElement(tag);
  item.textContent = text;
  return item;
}
function option(select, value, label) {
  const item = node("option", label);
  item.value = value;
  select.append(item);
}
function sync() {
  $("source-json").value = JSON.stringify(network, null, 2);
  $("worlds").replaceChildren();
  for (const id of Object.keys(worlds).sort()) {
    $("worlds").append(node("li", id + " — " + worlds[id].region));
  }
  $("from-world").replaceChildren();
  $("to-world").replaceChildren();
  for (const id of Object.keys(worlds).sort()) {
    option($("from-world"), id, id);
    option($("to-world"), id, id);
  }
  $("portals").replaceChildren();
  for (const portal of network.portals) {
    $("portals").append(node("li", portal.id + ": " + portal.from_world +
      "/" + portal.from_ending + " → " + portal.to_world + " — " + portal.label));
  }
  refreshEndings();
  $("status").textContent = "Draft only. Operator review and CLI compilation required.";
}
function refreshEndings() {
  $("from-ending").replaceChildren();
  const world = worlds[$("from-world").value];
  if (!world) return;
  for (const ending of world.endings) {
    option($("from-ending"), ending.scene, ending.label);
  }
}
$("from-world").addEventListener("change", refreshEndings);
$("add-portal").addEventListener("click", () => {
  try {
    const id = $("portal-id").value.trim();
    const from_world = $("from-world").value;
    const from_ending = $("from-ending").value;
    const to_world = $("to-world").value;
    const label = $("portal-label").value.trim();
    if (!/^[a-z][a-z0-9_-]{0,47}$/.test(id) || !label || label.length > 400 ||
        from_world === to_world || network.portals.length >= 32 ||
        network.portals.some(p => p.id === id)) {
      throw new Error("Invalid portal ID, label or destination");
    }
    if (!worlds[from_world].endings.some(e => e.scene === from_ending)) {
      throw new Error("Portal must start at a proven ending");
    }
    network.portals.push({id, from_world, from_ending, to_world, label});
    network.portals.sort((a,b) => a.id.localeCompare(b.id, "en"));
    sync();
  } catch (e) { $("status").textContent = e.message; }
});
$("remove-portal").addEventListener("click", () => {
  const id = $("portal-id").value.trim();
  network.portals = network.portals.filter(p => p.id !== id);
  sync();
});
function parseDraft() {
  const candidate = JSON.parse($("source-json").value);
  if (!candidate || candidate.schema !== "jeeves.world.portals.v1" ||
      candidate.id !== model.network.id ||
      candidate.approved !== false) {
    throw new Error("Invalid network identity or unreviewed state");
  }
  const ids = Object.keys(candidate.world_digests || {}).sort();
  if (JSON.stringify(ids) !== JSON.stringify(Object.keys(worlds).sort())) {
    throw new Error("World set changed; regenerate the editor from canonical sources");
  }
  for (const id of ids) {
    if (candidate.world_digests[id] !== model.network.world_digests[id]) {
      throw new Error("Stale or changed world digest");
    }
  }
  if (!Array.isArray(candidate.portals)) throw new Error("Invalid portal list");
  return candidate;
}
$("load-json").addEventListener("click", () => {
  try { network = parseDraft(); sync(); }
  catch (e) { $("status").textContent = e.message; }
});
$("export-json").addEventListener("click", () => {
  try {
    network = parseDraft();
    const output = JSON.stringify(network, null, 2) + "\n";
    if (new TextEncoder().encode(output).length > 524288) {
      throw new Error("Network source exceeds budget");
    }
    const url = URL.createObjectURL(new Blob([output], {type:"application/json"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = network.id + ".portals.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("status").textContent = "Exported unapproved JSON; save and review via CLI.";
  } catch (e) { $("status").textContent = e.message; }
});
sync();
""".strip()


def render_editor(network: Any, worlds: dict[str, Any]) -> bytes:
    validate_network(network, worlds)
    if network["approved"]:
        raise CanonError("portals_editor_requires_draft")
    embedded = canonical({
        "network": network, "worlds": worlds,
        "network_digest": digest(network),
    }).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(EDITOR_JS.encode()).digest()).decode()
    title = html.escape(network["id"], quote=True)
    output = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'\">"
        "<title>Original portal editor: " + title + "</title></head><body>"
        "<main><h1>Original multi-world portal editor</h1>"
        "<p>Unapproved offline proposal. The CLI performs authoritative proof.</p>"
        '<h2>Source-bound worlds</h2><ul id="worlds"></ul>'
        '<h2>Portal routes</h2><ul id="portals"></ul>'
        '<label>Portal ID <input id="portal-id" maxlength="48"></label>'
        '<label>From world <select id="from-world"></select></label>'
        '<label>Ending <select id="from-ending"></select></label>'
        '<label>To world <select id="to-world"></select></label>'
        '<label>Portal label <input id="portal-label" maxlength="400"></label>'
        '<button type="button" id="add-portal">Add portal</button>'
        '<button type="button" id="remove-portal">Remove portal by ID</button>'
        '<h2>Typed network JSON</h2>'
        '<label>Source <textarea id="source-json" rows="24" cols="90"></textarea></label>'
        '<button type="button" id="load-json">Load JSON edits</button>'
        '<button type="button" id="export-json">Export JSON</button>'
        '<p id="status" role="status" aria-live="polite"></p></main>'
        '<script id="portal-data" type="application/json">' + embedded +
        "</script><script>" + EDITOR_JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(output) > MAX_HTML_BYTES:
        raise CanonError("portals_editor_too_large")
    return output
