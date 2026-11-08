import copy


def good_plan():
    return copy.deepcopy({
        "schema": "skeleton.forge.ai_builder.game_plan.v1",
        "title": "Ledge Runner", "start_level": "l1", "goal_levels": ["l3"],
        "systems": ["combat", "levels"],
        "player": {"hp": 100, "dps": 10},
        "assets": [{"id": "tiles", "kind": "tileset"}, {"id": "crab", "kind": "sprite"}],
        "scenes": [{"id": "yard", "assets": ["tiles", "crab"]}, {"id": "gate", "assets": ["tiles"]}],
        "levels": [
            {"id": "l1", "scene": "yard", "exits": ["l2"], "encounters": ["e1"]},
            {"id": "l2", "scene": "yard", "exits": ["l3", "l1"], "encounters": ["e1", "e2"]},
            {"id": "l3", "scene": "gate", "exits": [], "encounters": []},
        ],
        "encounters": [
            {"id": "e1", "system": "combat", "enemy_hp": 20, "enemy_dps": 5},
            {"id": "e2", "system": "combat", "enemy_hp": 30, "enemy_dps": 5},
        ],
        "triggers": [
            {"id": "t1", "on": "level_start", "emits": ["spawn"]},
            {"id": "t2", "on": "spawn", "emits": ["music"]},
        ],
    })


def msgs(problems, severity=None):
    return [p.message for p in problems if severity is None or p.severity.value == severity]
