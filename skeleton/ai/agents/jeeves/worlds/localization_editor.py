"""Offline structured translation editor; exports only unapproved canonical drafts."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .localization import validate_localization
from .world_canon import CanonError, canonical

_EDITOR_JS = r"""
"use strict";
const source = JSON.parse(document.getElementById("source-data").textContent);
const root = document.getElementById("editor");
root.append(document.createElement("h1"));
root.firstChild.textContent = "Original narrative translation editor";
const form = document.createElement("form");
const inputs = [];
for (const locale of source.locales) {
  const heading = document.createElement("h2");
  heading.textContent = locale.tag; form.append(heading);
  for (const [kind, fields] of [["scenes", ["title", "narrative"]],
                                 ["choices", ["label"]], ["endings", ["label"]]]) {
    for (const row of locale[kind]) for (const field of fields) {
      const label = document.createElement("label");
      label.textContent = kind + "/" + (row.id || row.scene) + "/" + field + ": ";
      const input = document.createElement("textarea");
      input.value = row[field]; input.rows = field === "narrative" ? 5 : 2;
      input.cols = 80; label.append(input);
      form.append(label, document.createElement("br"));
      inputs.push({tag: locale.tag, kind, id: row.id || row.scene, field, input});
    }
  }
}
const button = document.createElement("button");
button.type = "submit"; button.textContent = "Export unapproved translations";
const output = document.createElement("textarea");
output.readOnly = true; output.rows = 24; output.cols = 90;
form.append(button); root.append(form, output);
form.addEventListener("submit", event => {
  event.preventDefault();
  const copy = JSON.parse(JSON.stringify(source));
  for (const item of inputs) {
    const locale = copy.locales.find(l => l.tag === item.tag);
    const row = locale[item.kind].find(r => (r.id || r.scene) === item.id);
    row[item.field] = item.input.value;
  }
  copy.approved = false;
  copy.review_note = "Translation export requires canonical validation and review";
  output.value = JSON.stringify(copy, null, 2);
});
""".strip()


def render_editor(source: Any, world: Any) -> bytes:
    validate_localization(source, world)
    payload = canonical(source).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_EDITOR_JS.encode()).digest()).decode("ascii")
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + html.escape(world["id"], quote=True) + ' translation editor</title>'
            '</head><body><main id="editor"></main>'
            '<script id="source-data" type="application/json">' + payload + '</script>'
            '<script>' + _EDITOR_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("localization_editor_too_large")
    return page
