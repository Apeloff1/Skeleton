import pytest

from skeleton.forge.ai_builder.edit import DiffError, EditOp, PlanDiff, apply_diff, invert, rule_based_diff

from .plan_fixtures import good_plan


def roundtrip(diff):
    p = good_plan()
    new, applied = apply_diff(p, diff)
    back, _ = apply_diff(new, invert(applied))
    assert back == p and p == good_plan()  # original untouched
    again, _ = apply_diff(p, applied)
    assert again == new  # applied diff is replayable (redo)
    return new, applied


def test_change_by_id_and_old_recorded():
    new, applied = roundtrip(PlanDiff((EditOp("change", ("encounters", "e2", "enemy_hp"), 40),)))
    assert new["encounters"][1]["enemy_hp"] == 40 and applied.ops[0].old == 30


def test_add_append_and_insert_index():
    new, _ = roundtrip(PlanDiff((EditOp("add", ("levels", "l1", "exits"), "l3"),)))
    assert new["levels"][0]["exits"] == ["l2", "l3"]
    new, a = roundtrip(PlanDiff((EditOp("add", ("systems",), "loot", index=0),)))
    assert new["systems"][0] == "loot" and a.ops[0].index == 0


def test_remove_list_item_by_id_and_string():
    new, a = roundtrip(PlanDiff((EditOp("remove", ("levels", "l2", "exits", "l1")),
                                 EditOp("remove", ("encounters", "e2")))))
    assert new["levels"][1]["exits"] == ["l3"] and [e["id"] for e in new["encounters"]] == ["e1"]
    assert a.ops[1].path == ("encounters", 1)


def test_change_creates_and_remove_drops_mapping_key():
    new, _ = roundtrip(PlanDiff((EditOp("change", ("player", "armor"), 3),)))
    assert new["player"]["armor"] == 3
    new, _ = roundtrip(PlanDiff((EditOp("remove", ("triggers",)),)))
    assert "triggers" not in new


def test_errors():
    p = good_plan()
    for d in (PlanDiff((EditOp("change", ("levels", "zz", "scene"), "x"),)),
              PlanDiff((EditOp("add", ("title",), "x"),)),
              PlanDiff((EditOp("add", ("levels",), {"id": "l1"}),)),
              PlanDiff((EditOp("add", ("systems",), "x", index=9),)),
              PlanDiff((EditOp("change", ("levels", 7, "scene"), "x"),))):
        with pytest.raises(DiffError):
            apply_diff(p, d)
    with pytest.raises(DiffError):
        EditOp("move", ("a",))
    with pytest.raises(DiffError):
        EditOp("add", ())
    with pytest.raises(DiffError):
        PlanDiff.from_obj({"ops": []})


def test_from_obj_and_as_dict_roundtrip():
    d = PlanDiff.from_obj({"ops": [{"op": "change", "path": ["player", "hp"], "value": 5}]})
    assert PlanDiff.from_obj(d.as_dict()) == d


@pytest.mark.parametrize("text,expected", [
    ("set title to Tide Gate", [("change", ("title",), "Tide Gate")]),
    ("set player hp to 150", [("change", ("player", "hp"), 150)]),
    ("set encounter e1 enemy_dps to 2.5", [("change", ("encounters", "e1", "enemy_dps"), 2.5)]),
    ("add exit from l1 to l3", [("add", ("levels", "l1", "exits"), "l3")]),
    ("remove exit from l2 to l1", [("remove", ("levels", "l2", "exits", "l1"), None)]),
    ("add encounter e2 to level l3", [("add", ("levels", "l3", "encounters"), "e2")]),
    ("remove encounter e1 from level l1", [("remove", ("levels", "l1", "encounters", "e1"), None)]),
    ("remove trigger t2", [("remove", ("triggers", "t2"), None)]),
    ("set player dps to 12; remove exit from l2 to l1 and then set title to X",
     [("change", ("player", "dps"), 12), ("remove", ("levels", "l2", "exits", "l1"), None),
      ("change", ("title",), "X")]),
])
def test_rule_grammar(text, expected):
    assert [(o.op, o.path, o.value) for o in rule_based_diff(text).ops] == expected


def test_rules_unknown_returns_none():
    assert rule_based_diff("make it more fun") is None
    assert rule_based_diff("set player hp to 5; dance") is None
