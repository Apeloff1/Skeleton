"""Smoke coverage for milestones 15-64."""
from skeleton.jeeves.game_frontier_milestone_9 import CampaignArchive
from skeleton.jeeves.game_frontier_milestone_12 import SnapshotHistory
from skeleton.jeeves.game_frontier_milestone_14 import receipt


def _receipts(n=3):
    archive = CampaignArchive()
    history = SnapshotHistory()
    out = []
    for _ in range(n):
        history.record(archive)
        out.append(receipt(history))
    return out


def test_15_same_lineage():
    from skeleton.jeeves.game_frontier_milestone_15 import same_lineage
    rs = _receipts()
    assert same_lineage(rs[0], rs[0]) is True
    assert same_lineage(rs[0], rs[1]) is False


def test_16_link():
    from skeleton.jeeves.game_frontier_milestone_16 import link
    rs = _receipts()
    result = link(rs[0], rs[1])
    assert result["parent"] == rs[0].receipt


def test_21_count():
    from skeleton.jeeves.game_frontier_milestone_21 import count
    assert count(_receipts()) == 3


def test_23_longest():
    from skeleton.jeeves.game_frontier_milestone_23 import longest
    rs = _receipts()
    assert longest(rs).length == 3


def test_25_total():
    from skeleton.jeeves.game_frontier_milestone_25 import total
    assert total(_receipts()) == 6


def test_30_ordered():
    from skeleton.jeeves.game_frontier_milestone_30 import ordered
    rs = _receipts()
    lengths = [r.length for r in ordered(rs)]
    assert lengths == sorted(lengths)


def test_34_delta():
    from skeleton.jeeves.game_frontier_milestone_34 import delta
    rs = _receipts()
    assert delta(rs[0], rs[2]) == 2


def test_39_nonempty():
    from skeleton.jeeves.game_frontier_milestone_39 import nonempty
    assert nonempty(_receipts()[0]) is True


def test_47_summarize():
    from skeleton.jeeves.game_frontier_milestone_47 import summarize
    s = summarize(_receipts()[0])
    assert s["length"] == 1


def test_50_contains():
    from skeleton.jeeves.game_frontier_milestone_50 import contains
    rs = _receipts()
    assert contains(rs, rs[1].receipt) is True


def test_55_reverse():
    from skeleton.jeeves.game_frontier_milestone_55 import reverse
    rs = _receipts()
    assert reverse(rs)[0].receipt == rs[-1].receipt


def test_58_max_length():
    from skeleton.jeeves.game_frontier_milestone_58 import max_length
    assert max_length(_receipts()) == 3


def test_60_mean():
    from skeleton.jeeves.game_frontier_milestone_60 import mean
    assert mean(_receipts()) == 2.0


def test_64_head_tail():
    from skeleton.jeeves.game_frontier_milestone_64 import tail
    r = _receipts()[0]
    assert tail(r, 4) == r.head[-4:]
