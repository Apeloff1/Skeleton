"""A claim polarity is a boolean, and a court verdict is too."""

import pytest

from skeleton.intelligence.cognition import Cognition


def test_a_string_polarity_is_not_a_belief() -> None:
    mind = Cognition(clock=lambda: 1.0)
    with pytest.raises(ValueError):
        mind.assert_plan_claims([{"predicate": "ship", "polarity": "false"}])
    assert mind.stats()["beliefs"] == 0
    mind.assert_plan_claims([{"predicate": "ship", "polarity": False}])
    belief_id = mind.hold("ship", False)
    belief = mind.belief(belief_id)
    assert belief.polarity is False
    assert belief.lodds > 0
    with pytest.raises(ValueError):
        mind.testify(belief_id, "plan", True, 5)


def test_a_non_boolean_verdict_does_not_clear_the_court() -> None:
    mind = Cognition(clock=lambda: 1.0)
    yes = mind.hold("ship", True)
    no = mind.hold("ship", False)
    for witness, belief_id in (("a", yes), ("b", yes), ("c", no), ("d", no)):
        mind.testify(belief_id, witness, True, 1)
    assert mind.schisms()
    assert mind.resolve_schism("ship", "yes") is False
    assert mind.schisms()
    assert mind.resolve_schism("ship", True) is True
    assert mind.schisms() == []
