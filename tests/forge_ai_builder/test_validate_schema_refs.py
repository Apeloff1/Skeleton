from skeleton.forge.ai_builder.validate import check_references, check_schema

from .plan_fixtures import good_plan, msgs


def test_good_plan_clean():
    assert check_schema(good_plan()) == []
    assert check_references(good_plan()) == []


def test_schema_non_mapping_and_wrong_schema():
    assert msgs(check_schema([])) == ["plan must be an object"]
    p = good_plan(); p["schema"] = "x"
    assert any("schema must be" in m for m in msgs(check_schema(p)))


def test_schema_required_scalars_and_player():
    p = good_plan(); del p["title"]; p["goal_levels"] = []; p["player"] = {"hp": 0, "dps": float("nan")}
    m = msgs(check_schema(p))
    assert "title: expected str" in m and "goal_levels: at least one goal" in m
    assert "player.hp: expected pos" in m and "player.dps: expected pos" in m


def test_schema_sections_fields_and_duplicates():
    p = good_plan()
    p["levels"] = []
    p["encounters"][0]["enemy_hp"] = True
    p["assets"].append({"id": "tiles", "kind": "x"})
    p["scenes"].append("nope")
    p["triggers"][0]["once"] = "yes"
    m = msgs(check_schema(p))
    assert "levels: expected non-empty list" in m
    assert "encounters[0].enemy_hp: expected pos" in m
    assert "assets: duplicate id 'tiles'" in m
    assert "scenes[2]: expected object" in m
    assert "triggers[0].once: expected bool" in m


def test_triggers_optional():
    p = good_plan(); del p["triggers"]
    assert check_schema(p) == []


def test_refs_unknown_asset_scene_exit_encounter_system():
    p = good_plan()
    p["scenes"][0]["assets"].append("ghost")
    p["levels"][0]["scene"] = "void"
    p["levels"][0]["exits"].append("l9")
    p["levels"][2]["encounters"] = ["e9"]
    p["encounters"][1]["system"] = "magic"
    m = msgs(check_references(p), "ERROR")
    assert "scene 'yard': unknown asset 'ghost'" in m
    assert "level 'l1': unknown scene 'void'" in m
    assert "level 'l1': unknown exit 'l9'" in m
    assert "level 'l3': unknown encounter 'e9'" in m
    assert "encounter 'e2': unknown system 'magic'" in m


def test_refs_start_goal_and_unused_warnings():
    p = good_plan(); p["start_level"] = "x"; p["goal_levels"] = ["y"]
    p["assets"].append({"id": "spare", "kind": "sfx"}); p["scenes"].append({"id": "idle", "assets": []})
    probs = check_references(p)
    assert {"start_level 'x' unknown", "goal level 'y' unknown"} <= set(msgs(probs, "ERROR"))
    assert {"asset 'spare' unused", "scene 'idle' unused"} <= set(msgs(probs, "WARNING"))
