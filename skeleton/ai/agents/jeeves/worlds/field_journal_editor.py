"""Offline player field-journal editor exporting lease-bound typed edits."""
from __future__ import annotations

import base64
from hashlib import sha256
from typing import Any

from .field_journal import PLAYER_SCHEMA
from .world_canon import CanonError, _keys, canonical

JS = r"""
"use strict";
const view = JSON.parse(document.getElementById("journal-data").textContent);
const root = document.getElementById("editor");
function element(tag, label) {
  const node = document.createElement(tag);
  if (label) node.textContent = label;
  return node;
}
root.append(element("h1", "Offline player field journal"));
root.append(element("p", "Export a typed edit; CLI validation and lease checks are required."));
for (const note of view.notes) {
  const label = element("label", "Note " + note.id + " at " + note.scene);
  const text = element("textarea");
  text.value = note.text;
  text.maxLength = 4096;
  text.rows = 4; text.cols = 72;
  label.append(text); root.append(label);
  const button = element("button", "Export edit for " + note.id);
  button.type = "button";
  const status = element("p");
  status.setAttribute("role", "status");
  button.addEventListener("click", () => {
    const operation = {
      world_id: view.world_id, slot: view.slot, note_id: note.id,
      text: text.value, expected_journal_digest: view.journal_digest
    };
    const body = JSON.stringify(operation, null, 2) + "\n";
    if (new TextEncoder().encode(body).length > 524288) {
      status.textContent = "Edit exceeds bounded size."; return;
    }
    const url = URL.createObjectURL(new Blob([body], {type: "application/json"}));
    const link = element("a");
    link.href = url;
    link.download = view.world_id + "." + note.id + ".field_note_edit.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = "Exported for operator CLI application.";
  });
  root.append(button, status);
}
""".strip()


def render_field_journal_editor(view: Any) -> bytes:
    obj = _keys(view, {
        "schema", "world_id", "world_digest", "slot",
        "session_digest", "journal_digest", "scene", "ending",
        "notes", "revision", "qualification",
    })
    if obj["schema"] != PLAYER_SCHEMA:
        raise CanonError("field_journal_invalid_editor")
    payload = canonical(obj).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(JS.encode()).digest()).decode("ascii")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + policy +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        '<title>Player field journal</title></head><body><main id="editor"></main>'
        '<script id="journal-data" type="application/json">' + payload +
        '</script><script>' + JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 524288:
        raise CanonError("field_journal_editor_too_large")
    return page
