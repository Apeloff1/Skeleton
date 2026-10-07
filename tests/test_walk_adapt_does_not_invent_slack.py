"""A missing walk time is not a perfect slack, and false is not true."""

import pytest

from skeleton.jeeves.builder import adapt_from_walk


def test_a_string_false_does_not_count_as_extracted() -> None:
    pack = {"session": {"collapse_max": 30}}
    with pytest.raises(ValueError):
        adapt_from_walk(
            pack, bias="balanced", spawn_weapon=False, extract_late=False,
            trash=2, elite=0, boss=0,
            walk={"extracted": "false", "collapsed": False, "t": 10, "fights": 1, "hops": 1},
        )
    with pytest.raises(ValueError):
        adapt_from_walk(
            pack, bias="balanced", spawn_weapon=False, extract_late=False,
            trash=2, elite=0, boss=0, walk={"extracted": True, "collapsed": False},
        )
    bias, armed, late, trash, elite, boss, tag, slack, notes = adapt_from_walk(
        pack, bias="balanced", spawn_weapon=False, extract_late=True,
        trash=2, elite=0, boss=0, walk=None,
    )
    assert tag == "none"
    assert slack == 0.0
    assert late is True
    held = adapt_from_walk(
        pack, bias="balanced", spawn_weapon=False, extract_late=False,
        trash=2, elite=0, boss=0,
        walk={"extracted": True, "collapsed": False, "t": 10, "fights": 2, "hops": 3},
    )
    assert held[6] == "hold"
    assert held[7] == pytest.approx(20 / 30)
