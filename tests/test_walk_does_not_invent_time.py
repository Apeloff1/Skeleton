"""A missing fight time is not zero, and the string false is not a boolean."""

import pytest

from skeleton.forge.walk import walk_graph


def _graph():
    return {
        "rooms": [
            {"id": "start", "kind": "spawn", "x": 0, "y": 0},
            {"id": "pit", "kind": "combat", "x": 10, "y": 0, "occupants": [{"kind": "enemy", "tier": "trash"}]},
            {"id": "out", "kind": "extract", "x": 20, "y": 0},
        ],
        "doors": [
            {"from": "start", "to": "pit"},
            {"from": "pit", "to": "out"},
        ],
    }


def _pack():
    return {
        "player": {"speed": 100},
        "session": {"collapse_max": 30},
        "enemies": [{"id": "trash", "ttk_target": 1.5}],
    }


def test_missing_time_and_a_string_flag_are_refused() -> None:
    pack = _pack()
    del pack["enemies"][0]["ttk_target"]
    with pytest.raises(ValueError):
        walk_graph(pack, _graph())
    pack = _pack()
    pack["enemies"][0]["ttk_target"] = 0
    with pytest.raises(ValueError):
        walk_graph(pack, _graph())
    with pytest.raises(ValueError):
        walk_graph(_pack(), _graph(), plan={"extract_late": "false"})
    bare = dict(_pack())
    del bare["session"]
    with pytest.raises(ValueError):
        walk_graph(bare, _graph())
    report = walk_graph(_pack(), _graph())
    assert report.required_cores == 0
    assert report.fights == 1
    assert report.t > 1
