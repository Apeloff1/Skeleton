"""CSP-protected offline narrative pacing editor; only unapproved export."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .pacing import validate_pacing
from .world_canon import CanonError, canonical

_EDITOR_JS = r"""
"use strict";
const source = JSON.parse(document.getElementById("source-data").textContent);
const root = document.getElementById("editor");
const heading = document.createElement("h1");
heading.textContent = "Original narrative pacing editor"; root.append(heading);
const form = document.createElement("form"), inputs = [];
for (const beat of source.beats) {
  const label = document.createElement("label");
  label.textContent = beat.scene + " / phase, intensity, note: ";
  const phase = document.createElement("select");
  for (const name of ["setup", "rising", "climax", "resolution"]) {
    const option = document.createElement("option");
    option.value = name; option.textContent = name;
    option.selected = beat.phase === name; phase.append(option);
  }
  const intensity = document.createElement("input");
  intensity.type = "number"; intensity.min = "0"; intensity.max = "10";
  intensity.value = beat.intensity;
  const note = document.createElement("textarea");
  note.value = beat.note; note.rows = 3; note.cols = 80;
  label.append(phase, intensity, note);
  form.append(label, document.createElement("br"));
  inputs.push({scene: beat.scene, phase, intensity, note});
}
const button = document.createElement("button");
button.type = "submit"; button.textContent = "Export unapproved pacing";
const output = document.createElement("textarea");
output.readOnly = true; output.rows = 24; output.cols = 90;
form.append(button); root.append(form, output);
form.addEventListener("submit", event => {
  event.preventDefault();
  const copy = JSON.parse(JSON.stringify(source));
  for (const item of inputs) {
    const beat = copy.beats.find(b => b.scene === item.scene);
    beat.phase = item.phase.value; beat.intensity = Number(item.intensity.value);
    beat.note = item.note.value;
  }
  copy.approved = false;
  copy.review_note = "Export requires canonical validation and human review";
  output.value = JSON.stringify(copy, null, 2);
});
""".strip()


def render_editor(source: Any, world: Any) -> bytes:
    validate_pacing(source, world)
    payload = canonical(source).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_EDITOR_JS.encode()).digest()).decode("ascii")
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + html.escape(world["id"], quote=True) + ' pacing editor</title>'
            '</head><body><main id="editor"></main>'
            '<script id="source-data" type="application/json">' + payload + '</script>'
            '<script>' + _EDITOR_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("pacing_editor_too_large")
    return page
