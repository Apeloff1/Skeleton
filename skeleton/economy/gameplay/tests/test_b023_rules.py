"""B023: sandboxed integer price-rule scripting."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.rules import MAX_MAGNITUDE, RuleError, compile_rule


def test_rule_evaluates_integer_formula_with_clamps():
    rule = compile_rule(
        "ore_price",
        "base * (100 + demand) // 100 + max(0, 5 - stock) * 7",
        {"base", "demand", "stock"},
        floor=5,
        ceiling=500,
    )
    assert rule.evaluate({"base": 10, "demand": 50, "stock": 2}) == 15 + 21
    assert rule.evaluate({"base": 10, "demand": -100, "stock": 9}) == 5  # floor
    assert rule.evaluate({"base": 1_000, "demand": 0, "stock": 9}) == 500  # ceiling


def test_conditionals_and_helpers():
    rule = compile_rule("tier", "clamp(base * 2, 1, 50) if level >= 10 else abs(-base)", {"base", "level"})
    assert rule.evaluate({"base": 40, "level": 10}) == 50
    assert rule.evaluate({"base": 40, "level": 3}) == 40
    chained = compile_rule("band", "1 if 0 < x < 10 else 2", {"x"})
    assert chained.evaluate({"x": 5}) == 1
    assert chained.evaluate({"x": 10}) == 2


@pytest.mark.parametrize(
    "source, message",
    [
        ("__import__('os').system('true')", "call not allowed"),
        ("base.__class__", "Attribute"),
        ("base ** 99", "Pow"),
        ("base / 2", "Div"),
        ("1.5 * base", "integer literals"),
        ("'a' * base", "integer literals"),
        ("[base]", "List"),
        ("unknown + 1", "unknown variable"),
        ("min(base)", "arity"),
        ("max(*base)", "star"),
        ("base if base else 1", "comparison"),
        ("lambda: 1", "Lambda"),
        ("base +", "syntax error"),
        ("True + base", "integer literals"),
        ("not base", "unary"),
    ],
)
def test_unsafe_or_invalid_rules_rejected(source, message):
    with pytest.raises(RuleError, match=message):
        compile_rule("r", source, {"base"})


def test_complexity_and_magnitude_limits():
    with pytest.raises(RuleError, match="complex"):
        compile_rule("r", " + ".join(["base"] * 60), {"base"})
    with pytest.raises(RuleError, match="too long"):
        compile_rule("r", "1" * 600, set())
    rule = compile_rule("r", "base * base * base", {"base"})
    with pytest.raises(RuleError, match="out of range"):
        rule.evaluate({"base": 10**6})
    with pytest.raises(RuleError, match="out of range"):
        rule.evaluate({"base": MAX_MAGNITUDE + 1})


def test_runtime_errors_fail_closed():
    rule = compile_rule("r", "base // div", {"base", "div"})
    with pytest.raises(RuleError, match="division by zero"):
        rule.evaluate({"base": 1, "div": 0})
    with pytest.raises(RuleError, match="missing"):
        rule.evaluate({"base": 1})
    with pytest.raises(RuleError, match="integer"):
        rule.evaluate({"base": 1, "div": True})
    with pytest.raises(RuleError, match="invalid variable"):
        compile_rule("r", "1", {"min"})
