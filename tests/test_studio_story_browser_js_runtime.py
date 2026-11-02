"""Dependency-free Node DOM smoke for the actual CSP-bound authored story JS.

This is a real JavaScript execution regression, not a source-string assertion.
The browser/device integration qualification remains separate.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from skeleton.ai.game_builder import studio_ecosystem_story_html as story


NODE_HARNESS = r"""
"use strict";
const fs=require("node:fs");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const js=fs.readFileSync(0,"utf8");
class Element {
  constructor(tag="div",text=""){
    this.tag=tag;this.textContent=text;this.children=[];
    this.handlers={};this.value="";
  }
  replaceChildren(){this.children=[];}
  append(...items){this.children.push(...items);}
  addEventListener(event,handler){this.handlers[event]=handler;}
  setAttribute(){}
}
const ids=["studio-source","stages","summary","premise","transcript",
 "endings","restart","checkpoint","checkpoint-status","choice-preview",
 "checkpoint-copy","checkpoint-restore"];
const nodes=Object.fromEntries(ids.map(id=>[id,new Element()]));
const source={
 project_id:"original",source_digest:"a".repeat(64),
 premise:"Original world",protagonist_name:"Pilot",
 stages:[{
   id:"gate",scene_id:"gate-scene",authored_goal:"Reach the gate",
   authored_decision:"Choose a path",prerequisites:[],
   alternatives:["mercy","force"],reward:"gate_open",
   choice_effects:{mercy:["choice:gate:mercy"],force:["choice:gate:force"]}
 }],
 endings:[
   {id:"peace",requires:["choice:gate:mercy"]},
   {id:"war",requires:["choice:gate:force"]}
 ]
};
nodes["studio-source"].textContent=JSON.stringify(source);
const document={
 getElementById(id){assert.ok(nodes[id],"missing DOM node "+id);return nodes[id];},
 createElement(tag){return new Element(tag);}
};
vm.runInNewContext(js,{document},{timeout:2000});
const buttons=nodes.stages.children[0].children;
const mercy=buttons.find(el=>el.tag==="button"&&el.textContent==="mercy");
assert.ok(mercy,"source-authored choice not rendered");
const preview=buttons.find(el=>el.tag==="button"&&el.textContent==="Preview: mercy");
assert.ok(preview,"noncommitting preview not rendered");
preview.handlers.click();
assert.match(nodes["choice-preview"].textContent,/newly eligible endings: peace/);
assert.equal(nodes.summary.textContent,"0 of 1 authored stages complete");
mercy.handlers.click();
assert.match(nodes.endings.children[0].textContent,/eligible in authored sandbox/);
assert.match(nodes.endings.children[1].textContent,/unmet predicates/);
nodes["checkpoint-copy"].handlers.click();
const good=nodes.checkpoint.value;
nodes.restart.handlers.click();
assert.equal(nodes.summary.textContent,"0 of 1 authored stages complete");
nodes["checkpoint-restore"].handlers.click();
assert.equal(nodes.summary.textContent,"1 of 1 authored stages complete");
nodes.checkpoint.value=good.replace('"choices": [','"choices": [],\\n  "choices": [');
nodes["checkpoint-restore"].handlers.click();
assert.match(nodes["checkpoint-status"].textContent,/rejected/);
assert.equal(nodes.summary.textContent,"1 of 1 authored stages complete");
nodes.checkpoint.value=good.replace(source.source_digest,"b".repeat(64));
nodes["checkpoint-restore"].handlers.click();
assert.match(nodes["checkpoint-status"].textContent,/rejected/);
assert.equal(nodes.summary.textContent,"1 of 1 authored stages complete");
// Prototype-named source choices must not read inherited JS methods as effects.
for(const id of ids){nodes[id]=new Element();}
source.stages[0].alternatives=["toString"];
source.stages[0].choice_effects={};
source.endings=[{id:"safe",requires:["choice:gate:mercy"]}];
nodes["studio-source"].textContent=JSON.stringify(source);
vm.runInNewContext(js,{document},{timeout:2000});
const protoButtons=nodes.stages.children[0].children;
const proto=protoButtons.find(el=>el.tag==="button"&&el.textContent==="toString");
assert.ok(proto,"prototype-named authored choice missing");
proto.handlers.click();
assert.match(nodes.endings.children[0].textContent,/unmet predicates/);
process.stdout.write("story-browser-js-smoke: PASS\\n");
"""


def test_browser_choice_effect_and_checkpoint_runtime():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime unavailable; browser JS smoke not executed")
    run = subprocess.run(
        [node, "-e", NODE_HARNESS], input=story._JS,
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert run.returncode == 0, run.stderr
    assert "story-browser-js-smoke: PASS" in run.stdout
