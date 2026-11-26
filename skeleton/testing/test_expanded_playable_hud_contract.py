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
