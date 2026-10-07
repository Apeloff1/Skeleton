"""Recalled prose is not a walk with zero time."""

from skeleton.jeeves.builder import _walk_from_cortex


class _Cortex:
    def __init__(self, rec):
        self.rec = rec

    def recall(self, stim):
        return self.rec


def test_a_sentence_does_not_become_an_extracted_walk() -> None:
    prose = _Cortex({"composed": {"thought": {"text": "forge run extracted hops 4"}}})
    assert _walk_from_cortex(prose, "soulslike") is None
    assert _walk_from_cortex(None, "soulslike") is None
    measured = _Cortex({
        "composed": {
            "thought": {
                "walk": {"extracted": True, "collapsed": False, "t": 12, "fights": 2, "hops": 3},
            },
        },
    })
    walk = _walk_from_cortex(measured, "soulslike")
    assert walk["t"] == 12
    assert walk["fights"] == 2
