"""Offline alternate-session authoring: CSP-bound UI exports a request, never authority."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .session import _source_session, player_view, validate_session
from .world_canon import CanonError, canonical, digest, prove

JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("fork-source").textContent);
const root = document.getElementById("fork-editor");
const $ = id => document.getElementById(id);
function option(value, label) {
  const o = document.createElement("option");
  o.value = String(value); o.textContent = label; return o;
}
const revision = $("revision"), choice = $("choice");
for (const item of data.revisions) {
  revision.append(option(item.revision, "Revision " + item.revision +
    " — " + item.scene + " (" + item.choices.length + " choices)"));
}
function refresh() {
  const item = data.revisions.find(r => r.revision === Number(revision.value));
  choice.replaceChildren();
  for (const c of item.choices) choice.append(option(c.id, c.label));
  $("status").textContent = item.choices.length ?
    "Choose a divergence and export a request for CLI proof." :
    "No valid divergence from this revision.";
  $("export").disabled = !item.choices.length;
}
revision.addEventListener("change", refresh);
$("export").addEventListener("click", () => {
  const target_slot = $("target").value.trim();
  const prompt = $("prompt").value.trim();
  if (!/^[a-z][a-z0-9_-]{0,47}$/.test(target_slot) ||
      target_slot === data.parent_slot || !prompt ||
      prompt.length > 1000) {
    $("status").textContent = "Enter a new valid slot and an original prompt.";
    return;
  }
  const request = {
    world_id: data.world_id, parent_slot: data.parent_slot,
    target_slot, prompt, at_revision: Number(revision.value),
    choice_id: choice.value
  };
  const body = JSON.stringify(request, null, 2) + "\n";
  if (new TextEncoder().encode(body).length > 524288) {
    $("status").textContent = "Request exceeds the bounded import limit.";
    return;
  }
  const url = URL.createObjectURL(new Blob([body], {type:"application/json"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = data.world_id + ".fork-request.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  $("status").textContent = "Request exported; CLI preview and explicit review required.";
});
root.insertBefore(document.createTextNode("World source lease: " +
  data.world_digest + " · Parent session lease: " + data.parent_digest),
  root.firstChild);
refresh();
""".strip()


def render_fork_editor(world: Any, parent: Any, parent_slot: str) -> bytes:
    prove(world)
    validate_session(parent, world)
    if len(parent["choices"]) > 128:
        raise CanonError("fork_editor_revision_budget")
    revisions = []
    for revision in range(len(parent["choices"]) + 1):
        seed = _source_session(world, parent["choices"][:revision])
        view = player_view(seed, world)
        revisions.append({
            "revision": revision, "scene": seed["scene"],
            "choices": view["available_choices"],
        })
    payload = canonical({
        "world_id": world["id"], "world_digest": digest(world),
        "parent_slot": parent_slot, "parent_digest": digest(parent),
        "revisions": revisions,
    }).decode("utf-8").replace("<", "\\u003c")
    hash_value = base64.b64encode(sha256(JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + hash_value +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        '<title>Original-world fork editor — ' + title + '</title></head><body>'
        '<main id="fork-editor"><h1>Alternate-playthrough editor</h1>'
        '<p>Offline request only. Canonical CLI must revalidate, review and publish.</p>'
        '<label>Fork revision <select id="revision"></select></label>'
        '<label>Alternative choice <select id="choice"></select></label>'
        '<label>New save slot <input id="target" maxlength="48"></label>'
        '<label>Original author prompt <textarea id="prompt" maxlength="1000"></textarea></label>'
        '<button type="button" id="export">Export unapproved request</button>'
        '<p id="status" role="status" aria-live="polite"></p></main>'
        '<script id="fork-source" type="application/json">' + payload +
        '</script><script>' + JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 1048576:
        raise CanonError("fork_editor_too_large")
    return page
