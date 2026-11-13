"""CSP-bound original dialogue locale editing, no implicit translation."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .world_canon import CanonError, canonical, digest

JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("source").textContent);
const root = document.getElementById("editor");
function node(tag, value) {
  const item = document.createElement(tag); item.textContent = value; return item;
}
function input(label, value) {
  const row = document.createElement("label");
  row.append(node("span", label + ": "));
  const field = document.createElement("input");
  field.value = value; row.append(field); root.append(row);
  root.append(node("br", "")); return field;
}
root.append(node("h1", "Original dialogue locale editor"));
root.append(node("p", "Source lease: " + model.lease));
root.append(node("p", "Review every translation before approving."));
const rows = [];
for (const edition of model.source.locales) {
  root.append(node("h2", edition.tag));
  for (const conversation of edition.conversations)
    for (const item of conversation.nodes) {
      const field = input(conversation.id + "/" + item.id, item.text);
      rows.push({tag: edition.tag, conversation: conversation.id,
                 nodeId: item.id, field});
    }
}
const button = node("button", "Export unapproved JSON");
button.type = "button";
button.addEventListener("click", () => {
  const draft = JSON.parse(JSON.stringify(model.source));
  draft.approved = false; draft.review_note = "";
  for (const row of rows) {
    const edition = draft.locales.find(e => e.tag === row.tag);
    const conversation = edition.conversations.find(c => c.id === row.conversation);
    conversation.nodes.find(n => n.id === row.nodeId).text = row.field.value;
  }
  const blob = new Blob([JSON.stringify(draft, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = model.world_id + ".dialogue.locales.unapproved.json";
  anchor.click(); URL.revokeObjectURL(url);
});
root.append(button);
""".strip()


def render_editor(source: Any, world: Any, cast: Any, dialogue: Any) -> bytes:
    embedded = canonical({
        "source": source, "world_id": world["id"], "lease": digest(source),
        "cast_digest": digest(cast), "dialogue_digest": digest(dialogue),
    }).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(JS.encode()).digest()).decode()
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        "<title>Dialogue locale editor " + html.escape(world["id"]) +
        '</title></head><body><main id="editor"></main>'
        '<script id="source" type="application/json">' + embedded +
        "</script><script>" + JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("dialogue_locale_editor_too_large")
    return page
