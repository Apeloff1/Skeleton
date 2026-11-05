"""CSP-protected offline authoring UI for original character arcs."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .world_canon import CanonError, canonical, digest

JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("source").textContent);
const root = document.getElementById("editor");
function node(tag, value) {
  const item = document.createElement(tag);
  item.textContent = value; return item;
}
function input(label, value) {
  const row = document.createElement("label");
  row.append(node("span", label + ": "));
  const field = document.createElement("input");
  field.value = value; row.append(field); root.append(row);
  root.append(node("br", "")); return field;
}
root.append(node("h1", "Original character arc editor"));
root.append(node("p", "Source lease: " + data.lease));
root.append(node("p", "Export requires renewed author review and proof."));
const prompt = input("Original prompt", data.source.prompt);
const rows = [];
for (const arc of data.source.arcs) {
  root.append(node("h2", arc.actor + " — " + arc.desire));
  rows.push({
    arc, starting: input("Starting belief", arc.starting_belief),
    resolved: input("Resolved belief", arc.resolved_belief),
  });
}
const button = node("button", "Export unapproved JSON");
button.type = "button";
button.addEventListener("click", () => {
  const draft = JSON.parse(JSON.stringify(data.source));
  draft.prompt = prompt.value; draft.approved = false; draft.review_note = "";
  for (let i = 0; i < rows.length; i++) {
    draft.arcs[i].starting_belief = rows[i].starting.value;
    draft.arcs[i].resolved_belief = rows[i].resolved.value;
  }
  const blob = new Blob([JSON.stringify(draft, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = data.world_id + ".arcs.unapproved.json";
  anchor.click(); URL.revokeObjectURL(url);
});
root.append(button);
""".strip()


def render_editor(source: Any, world: Any, cast: Any) -> bytes:
    payload = canonical({
        "source": source, "world_id": world["id"],
        "cast_digest": digest(cast), "lease": digest(source),
    }).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(JS.encode()).digest()).decode()
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        "<title>Character arcs " + html.escape(world["id"]) +
        '</title></head><body><main id="editor"></main>'
        '<script id="source" type="application/json">' + payload +
        "</script><script>" + JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("arcs_editor_too_large")
    return page
