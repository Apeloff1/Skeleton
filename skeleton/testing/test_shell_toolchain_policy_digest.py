from skeleton.shells.arguments import ArgumentPolicy, OptionRule, ValueConstraint
from skeleton.shells.environment import EnvironmentPolicy, EnvironmentValueRule
from skeleton.shells.toolchains.catalog import ToolchainCatalog
from skeleton.shells.toolchains.types import LogicalCommandContract


def _contract(
    *,
    arguments: ArgumentPolicy,
    environment: EnvironmentPolicy | None = None,
) -> LogicalCommandContract:
    return LogicalCommandContract(
        name="python-test",
        executable_key="python",
        arguments=arguments,
        environment=environment or EnvironmentPolicy.empty(),
    )


def test_catalog_digest_changes_when_argument_policy_changes() -> None:
    strict = _contract(
        arguments=ArgumentPolicy(
            positional=(ValueConstraint(choices=frozenset({"-m"})),),
            min_positionals=1,
            max_positionals=1,
        )
    )
    permissive = _contract(
        arguments=ArgumentPolicy(
            variadic=ValueConstraint(max_length=1024),
            min_positionals=0,
            max_positionals=None,
        )
    )

    assert (
        ToolchainCatalog((strict,)).snapshot().digest
        != ToolchainCatalog((permissive,)).snapshot().digest
    )


def test_catalog_digest_changes_when_option_value_policy_changes() -> None:
    short = _contract(
        arguments=ArgumentPolicy(
            options={
                "--target": OptionRule(
                    "--target",
                    takes_value=True,
                    value=ValueConstraint(max_length=16),
                )
            }
        )
    )
    long = _contract(
        arguments=ArgumentPolicy(
            options={
                "--target": OptionRule(
                    "--target",
                    takes_value=True,
                    value=ValueConstraint(max_length=64),
                )
            }
        )
    )

    assert (
        ToolchainCatalog((short,)).snapshot().digest
        != ToolchainCatalog((long,)).snapshot().digest
    )


def test_catalog_digest_changes_when_environment_policy_changes() -> None:
    inherited = _contract(
        arguments=ArgumentPolicy(),
        environment=EnvironmentPolicy(
            rules={"HOME": EnvironmentValueRule(max_bytes=4096)},
            inherited=frozenset({"HOME"}),
        ),
    )
    requested_only = _contract(
        arguments=ArgumentPolicy(),
        environment=EnvironmentPolicy(
            rules={"HOME": EnvironmentValueRule(max_bytes=4096)},
        ),
    )

    assert (
        ToolchainCatalog((inherited,)).snapshot().digest
        != ToolchainCatalog((requested_only,)).snapshot().digest
    )


def test_catalog_digest_is_stable_across_mapping_insertion_order() -> None:
    left = _contract(
        arguments=ArgumentPolicy(
            options={
                "--alpha": OptionRule("--alpha"),
                "--beta": OptionRule("--beta"),
            }
        ),
        environment=EnvironmentPolicy(
            rules={
                "HOME": EnvironmentValueRule(max_bytes=4096),
                "LANG": EnvironmentValueRule(max_bytes=128),
            }
        ),
    )
    right = _contract(
        arguments=ArgumentPolicy(
            options={
                "--beta": OptionRule("--beta"),
                "--alpha": OptionRule("--alpha"),
            }
        ),
        environment=EnvironmentPolicy(
            rules={
                "LANG": EnvironmentValueRule(max_bytes=128),
                "HOME": EnvironmentValueRule(max_bytes=4096),
            }
        ),
    )

    assert (
        ToolchainCatalog((left,)).snapshot().digest
        == ToolchainCatalog((right,)).snapshot().digest
    )


def test_contract_rejects_non_finite_and_boolean_timeouts() -> None:
    for value in (True, float("inf"), float("-inf"), float("nan"), 0.0, -1.0):
        try:
            _contract(
                arguments=ArgumentPolicy(),
            ).__class__(
                name="python-test",
                executable_key="python",
                arguments=ArgumentPolicy(),
                max_timeout=value,
            )
        except ValueError:
            continue
        raise AssertionError(f"expected max_timeout={value!r} to be rejected")


def test_contract_normalizes_string_enum_values() -> None:
    contract = LogicalCommandContract(
        name="python-test",
        executable_key="python",
        arguments=ArgumentPolicy(),
        required_capabilities=frozenset({"execute"}),
        effects=frozenset({"test"}),
        risk="moderate",
    )

    assert sorted(capability.value for capability in contract.required_capabilities) == [
        "execute"
    ]
    assert sorted(effect.value for effect in contract.effects) == ["test"]
    assert contract.risk.value == "moderate"
