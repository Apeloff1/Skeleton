"""Offline CSP-bound original puzzle editor with review-reset JSON export."""
from __future__ import annotations

import base64
from hashlib import sha256
import html

from .puzzles import validate_puzzles
from .world_canon import CanonError, canonical, digest

_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("puzzles-source").textContent);
const data = model.puzzles;
const root = document.getElementById("editor");
const status = document.getElementById("status");
const output = document.getElementById("export");
function element(tag, label) {
  const node = document.createElement(tag);
  node.textContent = label;
  return node;
}
const rows = [];
for (const puzzle of data.puzzles) {
  const fieldset = document.createElement("fieldset");
  fieldset.append(element("legend", puzzle.id + " at " + puzzle.scene));
  const fields = {};
  for (const name of ["question", "answer", "hint", "unlock_choice"]) {
    const label = element("label", name + " ");
    const field = document.createElement("input");
    field.value = puzzle[name];
    field.setAttribute("aria-label", puzzle.id + " " + name);
    label.append(field);
    fieldset.append(label);
    fields[name] = field;
  }
  rows.push(fields);
  root.append(fieldset);
}
const button = element("button", "Export unapproved puzzle JSON");
button.addEventListener("click", () => {
  try {
    const next = JSON.parse(JSON.stringify(data));
    for (const [index, fields] of rows.entries()) {
      for (const name of ["question", "answer", "hint", "unlock_choice"]) {
        next.puzzles[index][name] = fields[name].value;
      }
      const puzzle = next.puzzles[index];
      if (!puzzle.question.trim() || !puzzle.hint.trim() ||
          !puzzle.answer.trim() || puzzle.answer !== puzzle.answer.trim()) {
        throw Error("Invalid puzzle text");
      }
    }
    next.approved = false;
    next.review_note = "Review required after offline puzzle edit";
    output.textContent = JSON.stringify(next);
    status.textContent = "Export ready; CLI revalidation and author approval required.";
  } catch (error) {
    output.textContent = "";
    status.textContent = "Export rejected: " + String(error.message);
  }
});
root.append(button);
status.textContent = "No changes are saved or approved in the browser.";
""".strip()


def render_editor(data: dict, world: dict) -> bytes:
    validate_puzzles(data, world)
    payload = canonical({"puzzles": data, "world_digest": digest(world)}).decode(
        "utf-8"
    ).replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    content = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "script-src 'sha256-" + policy + "'; connect-src 'none'; "
        'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        '<title>' + title + ' puzzle editor</title></head><body>'
        '<h1>Original puzzle review</h1><p>Source lease: ' + digest(data) + '</p>'
        '<main id="editor"></main><p id="status" role="status"></p>'
        '<h2>Unapproved typed JSON export</h2><pre id="export"></pre>'
        '<script id="puzzles-source" type="application/json">' + payload + '</script>'
        '<script>' + _JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(content) > 1048576:
        raise CanonError("puzzles_editor_too_large")
    return content
