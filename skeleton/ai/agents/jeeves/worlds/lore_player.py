"""Canonical offline player with branch-earned original lore, no spoilers."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .lore import validate_lore
from .world_canon import (
    CanonError, _PLAYER_JS, canonical, compile_manifest, digest,
)

_SOURCE_SEAM = 'const world = model.world;'
_RENDER_SEAM = '  root.append(element("p", "Choices taken: " + trace.join(", ")));'
_RESTART_SEAM = 'current = world.start; flags = new Set(); trace = []; render();'

_LORE_RENDER = r"""
  for (const fact of lore.facts) {
    if (fact.scene === current &&
        fact.requires_flags.every(flag => flags.has(flag))) {
      discovered.add(fact.id);
    }
  }
  if (discovered.size) {
    const heading = element("h2", "Discovered lore");
    root.append(heading);
    const entries = document.createElement("ul");
    for (const fact of lore.facts) {
      if (!discovered.has(fact.id)) continue;
      const entry = element("li", fact.subject + ": " + fact.statement);
      entries.append(entry);
    }
    root.append(entries);
  }
""".rstrip()

if (_PLAYER_JS.count(_SOURCE_SEAM) != 1 or
    _PLAYER_JS.count(_RENDER_SEAM) != 1 or
    _PLAYER_JS.count(_RESTART_SEAM) != 1):
    raise RuntimeError("canonical_lore_player_seam_changed")

_LORE_JS = (
    _PLAYER_JS.replace(
        _SOURCE_SEAM,
        _SOURCE_SEAM + "\nconst lore = model.lore;\nlet discovered = new Set();",
    )
    .replace(_RENDER_SEAM, _RENDER_SEAM + "\n" + _LORE_RENDER)
    .replace(
        _RESTART_SEAM,
        "current = world.start; flags = new Set(); trace = []; "
        "discovered = new Set(); render();",
    )
)


def render_lore_playable(world: Any, lore: Any) -> bytes:
    """Author-approved source yields an actual playable with earned lore."""
    validate_lore(lore, world)
    if not lore["approved"]:
        raise CanonError("lore_review_required")
    manifest = compile_manifest(world)
    manifest["lore"] = {
        "schema": "jeeves.world.lore_player.v1",
        "world_digest": digest(world),
        "lore_digest": digest(lore),
        "facts": lore["facts"],
    }
    embedded = canonical(manifest).decode("utf-8").replace("<", "\\u003c")
    policy_hash = base64.b64encode(
        sha256(_LORE_JS.encode("utf-8")).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        f"script-src 'sha256-{policy_hash}'; style-src 'none'; "
        "connect-src 'none'; img-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'\">"
        f"<title>{title} — lore-aware world</title></head><body>"
        "<main id='play' aria-live='polite'></main>"
        f"<script id='world-data' type='application/json'>{embedded}</script>"
        f"<script>{_LORE_JS}</script></body></html>\n"
    )
    return page.encode("utf-8")
