"""Offline NPC relationship editor with CSP and unapproved source export."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .relationships import validate_relationships
from .world_canon import CanonError, canonical, digest

_EDITOR_JS = r"""
"use strict";
const original = JSON.parse(document.getElementById("relationship-source").textContent);
const lease = document.getElementById("lease").textContent;
const root = document.getElementById("editor");
const input = document.createElement("textarea");
input.rows = 24; input.cols = 88;
input.setAttribute("aria-label", "Original relationship source JSON");
input.value = JSON.stringify(original, null, 2);
const button = document.createElement("button");
button.textContent = "Export unapproved relationships";
const output = document.createElement("pre");
output.setAttribute("role", "status");
button.addEventListener("click", () => {
  try {
    const candidate = JSON.parse(input.value);
    if (!candidate || Array.isArray(candidate) || typeof candidate !== "object" ||
        candidate.schema !== original.schema ||
        candidate.world_id !== original.world_id ||
        candidate.world_digest !== original.world_digest ||
        candidate.cast_digest !== original.cast_digest ||
        !Array.isArray(candidate.bonds) || candidate.bonds.length < 1 ||
        candidate.bonds.length > 8) throw Error("invalid source lease");
    const ids = new Set();
    for (const bond of candidate.bonds) {
      if (!bond || !/^[a-z][a-z0-9_-]{0,47}$/.test(bond.id) ||
          ids.has(bond.id) || !Array.isArray(bond.rules) ||
          !Array.isArray(bond.reactions)) throw Error("invalid bond");
      ids.add(bond.id);
      bond.rules.sort((a,b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
      bond.reactions.sort((a,b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    }
    candidate.bonds.sort((a,b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    candidate.approved = false;
    candidate.review_note = "Review required after offline editor export";
    output.textContent = JSON.stringify({
      expected_digest: lease, source: candidate, review_required: true
    }, null, 2);
  } catch (error) {
    output.textContent = "Export rejected: " + error.message;
  }
});
root.append(input, button, output);
""".strip()


def render_editor(data: Any, world: Any, cast: Any) -> bytes:
    validate_relationships(data, world, cast)
    payload = canonical(data).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_EDITOR_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "script-src 'sha256-" + policy + "'; connect-src 'none'; "
        'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        '<title>' + title + ' relationship editor</title></head><body>'
        '<main id="editor"></main><span id="lease" hidden>' + digest(data) + '</span>'
        '<script id="relationship-source" type="application/json">' + payload + '</script>'
        '<script>' + _EDITOR_JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("relationships_editor_too_large")
    return page
