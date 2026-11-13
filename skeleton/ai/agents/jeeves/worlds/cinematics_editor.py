"""CSP-hashed offline storyboard editor with unapproved, source-leased export."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .cinematics import validate_cinematics
from .world_canon import canonical

_EDITOR_JS = r"""
"use strict";
const source = JSON.parse(document.getElementById("source-data").textContent);
const root = document.getElementById("editor");
const title = document.createElement("h1");
title.textContent = "Original cinematic storyboard editor"; root.append(title);
const help = document.createElement("p");
help.textContent = "Edit captions and cue timings. Export JSON, then publish and explicitly review using the CLI.";
root.append(help);
const form = document.createElement("form"), inputs = [];
for (const sequence of source.sequences) {
  const heading = document.createElement("h2");
  heading.textContent = "Scene: " + sequence.scene; form.append(heading);
  for (const beat of sequence.beats) {
    const label = document.createElement("label");
    label.textContent = "Beat " + beat.id + " (" + beat.cue + ")";
    const caption = document.createElement("textarea");
    caption.rows = 3; caption.cols = 80; caption.maxLength = 2048;
    caption.value = beat.caption;
    const duration = document.createElement("input");
    duration.type = "number"; duration.min = "500"; duration.max = "15000";
    duration.step = "1"; duration.value = beat.duration_ms;
    label.append(caption, duration); form.append(label, document.createElement("br"));
    inputs.push({beat, caption, duration});
  }
}
const submit = document.createElement("button");
submit.type = "submit"; submit.textContent = "Export unapproved JSON";
const output = document.createElement("textarea");
output.readOnly = true; output.rows = 14; output.cols = 90;
form.append(submit); root.append(form, output);
form.addEventListener("submit", event => {
  event.preventDefault();
  const result = JSON.parse(JSON.stringify(source));
  let cursor = 0;
  for (const sequence of result.sequences) for (const beat of sequence.beats) {
    const entry = inputs[cursor++];
    beat.caption = entry.caption.value;
    beat.duration_ms = Number(entry.duration.value);
  }
  result.approved = false;
  result.review_note = "Offline storyboard edit requires renewed author review";
  output.value = JSON.stringify(result, null, 2);
  output.focus(); output.select();
});
""".strip()


def render_editor(source: Any, world: Any) -> bytes:
    validate_cinematics(source, world)
    payload = canonical(source).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_EDITOR_JS.encode()).digest()).decode("ascii")
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + html.escape(world["id"], quote=True) + ' storyboard editor</title>'
            '</head><body><main id="editor"></main>'
            '<script id="source-data" type="application/json">' + payload + '</script>'
            '<script>' + _EDITOR_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        from .world_canon import CanonError
        raise CanonError("cinematics_editor_too_large")
    return page
