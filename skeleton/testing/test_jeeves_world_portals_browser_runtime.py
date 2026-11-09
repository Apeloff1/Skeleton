"""Execute the real offline portal browser JS against a deterministic DOM.

No network or browser installation is needed; Node is optional in Python-only
developer environments, but the full runtime path is exercised where present.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from skeleton.jeeves.worlds.portals import PLAYER_JS


HARNESS = r"""
"use strict";
const fs = require("fs");
const source = fs.readFileSync(0, "utf8");
class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.textContent = "";
    this.value = "";
    this.id = "";
    this.handlers = {};
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = [...items]; }
  addEventListener(name, action) { this.handlers[name] = action; }
  setAttribute(key, value) { this[key] = value; }
  focus() {}
  select() {}
  click() {
    if (!this.handlers.click) throw Error("Missing click handler");
    this.handlers.click();
  }
}
function world(id) {
  return {
    id, region: id, start: "opening",
    scenes: [
      {id: "opening", title: "Opening", narrative: "Original narrative"},
      {id: "resolution", title: "End", narrative: "Original resolution"}
    ],
    choices: [
      {id: "pursue_goal", from: "opening", to: "resolution",
       label: "Pursue", requires: [], grants: []}
    ],
    endings: [{scene: "resolution", label: "Finished"}]
  };
}
const model = {
  network: {
    id: "journey", root_world: "harbor",
    world_digests: {harbor: "b".repeat(64), forest: "c".repeat(64)},
    portals: [{id: "first_crossing", from_world: "harbor",
               from_ending: "resolution", to_world: "forest", label: "Cross"}]
  },
  worlds: {harbor: world("harbor"), forest: world("forest")},
  proof: {network_digest: "a".repeat(64)}
};
const root = new Element("main");
const data = new Element("script");
data.textContent = JSON.stringify(model);
function find(id, node = root) {
  if (node.id === id) return node;
  for (const child of node.children) {
    const result = find(id, child);
    if (result) return result;
  }
  return null;
}
const document = {
  getElementById(id) {
    if (id === "portals-data") return data;
    if (id === "play") return root;
    return find(id);
  },
  createElement(tag) { return new Element(tag); }
};
function button(label) {
  const match = root.children.find(
    element => element.tag === "button" && element.textContent === label
  );
  if (!match) throw Error("Missing button " + label);
  return match;
}
new Function("document", source)(document);
button("Pursue").click();
button("Travel: Cross").click();
button("Pursue").click();
button("Export session JSON").click();
const serialized = document.getElementById("session-export").value;
const trace = JSON.parse(serialized);
if (trace.steps.length !== 3 || trace.current_world !== "forest" ||
    trace.current_scene !== "resolution") throw Error("Export failed");
button("Restart").click();
button("Import session JSON").click();
document.getElementById("session-import").value = serialized;
button("Restore locally checked session").click();
if (!root.children.some(e => e.textContent === "Ending: Finished"))
  throw Error("Restore failed");
button("Import session JSON").click();
trace.flags.harbor = ["unearned"];
document.getElementById("session-import").value = JSON.stringify(trace);
button("Restore locally checked session").click();
if (!root.children.some(
  e => e.textContent === "Session rejected: invalid, stale or unearned replay."
)) throw Error("Forged flags accepted");
process.stdout.write(JSON.stringify({
  moves: 3, ending: "forest:resolution", forged_flags_rejected: true
}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node runtime unavailable")
def test_real_browser_export_import_and_forgery_rejection():
    completed = subprocess.run(
        ["node", "-e", HARNESS],
        input=PLAYER_JS,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "moves": 3, "ending": "forest:resolution",
        "forged_flags_rejected": True,
    }
