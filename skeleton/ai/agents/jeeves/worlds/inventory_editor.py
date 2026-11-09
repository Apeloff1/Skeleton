"""Network-disabled inventory review editor; exports unapproved typed JSON only."""
from __future__ import annotations

import base64
from hashlib import sha256
import html

from .inventory import validate_inventory
from .world_canon import CanonError, canonical, digest

_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("inventory-source").textContent);
const data = model.inventory;
const root = document.getElementById("editor");
const status = document.getElementById("status");
const output = document.getElementById("export");
function node(tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  return element;
}
function input(label, value, type) {
  const container = node("label", label + " ");
  const field = document.createElement("input");
  field.value = String(value);
  field.type = type || "text";
  field.setAttribute("aria-label", label);
  container.append(field);
  return [container, field];
}
function exportSource() {
  try {
    const updated = JSON.parse(JSON.stringify(data));
    for (const [index, fields] of itemFields.entries()) {
      const item = updated.items[index];
      item.name = fields.name.value;
      item.description = fields.description.value;
      for (const key of ["initial", "capacity"]) {
        const raw = fields[key].value;
        if (!/^(0|[1-9][0-9]*)$/.test(raw)) throw Error("Invalid " + key);
        const number = Number(raw);
        if (!Number.isSafeInteger(number) || number > 9) throw Error("Invalid " + key);
        item[key] = number;
      }
      if (!item.name.trim() || !item.description.trim()) throw Error("Missing item text");
      if (item.capacity === 0 || item.initial > item.capacity) throw Error("Invalid capacity");
    }
    const effects = JSON.parse(effectsEditor.value);
    if (!Array.isArray(effects)) throw Error("Effects must be an array");
    updated.effects = effects;
    updated.approved = false;
    updated.review_note = "Review required after offline edit";
    output.textContent = JSON.stringify(updated);
    status.textContent = "Export ready. Revalidate with world-inventory save and approve explicitly.";
  } catch (error) {
    output.textContent = "";
    status.textContent = "Export rejected: " + String(error.message);
  }
}
const itemFields = [];
for (const item of data.items) {
  const fieldset = document.createElement("fieldset");
  fieldset.append(node("legend", item.id));
  const fields = {};
  for (const [name, type] of [
    ["name", "text"], ["description", "text"],
    ["initial", "number"], ["capacity", "number"],
  ]) {
    const [label, field] = input(item.id + " " + name, item[name], type);
    fieldset.append(label);
    fields[name] = field;
  }
  itemFields.push(fields);
  root.append(fieldset);
}
root.append(node("h2", "Choice item effects"));
const effectsEditor = document.createElement("textarea");
effectsEditor.setAttribute("aria-label", "Choice item effects JSON");
effectsEditor.rows = 12;
effectsEditor.cols = 75;
effectsEditor.value = JSON.stringify(data.effects, null, 2);
root.append(effectsEditor);
const button = node("button", "Export unapproved JSON");
button.addEventListener("click", exportSource);
root.append(button);
status.textContent = "Offline source-bound editor. Export does not publish or approve.";
""".strip()


def render_editor(data: dict, world: dict) -> bytes:
    validate_inventory(data, world)
    payload = canonical({
        "inventory": data,
        "world_digest": digest(world),
    }).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    markup = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "script-src 'sha256-" + policy + "'; connect-src 'none'; "
        'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        '<title>' + title + ' inventory editor</title></head><body>'
        '<h1>Original item review</h1><p>Source lease: ' + digest(data) + '</p>'
        '<main id="editor"></main><p id="status" role="status"></p>'
        '<h2>Unapproved typed JSON export</h2><pre id="export"></pre>'
        '<script id="inventory-source" type="application/json">' + payload + '</script>'
        '<script>' + _JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(markup) > 1048576:
        raise CanonError("inventory_editor_too_large")
    return markup
