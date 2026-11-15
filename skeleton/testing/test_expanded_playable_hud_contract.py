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


@pytest.mark.parametrize("risk,rate", [(0.0, 1.0), (0.5, 3.0), (1.0, 5.0)])
def test_survival_exposure_rate_and_finite_water_inventory(risk, rate):
    import json
    from skeleton.forge.playable_tuning import SOURCE_PATH
    files = archetype_files("survival", operator_axes={"risk": risk})
    loop = files["scripts/archetypes/survival/core_loop.gd"]
    assert f"const EXPOSURE_DRAIN := {rate:.2f}" in loop
    assert "var water_reserve: int = 0" in loop
    assert "water_reserve += WATER_PER_SUPPLY" in loop
    assert "water_reserve <= 0 or hydration >= 100.0" in loop
    assert "water_reserve -= 1" in loop
    assert "use_pressed = false" in loop
    assert "not autopilot and use_pressed" in loop
    assert "EXPOSURE_DRAIN if exposed else 0.0" in loop
    assert "supplies.is_empty() and player.global_position.distance_to(shelter)" in loop
    assert json.loads(files[SOURCE_PATH])["applied"]["survival.exposure_drain_per_second"] == rate


@pytest.mark.parametrize("severity,rate", [(0.0, 0.55), (0.5, 0.95), (1.0, 1.35)])
def test_stealth_moving_patrol_and_progressive_detection(severity, rate):
    import json
    from skeleton.forge.playable_tuning import SOURCE_PATH
    files = archetype_files("stealth", operator_axes={"lethality": severity, "risk": 1.0, "opacity": 1.0})
    loop = files["scripts/archetypes/stealth/core_loop.gd"]
    assert f"const ALERT_RISE := {rate:.2f}" in loop
    assert "const DETECTION_RADIUS := 80.00" in loop
    assert "const SHOW_GUARD_ZONES := false" in loop
    assert "patrol_time += delta" in loop
    assert "Vector2(cos(phase), sin(phase)) * PATROL_AMPLITUDE" in loop
    assert "pressure = maxf(pressure, 1.0 - distance / DETECTION_RADIUS)" in loop
    assert "alert = minf(1.0, alert + ALERT_RISE" in loop
    assert "alert = maxf(0.0, alert - ALERT_DECAY * delta)" in loop
    assert 'if alert >= 1.0:' in loop
    assert "distance < PROXIMITY_RADIUS" in loop
    assert json.loads(files[SOURCE_PATH])["applied"]["stealth.alert_rise_per_second"] == rate


@pytest.mark.parametrize("depth,count", [(0.0, 2), (0.5, 4), (1.0, 6)])
def test_stealth_intel_route_count_matches_native_progression(depth, count):
    import re
    import json
    from skeleton.forge.playable_tuning import SOURCE_PATH
    files = archetype_files("stealth", operator_axes={"grind": depth})
    loop = files["scripts/archetypes/stealth/core_loop.gd"]
    route = re.search(r"var objectives: Array\[Vector2\] = \[(.*?)\]", loop, re.S).group(1)
    assert route.count("Vector2(") == count
    assert f"Intel %d/{count}" in loop
    assert "if not objectives.is_empty():" in loop
    assert "objectives.remove_at(selected)" in loop
    assert "and not exposed:" in loop
    assert json.loads(files[SOURCE_PATH])["applied"]["stealth.objectives_required"] == count


def test_stealth_fixed_route_avoids_maximum_patrol_envelope():
    # Independent analytic route check, not a Godot execution claim.
    import math
    from skeleton.forge.playable_tuning import _ROUTE_POINTS
    points = _ROUTE_POINTS["stealth"][1]
    guards = ((90, -120), (260, -80), (40, 320), (-240, 170))
    def distance_to_segment(point, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        fraction = max(0.0, min(1.0, ((point[0] - start[0])*dx + (point[1] - start[1])*dy) / (dx*dx + dy*dy)))
        return math.hypot(point[0] - (start[0] + fraction*dx), point[1] - (start[1] + fraction*dy))
    # Maximum radius 80 and patrol displacement 14. Allow additional
    # 22.5-unit interaction completion tolerance around route objectives.
    for count in (2, 3, 4, 5, 6):
        route = ((0, 0), *points[:count], (-180, 50))
        for a, b in zip(route, route[1:]):
            assert min(distance_to_segment(guard, a, b) for guard in guards) > 80 + 14 + 22.5


@pytest.mark.parametrize("mode,matrix,phase,axis,control", [
    ("survival", "world_matrix", "weather", "complexity", "risk"),
    ("stealth", "mechanics_matrix", "stealth", "count", "grind"),
    ("stealth", "mechanics_matrix", "stealth", "secrets", "lethality"),
])
def test_galaxy_new_survival_and_stealth_controls_are_effective(mode, matrix, phase, axis, control):
    from skeleton.context.galaxy_profile import MATRIX_FIELDS, SCHEMA, compile_galaxy_playable_axes
    config = {field: {} for field in MATRIX_FIELDS}
    config.update(title="Original challenge", genre=mode, narrative_phases={}, extra_params={}, style_params={})
    config[matrix][phase] = {axis: 1000}
    effective, receipt = compile_galaxy_playable_axes({"schema": SCHEMA, "config": config}, mode, {})
    assert effective == {control: 1.0}
    assert receipt["mapped_matrix_dials"] == 1
    assert archetype_files(mode, operator_axes=effective) != archetype_files(mode)


@pytest.mark.parametrize("scarcity,recharge", [(0.0, 20.0), (0.5, 12.5), (1.0, 5.0)])
def test_racing_specialized_controller_has_finite_boost_and_acceleration(scarcity, recharge):
    import json
    from skeleton.forge.playable_tuning import SOURCE_PATH
    files = archetype_files("racing", operator_axes={"scarcity": scarcity, "tempo": 1.0})
    player = files["scripts/archetypes/racing/player_controller.gd"]
    assert "@export var speed: float = 525.00" in player
    assert f"const BOOST_RECHARGE := {recharge:.2f}" in player
    assert "boost_charge >= BOOST_DRAIN * delta" in player
    assert "boost_charge - BOOST_DRAIN * delta" in player
    assert "minf(100.0, boost_charge + BOOST_RECHARGE * delta)" in player
    assert 'Input.is_action_pressed("ui_accept")' in player
    assert "velocity.move_toward(desired, acceleration * delta)" in player
    assert "sqrt(2.0 * BRAKE_ACCELERATION * distance)" in player
    assert json.loads(files[SOURCE_PATH])["applied"]["racing.boost_recharge_per_second"] == recharge


def test_racing_first_checkpoint_starts_lap_and_each_lap_requires_closed_circuit():
    loop = archetype_files("racing", operator_axes={"grind": 1.0})["scripts/archetypes/racing/core_loop.gd"]
    assert "const GOAL_LAPS := 4" in loop
    assert "var started: bool = false" in loop
    assert "if not started:" in loop and "waypoint = 1" in loop
    assert "if waypoint == 0:" in loop
    assert "laps += 1" in loop
    assert "waypoint = (waypoint + 1) % course.size()" in loop
    assert "last_sector = elapsed - sector_started_at" in loop
    assert "last_lap = elapsed - lap_started_at" in loop
    assert "lap_times.append(last_lap)" in loop
    assert "last_lap < best_lap" in loop
    assert "elapsed >= TIME_LIMIT" in loop


def test_galaxy_economy_tunes_racing_boost_regeneration():
    from skeleton.context.galaxy_profile import MATRIX_FIELDS, SCHEMA, compile_galaxy_playable_axes
    config = {field: {} for field in MATRIX_FIELDS}
    config.update(title="Time trial", genre="racing", narrative_phases={}, extra_params={}, style_params={})
    config["mechanics_matrix"]["economy"] = {"complexity": 1000}
    axes, receipt = compile_galaxy_playable_axes({"schema": SCHEMA, "config": config}, "racing", {})
    assert axes == {"scarcity": 1.0}
    player = archetype_files("racing", operator_axes=axes)["scripts/archetypes/racing/player_controller.gd"]
    assert "const BOOST_RECHARGE := 5.00" in player
    assert receipt["mapped_matrix_dials"] == 1


@pytest.mark.parametrize("depth,count", [(0.0, 2), (0.25, 3), (0.5, 4), (0.75, 5), (1.0, 6)])
def test_extraction_cache_goal_matches_actual_collectibles_and_finite_coolant(depth, count):
    import re
    files = archetype_files("extraction", operator_axes={"grind": depth, "risk": 1.0, "scarcity": 1.0})
    loop = files["scripts/archetypes/extraction/core_loop.gd"]
    points = re.search(r"var loot: Array\[Vector2\] = \[(.*?)\]", loop).group(1)
    assert points.count("Vector2(") == count
    assert f"const CACHE_GOAL := {count}" in loop
    assert "const HEAT_LIMIT := 70.00" in loop
    assert "const HEAT_PER_SECOND := 10.00" in loop
    assert "CARGO_HEAT * float(carried) / float(CACHE_GOAL)" in loop
    assert "var coolant: int = 2" in loop
    assert "if coolant <= 0 or heat < COOLANT_RESTORE:" in loop
    assert "coolant -= 1" in loop and "heat - COOLANT_RESTORE" in loop
    assert "carried == CACHE_GOAL:" in loop
    assert "100.0 * heat / HEAT_LIMIT" in loop


@pytest.mark.parametrize("scarcity,capacity", [(0.0, 3), (0.5, 2), (1.0, 1)])
@pytest.mark.parametrize("depth,quota", [(0.0, 2), (0.5, 5), (1.0, 8)])
def test_factory_cargo_capacity_and_finite_stock_are_bound_to_quota(scarcity, capacity, depth, quota):
    files = archetype_files("pipeline", operator_axes={"scarcity": scarcity, "grind": depth})
    loop = files["scripts/archetypes/pipeline/core_loop.gd"]
    assert f"const CARGO_CAPACITY := {capacity}" in loop
    assert f"const QUOTA := {quota}" in loop
    assert "var source_stock: int = QUOTA" in loop
    assert "raw_cargo + refined_cargo <= CARGO_CAPACITY" in loop
    assert "source_stock + raw_cargo + refined_cargo + shipped == QUOTA" in loop
    assert "raw_cargo = mini(CARGO_CAPACITY, source_stock)" in loop
    assert "source_stock -= raw_cargo" in loop
    assert "refine_timer = REFINE_SECONDS_PER_UNIT * float(raw_cargo)" in loop
    assert "refined_cargo = raw_cargo" in loop and "raw_cargo = 0" in loop
    assert "shipped += refined_cargo" in loop and "refined_cargo = 0" in loop
    assert "if shipped == QUOTA and source_stock == 0 and raw_cargo == 0 and refined_cargo == 0:" in loop
    assert 'Input.is_action_just_pressed("ui_accept")' in loop
    assert 'elif autopilot or Input.is_action_pressed("ui_accept"):' in loop


@pytest.mark.parametrize("mode,matrix,phase,dial,control", [
    ("extraction", "world_matrix", "dungeon", "secrets", "grind"),
    ("pipeline", "mechanics_matrix", "economy", "intricacy", "scarcity"),
])
def test_galaxy_extraction_and_factory_resource_controls(mode, matrix, phase, dial, control):
    from skeleton.context.galaxy_profile import MATRIX_FIELDS, SCHEMA, compile_galaxy_playable_axes
    config = {field: {} for field in MATRIX_FIELDS}
    config.update(title="Resource operation", genre=mode, narrative_phases={}, extra_params={}, style_params={})
    config[matrix][phase] = {dial: 1000}
    axes, receipt = compile_galaxy_playable_axes({"schema": SCHEMA, "config": config}, mode, {})
    assert axes == {control: 1.0}
    assert receipt["mapped_matrix_dials"] == 1
    # Factory's default capacity already equals the high-scarcity boundary.
    expected = "const CACHE_GOAL := 6" if mode == "extraction" else "const CARGO_CAPACITY := 1"
    loop = archetype_files(mode, operator_axes=axes)[f"scripts/archetypes/{mode}/core_loop.gd"]
    assert expected in loop
