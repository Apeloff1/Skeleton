"""Network-disabled scene advisory authoring; export remains unapproved."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .advisories import validate_advisories
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
root.append(element("h1", "Scene advisory authoring"));
root.append(element("p", "Offline draft only; explicit CLI review is required."));
for (const entry of source.entries) {
  root.append(element("h2", "Scene: " + entry.scene));
  const label = element("label", "Safe scene summary");
  const summary = element("textarea");
  summary.value = entry.safe_summary;
  summary.maxLength = 1024;
  summary.rows = 4; summary.cols = 72;
  label.append(summary); root.append(label);
  const categories = element("fieldset");
  categories.append(element("legend", "Scene categories"));
  const checkboxes = [];
  for (const category of [
    "conflict", "fear", "flashing", "grief", "loud_audio", "romance", "violence"
  ]) {
    const tagLabel = element("label", category);
    const checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.checked = entry.categories.includes(category);
    tagLabel.prepend(checkbox);
    categories.append(tagLabel);
    checkboxes.push({category, checkbox});
  }
  root.append(categories);
  fields.push({summary, checkboxes});
}
const button = element("button", "Export unapproved advisory source");
button.type = "button";
const status = element("p");
status.setAttribute("role", "status");
status.setAttribute("aria-live", "polite");
root.append(button, status);
button.addEventListener("click", () => {
  const draft = JSON.parse(JSON.stringify(source));
  draft.approved = false;
  draft.review_note = "";
  fields.forEach((field, i) => {
    draft.entries[i].safe_summary = field.summary.value;
    draft.entries[i].categories = field.checkboxes
      .filter(item => item.checkbox.checked)
      .map(item => item.category).sort();
  });
  const body = JSON.stringify(draft, null, 2) + "\n";
  if (new TextEncoder().encode(body).length > 524288) {
    status.textContent = "Source exceeds bounded import size."; return;
  }
  const url = URL.createObjectURL(new Blob([body], {type: "application/json"}));
  const link = element("a");
  link.href = url;
  link.download = source.world_id + ".advisories.unapproved.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  status.textContent = "Exported for CLI validation and review.";
});
""".strip()


def render_advisories_editor(source: Any, world: Any) -> bytes:
    validate_advisories(source, world)
    if source["approved"]:
        raise CanonError("advisories_editor_requires_draft")
    payload = canonical(source).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(JS.encode()).digest()).decode("ascii")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + policy +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        '<title>Advisory editor: ' + html.escape(world["id"], quote=True) +
        '</title></head><body><main id="editor"></main>'
        '<script id="source-data" type="application/json">' + payload +
        '</script><script>' + JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 524288:
        raise CanonError("advisories_editor_too_large")
    return page
