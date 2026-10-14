import pytest
from skeleton.ai.providers.model_deprecation import *


def test_consumer_inventory_blocks_early_retirement():
    decision = retire(
        ModelDeprecation(
            "m",
            "n",
            10,
            (ModelConsumer("c", False),),
        ),
        11,
    )
    assert not decision.retired


def test_explicit_exception_allows_retirement_after_deadline():
    decision = retire(
        ModelDeprecation(
            "m",
            "n",
            10,
            (ModelConsumer("c", False, "approved"),),
        ),
        11,
    )
    assert decision.retired


def test_duplicate_consumer_inventory_rejected_at_boundary():
    consumer = ModelConsumer("c", True)
    with pytest.raises(ValueError):
        ModelDeprecation("m", "n", 0, (consumer, consumer))


def test_deadline_still_blocks_migrated_inventory():
    decision = retire(
        ModelDeprecation(
            "m",
            "n",
            10,
            (ModelConsumer("c", True),),
        ),
        9,
    )
    assert not decision.retired
    assert decision.reason == "deadline not reached"


def test_empty_exception_is_not_an_approval():
    with pytest.raises(ValueError):
        ModelConsumer("c", False, "")
