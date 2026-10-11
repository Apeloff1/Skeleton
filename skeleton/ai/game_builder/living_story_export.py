"""Produce a second, independently playable genre for browser and Godot 4.

Every story/quest/NPC schedule is serialized from Python's verified reference
runtime. Executable browser and Godot logic is hand-authored original code.
Native replay on Linux and Windows can verify the same story witness.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .contracts import canonical_digest
from .living_story_runtime import StoryWorld, StoryReplay, StoryError, story_verify
from .playable_export import _safe_script_json, _sha256_csp
from .dual_runtime_export import _EXPORT_PRESETS


class StoryExportError(ValueError):
    """Narrative package failed reproducibility or source-safety checks."""


_CSS = r"""
:root{color-scheme:dark;font:16px/1.55 system-ui,sans-serif;color:#eaf5f3;background:#091821}
*{box-sizing:border-box}
body{margin:0}header{padding:1.3rem;background:#133141;border-bottom:1px solid #4d8792}
h1{margin:0;font-size:clamp(1.4rem,4vw,2rem)}
main{max-width:1160px;margin:0 auto;padding:1rem;display:grid;grid-template-columns:1fr;gap:1rem}
.panel{padding:1rem;background:#142935;border:1px solid #375d67;border-radius:1rem;min-width:0}
h2{margin:.2rem 0 .65rem}h3{margin:.5rem 0}
.stats{display:flex;gap:1rem;flex-wrap:wrap;font-variant-numeric:tabular-nums}
#places{display:grid;grid-template-columns:repeat(auto-fill,minmax(142px,1fr));gap:.4rem}
button{font:inherit;border:1px solid #83c9b2;background:#1e4a56;color:white;min-height:44px;
 padding:.5rem .65rem;border-radius:.5rem;text-align:left;cursor:pointer}
button:hover{background:#326674}button:focus-visible{outline:3px solid #ffdb7c;outline-offset:2px}
button[disabled]{opacity:.55;cursor:not-allowed}
.place{padding:.65rem;border-radius:.5rem;background:#203c4b;border:1px solid #4c7881}
.place[aria-current=location]{border:3px solid #ffd577;background:#305869}
.npc{padding:.6rem;border-left:3px solid #79d8b6;background:#183847;margin:.5rem 0}
#actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.5rem}
#journal{white-space:pre-wrap;max-height:260px;overflow:auto;font:13px/1.5 ui-monospace,monospace}
#message{color:#ffde9a;min-height:2em}
label{display:block}summary{cursor:pointer}footer{padding:1.5rem;text-align:center;opacity:.8}
@media(min-width:800px){main{grid-template-columns:minmax(0,2fr) minmax(280px,1fr)}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important}}
"""

_JS = r"""
"use strict";
const WORLD=__STORY_DATA__;
const first=WORLD.regions[0].key;
const citizenById=Object.fromEntries(WORLD.citizens.map(n=>[n.key,n]));
const regionById=Object.fromEntries(WORLD.regions.map(n=>[n.key,n]));
const questById=Object.fromEntries(WORLD.quests.map(n=>[n.key,n]));
const factions=["gardeners","wayfinders","makers"];
const phases=["morning","working hours","evening","night"];
const MAX=1024;
const nodes={
 phase:document.getElementById("phase"),region:document.getElementById("region"),
 turn:document.getElementById("turn"),quests:document.getElementById("quests"),
 score:document.getElementById("score"),status:document.getElementById("status"),
 ending:document.getElementById("ending"),message:document.getElementById("message"),
 places:document.getElementById("places"),npcs:document.getElementById("npcs"),
 actions:document.getElementById("actions"),journal:document.getElementById("journal")
};
let state,history=[],events=[];
function initial(){return {location:first,turn:0,inventory:[],known:[],completed:[],
 discussed:[],faction_trust:[0,0,0],ending:null,status:"playing",score:0};}
function clone(s){return JSON.parse(JSON.stringify(s));}
function where(n,turn){
 const phase=Math.floor(turn/3)%4;
 return [n.home,n.workplace,n.lookout,n.home][phase];
}
function available(s){
 if(s.status==="won"||s.turn>=MAX)return [];
 const output=["wait"];
 output.push(...regionById[s.location].neighbors.map(x=>"travel:"+x));
 for(const q of WORLD.quests){
  if(!s.completed.includes(q.key)&&!s.inventory.includes(q.item)&&q.source_region===s.location)
   output.push("gather:"+q.item);
 }
 for(const npc of WORLD.citizens){
  if(where(npc,s.turn)!==s.location)continue;
  if(!s.discussed.includes(npc.key))output.push("talk:"+npc.key);
  for(const q of WORLD.quests){
   if(q.giver===npc.key&&s.known.includes(q.key)&&s.inventory.includes(q.item)
      &&!s.completed.includes(q.key))output.push("resolve:"+q.key);
  }
 }
 if(s.ending===null&&s.completed.length>=WORLD.intent.quests_to_finish)
  output.push("choose:stewardship","choose:discovery","choose:independence");
 return output;
}
function line(n,s){
 const q=WORLD.quests.find(v=>v.giver===n.key);
 let purpose="I keep notes on changing paths and visitors.";
 if(q&&s.completed.includes(q.key))purpose="Your work helped our community thrive.";
 else if(q&&s.inventory.includes(q.item))purpose="You found our missing item. Please bring it to me.";
 else if(q)purpose=q.premise+" — seek the artifact in "+regionById[q.source_region].name+".";
 return n.name+", the "+n.temperament+" "+n.role+" ("+n.faction+
  "), says during "+phases[Math.floor(s.turn/3)%4]+": "+purpose;
}
function actionLabel(a){
 const [verb,arg]=a.split(":");
 if(verb==="wait")return "Wait one turn";
 if(verb==="travel")return "Travel to "+regionById[arg].name;
 if(verb==="talk")return "Talk: "+citizenById[arg].name;
 if(verb==="gather")return "Collect original artifact "+arg.slice(-2);
 if(verb==="resolve")return "Complete: "+questById[arg].premise;
 if(verb==="choose")return "Choose ending: "+arg;
 return a;
}
function play(action){
 if(!available(state).includes(action))return;
 if(events.length>=MAX)return;
 history.push(clone(state));
 const s=clone(state);
 if(action.startsWith("travel:"))s.location=action.slice(7);
 else if(action.startsWith("gather:"))s.inventory.push(action.slice(7));
 else if(action.startsWith("talk:")){
  const id=action.slice(5);s.discussed.push(id);
  for(const q of WORLD.quests)if(q.giver===id)s.known.push(q.key);
 }else if(action.startsWith("resolve:")){
  const q=questById[action.slice(8)];
  s.inventory.splice(s.inventory.indexOf(q.item),1);s.completed.push(q.key);
 }else if(action.startsWith("choose:"))s.ending=action.slice(7);
 for(const k of ["inventory","known","completed","discussed"])s[k].sort();
 s.faction_trust=factions.map(f=>25*WORLD.quests.filter(
  q=>q.faction===f&&s.completed.includes(q.key)).length);
 s.score=WORLD.quests.filter(q=>s.completed.includes(q.key))
    .reduce((t,q)=>t+q.reward,0);
 s.turn++;
 s.status=s.ending===null?"playing":WORLD.intent.mode==="campaign"?"won":
    WORLD.intent.mode==="postgame"?"epilogue":"open";
 state=s;events.push(action);
 render("Action: "+actionLabel(action));
}
function render(message){
 nodes.phase.textContent=phases[Math.floor(state.turn/3)%4];
 nodes.turn.textContent=state.turn;
 nodes.region.textContent=regionById[state.location].name;
 nodes.quests.textContent=state.completed.length+" / "+WORLD.quests.length;
 nodes.score.textContent=state.score;
 nodes.status.textContent=state.status;
 nodes.ending.textContent=state.ending||"undecided";
 nodes.message.textContent=message;
 nodes.places.replaceChildren();
 for(const r of WORLD.regions){
  const box=document.createElement("div");box.className="place";
  if(r.key===state.location)box.setAttribute("aria-current","location");
  const title=document.createElement("strong");title.textContent=r.name;
  const weather=document.createElement("div");weather.textContent=r.atmosphere;
  box.append(title,weather);nodes.places.append(box);
 }
 nodes.npcs.replaceChildren();
 const local=WORLD.citizens.filter(n=>where(n,state.turn)===state.location);
 for(const npc of local){
  const div=document.createElement("div");div.className="npc";
  const heading=document.createElement("strong");heading.textContent=npc.name+" · "+npc.role;
  const detail=document.createElement("div");detail.textContent=
   npc.temperament+" · "+npc.faction;
  div.append(heading,detail);
  if(state.discussed.includes(npc.key)){
   const speech=document.createElement("p");speech.textContent=line(npc,state);
   div.append(speech);
  }
  nodes.npcs.append(div);
 }
 if(local.length===0)nodes.npcs.textContent="The square is quiet this turn. Citizens have daily schedules.";
 nodes.actions.replaceChildren();
 for(const a of available(state)){
  const button=document.createElement("button");button.type="button";
  button.textContent=actionLabel(a);button.addEventListener("click",()=>play(a));
  nodes.actions.append(button);
 }
 const log=["World: "+WORLD.intent.title,
   "Factions: "+factions.map((f,i)=>f+" "+state.faction_trust[i]).join(" · "),
   "Inventory: "+(state.inventory.join(", ")||"empty"),
   "Known: "+(state.known.join(", ")||"none"),
   "Completed: "+(state.completed.join(", ")||"none"),
   "Citizens: "+WORLD.citizens.length+" · Regions: "+WORLD.regions.length,
   "Turn history: "+events.slice(-24).join(" → ")];
 nodes.journal.textContent=log.join("\n");
}
function reset(){state=initial();history=[];events=[];render("A new original world begins.");}
function undo(){if(!history.length)return;state=history.pop();events.pop();render("Undid the previous action.");}
function save(){
 const data={schema:"skeleton.game_builder.story_browser_actions.v1",
  world_digest:WORLD.world_digest,actions:events.slice(),
  note:"Client action trace. Verify independently with the Python story engine."};
 const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
 const url=URL.createObjectURL(blob),a=document.createElement("a");
 a.href=url;a.download="original-story-actions.json";
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),0);
}
document.getElementById("reset").addEventListener("click",reset);
document.getElementById("undo").addEventListener("click",undo);
document.getElementById("save").addEventListener("click",save);
document.addEventListener("keydown",e=>{
 if(["INPUT","TEXTAREA","SELECT"].includes(e.target.tagName)||e.ctrlKey||e.metaKey)return;
 if(e.code==="KeyZ"){e.preventDefault();undo();}
});
reset();
"""

_GODOT = r'''
extends Control
## Original living-world RPG. Typed narrative data only; no network or plugins.
const MAX_ACTIONS = 1024
var world: Dictionary = {}
var regions: Array = []
var citizens: Array = []
var quests: Array = []
var location: String = ""
var turn: int = 0
var inventory: Array = []
var known: Array = []
var completed: Array = []
var discussed: Array = []
var trust: Array = [0, 0, 0]
var ending: Variant = null
var status: String = "playing"
var score: int = 0
var message: String = "Explore the world and meet its people."
var ready_to_play: bool = false
var action_log: Array = []
var undo_log: Array = []
var buttons: VBoxContainer

func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var text: String = FileAccess.get_file_as_string("res://story.json")
    if text.is_empty() or text.length() > 190000:
        push_error("Invalid original narrative world")
        return
    var decoded: Variant = JSON.parse_string(text)
    if typeof(decoded) != TYPE_DICTIONARY:
        push_error("Narrative world is not a map")
        return
    world = decoded
    if str(world.get("schema", "")) != "skeleton.game_builder.living_story.v1":
        push_error("Unknown narrative format")
        return
    regions = world.get("regions", [])
    citizens = world.get("citizens", [])
    quests = world.get("quests", [])
    if regions.is_empty() or citizens.is_empty() or quests.size() != 3:
        push_error("Invalid original RPG content")
        return
    get_window().title = str(world["intent"]["title"])
    buttons = VBoxContainer.new()
    buttons.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
    buttons.position = Vector2(560, 18)
    buttons.custom_minimum_size = Vector2(310, 640)
    add_child(buttons)
    ready_to_play = true
    _reset()
    if "--verify-story" in OS.get_cmdline_user_args():
        _verify()

func _reset() -> void:
    location = str(regions[0]["key"])
    turn = 0
    inventory = []
    known = []
    completed = []
    discussed = []
    trust = [0, 0, 0]
    ending = null
    status = "playing"
    score = 0
    action_log = []
    undo_log = []
    message = "A new world begins. Original NPCs follow daily schedules."
    _redraw()

func _region(id: String) -> Dictionary:
    for r in regions:
        if str(r["key"]) == id:
            return r
    return {}

func _npc(id: String) -> Dictionary:
    for n in citizens:
        if str(n["key"]) == id:
            return n
    return {}

func _where(n: Dictionary) -> String:
    var phase: int = (turn / 3) % 4
    match phase:
        0: return str(n["home"])
        1: return str(n["workplace"])
        2: return str(n["lookout"])
        _: return str(n["home"])

func _choices() -> Array:
    var choices: Array = []
    if not ready_to_play or status == "won" or turn >= MAX_ACTIONS:
        return choices
    choices.append("wait")
    for next_region in _region(location)["neighbors"]:
        choices.append("travel:" + str(next_region))
    for q in quests:
        if not completed.has(q["key"]) and not inventory.has(q["item"]) and str(q["source_region"]) == location:
            choices.append("gather:" + str(q["item"]))
    for n in citizens:
        if _where(n) != location:
            continue
        if not discussed.has(n["key"]):
            choices.append("talk:" + str(n["key"]))
        for q in quests:
            if str(q["giver"]) == str(n["key"]) and known.has(q["key"]) and inventory.has(q["item"]) and not completed.has(q["key"]):
                choices.append("resolve:" + str(q["key"]))
    if ending == null and completed.size() >= int(world["intent"]["quests_to_finish"]):
        choices.append_array(["choose:stewardship", "choose:discovery", "choose:independence"])
    return choices

func _snapshot() -> Dictionary:
    return {"location": location, "turn": turn, "inventory": inventory.duplicate(),
        "known": known.duplicate(), "completed": completed.duplicate(),
        "discussed": discussed.duplicate(), "trust": trust.duplicate(),
        "ending": ending, "status": status, "score": score}

func _restore(s: Dictionary) -> void:
    location = s["location"]
    turn = s["turn"]
    inventory = s["inventory"]
    known = s["known"]
    completed = s["completed"]
    discussed = s["discussed"]
    trust = s["trust"]
    ending = s["ending"]
    status = s["status"]
    score = s["score"]

func _act(action: String, record: bool = true) -> bool:
    if not _choices().has(action):
        return false
    if record:
        undo_log.append(_snapshot())
        if undo_log.size() > 100:
            undo_log.pop_front()
    if action.begins_with("travel:"):
        location = action.substr(7)
    elif action.begins_with("gather:"):
        inventory.append(action.substr(7))
    elif action.begins_with("talk:"):
        var npc_id: String = action.substr(5)
        discussed.append(npc_id)
        for q in quests:
            if str(q["giver"]) == npc_id:
                known.append(q["key"])
    elif action.begins_with("resolve:"):
        var quest_id: String = action.substr(8)
        for q in quests:
            if str(q["key"]) == quest_id:
                inventory.erase(q["item"])
                completed.append(quest_id)
    elif action.begins_with("choose:"):
        ending = action.substr(7)
    inventory.sort()
    known.sort()
    completed.sort()
    discussed.sort()
    trust = [0, 0, 0]
    score = 0
    var names: Array = ["gardeners", "wayfinders", "makers"]
    for q in quests:
        if completed.has(q["key"]):
            score += int(q["reward"])
            trust[names.find(str(q["faction"]))] += 25
    turn += 1
    status = "playing"
    if ending != null:
        match str(world["intent"]["mode"]):
            "campaign": status = "won"
            "postgame": status = "epilogue"
            "sandbox": status = "open"
    action_log.append(action)
    message = "Action: " + action
    if record:
        _redraw()
    return true

func _undo() -> void:
    if undo_log.is_empty():
        return
    _restore(undo_log.pop_back())
    action_log.pop_back()
    message = "Undid one narrative turn."
    _redraw()

func _redraw() -> void:
    queue_redraw()
    if not ready_to_play or buttons == null:
        return
    for child in buttons.get_children():
        buttons.remove_child(child)
        child.queue_free()
    var heading := Label.new()
    heading.text = "Original world choices"
    buttons.add_child(heading)
    var viewport_height: int = 580
    var scroll := ScrollContainer.new()
    scroll.custom_minimum_size = Vector2(300, viewport_height)
    buttons.add_child(scroll)
    var vertical := VBoxContainer.new()
    vertical.custom_minimum_size.x = 285
    scroll.add_child(vertical)
    for action in _choices():
        var button := Button.new()
        button.text = _action_label(str(action))
        button.pressed.connect(_select.bind(str(action)))
        vertical.add_child(button)
    var undo_button := Button.new()
    undo_button.text = "Undo turn"
    undo_button.disabled = undo_log.is_empty()
    undo_button.pressed.connect(_undo)
    buttons.add_child(undo_button)
    var restart := Button.new()
    restart.text = "Restart story"
    restart.pressed.connect(_reset)
    buttons.add_child(restart)

func _select(action: String) -> void:
    _act(action)

func _action_label(action: String) -> String:
    if action == "wait":
        return "Wait one turn"
    if action.begins_with("travel:"):
        return "Travel: " + str(_region(action.substr(7)).get("name", "?"))
    if action.begins_with("talk:"):
        return "Talk: " + str(_npc(action.substr(5)).get("name", "?"))
    if action.begins_with("resolve:"):
        for q in quests:
            if str(q["key"]) == action.substr(8):
                return "Complete quest: " + str(q["premise"])
    if action.begins_with("gather:"):
        return "Collect " + action.substr(7)
    if action.begins_with("choose:"):
        return "Choose ending: " + action.substr(7)
    return action

func _verify() -> void:
    var text: String = FileAccess.get_file_as_string("res://proof.json")
    if text.is_empty() or text.length() > 180000:
        push_error("STORY_NATIVE_ERROR: missing bounded proof")
        get_tree().quit(1)
        return
    var doc: Variant = JSON.parse_string(text)
    if typeof(doc) != TYPE_DICTIONARY or doc.get("world_digest") != world["world_digest"]:
        push_error("STORY_NATIVE_ERROR: source/proof world mismatch")
        get_tree().quit(1)
        return
    var sequence: Variant = doc.get("actions")
    var expected: Variant = doc.get("final")
    if typeof(sequence) != TYPE_ARRAY or typeof(expected) != TYPE_DICTIONARY or sequence.size() > MAX_ACTIONS:
        push_error("STORY_NATIVE_ERROR: proof fields missing or oversized")
        get_tree().quit(1)
        return
    for action in sequence:
        if typeof(action) != TYPE_STRING or not _act(action, false):
            push_error("STORY_NATIVE_ERROR: actual action was rejected: " + str(action))
            get_tree().quit(1)
            return
    var correct: bool = (
        str(expected.get("location", "")) == location
        and int(expected.get("turn", -1)) == turn
        and str(expected.get("status", "")) == status
        and int(expected.get("score", -1)) == score
        and str(expected.get("ending", "")) == str(ending)
        and action_log.size() == sequence.size()
    )
    for field in ["inventory", "known", "completed", "discussed"]:
        var actual: Array = []
        match field:
            "inventory": actual = inventory
            "known": actual = known
            "completed": actual = completed
            "discussed": actual = discussed
        var target: Variant = expected.get(field)
        if typeof(target) != TYPE_ARRAY:
            correct = false
        elif actual != target:
            correct = false
    var target_trust: Variant = expected.get("faction_trust")
    if typeof(target_trust) != TYPE_ARRAY or target_trust.size() != 3:
        correct = false
    else:
        for i in range(3):
            if trust[i] != int(target_trust[i]):
                correct = false
    if not correct:
        push_error("STORY_NATIVE_ERROR: actual player, quest or faction state differs from Python")
        get_tree().quit(1)
        return
    print("STORY_NATIVE_REPLAY_OK " + str(world["world_digest"]) +
        " actions=" + str(action_log.size()) + " ending=" + str(ending) +
        " mode=" + str(world["intent"]["mode"]))
    get_tree().quit(0)

func _unhandled_key_input(event: InputEvent) -> void:
    if not event is InputEventKey or not event.pressed or event.echo:
        return
    if event.keycode == KEY_Z:
        _undo()
        get_viewport().set_input_as_handled()

func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO, size), Color("#0a1924"), true)
    if not ready_to_play:
        return
    _label(Vector2(20, 32), str(world["intent"]["title"]), 23, Color("#d5f5e6"))
    var region: Dictionary = _region(location)
    _label(Vector2(20, 65), str(region.get("name", "")) + " | turn " + str(turn), 17, Color.WHITE)
    _label(Vector2(20, 91), "Status: " + status + " | score " + str(score) +
        " | quests " + str(completed.size()) + "/" + str(quests.size()), 15, Color.WHITE)
    _label(Vector2(20, 117), "Ending: " + str(ending), 15, Color("#f2dd9f"))
    _label(Vector2(20, 143), message, 14, Color("#f7daa8"))
    var y: float = 183.0
    _label(Vector2(20, y), "Living citizens at this location:", 16, Color("#96e7c8"))
    y += 24
    var count: int = 0
    for citizen in citizens:
        if _where(citizen) == location:
            _label(Vector2(24, y), str(citizen["name"]) + " · " +
                str(citizen["role"]) + " · " + str(citizen["faction"]), 14, Color.WHITE)
            y += 21
            count += 1
            if count >= 12:
                break
    if count == 0:
        _label(Vector2(24, y), "Citizens are away on their schedules.", 14, Color.WHITE)
        y += 25
    y = maxf(y + 25, 505.0)
    _label(Vector2(20, y), "Inventory: " + ", ".join(inventory), 13, Color("#c0dfea"))
    y += 22
    _label(Vector2(20, y), "Known: " + ", ".join(known), 13, Color("#c0dfea"))
    y += 22
    _label(Vector2(20, y), "Completed: " + ", ".join(completed), 13, Color("#c0dfea"))
    y += 25
    _label(Vector2(20, y), "After story completion, open worlds remain playable.", 13, Color("#ffdaa0"))

func _label(at: Vector2, value: String, font_size: int, ink: Color) -> void:
    draw_string(ThemeDB.fallback_font, at, value,
        HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, ink)
'''

_PROJECT = """config_version=5

[application]
config/name="Skeleton Original Living World"
run/main_scene="res://scenes/main.tscn"
config/features=PackedStringArray("4.2", "GL Compatibility")

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"

[display]
window/size/viewport_width=900
window/size/viewport_height=720
window/stretch/mode="canvas_items"
"""

_SCENE = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scripts/main.gd" id="1"]

[node name="LivingWorldGame" type="Control"]
layout_mode = 3
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
grow_horizontal = 2
grow_vertical = 2
script = ExtResource("1")
"""

_README = """# Living World — Original narrative RPG

A genuinely playable original narrative game with NPC schedules, 3 quest
arcs, inventory, faction reputation, travel on connected multi-region maps,
3 endings and persistent postgame or open sandbox modes.

Browser: open index.html offline. Select action buttons; review changing
NPC positions, dialogue, quests and ending. Download your local trace.

Native: Godot 4.4.1+ — open godot/project.godot or export with presets.
Native proof check:
  godot --headless --path godot -- --verify-story
Desktop export:
  godot --headless --path godot --import
  godot --headless --path godot --export-release Linux living-world.x86_64
  godot --headless --path godot --export-release "Windows Desktop" living-world.exe

The source package deliberately carries no scraped assets, original games,
other companies' characters, console signing keys or provider execution.
The proof records machine replay only; human enjoyment and external hardware
distribution require separate review.
"""


def _stable_bytes(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class StoryPackage:
    files: dict[str, bytes]
    manifest: dict[str, object]

    def __post_init__(self):
        if not isinstance(self.files, dict) or not isinstance(self.manifest, dict):
            raise StoryExportError("typed, deterministic source release required")
        if set(self.files) != set(self.manifest.get("files", {})) | {"release.json"}:
            raise StoryExportError("source file manifest mismatch")
        for path, digest in self.manifest["files"].items():
            if path not in self.files or sha256(self.files[path]).hexdigest() != digest:
                raise StoryExportError("narrative source file integrity mismatch")
        if self.files["release.json"] != _stable_bytes(self.manifest):
            raise StoryExportError("serialized narrative release manifest does not match")
        body = {k: v for k, v in self.manifest.items() if k != "manifest_digest"}
        if canonical_digest(body) != self.manifest.get("manifest_digest"):
            raise StoryExportError("narrative release metadata integrity mismatch")

    @property
    def digest(self) -> str:
        return str(self.manifest["manifest_digest"])


def render_story_package(
    world: StoryWorld, proof: StoryReplay, *, authorized: bool,
) -> StoryPackage:
    if not authorized:
        raise PermissionError("living story packaging requires trusted operator")
    if not isinstance(world, StoryWorld) or not isinstance(proof, StoryReplay):
        raise StoryExportError("typed world and independently played story required")
    story_verify(world, proof, authorized=True)
    if proof.final.ending is None or proof.final.status not in {"won", "epilogue", "open"}:
        raise StoryExportError("source package requires evidence of a real reachable ending")
    story_data = {**world.payload(), "world_digest": world.digest}
    js = _JS.replace("__STORY_DATA__", _safe_script_json(story_data))
    csp = ("default-src 'none'; script-src '" + _sha256_csp(js) +
           "'; style-src '" + _sha256_csp(_CSS) +
           "'; img-src 'none'; font-src 'none'; connect-src 'none'; "
           "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'")
    from html import escape
    title = escape(world.intent.title, quote=True)
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">'
        '<title>' + title + ' — Living World</title>'
        '<style>' + _CSS + '</style></head><body>'
        '<header><h1>' + title + '</h1>'
        '<p>Original living world · Scheduled NPCs · Faction quests · Branching outcomes · Offline</p></header>'
        '<main><section class="panel"><div class="stats">'
        '<span>Region: <b id="region"></b></span><span>Time: <b id="phase"></b></span>'
        '<span>Turn: <b id="turn"></b></span><span>Quests: <b id="quests"></b></span>'
        '<span>Score: <b id="score"></b></span><span>Status: <b id="status"></b></span>'
        '<span>Ending: <b id="ending"></b></span></div><p id="message" role="status" aria-live="polite"></p>'
        '<h2>Original regions</h2><div id="places"></div>'
        '<h2>People here</h2><div id="npcs"></div>'
        '</section><section class="panel"><h2>Choices</h2><div id="actions"></div>'
        '<p><button id="undo" type="button">Undo last turn</button> '
        '<button id="reset" type="button">Restart</button> '
        '<button id="save" type="button">Download actions</button></p>'
        '<details><summary>Quest and character journal</summary><pre id="journal"></pre></details>'
        '<p>Every action advances NPC schedules. Unlike campaign mode, sandbox and postgame'
        ' modes remain playable after the story reaches an ending.</p>'
        '</section></main><footer>Offline original game. No third-party assets or external services.</footer>'
        '<script>' + js + '</script></body></html>'
    )
    doc = {
        "schema": "skeleton.game_builder.story_native_proof.v1",
        "world_digest": world.digest,
        "actions": [r.action for r in proof.receipts],
        "final": proof.final.payload(),
        "python_replay_digest": proof.digest,
    }
    files = {
        "index.html": html.encode("utf-8"),
        "godot/project.godot": _PROJECT.encode("utf-8"),
        "godot/export_presets.cfg": _EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn": _SCENE.encode("utf-8"),
        "godot/scripts/main.gd": _GODOT.encode("utf-8"),
        "godot/story.json": _stable_bytes(story_data),
        "godot/proof.json": _stable_bytes(doc),
        "world.json": _stable_bytes(story_data),
        "proof.json": _stable_bytes(doc),
        "README.md": _README.encode("utf-8"),
    }
    if sum(map(len, files.values())) > 800_000:
        raise StoryExportError("original story source archive exceeds safe byte budget")
    body = {
        "schema": "skeleton.game_builder.original_story_package.v1",
        "world_digest": world.digest, "proof_digest": proof.digest,
        "mode": world.intent.mode, "npc_count": len(world.citizens),
        "regions": len(world.regions), "quest_count": len(world.quests),
        "ending": proof.final.ending, "proof_actions": len(proof.receipts),
        "original_game_source": True, "external_assets": False,
        "trained_model": False, "publication_approved": False,
        "files": {name: sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    manifest = {**body, "manifest_digest": canonical_digest(body)}
    files["release.json"] = _stable_bytes(manifest)
    return StoryPackage(files, manifest)


__all__ = ["StoryExportError", "StoryPackage", "render_story_package"]
