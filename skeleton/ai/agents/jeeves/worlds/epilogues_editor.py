"""Network-disabled, CSP-hashed original ending prose editor (unapproved export)."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .epilogues import validate_epilogues
from .world_canon import CanonError, canonical

JS = r"""
"use strict";
const source = JSON.parse(document.getElementById("source-data").textContent);
const root = document.getElementById("editor");
const fields = [];
function element(tag, label) {
  const node = document.createElement(tag);
  if (label) node.textContent = label;
  return node;
}
root.append(element("h1", "Original ending epilogue editor"));
root.append(element("p", "Offline draft only; CLI review and approval required."));
for (const entry of source.entries) {
  root.append(element("h2", "Ending scene: " + entry.scene));
  const titleLabel = element("label", "Title");
  const title = element("textarea");
  title.value = entry.title; title.maxLength = 256;
  titleLabel.append(title); root.append(titleLabel);
  const textLabel = element("label", "Original epilogue prose");
  const prose = element("textarea");
  prose.value = entry.text; prose.maxLength = 4096;
  prose.rows = 6; prose.cols = 80;
  textLabel.append(prose); root.append(textLabel);
  fields.push({title, prose});
}
const exportButton = element("button", "Export unapproved source");
exportButton.type = "button";
const status = element("p");
status.setAttribute("role", "status");
status.setAttribute("aria-live", "polite");
root.append(exportButton, status);
exportButton.addEventListener("click", () => {
  const draft = JSON.parse(JSON.stringify(source));
  draft.approved = false;
  draft.review_note = "";
  for (let i = 0; i < fields.length; i++) {
    draft.entries[i].title = fields[i].title.value;
    draft.entries[i].text = fields[i].prose.value;
  }
  const body = JSON.stringify(draft, null, 2) + "\n";
  if (new TextEncoder().encode(body).length > 524288) {
    status.textContent = "Source exceeds bounded import size."; return;
  }
  const url = URL.createObjectURL(new Blob([body], {type:"application/json"}));
  const link = element("a");
  link.href = url; link.download = source.world_id + ".epilogues.unapproved.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  status.textContent = "Exported for source-leased CLI review; not published.";
});
""".strip()


def render_epilogues_editor(source: Any, world: Any) -> bytes:
    validate_epilogues(source, world)
    if source["approved"]:
        raise CanonError("epilogues_editor_requires_draft")
    payload = canonical(source).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(JS.encode()).digest()).decode("ascii")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + policy +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        '<title>Original epilogues: ' + html.escape(world["id"], quote=True) +
        '</title></head><body><main id="editor"></main>'
        '<script id="source-data" type="application/json">' + payload +
        '</script><script>' + JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 524288:
        raise CanonError("epilogues_editor_too_large")
    return page
