"""CSP-bound offline economy authoring editor: export unapproved source only."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .world_canon import canonical, digest

JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("source").textContent);
const root = document.getElementById("editor");
const lease = document.getElementById("lease").textContent;
const data = model.economy;
function node(tag, label) {
  const item = document.createElement(tag);
  item.textContent = label;
  return item;
}
function input(label, value) {
  const row = document.createElement("label");
  row.append(node("span", label + ": "));
  const field = document.createElement("input");
  field.value = String(value); row.append(field); root.append(row);
  root.append(node("br", ""));
  return field;
}
root.append(node("h1", "Reviewed resource economy editor"));
root.append(node("p", "Source lease: " + lease));
root.append(node("p", "All exports are unapproved and must pass canonical validation."));
const prompt = input("Original prompt", data.prompt);
const rows = [];
for (const resource of data.resources) {
  root.append(node("h2", resource.name));
  const initial = input(resource.id + " initial", resource.initial);
  const capacity = input(resource.id + " capacity", resource.capacity);
  rows.push({resource, initial, capacity});
}
const exportButton = node("button", "Export unapproved JSON");
exportButton.type = "button";
exportButton.addEventListener("click", () => {
  const draft = JSON.parse(JSON.stringify(data));
  draft.prompt = prompt.value;
  draft.approved = false;
  draft.review_note = "";
  for (let i = 0; i < rows.length; i++) {
    draft.resources[i].initial = Number(rows[i].initial.value);
    draft.resources[i].capacity = Number(rows[i].capacity.value);
  }
  const content = JSON.stringify(draft, null, 2);
  const blob = new Blob([content], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = model.world.id + ".economy.unapproved.json";
  link.click(); URL.revokeObjectURL(url);
});
root.append(exportButton);
""".strip()


def render_editor(source: Any, world: Any) -> bytes:
    embedded = canonical({"economy": source, "world": world}).decode(
        "utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(JS.encode()).digest()).decode()
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + policy +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        "<title>Economy editor " + html.escape(world["id"]) +
        '</title></head><body><main id="editor"></main><p id="lease">' +
        digest(source) + '</p><script id="source" type="application/json">' +
        embedded + "</script><script>" + JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(page) > 1572864:
        from .world_canon import CanonError
        raise CanonError("economy_editor_too_large")
    return page
