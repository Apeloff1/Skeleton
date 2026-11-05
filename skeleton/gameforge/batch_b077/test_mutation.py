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


def test_runtime_unsupported_operands_never_inflate_mutation_score():
    from skeleton.gameforge.batch_b077.mutation import MutationUnsupportedError

    def truthy(x):
        return not x

    def checks(f):
        assert f(object()) is False

    with pytest.raises(MutationUnsupportedError, match="plain scalar"):
        run_mutation(truthy, checks)


def test_interpreter_rejects_unbounded_inputs_and_nonfinite_floats():
    from skeleton.gameforge.batch_b077.mutation import MutationUnsupportedError, _interpret
    import ast

    for value in (10**100, float("nan"), float("inf"), "x" * 1025, object()):
        with pytest.raises(MutationUnsupportedError):
            _interpret(ast.Name(id="x", ctx=ast.Load()), {"x": value})


def test_mutant_source_and_site_generation_budgets(monkeypatch):
    from skeleton.gameforge.batch_b077 import mutation
    monkeypatch.setattr(mutation, "MAX_MUTATION_SITES", 1)
    with pytest.raises(mutation.MutationUnsupportedError, match="site count"):
        mutation.generate_mutants(can_trade)
    monkeypatch.setattr(mutation.inspect, "getsource", lambda fn: "def f(x):\n    return x + 1\n" + " " * 32769)
    with pytest.raises(mutation.MutationUnsupportedError, match="byte bound"):
        mutation.generate_mutants(can_trade)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.1, True, "0.5"])
def test_mutation_gate_rejects_invalid_thresholds_without_false_pass(bad):
    from skeleton.gameforge.batch_b077.mutation import MutationReport

    report = MutationReport("weak")
    with pytest.raises(ValueError, match="finite fraction"):
        report.gate(bad)


def test_empty_mutation_set_cannot_certify_quality():
    """A 100% score requires at least one executed mutation witness."""
    from skeleton.gameforge.batch_b077.mutation import MutationReport

    report = MutationReport("no_mutation_sites")
    assert report.score == 0.0
    for threshold in (0.0, 0.5, 1.0):
        with pytest.raises(AssertionError, match="no executable mutants"):
            report.gate(threshold)

    def identity(x):
        return x

    generated = run_mutation(identity, lambda fn: fn(5) == 5)
    assert generated.score == 0.0
    with pytest.raises(AssertionError, match="no executable mutants"):
        generated.gate()


def test_incomparable_mutant_operands_cannot_count_as_killed():
    import ast
    from skeleton.gameforge.batch_b077.mutation import MutationUnsupportedError, _interpret

    expr = ast.parse("left < right", mode="eval").body
    for left, right in (("3", 3), (True, 1), (None, "x")):
        with pytest.raises(MutationUnsupportedError):
            _interpret(expr, {"left": left, "right": right})
    assert _interpret(expr, {"left": 1, "right": 2.0}) is True
    assert _interpret(expr, {"left": "a", "right": "b"}) is True
