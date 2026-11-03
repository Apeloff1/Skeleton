"""CSP-hashed offline weather editor; exports drafts, never approves them."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .weather import validate_weather
from .world_canon import CanonError, canonical

JS = r"""
"use strict";
const source = JSON.parse(document.getElementById("source-data").textContent);
const root = document.getElementById("editor");
const fields = [];
function node(tag, text) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  return e;
}
root.append(node("h1", "Original scene weather editor"));
root.append(node("p", "Offline draft export only. Approval is an operator action."));
for (const scene of source.scenes) {
  const label = node("label", "Scene " + scene.scene + " — atmosphere");
  const input = node("textarea"); input.value = scene.description;
  input.maxLength = 1024; input.rows = 3;
  label.append(input); root.append(label);
  fields.push(input);
}
const exportButton = node("button", "Export unapproved weather source");
exportButton.type = "button"; root.append(exportButton);
const status = node("p"); status.setAttribute("role", "status");
root.append(status);
exportButton.addEventListener("click", () => {
  const draft = JSON.parse(JSON.stringify(source));
  draft.approved = false; draft.review_note = "";
  for (let i = 0; i < fields.length; i++)
    draft.scenes[i].description = fields[i].value;
  const body = JSON.stringify(draft, null, 2) + "\n";
  if (new TextEncoder().encode(body).length > 524288) {
    status.textContent = "Source too large"; return;
  }
  const url = URL.createObjectURL(new Blob([body], {type:"application/json"}));
  const link = node("a"); link.href = url;
  link.download = source.world_id + ".weather.unapproved.json";
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  status.textContent = "Exported for reviewed CLI publication.";
});
""".strip()


def render_weather_editor(source: Any, world: Any) -> bytes:
    validate_weather(source, world)
    if source["approved"]:
        raise CanonError("weather_editor_requires_draft")
    payload = canonical(source).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(JS.encode()).digest()).decode("ascii")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + policy +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        '<title>Weather editor</title></head><body><main id="editor"></main>'
        '<script id="source-data" type="application/json">' + payload +
        '</script><script>' + JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 524288:
        raise CanonError("weather_editor_too_large")
    return page
