from skeleton.forge.ai_builder.validate import check_cycles, check_reachability, check_winnable

from .plan_fixtures import good_plan, msgs


def test_good_plan_playable():
    p = good_plan()
    assert check_reachability(p) == [] and check_cycles(p) == []
    assert msgs(check_winnable(p), "ERROR") == []


def test_unreachable_goal_is_error():
    p = good_plan(); p["levels"][1]["exits"] = ["l1"]
    m = msgs(check_reachability(p), "ERROR")
    assert m == ["no goal level is reachable from start"]


def test_one_of_many_goals_unreachable_warns_and_orphans_warn():
    p = good_plan(); p["goal_levels"] = ["l3", "l4"]
    p["levels"].append({"id": "l4", "scene": "gate", "exits": [], "encounters": []})
    p["levels"].append({"id": "l5", "scene": "gate", "exits": [], "encounters": []})
    probs = check_reachability(p)
    assert msgs(probs, "ERROR") == []
    assert set(msgs(probs, "WARNING")) == {"goal 'l4' unreachable", "level 'l5' unreachable"}


def test_missing_start():
    p = good_plan(); p["start_level"] = "zz"
    assert msgs(check_reachability(p)) == ["no start level to search from"]


def test_unwinnable_single_encounter():
    p = good_plan(); p["encounters"][1]["enemy_hp"] = 500  # 50s * 5 = 250 dmg > 100 hp
    assert any("encounter 'e2' unwinnable" in m for m in msgs(check_winnable(p), "ERROR"))


def test_unwinnable_in_sequence():
    p = good_plan(); p["encounters"][0]["enemy_hp"] = 120; p["encounters"][1]["enemy_hp"] = 80
    probs = check_winnable(p)  # l2: 60 + 40 = 100 >= hp 100; each alone survivable
    assert msgs(probs, "ERROR") == ["level 'l2' unwinnable in sequence: 100.0 dmg vs hp 100"]
    assert msgs(probs, "WARNING") == []  # l1 takes 60 < 80


def test_near_lethal_warns():
    p = good_plan(); p["encounters"][0]["enemy_hp"] = 170  # l1 takes 85 >= 0.8 * 100
    assert "level 'l1' near-lethal: 85.0 dmg vs hp 100" in msgs(check_winnable(p), "WARNING")


def test_margin_tightens_bound():
    p = good_plan()  # l2 takes 10 + 15 = 25
    assert msgs(check_winnable(p, margin=3.0), "ERROR") == []
    assert msgs(check_winnable(p, margin=4.0), "ERROR") == ["level 'l2' unwinnable in sequence: 25.0 dmg vs hp 100"]


def test_missing_player_stats():
    p = good_plan(); p["player"] = {}
    assert msgs(check_winnable(p)) == ["player stats missing; cannot prove winnability"]


def test_infinite_trigger_loop_detected():
    p = good_plan(); p["triggers"].append({"id": "t3", "on": "music", "emits": ["spawn"]})
    m = msgs(check_cycles(p), "ERROR")
    assert len(m) == 1 and m[0].startswith("infinite loop") and "t2" in m[0] and "t3" in m[0]


def test_self_loop_and_once_bounded():
    p = good_plan(); p["triggers"] = [{"id": "a", "on": "tick", "emits": ["tick"]}]
    assert msgs(check_cycles(p), "ERROR") == ["infinite loop a -> a"]
    p["triggers"][0]["once"] = True
    assert msgs(check_cycles(p), "ERROR") == [] and msgs(check_cycles(p), "WARNING")


def test_deep_chain_no_recursion_error():
    p = good_plan()
    p["triggers"] = [{"id": f"t{i}", "on": f"e{i}", "emits": [f"e{i + 1}"]} for i in range(5000)]
    assert check_cycles(p) == []
