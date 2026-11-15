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
