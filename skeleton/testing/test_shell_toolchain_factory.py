import pytest

from skeleton.shells.errors import ArgumentRejected
from skeleton.shells.toolchains.factory import OperationSpec, OptionSpec, build_contract
from skeleton.shells.toolchains.types import CommandEffect


def test_dash_prefixed_literal_subcommand_is_admitted() -> None:
    contract = build_contract(
        OperationSpec(
            logical_name="tool.version",
            executable_key="tool",
            subcommand="--version",
        )
    )

    assert contract.arguments.validate(
        contract.name,
        ("--version",),
    ) == ("--version",)


def test_fixed_dash_prefix_can_precede_normal_options_and_paths() -> None:
    contract = build_contract(
        OperationSpec(
            logical_name="py.compileall",
            executable_key="python",
            fixed_prefix=("-m", "compileall"),
            options=(OptionSpec("-q"),),
            variadic="path",
            min_positionals=2,
            max_positionals=None,
            effects=frozenset({CommandEffect.BUILD}),
        )
    )

    assert contract.arguments.validate(
        contract.name,
        ("-m", "compileall", "-q", "skeleton"),
    ) == ("-m", "compileall", "-q", "skeleton")


def test_unknown_dash_token_is_not_reclassified_as_positional_data() -> None:
    contract = build_contract(
        OperationSpec(
            logical_name="tool.read",
            executable_key="tool",
            positionals=("safe",),
            min_positionals=1,
            max_positionals=1,
        )
    )

    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(
            contract.name,
            ("--not-authorized",),
        )


def test_literal_prefix_must_match_exact_allowlisted_token() -> None:
    contract = build_contract(
        OperationSpec(
            logical_name="py.module",
            executable_key="python",
            fixed_prefix=("-m",),
            positionals=("module",),
            min_positionals=2,
            max_positionals=2,
        )
    )

    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(
            contract.name,
            ("--module", "package"),
        )
