"""Independently replayable, playable Godot 4 adapter for original puzzle scenes.

Unlike screenshot/trace playback, this GDScript implements the authored game
rules. The Python proof is an expectation to compare, not the source of native
state. No remote fetch, third-party assets, editor plugins or auto publication.
Only `puzzle` has a native adapter here; other advanced families fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from .advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session, AdvancedRuntimeError,
)
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .dual_runtime_export import _PROJECT, _SCENE, _EXPORT_PRESETS
from .system_editors import make_editor_document

NATIVE_SCHEMA="skeleton.game_builder.godot_advanced_puzzle.v1"
PROOF_SCHEMA="skeleton.game_builder.godot_advanced_puzzle_proof.v1"

# Keep a single GDScript executable independent of the Python reference. The
# proof mode executes exactly these rules, then compares gameplay state.
GODOT_PUZZLE = r'''
extends Control
## Original offline puzzle executable and independent replay convergence.
const PROOF_FLAG: String = "--verify-advanced"
const MAX_STEPS: int = 128

var game: Dictionary = {}
var config: Dictionary = {}
var scene: Dictionary = {}
var layout: Dictionary = {}
var mode: String = ""
var board_width: int = 0
var board_height: int = 0
var player: Array = []
var exit_tile: Array = []
var crates: Array = []
var walls: Array = []
var doors: Array = []
var switches: Array = []
var targets: Array = []
var nodes: Array = []
var portals: Array = []
var phase_gates: Array = []
var switches_on: Array = []
var powered_nodes: Array = []
var phase: int = 0
var portal_visited: bool = false
var undo_available: int = 0
var history: Array = []
var tick: int = 0
var move_count: int = 0
var finished: bool = false
var failed: bool = false
var notice: String = "Original puzzle — arrows move; Enter interacts; Z rewinds"
var native_actions: Array = []
var ready_to_play: bool = false


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var source: String = FileAccess.get_file_as_string("res://game.json")
    if source.is_empty() or source.length() > 80000:
        push_error("ADVANCED_PUZZLE_SOURCE: missing or oversized source")
        if PROOF_FLAG in OS.get_cmdline_user_args():
            get_tree().quit(1)
        return
    var parsed: Variant = JSON.parse_string(source)
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("ADVANCED_PUZZLE_SOURCE: invalid JSON")
        if PROOF_FLAG in OS.get_cmdline_user_args():
            get_tree().quit(1)
        return
    game = parsed
    if str(game.get("schema","")) != "skeleton.game_builder.godot_advanced_puzzle.v1":
        push_error("ADVANCED_PUZZLE_SOURCE: incompatible native contract")
        if PROOF_FLAG in OS.get_cmdline_user_args():
            get_tree().quit(1)
        return
    config = game["settings"]
    scene = game["scene"]
    layout = scene["layout"]
    mode = str(config["logic"])
    board_width = int(config["board_width"])
    board_height = int(config["board_height"])
    if board_width < 3 or board_height < 3 or board_width > 50 or board_height > 50:
        push_error("ADVANCED_PUZZLE_SOURCE: bounds rejected")
        if PROOF_FLAG in OS.get_cmdline_user_args():
            get_tree().quit(1)
        return
    ready_to_play = true
    get_window().title = "Skeleton Original Puzzle · " + mode
    _reset_game()
    if PROOF_FLAG in OS.get_cmdline_user_args():
        _verify_advanced_proof()


func _point(raw: Array) -> Array:
    # Godot JSON may load every number as a floating-point Variant; convert
    # original integer-grid coordinates before membership and tuple equality.
    return [int(raw[0]), int(raw[1])]


func _points(raw: Array) -> Array:
    var result: Array = []
    for item in raw:
        result.append(_point(item))
    return result


func _links(raw: Array) -> Array:
    var result: Array = []
    for link in raw:
        result.append([_point(link[0]), _point(link[1])])
    return result


func _reset_game() -> void:
    tick = 0
    move_count = 0
    history = []
    native_actions = []
    finished = false
    failed = false
    undo_available = mini(int(config["undo_depth"]), MAX_STEPS)
    phase = int(scene["seed"]) % 2
    player = _point(layout["spawn"])
    exit_tile = _point(layout["exit"])
    walls = _points(layout["walls"])
    doors = _points(layout["doors"])
    switches = _points(layout["switches"])
    crates = _points(layout["crates"])
    targets = _points(layout["targets"])
    nodes = _points(layout["nodes"])
    portals = _links(layout["portals"])
    phase_gates = _points(layout["phase_gates"])
    switches_on = []
    powered_nodes = []
    portal_visited = false
    notice = mode.replace("_", " ") + " · complete the authored objective"
    queue_redraw()


func _snapshot() -> Dictionary:
    return {
        "player": player.duplicate(true),
        "crates": crates.duplicate(true),
        "switches_on": switches_on.duplicate(true),
        "powered_nodes": powered_nodes.duplicate(true),
        "phase": phase,
        "portal_visited": portal_visited
    }


func _offset(action: String) -> Array:
    match action:
        "north": return [0, -1]
        "south": return [0, 1]
        "west": return [-1, 0]
        "east": return [1, 0]
    return [0, 0]


func _valid_cell(point: Array) -> bool:
    var x: int = int(point[0])
    var y: int = int(point[1])
    if x < 0 or y < 0 or x >= board_width or y >= board_height:
        return false
    if point in walls:
        return false
    if point in doors:
        if mode == "switches" and switches_on.size() < switches.size():
            return false
        if mode == "circuits" and powered_nodes.size() < nodes.size():
            return false
    if point in phase_gates and mode == "time" and phase % 2 != 0:
        return false
    return true


func _step(action: String, record: bool = true) -> bool:
    if not ready_to_play or finished or failed or tick >= MAX_STEPS:
        return false
    if action not in ["north","south","west","east","interact",
                      "undo","rewind","wait"]:
        return false
    if action == "undo" or action == "rewind":
        if history.is_empty() or undo_available <= 0:
            return false
        var previous: Dictionary = history.pop_back()
        player = previous["player"]
        crates = previous["crates"]
        switches_on = previous["switches_on"]
        powered_nodes = previous["powered_nodes"]
        phase = int(previous["phase"])
        portal_visited = bool(previous["portal_visited"])
        undo_available -= 1
        tick += 1
        notice = "Rewound the previous causal state"
        if record:
            native_actions.append(action)
        queue_redraw()
        return true
    var before: Dictionary = _snapshot()
    if action in ["north","south","west","east"]:
        var delta: Array = _offset(action)
        var destination: Array = [int(player[0]) + int(delta[0]),
                                  int(player[1]) + int(delta[1])]
        if not _valid_cell(destination):
            return false
        if destination in crates:
            var target: Array = [int(destination[0]) + int(delta[0]),
                                 int(destination[1]) + int(delta[1])]
            if mode != "push_blocks" or not _valid_cell(target) or target in crates:
                return false
            crates[crates.find(destination)] = target
        player = destination
        move_count += 1
        if mode == "non_euclidean":
            for link in portals:
                if player == link[0]:
                    player = link[1].duplicate(true)
                    portal_visited = true
                    break
                if player == link[1]:
                    player = link[0].duplicate(true)
                    portal_visited = true
                    break
    elif action == "interact":
        if mode == "switches" and player in switches:
            if player not in switches_on:
                switches_on.append(player.duplicate(true))
        elif mode == "circuits" and player in nodes:
            if player not in powered_nodes:
                powered_nodes.append(player.duplicate(true))
        else:
            return false
    tick += 1
    if mode == "time":
        phase = 1 - phase
    if int(config["undo_depth"]) > 0:
        history.append(before)
        var limit: int = mini(int(config["undo_depth"]), MAX_STEPS)
        if history.size() > limit:
            history.pop_front()
    var satisfied: bool = false
    match mode:
        "switches": satisfied = switches_on.size() == switches.size()
        "push_blocks":
            var actual: Array = crates.duplicate(true)
            var required: Array = targets.duplicate(true)
            actual.sort()
            required.sort()
            satisfied = actual == required
        "circuits": satisfied = powered_nodes.size() == nodes.size()
        "time": satisfied = phase == 0
        "non_euclidean": satisfied = portal_visited
    if player == exit_tile and (satisfied or not bool(config["solution_required"])):
        finished = true
        notice = "Original puzzle completed"
    else:
        notice = action + " · " + mode.replace("_", " ")
    if record:
        native_actions.append(action)
    queue_redraw()
    return true


func _verify_advanced_proof() -> void:
    var source: String = FileAccess.get_file_as_string("res://proof.json")
    if source.is_empty() or source.length() > 180000:
        push_error("NATIVE_ADVANCED_PUZZLE_ERROR: proof missing or too large")
        get_tree().quit(1)
        return
    var parsed: Variant = JSON.parse_string(source)
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("NATIVE_ADVANCED_PUZZLE_ERROR: invalid proof")
        get_tree().quit(1)
        return
    var proof: Dictionary = parsed
    if proof.get("schema") != "skeleton.game_builder.godot_advanced_puzzle_proof.v1":
        push_error("NATIVE_ADVANCED_PUZZLE_ERROR: unsupported proof version")
        get_tree().quit(1)
        return
    if proof.get("scene_digest") != scene.get("digest") or proof.get("settings_digest") != game.get("settings_digest"):
        push_error("NATIVE_ADVANCED_PUZZLE_ERROR: world/settings source mismatch")
        get_tree().quit(1)
        return
    var actions: Variant = proof.get("actions")
    var expected: Variant = proof.get("expected")
    if typeof(actions) != TYPE_ARRAY or typeof(expected) != TYPE_DICTIONARY:
        push_error("NATIVE_ADVANCED_PUZZLE_ERROR: invalid action/state schema")
        get_tree().quit(1)
        return
    if actions.size() > MAX_STEPS:
        push_error("NATIVE_ADVANCED_PUZZLE_ERROR: transcript too long")
        get_tree().quit(1)
        return
    for action in actions:
        if typeof(action) != TYPE_STRING or not _step(action):
            push_error("NATIVE_ADVANCED_PUZZLE_ERROR: input rejected " + str(action))
            get_tree().quit(1)
            return
    var actual: Dictionary = {
        "player": player,
        "crates": crates,
        "switches_on": switches_on,
        "powered_nodes": powered_nodes,
        "phase": phase,
        "portal_visited": portal_visited,
        "tick": tick,
        "move_count": move_count,
        "undo_available": undo_available,
        "finished": finished,
        "failed": failed
    }
    var reference: Dictionary = expected.duplicate(true)
    if reference.has("player"):
        reference["player"] = _point(reference["player"])
    for field in ["crates", "switches_on", "powered_nodes"]:
        if reference.has(field):
            reference[field] = _points(reference[field])
    for field in actual:
        if not reference.has(field) or actual[field] != reference[field]:
            push_error("NATIVE_ADVANCED_PUZZLE_ERROR: " + field + " mismatch: native=" +
                str(actual[field]) + " python=" + str(reference.get(field, "<missing>")))
            get_tree().quit(1)
            return
    if expected.size() != actual.size():
        push_error("NATIVE_ADVANCED_PUZZLE_ERROR: unexpected proof keys")
        get_tree().quit(1)
        return
    print("NATIVE_ADVANCED_PUZZLE_OK " + str(scene["digest"]) +
          " actions=" + str(native_actions.size()) +
          " mode=" + mode)
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not ready_to_play or not event is InputEventKey or not event.pressed or event.echo:
        return
    var action: String = ""
    match event.keycode:
        KEY_W, KEY_UP: action = "north"
        KEY_S, KEY_DOWN: action = "south"
        KEY_A, KEY_LEFT: action = "west"
        KEY_D, KEY_RIGHT: action = "east"
        KEY_ENTER, KEY_KP_ENTER: action = "interact"
        KEY_SPACE: action = "wait"
        KEY_Z: action = "undo"
        KEY_BACKSPACE: _reset_game()
    if action != "":
        _step(action)
    get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var action: String = ""
        match event.button_index:
            JOY_BUTTON_DPAD_UP: action = "north"
            JOY_BUTTON_DPAD_DOWN: action = "south"
            JOY_BUTTON_DPAD_LEFT: action = "west"
            JOY_BUTTON_DPAD_RIGHT: action = "east"
            JOY_BUTTON_A: action = "interact"
            JOY_BUTTON_B: action = "undo"
            JOY_BUTTON_START: _reset_game()
        if action != "":
            _step(action)
        get_viewport().set_input_as_handled()


func _notification(code: int) -> void:
    if code == NOTIFICATION_RESIZED:
        queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO, size), Color("#101b2c"))
    if not ready_to_play:
        return
    var step_size: float = floor(min(36.0, min((size.x - 60.0)/float(board_width),
        (size.y - 175.0)/float(board_height))))
    step_size = maxf(5.0, step_size)
    var origin: Vector2 = Vector2(20, 100)
    _text(Vector2(20, 31), "Original " + mode.replace("_", " ") + " puzzle", 23, Color.WHITE)
    _text(Vector2(20, 59), "Moves %d · Tick %d · Undo %d · Phase %d" %
        [move_count, tick, undo_available, phase], 16, Color("#a4e5d7"))
    _text(Vector2(20, 80), notice, 15, Color("#f0d39d"))
    for y in range(board_height):
        for x in range(board_width):
            var point: Array = [x, y]
            var rect: Rect2 = Rect2(origin + Vector2(x, y) * step_size,
                                   Vector2.ONE * step_size)
            var ink: Color = Color("#203f50")
            if point in walls:
                ink = Color("#6c738c")
            elif point in doors:
                ink = Color("#ad7569") if switches_on.size() < switches.size() and mode == "switches" else Color("#80bbad")
            elif point in phase_gates and phase == 1:
                ink = Color("#bba4ed")
            elif point in targets:
                ink = Color("#7ccdc0")
            elif point in switches or point in nodes:
                ink = Color("#e9c575")
            for link in portals:
                if point in link:
                    ink = Color("#a184f5")
            if point in crates:
                ink = Color("#c7a179")
            if point == exit_tile:
                ink = Color("#66ba96")
            if point == player:
                ink = Color("#f6f4ee")
            draw_rect(rect, ink, true)
            draw_rect(rect, Color("#355b6b"), false, 1.0)
    _text(Vector2(20, origin.y + board_height * step_size + 26),
        "WASD/arrows: move · Enter/A: interact · Z/B: rewind · Space: wait", 13, Color.WHITE)
    _text(Vector2(20, origin.y + board_height * step_size + 48),
        "Offline original homebrew · independently proved action rules", 12, Color("#b9d3cd"))


func _text(at: Vector2, label: String, font_size: int, ink: Color) -> void:
    draw_string(ThemeDB.fallback_font, at, label,
        HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, ink)
'''

_PROOF_FIELDS=(
    "player","crates","switches_on","powered_nodes",
    "phase","portal_visited","tick","move_count",
    "undo_available","finished","failed",
)


class AdvancedGodotExportError(AdvancedRuntimeError):
    """A game source/proof is not eligible for an original native target."""


def _json(data: object)->bytes:
    return (json.dumps(data,ensure_ascii=True,sort_keys=True,
                       separators=(",",":"),allow_nan=False)+"\n").encode("utf-8")


@dataclass(frozen=True)
class NativeAdvancedGamePackage:
    files: dict[str,bytes]
    manifest: dict[str,object]

    def __post_init__(self):
        if set(self.files)!=set(self.manifest["files"])|{"release.json"}:
            raise AdvancedGodotExportError("native source manifest does not cover exact output files")
        if any(sha256(self.files[path]).hexdigest()!=digest
               for path,digest in self.manifest["files"].items()):
            raise AdvancedGodotExportError("native game package checksum mismatch")


def render_advanced_godot_package(session: dict,
                                  settings: dict|None = None,
                                  *, authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("native game export requires explicit operator authorization")
    if type(session) is not dict or session.get("editor")!="puzzle":
        raise AdvancedGodotExportError("only the original puzzle engine has a native Godot adapter")
    config=make_editor_document("puzzle",settings)
    if not verify_advanced_session(session,config["settings"]):
        raise AdvancedGodotExportError("original Python gameplay proof failed replay")
    scene=(validate_advanced_scene(session["scene"],config["settings"])
           if session.get("scene") is not None else
           make_advanced_scene("puzzle",config["settings"],seed=session["seed"]))
    if session.get("scene") is None:
        session=run_advanced_session("puzzle",config["settings"],
                                    session["actions"],seed=session["seed"],scene=scene)
    state=session["state"]
    proof={
        "schema":PROOF_SCHEMA,
        "scene_digest":scene["digest"],
        "settings_digest":config["digest"],
        "actions":list(session["actions"]),
        "expected":{field:state[field] for field in _PROOF_FIELDS},
        "python_session_digest":session["digest"],
        "verified_by_python_replay":True,
    }
    game={
        "schema":NATIVE_SCHEMA,
        "editor":"puzzle",
        "quality_floor":"advanced",
        "settings":config["settings"],
        "settings_digest":config["digest"],
        "scene":scene,
        "native_parity_verified":False,
    }
    files={
        "godot/project.godot":_PROJECT.replace("Skeleton Original Adventure",
                                              "Skeleton Original Advanced Puzzle").encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_PUZZLE.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Original advanced puzzle Godot 4 export\n\n"
            "Godot 4.4.1+ project: godot/project.godot. Real authored switch, crate, circuit,\n"
            "time and portal gameplay with local keyboard/gamepad commands; no provider needed.\n"
            "Independent convergence: godot --headless --path godot -- --verify-advanced\n"
            "Exit code 0 and NATIVE_ADVANCED_PUZZLE_OK require comparing the native final\n"
            "puzzle state against the verified Python gameplay receipt. Source export alone\n"
            "does not imply the Godot program has been run or hardware tested.\n"
            "Native release/store publication and commercial rights are not approved.\n"
        ).encode("utf-8"),
    }
    manifest={
        "schema":"skeleton.game_builder.advanced_native_package.v1",
        "native_editor":"puzzle",
        "native_adapter":"godot4_independent_puzzle",
        "advanced_floor":True,
        "source_session_digest":session["digest"],
        "authored_scene_digest":scene["digest"],
        "files":{path:sha256(body).hexdigest() for path,body in sorted(files.items())},
        "godot_executed":False,
        "native_hardware_certified":False,
        "publish_approved":False,
    }
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


def archive_advanced_godot_package(package: NativeAdvancedGamePackage)->bytes:
    """Deterministic, bounded, fixed-path source archive for explicit studio download."""
    if not isinstance(package,NativeAdvancedGamePackage):
        raise AdvancedGodotExportError("typed original native game package required")
    genre=package.manifest.get("native_editor")
    if genre not in ("puzzle","platformer","deck_battler","shooter","tactics","tower_defense","racing"):
        raise AdvancedGodotExportError("only independently implemented native genres may be archived")
    output=BytesIO()
    with ZipFile(output,"w",compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for path,data in sorted(package.files.items()):
            if path.startswith("/") or ".." in Path(path).parts or "\\\\" in path:
                raise AdvancedGodotExportError("native source package contains unsafe path")
            entry=ZipInfo("original-godot-"+genre+"/"+path,date_time=(1980,1,1,0,0,0))
            entry.compress_type=ZIP_DEFLATED
            entry.external_attr=(0o100644<<16)
            archive.writestr(entry,data,compress_type=ZIP_DEFLATED,compresslevel=9)
    blob=output.getvalue()
    if not blob or len(blob)>512_000:
        raise AdvancedGodotExportError("native offline source archive exceeds safe size")
    return blob


def write_advanced_godot_package(package: NativeAdvancedGamePackage,
                                 dest: str|Path, *, authorized: bool)->Path:
    if not authorized:
        raise PermissionError("exporting local original-game files requires authorization")
    if not isinstance(package,NativeAdvancedGamePackage):
        raise AdvancedGodotExportError("typed, independently verified native package required")
    target=Path(dest).absolute()
    if target.exists() or target.is_symlink():
        raise AdvancedGodotExportError("native export requires an unused destination directory")
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise AdvancedGodotExportError("native export parent is not a safe existing directory")
    # Only fixed exporter-owned paths appear in the manifest; no untrusted
    # scene ID is allowed to become a filename or executable code.
    with tempfile.TemporaryDirectory(dir=target.parent,prefix=".advanced_game_") as temp:
        root=Path(temp)
        for path,body in package.files.items():
            output=root/path
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_bytes(body)
        root.rename(target)
    return target


__all__=["NATIVE_SCHEMA","PROOF_SCHEMA","GODOT_PUZZLE","NativeAdvancedGamePackage",
         "AdvancedGodotExportError","render_advanced_godot_package",
         "write_advanced_godot_package","archive_advanced_godot_package"]
