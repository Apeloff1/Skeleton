"""Actual Godot quest event/autoload and save replay acceptance.

Unlike source-only proof, these tests run the generated Godot project in a
real pinned native binary, execute the event signal and inspect the completed
quest progression and save-replay contracts in GDScript itself.
"""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.godot_quest_bridge import (
    QUEST_PATH, attach_native_quest, verify_native_quest,
)
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.playtest import playtest, resolve_binary

PROBE_PATH = "scripts/testing/native_quest_probe.gd"
SCENE_PATH = "scenes/testing/native_quest_probe.tscn"
WIN_MARKER = "NATIVE_QUEST_COMPLETE"
LOSS_MARKER = "NATIVE_QUEST_FAILED"

PROBE_SCRIPT = r'''extends Node
## Native quest witness: real Godot signals, snapshots and replay denials.

func _ready() -> void:
	call_deferred("_probe")


func _fail(reason: String) -> void:
	print("NATIVE_QUEST_FAILED " + reason)
	push_error("NATIVE_QUEST_FAILED " + reason)
	get_tree().quit(1)


func _probe() -> void:
	var runtime: Node = get_node_or_null("/root/QuestRuntime")
	if runtime == null:
		_fail("missing quest autoload")
		return
	var status: Dictionary = runtime.call("quest_status")
	if not bool(status.get("loaded", false)):
		_fail("source was not admitted")
		return
	var raw: String = FileAccess.get_file_as_string("res://data/quest_slice.json")
	var document: Variant = JSON.parse_string(raw)
	if typeof(document) != TYPE_DICTIONARY:
		_fail("invalid canonical document")
		return
	var slice_doc: Dictionary = document.get("slice", {})
	var world_quest: Dictionary = slice_doc.get("world_quest", {})
	var quest: Dictionary = world_quest.get("quest", {})
	var steps: Array = quest.get("steps", [])
	if steps.size() < 1 or steps.size() > 8:
		_fail("invalid source step inventory")
		return
	if int(status.get("total_steps", -1)) != steps.size():
		_fail("runtime and source disagree on steps")
		return
	var zero: Dictionary = runtime.call("snapshot")
	if not bool(runtime.call("restore_snapshot", zero)):
		_fail("initial snapshot was not accepted")
		return
	var forged: Dictionary = zero.duplicate(true)
	forged["earned"] = {"xp": 999}
	if bool(runtime.call("restore_snapshot", forged)):
		_fail("forged reward amount was accepted")
		return
	for i in range(steps.size()):
		EventBus.room_entered.emit("r99")
		var after_noise: Dictionary = runtime.call("quest_status")
		if int(after_noise.get("next_step", -1)) != i:
			_fail("unrelated room advanced objective")
			return
		var entry: Dictionary = steps[i]
		var room: String = str(entry.get("location", ""))
		EventBus.room_entered.emit(room)
		var after_real: Dictionary = runtime.call("quest_status")
		if int(after_real.get("next_step", -1)) != i + 1:
			_fail("valid room did not advance objective")
			return
		var progress: Dictionary = runtime.call("snapshot")
		if not bool(runtime.call("restore_snapshot", progress)):
			_fail("valid progress snapshot was rejected")
			return
		var replaced_visit: Dictionary = progress.duplicate(true)
		var visits: Array = replaced_visit.get("visits", [])
		visits[0] = "r99"
		if bool(runtime.call("restore_snapshot", replaced_visit)):
			_fail("forged room history was accepted")
			return
	var completed: Dictionary = runtime.call("quest_status")
	if not bool(completed.get("completed", false)):
		_fail("quest did not reach terminal state")
		return
	if int(completed.get("next_step", -1)) != steps.size():
		_fail("terminal progress mismatch")
		return
	print("NATIVE_QUEST_COMPLETE ", steps.size())
	get_tree().quit(0)
'''

PROBE_SCENE = '''[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scripts/testing/native_quest_probe.gd" id="1_probe"]

[node name="NativeQuestProbe" type="Node"]
script = ExtResource("1_probe")
'''


def probe_files(length: int) -> dict[str, str]:
    files = emit_godot(compile_era("extraction_now"))
    files, _receipt = attach_native_quest(files, length=length)
    assert verify_native_quest(files)
    previous = 'run/main_scene="res://scenes/levels/run_level.tscn"'
    assert files["project.godot"].count(previous) == 1
    files["project.godot"] = files["project.godot"].replace(
        previous,
        'run/main_scene="res://scenes/testing/native_quest_probe.tscn"',
    )
    files[PROBE_PATH] = PROBE_SCRIPT
    files[SCENE_PATH] = PROBE_SCENE
    return files


@pytest.mark.parametrize("quest_length", (1, 3, 8))
def test_native_godot_events_and_save_restore_for_real_generated_quest(quest_length):
    binary, source, verified = resolve_binary()
    if binary is None:
        pytest.skip("Godot binary unavailable: no native quest acceptance")
    files = probe_files(quest_length)
    result = playtest(files, binary=binary, frames=240, timeout=100.0)
    assert result["passed"] and result["status"] == "passed", (
        quest_length, source, verified, result,
    )
    boot = next((step for step in result["steps"] if step["step"] == "boot"), None)
    assert boot is not None and boot["returncode"] == 0 and not boot["timed_out"]
    assert f"{WIN_MARKER} {quest_length}" in boot["log_tail"]
    assert LOSS_MARKER not in boot["log_tail"]
