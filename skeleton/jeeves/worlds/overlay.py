"""Deterministic offline browser player for authored faction and clue effects.

The player is a rendering of the same source-validated choice graph as the
canonical world engine. It never writes custody files or claims its browser
state is an authenticated save. Python remains the authoritative replay proof.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import html
from typing import Any

from .world_canon import CanonError, MAX_SOURCE_BYTES, canonical, digest, prove

_SCRIPT = r"""
"use strict";
const manifest = JSON.parse(document.getElementById("world-data").textContent);
const world = manifest.world;
const factions = manifest.factions;
const evidence = manifest.evidence;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const root = document.getElementById("play");
let scene = world.start;
const flags = new Set();
const trace = [];
const observed = new Set();
const collected = new Set();
const reputation = new Map(
  factions ? factions.factions.map(f => [f.id, 0]) : []);
function element(tag, value) {
  const node = document.createElement(tag);
  node.textContent = String(value);
  return node;
}
function addChoice(choice) {
  if (endings.has(scene) || choice.from !== scene ||
      !choice.requires.every(flag => flags.has(flag))) return;
  trace.push(choice.id);
  for (const flag of choice.grants) flags.add(flag);
  if (factions) for (const rule of factions.rules) {
    if (rule.choice_id === choice.id) {
      const previous = reputation.get(rule.faction_id);
      reputation.set(rule.faction_id,
        Math.max(-100, Math.min(100, previous + rule.delta)));
    }
  }
  observed.add(choice.id);
  if (evidence) {
    let changed = true;
    while (changed) {
      changed = false;
      for (const clue of evidence.clues) {
        if (!collected.has(clue.id) &&
            observed.has(clue.unlock_choice) &&
            clue.depends_on.every(id => collected.has(id))) {
          collected.add(clue.id);
          changed = true;
        }
      }
    }
  }
  scene = choice.to;
  render();
}
function render() {
  root.replaceChildren();
  const current = scenes.get(scene);
  root.append(element("h1", current.title));
  root.append(element("p", current.narrative));
  if (endings.has(scene)) {
    root.append(element("h2", "Ending: " + endings.get(scene)));
  } else {
    const options = world.choices.filter(c => c.from === scene &&
      c.requires.every(flag => flags.has(flag)))
      .sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    for (const choice of options) {
      const button = element("button", choice.label);
      button.type = "button";
      button.addEventListener("click", () => addChoice(choice));
      root.append(button);
    }
  }
  if (factions) {
    root.append(element("h2", "Faction reputation"));
    for (const faction of factions.factions) {
      root.append(element("p",
        faction.name + ": " + String(reputation.get(faction.id))));
    }
  }
  if (evidence) {
    root.append(element("h2", "Discovered evidence"));
    const visible = evidence.clues.filter(clue => collected.has(clue.id));
    if (!visible.length) root.append(element("p", "No clues discovered yet."));
    for (const clue of visible) {
      root.append(element("h3", clue.title));
      root.append(element("p", clue.detail));
    }
  }
  root.append(element("p", "Choices played: " + String(trace.length)));
}
render();
""".strip()


def compile_overlay_html(world: Any, *, factions: Any = None,
                         evidence: Any = None) -> str:
    proof = prove(world)
    if factions is None and evidence is None:
        raise CanonError("empty_world_overlay")
    if factions is not None:
        from .factions import compile_factions
        compile_factions(factions, world)
    if evidence is not None:
        from .evidence import compile_evidence
        compile_evidence(evidence, world)
    manifest = {
        "schema": "jeeves.world.browser_overlay.v1",
        "world": world, "world_digest": proof.source_digest,
        "factions": factions, "factions_digest": (
            digest(factions) if factions is not None else None),
        "evidence": evidence, "evidence_digest": (
            digest(evidence) if evidence is not None else None),
        "qualification": "offline_source_replay_not_device_certified",
    }
    embedded = canonical(manifest).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(_SCRIPT.encode()).digest()).decode()
    title = html.escape(world["id"], quote=True)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        f"script-src 'sha256-{script_hash}'; style-src 'none'; "
        "connect-src 'none'; img-src 'none'; object-src 'none'; "
        'base-uri \'none\'; form-action \'none\'">'
        f"<title>Original world: {title}</title></head>"
        '<body><main id="play" aria-live="polite"></main>'
        '<script id="world-data" type="application/json">'
        f"{embedded}</script><script>{_SCRIPT}</script></body></html>\n"
    )
    if len(page.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise CanonError("overlay_too_large")
    return page
