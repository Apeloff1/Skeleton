"""Five expanded game modes must have actual shared controls and live HUD."""
import pytest

from skeleton.forge.archetype_content import archetype_files


@pytest.mark.parametrize("mode", ["crafting", "puzzle", "racing", "stealth", "survival"])
def test_extended_mode_has_one_interactive_hud_owner(mode):
    files = archetype_files(mode)
    loop = files[f"scripts/archetypes/{mode}/core_loop.gd"]
    player = files[f"scripts/archetypes/{mode}/player_controller.gd"]
    assert loop.count("func _draw() -> void:") == 1
    assert loop.count("func _draw_objectives() -> void:") == 1
    assert loop.count("func _hud_status() -> String:") == 1
    assert "_draw_objectives()" in loop
    assert 'controls, "ui_accept", "USE"' in loop
    assert '["ui_up", "ui_down", "ui_left", "ui_right", "ui_accept"]' in loop
    assert "if not finished and hud_label != null:" in loop
    assert "Input.action_press(action)" in loop
    assert "Input.action_release(action)" in loop
    assert "Input.action_press" not in player
    assert 'DisplayServer.get_name() == "headless"' in loop


@pytest.mark.parametrize("mode", ["extraction", "combat_loop", "pipeline", "puzzle", "racing", "survival", "stealth", "crafting"])
def test_every_native_mode_freezes_terminal_state_and_exposes_retry(mode):
    from skeleton.ai.forge.archetype_content import archetype_files as mirrored
    files = archetype_files(mode)
    assert mirrored(mode) == files
    loop = files[f"scripts/archetypes/{mode}/core_loop.gd"]
    assert loop.count('retry_button.name = "RetryPrototype"') == 1
    assert "retry_button.pressed.connect(_request_retry)" in loop
    assert "if not finished or retry_pending" in loop
    assert "get_tree().current_scene != self" in loop
    assert "get_tree().reload_current_scene()" in loop
    assert "player.set_physics_process(false)" in loop
    assert "player.velocity = Vector2.ZERO" in loop
    assert "if not finished and hud_label != null:" in loop
    assert loop.count('controls, "ui_accept", "USE"') == 1
    assert "func _release_controls() -> void:" in loop
    assert "get_tree().quit(0 if ok else 1)" in loop


def test_combat_targets_nearest_and_requires_real_attack_input():
    loop = archetype_files("combat_loop", operator_axes={"lethality": 1.0, "grind": 1.0})["scripts/archetypes/combat_loop/core_loop.gd"]
    assert "func _nearest_enemy() -> int:" in loop
    assert "distance_squared_to(player.global_position)" in loop
    assert 'bool(player.get("autopilot")) or Input.is_action_pressed("ui_accept")' in loop
    assert "ENEMY_SPEED * delta" in loop
    assert "attack_cooldown = maxf(0.0, attack_cooldown - delta)" in loop
    assert "contact_cooldown = CONTACT_INTERVAL" in loop
    assert "enemies.remove_at(target_index)" in loop
    assert "const CONTACT_DAMAGE := 5" in loop
    assert "const WAVES := 5" in loop
    assert 'enemy["max_hp"]' in loop


def test_hidden_puzzle_has_temporal_clues_error_budget_and_real_selection():
    loop = archetype_files("puzzle", operator_axes={"opacity": 1.0, "grind": 1.0})["scripts/archetypes/puzzle/core_loop.gd"]
    assert "const SHOW_ACTIVE_SWITCH := false" in loop
    assert "func _near_switch() -> int:" in loop
    assert "selected == next_switch" in loop
    assert "var clue_until: int = 120" in loop
    assert "clue_until = frames + 90" in loop
    assert "clue_until = frames + 120" in loop
    assert "mistakes += 1" in loop
    assert 'if mistakes >= MAX_MISTAKES:' in loop
    assert '_finish(false, "too many incorrect switches")' in loop


@pytest.mark.parametrize("mode,targets", [
    ("extraction", "loot"), ("survival", "supplies"),
    ("stealth", "objectives"), ("crafting", "materials"),
])
def test_collectible_routes_allow_player_selected_order(mode, targets):
    loop = archetype_files(mode)[f"scripts/archetypes/{mode}/core_loop.gd"]
    assert f"_nearest_point({targets}," in loop
    assert f"{targets}.remove_at(selected)" in loop
    assert f"{targets}.remove_at(0)" not in loop
    assert "distance_squared_to(points[index])" in loop


def test_pipeline_cannot_refine_while_outside_station():
    loop = archetype_files("pipeline")["scripts/archetypes/pipeline/core_loop.gd"]
    refining = loop.split('"refining":', 1)[1].split('"to_depot":', 1)[0]
    assert 'player.autopilot_target = refinery' in refining
    assert "distance_to(refinery) > RADIUS" in refining
    assert 'stage = "to_refinery"' in refining
    assert "refine_timer = 0.0" in refining
    assert "refine_timer = maxf(0.0, refine_timer - delta)" in refining


@pytest.mark.parametrize("risk,duration", [(0.0, 0.60), (0.5, 1.20), (1.0, 1.80)])
def test_crafting_timed_assembly_is_bound_to_location_input_and_inventory(risk, duration):
    import json
    from skeleton.forge.playable_tuning import SOURCE_PATH
    files = archetype_files("crafting", operator_axes={"risk": risk, "grind": 1.0})
    loop = files["scripts/archetypes/crafting/core_loop.gd"]
    assert f"const ASSEMBLY_SECONDS := {duration:.2f}" in loop
    assert "distance_to(workshop) > USE_RADIUS" in loop
    assert "assembly_progress = 0.0" in loop
    assert 'elif autopilot or Input.is_action_pressed("ui_accept"):' in loop
    assert "assembly_progress = minf(ASSEMBLY_SECONDS, assembly_progress + delta)" in loop
    assert "if assembly_progress >= ASSEMBLY_SECONDS:" in loop
    assert "crafted = collected == 6" in loop
    assert "Materials %d/6" in loop and "Assembly %d%%" in loop
    receipt = json.loads(files[SOURCE_PATH])
    assert receipt["applied"]["crafting.assembly_seconds"] == duration


def test_galaxy_crafting_complexity_drives_native_assembly_duration():
    from skeleton.context.galaxy_profile import MATRIX_FIELDS, SCHEMA, compile_galaxy_playable_axes
    config = {field: {} for field in MATRIX_FIELDS}
    config.update(title="Workshop", genre="crafting", narrative_phases={}, extra_params={}, style_params={})
    config["mechanics_matrix"]["crafting"] = {"complexity": 1000, "count": 750}
    axes, receipt = compile_galaxy_playable_axes({"schema": SCHEMA, "config": config}, "crafting", {})
    assert axes == {"risk": 1.0, "grind": 0.75}
    loop = archetype_files("crafting", operator_axes=axes)["scripts/archetypes/crafting/core_loop.gd"]
    assert "const ASSEMBLY_SECONDS := 1.80" in loop
    assert "crafted = collected == 5" in loop
    assert receipt["mapped_matrix_dials"] == 2
