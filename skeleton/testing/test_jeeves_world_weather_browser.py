"""Run actual CSP-embedded weather player/editor JavaScript in a bounded DOM."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from skeleton.jeeves.worlds.weather import _PLAYABLE_JS
from skeleton.jeeves.worlds.weather_editor import JS


HARNESS = r"""
"use strict";
const fs = require("fs");
const script = fs.readFileSync(0, "utf8");
class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.handlers = {};
    this.textContent = ""; this.value = "";
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = [...items]; }
  addEventListener(event, handler) { this.handlers[event] = handler; }
  setAttribute() {}
  remove() {}
  click() { if (this.handlers.click) this.handlers.click(); }
}
const root = new Element("main");
const world = {
  id: "harbor", start: "opening",
  scenes: [
    {id:"opening", title:"Storm", narrative:"The sea rises."},
    {id:"resolution", title:"Dawn", narrative:"The sea calms."}
  ],
  choices: [
    {id:"relight", from:"opening", to:"resolution",
     label:"Relight", requires:[], grants:["beacon_lit"]}
  ],
  endings:[{scene:"resolution", label:"Saved"}]
};
const weather = {
  schema:"jeeves.world.weather.v1", world_id:"harbor",
  world_digest:"a".repeat(64), prompt:"Original weather",
  approved:true, review_note:"Reviewed",
  scenes:[
    {scene:"opening", weather:"storm", visibility:"obscured",
     description:"A storm."},
    {scene:"resolution", weather:"clear", visibility:"clear",
     description:"Dawn."}
  ],
  overrides:[{choice:"relight", weather:"fog", visibility:"limited"}]
};
const data = new Element("script");
data.textContent = JSON.stringify({world,weather});
const document = {
  getElementById(id) { return id === "weather-data" ? data : root; },
  createElement(tag) { return new Element(tag); }
};
function has(text) { return root.children.some(e => e.textContent === text); }
function button(text) {
  const found = root.children.find(e => e.tag === "button" &&
                                      e.textContent === text);
  if (!found) throw Error("Missing button: " + text);
  return found;
}
new Function("document", script)(document);
if (!has("Weather: storm") || !has("Visibility: obscured"))
  throw Error("Initial weather not rendered");
button("Relight").click();
if (!has("Weather: fog") || !has("Visibility: limited") ||
    !has("Ending: Saved") || !has("Choices taken: relight"))
  throw Error("Choice override not replayed");
button("Restart").click();
if (!has("Weather: storm") || has("Ending: Saved"))
  throw Error("Restart did not reset weather and ending");
process.stdout.write(JSON.stringify({weather:"storm", override:"fog", reset:true}));
"""


EDITOR_HARNESS = r"""
"use strict";
const fs = require("fs");
const script = fs.readFileSync(0, "utf8");
class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.handlers = {};
    this.textContent = ""; this.value = ""; this.disabled = false;
  }
  append(...items) { this.children.push(...items); }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  setAttribute() {}
  remove() {}
  click() { if (this.handlers.click) this.handlers.click(); }
}
const root = new Element("main");
const source = {
  schema:"jeeves.world.weather.v1", world_id:"harbor",
  world_digest:"a".repeat(64), prompt:"Original weather",
  approved:false, review_note:"",
  scenes:[{scene:"opening", weather:"storm", visibility:"obscured",
           description:"Original storm"}],
  overrides:[{choice:"relight", weather:"fog", visibility:"limited"}]
};
const data = new Element("script");
data.textContent = JSON.stringify({source, choices:["relight"]});
const document = {
  getElementById(id) { return id === "source-data" ? data : root; },
  createElement(tag) { return new Element(tag); }
};
let exported;
const URL = {
  createObjectURL(blob) { exported = blob; return "blob:local"; },
  revokeObjectURL() {}
};
function walk(node) {
  return [node, ...node.children.flatMap(walk)];
}
new Function("document", "URL", "setTimeout", script)(
  document, URL, () => {}
);
const fields = walk(root);
const description = fields.find(e => e.tag === "textarea");
description.value = "Reviewed draft atmosphere";
const button = fields.find(e => e.tag === "button" &&
                                e.textContent === "Export unapproved weather source");
if (!button) throw Error("Export button missing");
button.click();
if (!exported) throw Error("Editor did not export");
exported.text().then(text => {
  const parsed = JSON.parse(text);
  if (parsed.approved || parsed.review_note ||
      parsed.scenes[0].description !== "Reviewed draft atmosphere" ||
      parsed.overrides[0].choice !== "relight")
    throw Error("Editor export altered custody or lost overrides");
  process.stdout.write(JSON.stringify({unapproved:true, choice:"relight"}));
}).catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node unavailable")
def test_weather_choice_override_and_restart_in_real_player_js():
    result = subprocess.run(["node", "-e", HARNESS], input=_PLAYABLE_JS,
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "weather": "storm", "override": "fog", "reset": True,
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="Node unavailable")
def test_offline_weather_editor_exports_unapproved_source():
    result = subprocess.run(["node", "-e", EDITOR_HARNESS], input=JS,
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "unapproved": True, "choice": "relight",
    }
