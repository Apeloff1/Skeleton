from __future__ import annotations

import pytest

from skeleton.ubuntu.operations import (
    UbuntuAction,
    UbuntuPlan,
    merge_plans,
    plan_package_apt,
    validate_package_apt,
    validate_plan,
)


def test_action_is_bounded_and_serializable() -> None:
    action = UbuntuAction("package-apt:curl", ("ubuntu", "package", "apt", "curl", "present"), "install curl")
    assert action.as_dict()["name"] == "package-apt:curl"
    assert action.as_dict()["argv"] == ("ubuntu", "package", "apt", "curl", "present")


def test_empty_argv_is_rejected() -> None:
    with pytest.raises(ValueError, match="argv"):
        UbuntuAction("x", (), "test")


def test_timeout_is_bounded() -> None:
    with pytest.raises(ValueError, match="timeout"):
        UbuntuAction("x", ("ubuntu", "noop"), "test", timeout_seconds=0)
    with pytest.raises(ValueError, match="timeout"):
        UbuntuAction("x", ("ubuntu", "noop"), "test", timeout_seconds=3601)


def test_nul_and_oversized_text_are_rejected() -> None:
    with pytest.raises(ValueError, match="bounded"):
        UbuntuAction("bad\\x00name", ("ubuntu", "noop"), "test")
    with pytest.raises(ValueError, match="bounded"):
        UbuntuAction("x", ("ubuntu", "noop"), "a" * 4097)


def test_package_planning_is_deterministic() -> None:
    first = plan_package_apt(("curl", "git", "python3"))
    second = plan_package_apt(("curl", "git", "python3"))
    assert first.names() == ("package-apt:curl", "package-apt:git", "package-apt:python3")
    assert first == second
    assert validate_plan(first) == ()


def test_package_absent_requires_disabled_state() -> None:
    with pytest.raises(ValueError, match="enabled"):
        validate_package_apt("curl", "absent")
    action = validate_package_apt("curl", "absent", enabled=False)
    assert action.argv[-1] == "absent"


def test_plan_append_and_extend_preserve_immutability() -> None:
    base = UbuntuPlan(metadata={"domain": "test"})
    action = UbuntuAction("a", ("ubuntu", "noop", "a"), "test")
    appended = base.append(action)
    extended = base.extend((action,))
    assert base.actions == ()
    assert appended.actions == (action,)
    assert extended.actions == (action,)
    assert base.metadata == {"domain": "test"}


def test_duplicate_action_names_fail_validation() -> None:
    action = UbuntuAction("same", ("ubuntu", "noop"), "test")
    plan = UbuntuPlan((action, action))
    assert validate_plan(plan) == ("duplicate action: same",)


def test_merge_rejects_duplicate_actions() -> None:
    action = UbuntuAction("same", ("ubuntu", "noop"), "test")
    with pytest.raises(ValueError, match="duplicate action"):
        merge_plans(UbuntuPlan((action,)), UbuntuPlan((action,)))


def test_merge_preserves_order() -> None:
    a = UbuntuAction("a", ("ubuntu", "noop", "a"), "test")
    b = UbuntuAction("b", ("ubuntu", "noop", "b"), "test")
    merged = merge_plans(UbuntuPlan((a,)), UbuntuPlan((b,)))
    assert merged.names() == ("a", "b")


def test_plan_contains_no_shell_command_string() -> None:
    plan = plan_package_apt(("curl",))
    assert plan.actions[0].argv[0] == "ubuntu"
    assert all(isinstance(part, str) for part in plan.actions[0].argv)
    assert "shell=True" not in repr(plan)
