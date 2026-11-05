"""Offline rumor network editor; never authorizes or writes canonical custody."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .rumors import validate_rumors
from .world_canon import CanonError, canonical

_EDITOR_JS = r"""
"use strict";
const source = JSON.parse(document.getElementById("source-data").textContent);
const root = document.getElementById("editor");
const heading = document.createElement("h1");
heading.textContent = "Original rumor network editor";
root.append(heading);
const form = document.createElement("form");
const inputs = new Map();
for (const key of ["id", "claim", "stance", "origin", "seed_choice", "text"]) {
  const label = document.createElement("label");
  label.textContent = key + ": ";
  const input = document.createElement(key === "text" ? "textarea" : "input");
  input.value = source.rumors[0][key]; inputs.set(key, input);
  label.append(input); form.append(label, document.createElement("br"));
}
const routes = document.createElement("textarea");
routes.value = JSON.stringify(source.routes, null, 2);
routes.rows = 8; routes.cols = 80;
const routeLabel = document.createElement("label");
routeLabel.textContent = "Typed transfer routes (JSON array): ";
routeLabel.append(routes);
const button = document.createElement("button");
button.type = "submit"; button.textContent = "Export unapproved rumors";
const output = document.createElement("textarea");
output.readOnly = true; output.rows = 20; output.cols = 90;
form.append(routeLabel, document.createElement("br"), button);
root.append(form, output);
form.addEventListener("submit", event => {
  event.preventDefault();
  try {
    const copy = JSON.parse(JSON.stringify(source));
    copy.rumors = [Object.fromEntries(Array.from(inputs, ([key, input]) => [key, input.value]))];
    copy.routes = JSON.parse(routes.value);
    if (!Array.isArray(copy.routes)) throw new Error("Routes must be an array");
    copy.approved = false;
    copy.review_note = "Export requires canonical CLI validation and human review";
    output.value = JSON.stringify(copy, null, 2);
  } catch (_) { output.value = "Invalid route JSON; no export produced"; }
});
""".strip()


def render_editor(source: Any, world: Any, cast: Any) -> bytes:
    validate_rumors(source, world, cast)
    payload = canonical(source).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_EDITOR_JS.encode()).digest()).decode("ascii")
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + html.escape(world["id"], quote=True) + ' rumor editor</title>'
            '</head><body><main id="editor"></main>'
            '<script id="source-data" type="application/json">' + payload + '</script>'
            '<script>' + _EDITOR_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("rumors_editor_too_large")
    return page
