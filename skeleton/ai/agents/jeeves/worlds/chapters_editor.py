"""Offline chapter/act editorial titles with CSP and unapproved JSON export."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .chapters import validate_chapters
from .world_canon import CanonError, canonical

_EDITOR_JS = r"""
"use strict";
const source = JSON.parse(document.getElementById("source-data").textContent);
const root = document.getElementById("editor");
const heading = document.createElement("h1");
heading.textContent = "Original chapter and act editor"; root.append(heading);
const description = document.createElement("p");
description.textContent = "Edit chapter and act descriptions. Export unapproved JSON for source-leased CLI review.";
root.append(description);
const form = document.createElement("form"), inputs = [];
function field(labelText, value, maxLength) {
  const label = document.createElement("label");
  label.textContent = labelText;
  const input = document.createElement("textarea");
  input.rows = 3; input.cols = 80; input.maxLength = maxLength; input.value = value;
  label.append(input); form.append(label, document.createElement("br"));
  return input;
}
for (const chapter of source.chapters) {
  const chapterTitle = field("Chapter " + chapter.id + " title", chapter.title, 256);
  const chapterSummary = field("Chapter summary", chapter.summary, 2048);
  const acts = [];
  for (const act of chapter.acts) {
    acts.push({
      title: field("Act " + act.id + " title", act.title, 256),
      summary: field("Act summary", act.summary, 2048)
    });
  }
  inputs.push({chapterTitle, chapterSummary, acts});
}
const button = document.createElement("button");
button.type = "submit"; button.textContent = "Export unapproved JSON";
const output = document.createElement("textarea");
output.readOnly = true; output.rows = 14; output.cols = 90;
form.append(button); root.append(form, output);
form.addEventListener("submit", event => {
  event.preventDefault();
  const result = JSON.parse(JSON.stringify(source));
  result.chapters.forEach((chapter, i) => {
    const fields = inputs[i];
    chapter.title = fields.chapterTitle.value;
    chapter.summary = fields.chapterSummary.value;
    chapter.acts.forEach((act, j) => {
      act.title = fields.acts[j].title.value;
      act.summary = fields.acts[j].summary.value;
    });
  });
  result.approved = false;
  result.review_note = "Offline chapter edit requires renewed author review";
  output.value = JSON.stringify(result, null, 2);
  output.focus(); output.select();
});
""".strip()


def render_editor(source: Any, world: Any) -> bytes:
    validate_chapters(source, world)
    payload = canonical(source).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_EDITOR_JS.encode()).digest()).decode("ascii")
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + html.escape(world["id"], quote=True) + ' chapters editor</title>'
            '</head><body><main id="editor"></main>'
            '<script id="source-data" type="application/json">' + payload + '</script>'
            '<script>' + _EDITOR_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("chapters_editor_too_large")
    return page
