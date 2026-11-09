"""B023: AST-sandboxed scripting — policy, rewrite guards, budgets, boundary."""
from __future__ import annotations

import pytest

from skeleton.ecs.script import ScriptLimits, check_script, compile_script, to_script_value
from skeleton.ecs.script_guard import Budget
from skeleton.simulation.ecs.errors import (
    ScriptDepthLimitError,
    ScriptMemoryLimitError,
    ScriptRuntimeError,
    ScriptStepLimitError,
    ScriptTimeLimitError,
    ScriptValidationError,
)


def rules(src: str) -> set[str]:
    return {v["rule"] for v in check_script(src)}


@pytest.mark.parametrize(
    "src, rule",
    [
        ("import os\n", "construct"),
        ("from os import path\n", "construct"),
        ("x = ().__class__\n", "underscore"),
        ("x = __builtins__\n", "underscore"),
        ("eval('1')\n", "forbidden-name"),
        ("open('/etc/passwd')\n", "forbidden-name"),
        ("getattr(1, 'real')\n", "forbidden-name"),
        ("type(1)\n", "forbidden-name"),
        ("class A:\n    pass\n", "construct"),
        ("def g():\n    yield 1\n", "construct"),
        ("async def g():\n    pass\n", "construct"),
        ("with x:\n    pass\n", "construct"),
        ("global y\n", "construct"),
        ("x = {1, 2}\n", "construct"),
        ("x = 'a'.format\n", "attribute"),
        ("def f(g):\n    return g.gi_frame\n", "attribute"),
        ("x = [1]\nx.foo = 2\n", "attribute"),
        ("try:\n    pass\nfinally:\n    pass\n", "finally"),
        ("try:\n    pass\nexcept:\n    pass\n", "bare-except"),
        ("try:\n    pass\nexcept BaseException:\n    pass\n", "except-type"),
        ("x = f'{1:{9}}'\n", "format-spec"),
        ("x = f'{1:99999}'\n", "format-spec"),
        ("x = 1 +\n", "syntax"),
        ("@d\ndef f():\n    pass\n", "construct"),
    ],
)
def test_policy_rejects(src: str, rule: str) -> None:
    assert rule in rules(src)
    with pytest.raises(ScriptValidationError):
        compile_script(src)


def test_policy_reports_every_violation_in_source_order() -> None:
    v = check_script("import os\nx = ().__class__\neval('1')\n")
    assert [x["line"] for x in v] == sorted(x["line"] for x in v)
    assert len(v) >= 3


def test_policy_size_bounds() -> None:
    assert "size" in rules("x = 1\n" * 20000)
    assert "constant" in rules("x = '" + "a" * 5000 + "'\n")
    assert "size" in rules("x = 1\x00\n")


def test_valid_script_runs_and_keeps_module_state() -> None:
    s = compile_script(
        "count = 0\n"
        "def bump(n):\n"
        "    total = 0\n"
        "    for i in range(n):\n"
        "        total += i\n"
        "    return {'total': total, 'sq': [i * i for i in range(3)], 'm': math.floor(math.sqrt(17))}\n",
        name="ok",
    )
    inst = s.instantiate()
    r = inst.call("bump", 5)
    assert r.value == {"total": 10, "sq": [0, 1, 4], "m": 4}
    assert r.usage["steps"] > 0
    assert s.functions == ("bump",)
    assert len(s.digest) == 64


def test_step_budget_bounds_infinite_loops() -> None:
    s = compile_script("def f():\n    while True:\n        pass\n", limits=ScriptLimits(max_steps=1000))
    with pytest.raises(ScriptStepLimitError):
        s.call("f")


def test_comprehension_filter_items_are_charged() -> None:
    s = compile_script("def f():\n    return [x for x in range(10**6) if x < 0]\n", limits=ScriptLimits(max_steps=5000))
    with pytest.raises(ScriptStepLimitError):
        s.call("f")


def test_recursion_is_depth_limited() -> None:
    s = compile_script("def f(n):\n    return f(n + 1)\n", limits=ScriptLimits(max_depth=20))
    with pytest.raises(ScriptDepthLimitError):
        s.call("f", 0)


@pytest.mark.parametrize(
    "expr",
    ["'x' * 10**9", "[0] * 10**8", "9 ** 10**6", "1 << 10**7", "'a'.ljust(10**9)", "'ab'.replace('a', 'x' * 4000) * 1000"],
)
def test_memory_bombs_fail_before_allocating(expr: str) -> None:
    s = compile_script(f"def f():\n    return {expr}\n")
    with pytest.raises(ScriptMemoryLimitError):
        s.call("f")


def test_huge_range_and_builtin_sum_are_bounded() -> None:
    s = compile_script("def f():\n    return sum(range(10**12))\n")
    with pytest.raises(ScriptMemoryLimitError):
        s.call("f")


def test_memory_budget_accumulates() -> None:
    s = compile_script("def f():\n    out = []\n    for i in range(100000):\n        out.append('x' * 50)\n    return len(out)\n",
                       limits=ScriptLimits(max_memory=100_000, max_steps=10**7))
    with pytest.raises(ScriptMemoryLimitError):
        s.call("f")


def test_time_budget_with_injected_clock() -> None:
    t = [0.0]

    def clock() -> float:
        t[0] += 0.01
        return t[0]

    s = compile_script("def f():\n    n = 0\n    while n < 10**9:\n        n += 1\n", limits=ScriptLimits(max_steps=10**9, max_seconds=0.5))
    with pytest.raises(ScriptTimeLimitError):
        s.call("f", clock=clock)


def test_runtime_attribute_mediation_by_concrete_type() -> None:
    s = compile_script("def f(x):\n    return x.get('a')\n")
    assert s.call("f", {"a": 1}).value == 1
    with pytest.raises(ScriptRuntimeError):
        s.call("f", [1, 2])  # list has no .get in the method table
    m = compile_script("def f():\n    return math.lerp(0, 10, 0.5) + math.clamp(5, 0, 3)\n")
    assert m.call("f").value == 8.0


def test_ordinary_errors_are_normalised_with_line() -> None:
    s = compile_script("def f():\n    x = 1\n    return x / 0\n", name="div")
    with pytest.raises(ScriptRuntimeError) as info:
        s.call("f")
    assert info.value.context["error_type"] == "ZeroDivisionError"
    assert info.value.context["line"] == 3


def test_scripts_can_catch_allowed_exceptions() -> None:
    s = compile_script("def f(d):\n    try:\n        return d['k']\n    except KeyError:\n        return -1\n")
    assert s.call("f", {}).value == -1


def test_unknown_function_and_bad_api_names() -> None:
    s = compile_script("def f():\n    return 1\n")
    with pytest.raises(ScriptRuntimeError):
        s.call("g")
    with pytest.raises(ValueError):
        s.instantiate({"_evil": 1})


def test_boundary_rejects_host_objects_and_copies_values() -> None:
    src = {"a": [1, 2, {"b": (3, 4)}]}
    copied = to_script_value(src)
    assert copied == src and copied is not src and copied["a"] is not src["a"]
    with pytest.raises(ScriptRuntimeError):
        to_script_value(object())
    with pytest.raises(ScriptRuntimeError):
        to_script_value({(1, 2): 3})
    s = compile_script("def f(cb):\n    return cb\n")
    with pytest.raises(ScriptRuntimeError):
        s.call("f", len)


def test_scripts_cannot_reach_host_through_returned_functions() -> None:
    s = compile_script("def f():\n    return f\n")
    with pytest.raises(ScriptRuntimeError):
        s.call("f")


def test_budget_validation() -> None:
    with pytest.raises(ValueError):
        Budget(max_steps=0)
    with pytest.raises(ValueError):
        Budget(max_seconds=0)


def test_print_is_inert_and_sorted_is_metered() -> None:
    s = compile_script("def f():\n    print('hi')\n    return sorted([3, 1, 2])\n")
    assert s.call("f").value == [1, 2, 3]
