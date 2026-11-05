import json

from skeleton.gameforge.batch_b076 import Gen, check_property, fuzz_state_machine, shrink_list


class Inventory:
    CAP = 10

    def __init__(self):
        self.items = 0

    def add(self, n):
        if not isinstance(n, int) or n < 0 or self.items + n > self.CAP:
            raise ValueError("rejected")
        self.items += n

    def remove(self, n):
        if not isinstance(n, int) or n < 0 or n > self.items:
            raise ValueError("rejected")
        self.items -= n


class BuggyInventory(Inventory):
    def remove(self, n):
        self.items -= n  # no validation


def _parse(s):
    try:
        return json.loads(s)
    except (ValueError, RecursionError):
        return None


def test_parser_survives_hostile_text():
    assert check_property(Gen.text(), lambda s: _parse(s) is None or True, seed=4).ok


def test_property_failure_is_shrunk_and_seeded():
    r = check_property(Gen.ints(0, 100).lists(20), lambda xs: sum(xs) < 150, seed=1)
    assert not r.ok and r.failure.seed == 1
    assert sum(r.failure.value) >= 150 and len(r.failure.value) <= 3


def test_state_machine_good_and_buggy():
    acts = [("add", Gen.ints(-5, 15)), ("remove", Gen.ints(-5, 15))]
    inv = lambda s: 0 <= s.items <= Inventory.CAP
    assert fuzz_state_machine(Inventory, acts, inv, (ValueError,), seed=2).ok
    bad = fuzz_state_machine(BuggyInventory, acts, inv, (ValueError,), seed=2)
    assert not bad.ok and bad.failure.error == "invariant violated"


def test_crash_is_reported():
    class Crashy(Inventory):
        def add(self, n):
            raise KeyError("boom")
    r = fuzz_state_machine(Crashy, [("add", Gen.ints(0, 1))], lambda s: True, (ValueError,))
    assert "crash KeyError" in r.failure.error


def test_shrink_list_minimal():
    assert shrink_list([1, 2, 3, 99, 4], lambda xs: 99 in xs) == [99]


def test_fuzz_generation_and_execution_budgets_fail_closed():
    import pytest

    with pytest.raises(ValueError, match="text length"):
        Gen.text(100_000)
    with pytest.raises(ValueError, match="list length"):
        Gen.ints().lists(100_000)
    with pytest.raises(ValueError, match="case count"):
        check_property(Gen.ints(), lambda x: True, cases=0)
    with pytest.raises(ValueError, match="workload"):
        fuzz_state_machine(Inventory, [("add", Gen.ints())], lambda s: True, (ValueError,),
                           runs=10_000, steps=10_000)
    with pytest.raises(ValueError, match="shrink input"):
        shrink_list([0] * 10_001, lambda x: True)
