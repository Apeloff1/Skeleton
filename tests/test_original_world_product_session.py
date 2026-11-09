"""End-to-end real product: physical world, player, citizens and renderer."""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, step_product, product_save,
    product_restore, validate_product,
)
from skeleton.game.generation.original_world_product_render import (
    ascii_render, scene, svg_render, ppm_render,
)
from skeleton.game.generation.original_world_product_cli import (
    main, parse_script, parse_command,
)


def create():
    law = living_for(0, "puzzle", "lattice", "trophic", "sandbox")
    return create_product(law.index)


def use(state, layer, verb, amount=1, x=0, y=0, target=-1, option=""):
    return step_product(state, ProductAction(
        layer, verb, amount, x, y, target, option))[0]


def test_instantiates_one_real_product_with_fully_linked_subsystems() -> None:
    s = create()
    law = validate_product(s)
    assert law.foundation.system.system_id == "trophic"
    assert len(s.society.inhabitants) == 12
    assert s.terrain.design_id == law.design_id
    assert s.living.spatial.game.causal.action_points == 4
    assert s.society.tick == s.terrain.turns == s.living.living_turns == 0


def test_player_physically_harvests_and_donates_resources_to_shared_game() -> None:
    s = create()
    stock = s.terrain.provisions
    world_stock = s.living.spatial.game.causal.supplies
    s = use(s, "terrain", "forage", amount=2)
    assert s.terrain.provisions == stock + 2
    assert s.living.spatial.game.causal.action_points == 3
    s = use(s, "studio", "share_food", amount=2)
    assert s.terrain.provisions == stock
    assert s.living.spatial.game.causal.supplies == world_stock + 2
    s = use(s, "studio", "deposit_wood", amount=1)
    assert s.terrain.lumber == 2
    assert s.living.spatial.materials == 9
    s = use(s, "living", "reseed")
    assert s.living.spatial.game.causal.action_points == 0
    with pytest.raises(FoundationError):
        use(s, "terrain", "forage")
    s = use(s, "causal", "end_turn")
    assert s.terrain.turns == 1
    assert s.society.tick == 1
    assert s.living.living_turns == 1
    assert s.living.spatial.game.causal.action_points == 4
    assert s.events == 5


def test_a_real_source_world_turn_ticks_exactly_twelve_physical_citizens() -> None:
    s = create()
    before = s.society.inhabitants
    s, receipt = step_product(s, ProductAction("causal", "end_turn"))
    assert s.society.inhabitants != before
    assert "Autonomous citizens" in " ".join(receipt.changes)
    assert s.society.event_count == 1
    assert s.terrain.events == 1
    assert s.events == 1
    assert validate_product(s)


def test_social_job_assignment_and_gift_require_actual_proximity_and_cost() -> None:
    s = create()
    assert s.society.inhabitants[0].x == 0
    old = s.society.inhabitants[0].profession
    old_trust = s.living.spatial.game.causal.trust
    s = use(s, "studio", "assign", target=0, option="engineer")
    assert s.society.inhabitants[0].profession == "engineer"
    assert s.society.inhabitants[0].profession != old
    assert s.living.spatial.game.causal.trust == old_trust - 1
    old_food = s.terrain.provisions
    s = use(s, "studio", "gift", target=0)
    assert s.terrain.provisions == old_food - 1
    assert s.society.inhabitants[0].relationships == 5


def test_game_save_restore_covers_real_physical_changes_and_real_people() -> None:
    s = create()
    s = use(s, "terrain", "chop")
    s = use(s, "terrain", "build_hearth")
    s = use(s, "causal", "end_turn")
    saved = product_save(s)
    assert product_restore(saved) == s
    tampered = json.loads(saved)
    tampered["payload"]["terrain"]["payload"]["state"]["lumber"] = 999
    with pytest.raises(FoundationError):
        product_restore(json.dumps(tampered))


def test_real_world_renderers_show_actual_cells_and_resident_positions() -> None:
    s = create()
    svg = svg_render(s.terrain, s.society, radius=4, title="A <gentle> original world")
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert "&lt;gentle&gt;" in svg
    assert "<circle" in svg and "<rect" in svg
    assert "<script" not in svg
    ppm = ppm_render(s.terrain, s.society, radius=4, scale=3)
    assert ppm.startswith(b"P6\n27 27\n255\n")
    assert len(ppm) == len(b"P6\n27 27\n255\n") + 27 * 27 * 3
    ascii_map = ascii_render(s.terrain, s.society, radius=3)
    assert ascii_map.count("@") == 1
    assert len(ascii_map.splitlines()) == 7
    s2 = use(s, "terrain", "build_hearth")
    # The centered player sprite overlays the hearth glyph, but the building
    # remains rendered and persists in the actual editable world state.
    from skeleton.game.generation.original_world_product_terrain import cell_at
    assert cell_at(s2.terrain, 0, 0).building == "hearth"
    assert "#ffb55f" in svg_render(s2.terrain, s2.society)


def test_cli_runs_actual_physical_turn_and_writes_real_svg_ppm_and_save(tmp_path, capsys) -> None:
    save = tmp_path / "pilot-world.json"
    svg = tmp_path / "pilot-preview.svg"
    ppm = tmp_path / "pilot-preview.ppm"
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--system", "trophic", "--arc", "sandbox",
        "--actions-json", '[{"layer":"terrain","verb":"forage","amount":2},'
                          '{"layer":"studio","verb":"share_food","amount":2},'
                          '{"layer":"causal","verb":"end_turn"}]',
        "--svg", str(svg), "--ppm", str(ppm), "--save", str(save),
    ]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["product"]["world_turn"] == 1
    assert packet["product"]["local_residents"] == 12
    assert "<svg" in svg.read_text()
    assert ppm.read_bytes().startswith(b"P6")
    assert save.is_file()
    assert main(["--load", str(save), "--actions-json",
                 '[{"layer":"causal","verb":"end_turn"}]']) == 0
    loaded = json.loads(capsys.readouterr().out)
    assert loaded["product"]["world_turn"] == 2


def test_script_parser_rejects_invalid_embedded_actions_and_command_escape() -> None:
    assert parse_command("terrain walk north", (0, 0)) == ProductAction(
        "terrain", "walk", x=0, y=-1)
    assert parse_command("studio assign 0 engineer", (0, 0)).option == "engineer"
    assert parse_command("causal end_turn", (0, 0)).verb == "end_turn"
    assert len(parse_script('[{"layer":"terrain","verb":"forage"},'
                            '{"layer":"causal","verb":"end_turn"}]')) == 2
    for bad in ("{}", "null", "not-json",
                '[{"layer":"terrain","verb":"forage","secret":"x"}]'):
        with pytest.raises(FoundationError):
            parse_script(bad)


def test_headless_world_can_import_tk_desktop_launcher_without_a_display() -> None:
    from skeleton.game.generation.original_world_product_desktop import launch_desktop
    assert callable(launch_desktop)


def test_invalid_product_state_and_world_clock_rejected_without_mutation() -> None:
    s = create()
    forged = replace(s, society=replace(s.society, tick=5))
    with pytest.raises(FoundationError):
        validate_product(forged)
    initial = asdict(s)
    with pytest.raises(FoundationError):
        use(s, "terrain", "forage", amount=True)
    assert initial == asdict(s)
