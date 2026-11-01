import pytest

from skeleton.gameforge.batch_b077 import generate_mutants, run_mutation


def can_trade(level, gold, banned):
    return not banned and level >= 5 and gold > 0


def strong_test(f):
    assert f(5, 1, False) is True
    assert f(4, 1, False) is False
    assert f(5, 0, False) is False
    assert f(6, 1, True) is False
    assert f(6, 1, False) is True
    assert f(10, 2, False) is True


def weak_test(f):
    assert f(10, 100, False) is True


def test_mutants_generated():
    descs = [m.description for m in generate_mutants(can_trade)]
    assert any("GtE->Gt" in d for d in descs) and any("And->Or" in d for d in descs)
    assert any("removed not" in d for d in descs)


def test_strong_suite_kills_all():
    rep = run_mutation(can_trade, strong_test)
    assert rep.score == 1.0
    rep.gate(1.0)


def test_weak_suite_gated():
    rep = run_mutation(can_trade, weak_test)
    assert rep.survived
    with pytest.raises(AssertionError, match="mutation score"):
        rep.gate(0.9)


def test_rejects_failing_baseline():
    with pytest.raises(AssertionError):
        run_mutation(can_trade, lambda f: f(0, 0, True))


def test_unsupported_mutant_is_not_counted_as_a_kill():
    from skeleton.gameforge.batch_b077.mutation import MutationUnsupportedError

    def uses_a_call(x):
        return abs(x) > 0

    with pytest.raises(MutationUnsupportedError):
        run_mutation(uses_a_call, lambda f: f(1))
