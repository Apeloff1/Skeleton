"""Export a proved original game as an offline browser + Godot 4 source package.

Canonical owner: skeleton.ai.game_builder. Neither exporter runs external
toolchains, promotes third-party research, publishes a game, nor asserts that
Godot has been executed. The Godot runtime implements the same four-direction
turn, item, hazard, exit and score semantics as playable_simulation.advance.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from .contracts import canonical_digest
from .playable_compiler import CompiledPlayableProject
from .playable_simulation import verify_replay


class DualRuntimeExportError(ValueError):
    """A source package cannot be rendered or exported safely."""


# Game rules are authored here, not generated from research, URLs or model code.
_GODOT_SCRIPT = r'''
extends Control
## Original, turn-based Godot 4 game from a typed, verified Skeleton world.
## No network, plugins, scripts from source material, or proprietary assets.

const TRACE_PATH = "user://skeleton_game_actions.json"
const MAX_ACTIONS = 20000
const MAX_UNDO = 256
const PALETTES = {
    "forest": ["#214d43", "#152f2b", "#e2bc61", "#91edd3", "#e36e7b"],
    "space": ["#394773", "#192445", "#eab764", "#a0e3ff", "#ed82a3"],
    "desert": ["#80613f", "#3d3027", "#f0c772", "#a2eeae", "#e78065"],
    "ocean": ["#28607c", "#163447", "#e9ce84", "#94e4ef", "#f98099"],
    "arcade": ["#634480", "#261933", "#ffd15d", "#86f8b0", "#ed68a0"]
}
var world: Dictionary = {}
var levels: Array = []
var level_index: int = 0
var hero: Vector2i = Vector2i.ZERO
var collected: Dictionary = {}
var health: int = 0
var score: int = 0
var steps: int = 0
var status: String = "playing"
var notice: String = "Collect every crystal, then reach the exit."
var history: Array = []
var actions: Array = []
var ready_to_play: bool = false
var touch_origin: Vector2 = Vector2.ZERO
var touch_active: bool = false

func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var source: String = FileAccess.get_file_as_string("res://world.json")
    if source.length() > 150000 or source.is_empty():
        notice = "World data missing or too large."
        queue_redraw()
        return
    var decoded: Variant = JSON.parse_string(source)
    if typeof(decoded) != TYPE_DICTIONARY:
        notice = "Invalid world data."
        queue_redraw()
        return
    world = decoded
    if str(world.get("schema", "")) != "skeleton.game_builder.godot_world.v1":
        notice = "Unsupported world version."
        queue_redraw()
        return
    if not world.has("levels") or not world.has("intent"):
        notice = "World data incomplete."
        queue_redraw()
        return
    levels = world["levels"]
    if levels.is_empty() or levels.size() > 8:
        notice = "Unsupported level count."
        queue_redraw()
        return
    get_window().title = str(world["intent"].get("title", "Original Game"))
    ready_to_play = true
    _reset()
    if "--verify-proof" in OS.get_cmdline_user_args():
        _verify_native_proof()

func _reset() -> void:
    if not ready_to_play:
        return
    level_index = 0
    health = int(world["intent"]["starting_health"])
    score = 0
    steps = 0
    status = "playing"
    collected.clear()
    history.clear()
    actions.clear()
    _enter_level()
    notice = "Collect every crystal, then reach the exit."
    queue_redraw()

func _enter_level() -> void:
    var start: Array = levels[level_index]["start"]
    hero = Vector2i(int(start[0]), int(start[1]))
    collected.clear()

func _snapshot() -> Dictionary:
    return {
        "level": level_index, "hero": hero,
        "collected": collected.duplicate(), "health": health,
        "steps": steps, "score": score, "status": status
    }

func _step(direction: String, record: bool = true) -> bool:
    if not ready_to_play or status != "playing" or steps >= MAX_ACTIONS:
        return false
    var offset := Vector2i.ZERO
    match direction:
        "up": offset = Vector2i(0, -1)
        "left": offset = Vector2i(-1, 0)
        "right": offset = Vector2i(1, 0)
        "down": offset = Vector2i(0, 1)
        _: return false
    var level: Dictionary = levels[level_index]
    var rows: Array = level["rows"]
    var attempted: Vector2i = hero + offset
    var blocked := attempted.x < 0 or attempted.y < 0
    blocked = blocked or attempted.y >= rows.size()
    if not blocked:
        blocked = attempted.x >= str(rows[attempted.y]).length()
    if not blocked:
        blocked = str(rows[attempted.y]).substr(attempted.x, 1) == "#"
    if blocked:
        attempted = hero
    if record:
        history.append(_snapshot())
        if history.size() > MAX_UNDO:
            history.pop_front()
    var entered: bool = attempted != hero
    hero = attempted
    var tile: String = str(rows[hero.y]).substr(hero.x, 1)
    steps += 1
    if tile == "C":
        var key: String = str(hero.x) + "," + str(hero.y)
        if not collected.has(key):
            collected[key] = true
            score += 10
            notice = "Crystal collected."
    if tile == "H" and entered:
        health -= 1
        notice = "Hazard: one health lost."
    if health <= 0:
        health = 0
        status = "lost"
        notice = "Out of health. Undo or restart."
    elif tile == "G" and collected.size() == level["collectibles"].size():
        score += 100
        if level_index == levels.size() - 1:
            status = "won"
            notice = "All levels cleared!"
        else:
            level_index += 1
            _enter_level()
            notice = "Level complete. Explore the next world."
    elif tile == "G":
        notice = "Exit locked. Collect all crystals."
    elif blocked:
        notice = "A wall blocks that direction."
    elif tile != "C" and tile != "H":
        notice = "Exploring."
    actions.append(direction)
    queue_redraw()
    return true

func _undo() -> void:
    if history.is_empty():
        return
    var previous: Dictionary = history.pop_back()
    level_index = previous["level"]
    hero = previous["hero"]
    collected = previous["collected"]
    health = previous["health"]
    steps = previous["steps"]
    score = previous["score"]
    status = previous["status"]
    actions.pop_back()
    notice = "Undid previous turn."
    queue_redraw()

func _save_actions() -> void:
    if not ready_to_play:
        return
    var payload: Dictionary = {
        "schema": "skeleton.game_builder.godot_actions.v1",
        "world_digest": world["world_digest"],
        "project_id": world["intent"]["project_id"],
        "actions": actions.duplicate(),
        "note": "Unverified local trace; verify with the Python simulation."
    }
    var file := FileAccess.open(TRACE_PATH, FileAccess.WRITE)
    if file == null:
        notice = "Cannot write local save."
        queue_redraw()
        return
    file.store_string(JSON.stringify(payload))
    file.close()
    notice = "Local action trace saved (not independently verified)."
    queue_redraw()

func _load_actions() -> void:
    if not ready_to_play or not FileAccess.file_exists(TRACE_PATH):
        notice = "No local action trace."
        queue_redraw()
        return
    var source: String = FileAccess.get_file_as_string(TRACE_PATH)
    if source.length() > 200000:
        notice = "Save exceeds size budget."
        queue_redraw()
        return
    var data: Variant = JSON.parse_string(source)
    if typeof(data) != TYPE_DICTIONARY:
        notice = "Invalid local trace."
        queue_redraw()
        return
    if str(data.get("schema", "")) != "skeleton.game_builder.godot_actions.v1":
        notice = "Unsupported save format."
        queue_redraw()
        return
    if data.get("world_digest") != world["world_digest"] or data.get("project_id") != world["intent"]["project_id"]:
        notice = "Save belongs to another world."
        queue_redraw()
        return
    var incoming: Variant = data.get("actions")
    if typeof(incoming) != TYPE_ARRAY or incoming.size() > MAX_ACTIONS:
        notice = "Invalid saved action count."
        queue_redraw()
        return
    for direction in incoming:
        if typeof(direction) != TYPE_STRING or direction not in ["up", "left", "right", "down"]:
            notice = "Invalid saved action."
            queue_redraw()
            return
    _reset()
    for direction in incoming:
        if not _step(direction):
            _reset()
            notice = "Invalid sequence after a terminal state."
            queue_redraw()
            return
    notice = "Local actions replayed; external verification still required."
    queue_redraw()

func _verify_native_proof() -> void:
    ## Headless replay proof is an integration check, never proof of human play.
    var source: String = FileAccess.get_file_as_string("res://proof.json")
    if source.is_empty() or source.length() > 200000:
        push_error("NATIVE_REPLAY_ERROR: missing or oversized proof")
        get_tree().quit(1)
        return
    var proof: Variant = JSON.parse_string(source)
    if typeof(proof) != TYPE_DICTIONARY or proof.get("world_digest") != world["world_digest"]:
        push_error("NATIVE_REPLAY_ERROR: proof identity mismatch")
        get_tree().quit(1)
        return
    var sequence: Variant = proof.get("actions")
    var expected: Variant = proof.get("final_state")
    if typeof(sequence) != TYPE_ARRAY or sequence.size() > MAX_ACTIONS:
        push_error("NATIVE_REPLAY_ERROR: invalid replay actions")
        get_tree().quit(1)
        return
    if typeof(expected) != TYPE_DICTIONARY:
        push_error("NATIVE_REPLAY_ERROR: invalid expected state")
        get_tree().quit(1)
        return
    for direction in sequence:
        if typeof(direction) != TYPE_STRING or not _step(direction):
            push_error("NATIVE_REPLAY_ERROR: action rejected")
            get_tree().quit(1)
            return
    var actual_collected: Array = []
    for key in collected:
        var xy: PackedStringArray = str(key).split(",")
        actual_collected.append([int(xy[0]), int(xy[1])])
    actual_collected.sort()
    var expected_collected: Array = expected.get("collected", [])
    expected_collected.sort()
    var valid: bool = (
        status == str(expected.get("status", "invalid"))
        and level_index == int(expected.get("level_index", -1))
        and hero.x == int(expected.get("x", -1))
        and hero.y == int(expected.get("y", -1))
        and score == int(expected.get("score", -1))
        and steps == int(expected.get("steps", -1))
        and health == int(expected.get("health", -1))
        and actual_collected == expected_collected
        and actions.size() == sequence.size()
        and status == "won"
    )
    if not valid:
        push_error("NATIVE_REPLAY_ERROR: Godot and Python final states diverge")
        get_tree().quit(1)
        return
    print("NATIVE_REPLAY_OK " + str(world["world_digest"]) +
        " actions=" + str(sequence.size()))
    get_tree().quit(0)

func _unhandled_key_input(event: InputEvent) -> void:
    if not event is InputEventKey or not event.pressed or event.echo:
        return
    var action: String = ""
    match event.keycode:
        KEY_UP, KEY_W: action = "up"
        KEY_LEFT, KEY_A: action = "left"
        KEY_RIGHT, KEY_D: action = "right"
        KEY_DOWN, KEY_S: action = "down"
        KEY_Z: _undo()
        KEY_R: _reset()
        KEY_F5: _save_actions()
        KEY_F9: _load_actions()
    if not action.is_empty():
        _step(action)
    get_viewport().set_input_as_handled()

func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var action: String = ""
        match event.button_index:
            JOY_BUTTON_DPAD_UP: action = "up"
            JOY_BUTTON_DPAD_LEFT: action = "left"
            JOY_BUTTON_DPAD_RIGHT: action = "right"
            JOY_BUTTON_DPAD_DOWN: action = "down"
            JOY_BUTTON_B: _undo()
            JOY_BUTTON_START: _reset()
        if not action.is_empty():
            _step(action)
        get_viewport().set_input_as_handled()
    elif event is InputEventScreenTouch:
        if event.pressed:
            touch_origin = event.position
            touch_active = true
        elif touch_active:
            touch_active = false
            var swipe: Vector2 = event.position - touch_origin
            if swipe.length() >= 28.0:
                var direction: String = ""
                if absf(swipe.x) > absf(swipe.y):
                    direction = "right" if swipe.x > 0.0 else "left"
                else:
                    direction = "down" if swipe.y > 0.0 else "up"
                _step(direction)
                get_viewport().set_input_as_handled()

func _notification(what: int) -> void:
    if what == NOTIFICATION_RESIZED:
        queue_redraw()

func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO, size), Color("#101e2a"), true)
    if not ready_to_play:
        _text(Vector2(20, 34), notice, 18, Color.WHITE)
        return
    var level: Dictionary = levels[level_index]
    var rows: Array = level["rows"]
    var width: int = str(rows[0]).length()
    var height: int = rows.size()
    var tile_size: float = floor(min(38.0, min(
        (size.x - 40.0) / float(width),
        (size.y - 155.0) / float(height)
    )))
    tile_size = max(4.0, tile_size)
    var start: Vector2 = Vector2(20, 96)
    var color_codes: Array = PALETTES.get(str(world["intent"]["theme"]), PALETTES["forest"])
    _text(Vector2(20, 28), str(world["intent"]["title"]), 22, Color.WHITE)
    _text(Vector2(20, 54), "Level %d/%d    Health %d    Crystals %d/%d    Score %d    Turns %d" % [
        level_index + 1, levels.size(), health, collected.size(),
        level["collectibles"].size(), score, steps
    ], 16, Color.WHITE)
    _text(Vector2(20, 76), notice, 15, Color("#f9dda4"))
    for y in range(height):
        for x in range(width):
            var tile: String = str(rows[y]).substr(x, 1)
            var rect := Rect2(start + Vector2(x, y) * tile_size, Vector2.ONE * tile_size)
            var floor_color := Color(color_codes[1])
            if tile == "#":
                floor_color = Color(color_codes[0])
            draw_rect(rect, floor_color, true)
            draw_rect(rect, Color("#537076"), false, 1.0)
            var key: String = str(x) + "," + str(y)
            if tile == "C" and not collected.has(key):
                draw_circle(rect.get_center(), tile_size * 0.27, Color(color_codes[3]))
            elif tile == "G":
                var goal_color := Color("#607480")
                if collected.size() == level["collectibles"].size():
                    goal_color = Color(color_codes[2])
                draw_rect(rect.grow(-tile_size * 0.23), goal_color, true)
            elif tile == "H":
                draw_circle(rect.get_center(), tile_size * 0.24, Color(color_codes[4]))
    var player_rect := Rect2(start + Vector2(hero) * tile_size, Vector2.ONE * tile_size)
    draw_circle(player_rect.get_center(), tile_size * 0.32, Color("#f2f8fe"))
    _text(Vector2(20, start.y + height * tile_size + 26),
        "Arrows/WASD/D-pad/swipe move   Z/B undo   R/Start restart", 14, Color.WHITE)
    _text(Vector2(20, start.y + height * tile_size + 48),
        "Original geometry | Offline | No external game assets", 13, Color("#afc8c3"))

func _text(at: Vector2, message: String, font_size: int, ink: Color) -> void:
    draw_string(ThemeDB.fallback_font, at, message,
        HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, ink)
'''

_PROJECT = """config_version=5

[application]
config/name="Skeleton Original Adventure"
run/main_scene="res://scenes/main.tscn"
config/features=PackedStringArray("4.2", "GL Compatibility")

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
textures/default_filters/use_nearest_mipmap_filter=false

[display]
window/size/viewport_width=900
window/size/viewport_height=720
window/stretch/mode="canvas_items"
"""

_SCENE = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scripts/main.gd" id="1"]

[node name="OriginalGame" type="Control"]
layout_mode = 3
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
grow_horizontal = 2
grow_vertical = 2
script = ExtResource("1")
"""

README = """# Original offline game — two runnable source targets

The same deterministic, generated tile world powers index.html and the Godot
4.2+ project under godot/. Their controls and objective/health/score rules
match the Python reference simulator. No external artwork or licenses are
included, and the project needs no provider or network at runtime.

Browser: open index.html in a modern desktop/mobile browser.
Godot: open godot/project.godot in Godot 4.2+ and press F6/F5 to run.

Godot controls: arrows/WASD/gamepad D-pad/touch swipe movement, Z or gamepad B undo (256 moves), R or Start restart,
F5 local save, F9 local load. Local save stores actions rather than
trusting serialized game state, and binds them to the source world digest.
It is unverified until replayed by the Python reference simulator.

godot/proof.json is an engine-readable copy of the same winning trace.\nA locally installed Godot 4 can replay it with:\n  godot --headless --path godot -- --verify-proof\nThe process exits unsuccessfully on state divergence and prints NATIVE_REPLAY_OK\nonly after exact expected final state comparison.\n\nproof/verified_solution.json is a canonical reference *winning trace*,
not an actual human playtest. release.json includes SHA-256 hashes of every
packaged file except itself and the content digests for the verified world
and Python replay. Source exists; native executable build, emulator,
Godot scene load, hardware performance and user acceptance are NOT asserted.

Research sources, if used upstream, require canonical RightsLedger clearance.
No cited third-party expression becomes executable game code here.
Exporting the source is not commercial publication approval.
"""

@dataclass(frozen=True, slots=True)
class DualRuntimePackage:
    files: dict[str, bytes]
    manifest: dict[str, object]

    def __post_init__(self) -> None:
        if not self.files or "release.json" not in self.files:
            raise DualRuntimeExportError("empty or incomplete package")
        if set(self.files) != set(self.manifest["files"]) | {"release.json"}:
            raise DualRuntimeExportError("package manifest file coverage mismatch")
        for path, digest in self.manifest["files"].items():
            if sha256(self.files[path]).hexdigest() != digest:
                raise DualRuntimeExportError("package file integrity mismatch")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False,
                       sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def render_dual_runtime_package(
    project: CompiledPlayableProject, *, authorized: bool,
) -> DualRuntimePackage:
    """Render original browser and Godot 4 sources from one proved world."""
    if not authorized:
        raise PermissionError("game production export needs external authorization")
    if not isinstance(project, CompiledPlayableProject):
        raise DualRuntimeExportError("typed, compiled playable project required")
    verify_replay(project.world, project.proof, authorized=True)
    if project.proof.final_state.status != "won":
        raise DualRuntimeExportError("game must have an executed winning proof")
    if sha256(project.playable.html.encode("utf-8")).hexdigest() != project.playable.html_sha256:
        raise DualRuntimeExportError("browser gameplay source digest mismatch")
    if project.playable.world_digest != project.world.digest:
        raise DualRuntimeExportError("browser and generated world mismatch")
    if project.playable.proof_digest != project.proof.digest:
        raise DualRuntimeExportError("browser and proof mismatch")

    world = project.world
    levels = [{
        "rows": list(level.rows),
        "start": list(level.start),
        "collectibles": [list(pos) for pos in level.collectibles],
    } for level in world.levels]
    native_world = {
        "schema": "skeleton.game_builder.godot_world.v1",
        "world_digest": world.digest,
        "intent": world.intent.to_payload(),
        "levels": levels,
    }
    proof = {
        "schema": "skeleton.game_builder.solution_trace.v1",
        "world_digest": world.digest,
        "actions": [row.action for row in project.proof.action_receipts],
        "replay_digest": project.proof.digest,
        "final_state": project.proof.final_state.to_payload(),
    }
    files = {
        "index.html": project.playable.html.encode("utf-8"),
        "godot/project.godot": _PROJECT.encode("utf-8"),
        "godot/scenes/main.tscn": _SCENE.encode("utf-8"),
        "godot/scripts/main.gd": _GODOT_SCRIPT.encode("utf-8"),
        "godot/world.json": _json_bytes(native_world),
        "godot/proof.json": _json_bytes(proof),
        "README.md": README.encode("utf-8"),
        "proof/verified_solution.json": _json_bytes(proof),
    }
    if sum(map(len, files.values())) > 2_000_000:
        raise DualRuntimeExportError("source package exceeds 2 MB budget")
    manifest_body: dict[str, object] = {
        "schema": "skeleton.game_builder.dual_runtime_package.v1",
        "project_id": world.intent.project_id,
        "world_digest": world.digest,
        "world_algorithm": world.algorithm,
        "proof_digest": project.proof.digest,
        "proof_status": "python-simulated-winning-actions",
        "targets": {
            "offline-html5": "source-rendered",
            "godot-4.2": "source-rendered-unexecuted",
        },
        "godot_hardware_tested": False,
        "third_party_game_assets": False,
        "automatic_publication": False,
        "research_clearance_digest": (
            project.cleared_research.to_payload()["packet_digest"]
            if project.cleared_research is not None else None
        ),
        "files": {path: sha256(data).hexdigest() for path, data in sorted(files.items())},
    }
    manifest = {**manifest_body, "manifest_digest": canonical_digest(manifest_body)}
    files["release.json"] = _json_bytes(manifest)
    return DualRuntimePackage(files, manifest)


def export_dual_runtime_package(
    package: DualRuntimePackage, destination: str | Path, *, authorized: bool,
) -> Path:
    """Atomically publish a new directory; never follow or overwrite a destination.

    Rendering and verification finish before any write. Static relative package
    paths exclude supplied filenames; a same-parent temporary directory stages
    the complete set before one non-overwriting rename. This protects source
    projects from partial exported packages if a file write fails.
    """
    if not authorized:
        raise PermissionError("game project filesystem export requires authorization")
    if not isinstance(package, DualRuntimePackage):
        raise DualRuntimeExportError("typed release package required")
    root = Path(destination)
    if root.exists() or root.is_symlink():
        raise DualRuntimeExportError("destination already exists")
    if not root.parent.is_dir() or root.parent.is_symlink():
        raise DualRuntimeExportError("destination parent must be an existing directory")
    if any(
        not path or Path(path).is_absolute() or ".." in Path(path).parts
        or Path(path).as_posix() != path
        for path in package.files
    ):
        raise DualRuntimeExportError("unsafe generated package filename")
    for path, digest in package.manifest["files"].items():
        if sha256(package.files[path]).hexdigest() != digest:
            raise DualRuntimeExportError("source data changed since rendering")
    if package.files["release.json"] != _json_bytes(package.manifest):
        raise DualRuntimeExportError("release metadata changed since rendering")
    temporary = Path(tempfile.mkdtemp(prefix=".game-export-", dir=str(root.parent)))
    try:
        for relative, payload in package.files.items():
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        if root.exists() or root.is_symlink():
            raise DualRuntimeExportError("destination concurrently created")
        os.rename(temporary, root)
        if os.name == "posix":
            fd = os.open(root.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return root


__all__ = [
    "DualRuntimeExportError", "DualRuntimePackage",
    "render_dual_runtime_package", "export_dual_runtime_package",
]
