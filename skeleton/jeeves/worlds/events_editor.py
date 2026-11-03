"""Offline original scene-event editor: source-leased export, never approval."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .events import validate_events
from .world_canon import CanonError, canonical, digest

_EDITOR_JS = r"""
"use strict";
const original = JSON.parse(document.getElementById("event-source").textContent);
const sourceDigest = document.getElementById("lease").textContent;
const root = document.getElementById("editor");
const input = document.createElement("textarea");
input.setAttribute("aria-label", "Event source JSON");
input.value = JSON.stringify(original, null, 2);
input.rows = 24; input.cols = 88;
const exportButton = document.createElement("button");
exportButton.textContent = "Export unapproved source";
const output = document.createElement("pre");
output.setAttribute("role", "status");
exportButton.addEventListener("click", () => {
  try {
    const candidate = JSON.parse(input.value);
    if (!candidate || Array.isArray(candidate) || typeof candidate !== "object") {
      throw Error("expected object");
    }
    if (candidate.schema !== original.schema ||
        candidate.world_id !== original.world_id ||
        candidate.world_digest !== original.world_digest) {
      throw Error("source lease changed");
    }
    if (!Array.isArray(candidate.events) || candidate.events.length < 1 ||
        candidate.events.length > 16) throw Error("invalid event count");
    const ids = new Set();
    for (const event of candidate.events) {
      if (!event || typeof event !== "object" ||
          !/^[a-z][a-z0-9_-]{0,47}$/.test(event.id) ||
          ids.has(event.id) || !Array.isArray(event.requires) ||
          !Array.isArray(event.grants)) throw Error("invalid event");
      ids.add(event.id);
    }
    candidate.events.sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    candidate.approved = false;
    candidate.review_note = "Review required after offline editor export";
    output.textContent = JSON.stringify({
      expected_digest: sourceDigest,
      source: candidate,
      review_required: true
    }, null, 2);
  } catch (error) {
    output.textContent = "Export rejected: " + error.message;
  }
});
root.append(input, exportButton, output);
""".strip()


def render_editor(data: Any, world: Any) -> bytes:
    validate_events(data, world)
    payload = canonical(data).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_EDITOR_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "script-src 'sha256-" + policy + "'; connect-src 'none'; "
        'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        '<title>' + title + ' event editor</title></head><body>'
        '<main id="editor"></main>'
        '<span id="lease" hidden>' + digest(data) + '</span>'
        '<script id="event-source" type="application/json">' + payload + '</script>'
        '<script>' + _EDITOR_JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 1048576:
        raise CanonError("events_editor_too_large")
    return page
