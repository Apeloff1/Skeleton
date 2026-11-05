"""CSP-protected offline accessible-scene editor; export is never approved."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .accessibility import validate_accessibility
from .world_canon import CanonError, canonical

_EDITOR_JS = r"""
"use strict";
const source = JSON.parse(document.getElementById("source-data").textContent);
const root = document.getElementById("editor");
const heading = document.createElement("h1");
heading.textContent = "Original accessible narrative editor"; root.append(heading);
const form = document.createElement("form"), inputs = [];
for (const [kind, field] of [["scenes", "summary"], ["choices", "action"],
                             ["endings", "summary"]]) {
  for (const row of source[kind]) {
    const label = document.createElement("label");
    label.textContent = kind + "/" + (row.id || row.scene) + "/" + field + ": ";
    const input = document.createElement("textarea");
    input.value = row[field]; input.rows = 3; input.cols = 80;
    label.append(input); form.append(label, document.createElement("br"));
    inputs.push({kind, id: row.id || row.scene, field, input});
  }
}
const button = document.createElement("button");
button.type = "submit"; button.textContent = "Export unapproved accessible narrative";
const output = document.createElement("textarea");
output.readOnly = true; output.rows = 24; output.cols = 90;
form.append(button); root.append(form, output);
form.addEventListener("submit", event => {
  event.preventDefault();
  const copy = JSON.parse(JSON.stringify(source));
  for (const item of inputs) {
    const row = copy[item.kind].find(r => (r.id || r.scene) === item.id);
    row[item.field] = item.input.value;
  }
  copy.approved = false;
  copy.review_note = "Export requires canonical validation and human review";
  output.value = JSON.stringify(copy, null, 2);
});
""".strip()


def render_editor(source: Any, world: Any) -> bytes:
    validate_accessibility(source, world)
    payload = canonical(source).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_EDITOR_JS.encode()).digest()).decode("ascii")
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + html.escape(world["id"], quote=True) + ' accessibility editor</title>'
            '</head><body><main id="editor"></main>'
            '<script id="source-data" type="application/json">' + payload + '</script>'
            '<script>' + _EDITOR_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("accessibility_editor_too_large")
    return page
