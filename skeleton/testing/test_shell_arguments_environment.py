import pytest

from skeleton.shells.arguments import ArgumentPolicy, ArgumentPolicySet, OptionRule, ValueConstraint
from skeleton.shells.environment import EnvironmentPolicy, EnvironmentValueRule
from skeleton.shells.errors import ArgumentRejected, EnvironmentRejected


def python_policy():
    return ArgumentPolicy(
        options={
            "-m": OptionRule("-m", takes_value=True, value=ValueConstraint(pattern=r"[A-Za-z0-9_.]+")),
            "-q": OptionRule("-q"),
            "--tag": OptionRule("--tag", takes_value=True, repeatable=True, value=ValueConstraint(max_length=20)),
        },
        positional=(ValueConstraint(max_length=32),),
        variadic=ValueConstraint(max_length=64),
        min_positionals=0,
        max_positionals=4,
        deny_tokens=frozenset({"--danger"}),
        deny_patterns=(r"\x1b",),
    )


def test_value_constraint_choices_and_pattern():
    rule = ValueConstraint(pattern=r"[a-z]+", choices=frozenset({"alpha", "beta"}))
    assert rule.accepts("alpha")
    assert not rule.accepts("ALPHA")
    assert not rule.accepts("gamma")


def test_argument_policy_accepts_known_options_and_positionals():
    args = python_policy().validate("python", ("-q", "--tag=a", "--tag", "b", "file.py", "extra"))
    assert args[-2:] == ("file.py", "extra")


def test_argument_policy_rejects_unknown_option():
    with pytest.raises(ArgumentRejected):
        python_policy().validate("python", ("--unknown",))


def test_argument_policy_rejects_missing_option_value():
    with pytest.raises(ArgumentRejected):
        python_policy().validate("python", ("-m",))


def test_argument_policy_rejects_nonrepeatable_option():
    with pytest.raises(ArgumentRejected):
        python_policy().validate("python", ("-q", "-q"))


def test_argument_policy_allows_repeatable_option():
    assert python_policy().validate("python", ("--tag", "a", "--tag", "b"))


def test_argument_policy_rejects_denied_token():
    with pytest.raises(ArgumentRejected):
        python_policy().validate("python", ("--danger",))


def test_argument_policy_rejects_too_many_positionals():
    with pytest.raises(ArgumentRejected):
        python_policy().validate("python", ("a", "b", "c", "d", "e"))


def test_argument_policy_double_dash_switches_to_positionals():
    policy = ArgumentPolicy(options={"-q": OptionRule("-q")}, variadic=ValueConstraint(max_length=64))
    assert policy.validate("cmd", ("--", "-not-an-option")) == ("--", "-not-an-option")


def test_argument_policy_set_default_denies_missing_policy():
    policies = ArgumentPolicySet()
    with pytest.raises(ArgumentRejected):
        policies.validate("python", ())


def test_argument_policy_set_register_and_replace():
    policies = ArgumentPolicySet({"python": ArgumentPolicy.allow_any()})
    with pytest.raises(ValueError):
        policies.register("python", ArgumentPolicy.allow_any())
    policies.register("python", python_policy(), replace=True)
    with pytest.raises(ArgumentRejected):
        policies.validate("python", ("--unknown",))


def env_policy():
    return EnvironmentPolicy(
        rules={
            "LANG": EnvironmentValueRule(pattern=r"[A-Za-z0-9_.-]+", max_bytes=32),
            "MODE": EnvironmentValueRule(choices=frozenset({"test", "prod"}), allow_empty=False),
            "FIXED": EnvironmentValueRule(max_bytes=16),
        },
        inherited=frozenset({"LANG"}),
        required=frozenset({"MODE"}),
        fixed={"FIXED": "yes"},
        max_total_bytes=128,
    )


def test_environment_policy_inherits_only_allowlisted_keys():
    built = env_policy().build("python", {"MODE": "test"}, parent={"LANG": "C.UTF-8", "SECRET": "x"})
    assert built == {"LANG": "C.UTF-8", "MODE": "test", "FIXED": "yes"}
    assert "SECRET" not in built


def test_environment_policy_rejects_unknown_key():
    with pytest.raises(EnvironmentRejected):
        env_policy().build("python", {"MODE": "test", "SECRET": "x"}, parent={})


def test_environment_policy_rejects_invalid_choice():
    with pytest.raises(EnvironmentRejected):
        env_policy().build("python", {"MODE": "debug"}, parent={})


def test_environment_policy_requires_required_keys():
    with pytest.raises(EnvironmentRejected):
        env_policy().build("python", {}, parent={})


def test_environment_policy_rejects_total_byte_overflow():
    policy = EnvironmentPolicy(
        rules={"VALUE": EnvironmentValueRule(max_bytes=100)},
        max_total_bytes=8,
    )
    with pytest.raises(EnvironmentRejected):
        policy.build("x", {"VALUE": "123456789"}, parent={})


def test_environment_policy_definition_validates_inheritance_contract():
    with pytest.raises(ValueError):
        EnvironmentPolicy(rules={}, inherited=frozenset({"PATH"}))
