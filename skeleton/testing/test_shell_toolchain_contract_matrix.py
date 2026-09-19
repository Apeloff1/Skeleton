"""Exhaustive regression matrix for built-in logical toolchain contracts."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.capabilities import ShellCapability
from skeleton.shells.errors import ArgumentRejected
from skeleton.shells.toolchains import build, container, dotnet, git, go, jvm, node, posix, python, rust
from skeleton.shells.toolchains.all import ALL_CONTRACTS, DEFAULT_CATALOG, executable_keys
from skeleton.shells.toolchains.catalog import ToolchainBindingError
from skeleton.shells.toolchains.factory import OperationSpec, build_contract, constraint
from skeleton.shells.toolchains.profiles import PROFILES
from skeleton.shells.toolchains.recipes import DEFAULT_RECIPES
from skeleton.shells.toolchains.types import CommandEffect, CommandRisk


_MODULES = (git, python, node, rust, go, jvm, dotnet, build, container, posix)
_BY_NAME = {contract.name: contract for contract in ALL_CONTRACTS}
_SPECS = {
    spec.logical_name: spec
    for module in _MODULES
    for spec in module.SPECS
}

_SAMPLES = {
    "safe": "value",
    "short": "value",
    "identifier": "value",
    "path": "src/example.txt",
    "module": "package.module",
    "package": "example-package",
    "test": "tests/test_example.py",
    "git_ref": "main",
    "sha": "0123456789abcdef",
    "integer": "1",
    "https": "https://example.invalid/resource",
}


def _sample(kind: str) -> str:
    if kind.startswith("literal:"):
        return kind.removeprefix("literal:")
    return _SAMPLES[kind]


def _minimal_argv(spec: OperationSpec) -> tuple[str, ...]:
    values: list[str] = []
    if spec.subcommand is not None:
        values.append(spec.subcommand)
    values.extend(spec.fixed_prefix)
    values.extend(_sample(kind) for kind in spec.positionals)
    if spec.variadic is not None:
        values.append(_sample(spec.variadic))
    return tuple(values)


def _assert_contract(name: str) -> None:
    contract = _BY_NAME[name]
    spec = _SPECS[name]
    argv = _minimal_argv(spec)
    assert contract.name == name
    assert contract.executable_key == spec.executable_key
    assert ShellCapability.EXECUTE in contract.required_capabilities
    assert contract.description
    assert contract.max_timeout is None or contract.max_timeout > 0
    assert contract.risk in {CommandRisk.LOW, CommandRisk.MODERATE, CommandRisk.HIGH}
    assert contract.effects
    assert all(isinstance(effect, CommandEffect) for effect in contract.effects)
    assert contract.arguments.max_total_args == 256
    assert contract.arguments.max_total_bytes == 131_072
    payload = contract.to_dict()
    assert "path" not in payload
    assert payload["name"] == name
    assert payload["executable_key"] == spec.executable_key
    assert contract.arguments.validate(name, argv) == argv
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(name, ("--definitely-unknown-shell-option",))
    required_prefix = getattr(contract.arguments, "required_prefix", ())
    if required_prefix:
        with pytest.raises(ArgumentRejected, match="required logical command prefix"):
            contract.arguments.validate(name, argv[len(required_prefix):])


def _assert_recipe(name: str) -> None:
    recipe = DEFAULT_RECIPES.get(name)
    assert recipe.name == name
    assert recipe.steps
    for step in recipe.steps:
        contract = DEFAULT_CATALOG.get(step.contract)
        assert contract.name == step.contract
        assert isinstance(step.required, bool)
        assert isinstance(step.stop_on_failure, bool)


def test_builtin_contract_names_are_unique() -> None:
    names = [contract.name for contract in ALL_CONTRACTS]
    assert len(names) == len(set(names))


def test_specs_and_contracts_have_one_to_one_identity() -> None:
    assert set(_SPECS) == set(_BY_NAME)


def test_default_catalog_contains_every_contract() -> None:
    assert DEFAULT_CATALOG.names() == tuple(sorted(_BY_NAME))


def test_executable_key_index_is_nonempty() -> None:
    keys = executable_keys()
    assert keys
    assert keys == tuple(sorted(set(keys)))


def test_every_profile_selects_known_contracts() -> None:
    for profile in PROFILES.values():
        selected = profile.select()
        assert all(contract.name in _BY_NAME for contract in selected)


def test_read_only_profile_excludes_write_effect() -> None:
    selected = PROFILES["read-only"].select()
    assert selected
    assert all(CommandEffect.WRITE not in contract.effects for contract in selected)


def test_source_control_write_profile_is_git_scoped() -> None:
    selected = PROFILES["source-control-write"].select()
    assert selected
    assert all("git" in contract.tags for contract in selected)
    assert all(CommandEffect.WRITE in contract.effects for contract in selected)


def test_catalog_binding_fails_closed_when_paths_missing() -> None:
    with pytest.raises(ToolchainBindingError):
        DEFAULT_CATALOG.bind({}, names=("git.status",), require_all=True)


def test_catalog_partial_binding_can_intentionally_skip_missing_tools() -> None:
    bound = DEFAULT_CATALOG.bind({}, names=("git.status",), require_all=False)
    assert bound.definitions == ()


def test_single_contract_can_bind_to_explicit_absolute_file() -> None:
    contract = DEFAULT_CATALOG.get("py.python_version")
    bound = DEFAULT_CATALOG.bind(
        {contract.executable_key: sys.executable},
        names=(contract.name,),
        require_all=True,
    )
    assert bound.names() == (contract.name,)
    assert bound.definitions[0].spec.path


def test_constraint_lookup_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown toolchain constraint"):
        constraint("definitely-not-a-real-constraint")


def test_literal_constraint_is_exact() -> None:
    value = constraint("literal:package")
    assert value.accepts("package")
    assert not value.accepts("remove")
    assert not value.accepts("package-extra")


def test_operation_spec_rejects_unknown_positional_constraint() -> None:
    with pytest.raises(ValueError):
        OperationSpec(
            logical_name="test.invalid",
            executable_key="python",
            positionals=("missing-constraint",),
        )


def test_build_contract_adds_stdin_capability() -> None:
    spec = OperationSpec(
        logical_name="test.stdin",
        executable_key="python",
        allow_stdin=True,
    )
    contract = build_contract(spec)
    assert ShellCapability.STDIN in contract.required_capabilities


def test_build_contract_adds_custom_environment_capability() -> None:
    spec = OperationSpec(
        logical_name="test.env",
        executable_key="python",
        env_keys=("SAFE_VALUE",),
    )
    contract = build_contract(spec)
    assert ShellCapability.CUSTOM_ENV in contract.required_capabilities


def test_build_contract_adds_nonzero_success_capability() -> None:
    spec = OperationSpec(
        logical_name="test.nonzero",
        executable_key="python",
        allow_nonzero_success=True,
    )
    contract = build_contract(spec)
    assert ShellCapability.NONZERO_SUCCESS in contract.required_capabilities


def test_prefix_bound_contract_rejects_missing_prefix() -> None:
    spec = OperationSpec(
        logical_name="test.prefix",
        executable_key="python",
        fixed_prefix=("-m", "compileall"),
        variadic="path",
    )
    contract = build_contract(spec)
    assert contract.arguments.validate("test.prefix", ("-m", "compileall", "src"))
    with pytest.raises(ArgumentRejected, match="required logical command prefix"):
        contract.arguments.validate("test.prefix", ("src",))



def test_contract_git_version() -> None:
    """Validate the built-in git.version logical authority contract."""
    _assert_contract("git.version")
    contract = _BY_NAME["git.version"]
    spec = _SPECS["git.version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_status() -> None:
    """Validate the built-in git.status logical authority contract."""
    _assert_contract("git.status")
    contract = _BY_NAME["git.status"]
    spec = _SPECS["git.status"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_diff() -> None:
    """Validate the built-in git.diff logical authority contract."""
    _assert_contract("git.diff")
    contract = _BY_NAME["git.diff"]
    spec = _SPECS["git.diff"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_diff_word() -> None:
    """Validate the built-in git.diff_word logical authority contract."""
    _assert_contract("git.diff_word")
    contract = _BY_NAME["git.diff_word"]
    spec = _SPECS["git.diff_word"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_show() -> None:
    """Validate the built-in git.show logical authority contract."""
    _assert_contract("git.show")
    contract = _BY_NAME["git.show"]
    spec = _SPECS["git.show"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_log() -> None:
    """Validate the built-in git.log logical authority contract."""
    _assert_contract("git.log")
    contract = _BY_NAME["git.log"]
    spec = _SPECS["git.log"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_log_paths() -> None:
    """Validate the built-in git.log_paths logical authority contract."""
    _assert_contract("git.log_paths")
    contract = _BY_NAME["git.log_paths"]
    spec = _SPECS["git.log_paths"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_rev_parse() -> None:
    """Validate the built-in git.rev_parse logical authority contract."""
    _assert_contract("git.rev_parse")
    contract = _BY_NAME["git.rev_parse"]
    spec = _SPECS["git.rev_parse"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_rev_list() -> None:
    """Validate the built-in git.rev_list logical authority contract."""
    _assert_contract("git.rev_list")
    contract = _BY_NAME["git.rev_list"]
    spec = _SPECS["git.rev_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_ls_files() -> None:
    """Validate the built-in git.ls_files logical authority contract."""
    _assert_contract("git.ls_files")
    contract = _BY_NAME["git.ls_files"]
    spec = _SPECS["git.ls_files"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_ls_tree() -> None:
    """Validate the built-in git.ls_tree logical authority contract."""
    _assert_contract("git.ls_tree")
    contract = _BY_NAME["git.ls_tree"]
    spec = _SPECS["git.ls_tree"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_grep() -> None:
    """Validate the built-in git.grep logical authority contract."""
    _assert_contract("git.grep")
    contract = _BY_NAME["git.grep"]
    spec = _SPECS["git.grep"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_branch_list() -> None:
    """Validate the built-in git.branch_list logical authority contract."""
    _assert_contract("git.branch_list")
    contract = _BY_NAME["git.branch_list"]
    spec = _SPECS["git.branch_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_tag_list() -> None:
    """Validate the built-in git.tag_list logical authority contract."""
    _assert_contract("git.tag_list")
    contract = _BY_NAME["git.tag_list"]
    spec = _SPECS["git.tag_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_remote_list() -> None:
    """Validate the built-in git.remote_list logical authority contract."""
    _assert_contract("git.remote_list")
    contract = _BY_NAME["git.remote_list"]
    spec = _SPECS["git.remote_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_remote_get_url() -> None:
    """Validate the built-in git.remote_get_url logical authority contract."""
    _assert_contract("git.remote_get_url")
    contract = _BY_NAME["git.remote_get_url"]
    spec = _SPECS["git.remote_get_url"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_cat_file_type() -> None:
    """Validate the built-in git.cat_file_type logical authority contract."""
    _assert_contract("git.cat_file_type")
    contract = _BY_NAME["git.cat_file_type"]
    spec = _SPECS["git.cat_file_type"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_cat_file_size() -> None:
    """Validate the built-in git.cat_file_size logical authority contract."""
    _assert_contract("git.cat_file_size")
    contract = _BY_NAME["git.cat_file_size"]
    spec = _SPECS["git.cat_file_size"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_cat_file_pretty() -> None:
    """Validate the built-in git.cat_file_pretty logical authority contract."""
    _assert_contract("git.cat_file_pretty")
    contract = _BY_NAME["git.cat_file_pretty"]
    spec = _SPECS["git.cat_file_pretty"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_check_ignore() -> None:
    """Validate the built-in git.check_ignore logical authority contract."""
    _assert_contract("git.check_ignore")
    contract = _BY_NAME["git.check_ignore"]
    spec = _SPECS["git.check_ignore"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_check_attr() -> None:
    """Validate the built-in git.check_attr logical authority contract."""
    _assert_contract("git.check_attr")
    contract = _BY_NAME["git.check_attr"]
    spec = _SPECS["git.check_attr"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_describe() -> None:
    """Validate the built-in git.describe logical authority contract."""
    _assert_contract("git.describe")
    contract = _BY_NAME["git.describe"]
    spec = _SPECS["git.describe"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_merge_base() -> None:
    """Validate the built-in git.merge_base logical authority contract."""
    _assert_contract("git.merge_base")
    contract = _BY_NAME["git.merge_base"]
    spec = _SPECS["git.merge_base"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_name_rev() -> None:
    """Validate the built-in git.name_rev logical authority contract."""
    _assert_contract("git.name_rev")
    contract = _BY_NAME["git.name_rev"]
    spec = _SPECS["git.name_rev"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_add() -> None:
    """Validate the built-in git.add logical authority contract."""
    _assert_contract("git.add")
    contract = _BY_NAME["git.add"]
    spec = _SPECS["git.add"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_restore() -> None:
    """Validate the built-in git.restore logical authority contract."""
    _assert_contract("git.restore")
    contract = _BY_NAME["git.restore"]
    spec = _SPECS["git.restore"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_switch() -> None:
    """Validate the built-in git.switch logical authority contract."""
    _assert_contract("git.switch")
    contract = _BY_NAME["git.switch"]
    spec = _SPECS["git.switch"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_branch_create() -> None:
    """Validate the built-in git.branch_create logical authority contract."""
    _assert_contract("git.branch_create")
    contract = _BY_NAME["git.branch_create"]
    spec = _SPECS["git.branch_create"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_branch_delete() -> None:
    """Validate the built-in git.branch_delete logical authority contract."""
    _assert_contract("git.branch_delete")
    contract = _BY_NAME["git.branch_delete"]
    spec = _SPECS["git.branch_delete"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_tag_create() -> None:
    """Validate the built-in git.tag_create logical authority contract."""
    _assert_contract("git.tag_create")
    contract = _BY_NAME["git.tag_create"]
    spec = _SPECS["git.tag_create"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_tag_delete() -> None:
    """Validate the built-in git.tag_delete logical authority contract."""
    _assert_contract("git.tag_delete")
    contract = _BY_NAME["git.tag_delete"]
    spec = _SPECS["git.tag_delete"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_commit() -> None:
    """Validate the built-in git.commit logical authority contract."""
    _assert_contract("git.commit")
    contract = _BY_NAME["git.commit"]
    spec = _SPECS["git.commit"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_merge() -> None:
    """Validate the built-in git.merge logical authority contract."""
    _assert_contract("git.merge")
    contract = _BY_NAME["git.merge"]
    spec = _SPECS["git.merge"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_rebase() -> None:
    """Validate the built-in git.rebase logical authority contract."""
    _assert_contract("git.rebase")
    contract = _BY_NAME["git.rebase"]
    spec = _SPECS["git.rebase"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_cherry_pick() -> None:
    """Validate the built-in git.cherry_pick logical authority contract."""
    _assert_contract("git.cherry_pick")
    contract = _BY_NAME["git.cherry_pick"]
    spec = _SPECS["git.cherry_pick"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_revert() -> None:
    """Validate the built-in git.revert logical authority contract."""
    _assert_contract("git.revert")
    contract = _BY_NAME["git.revert"]
    spec = _SPECS["git.revert"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_fetch() -> None:
    """Validate the built-in git.fetch logical authority contract."""
    _assert_contract("git.fetch")
    contract = _BY_NAME["git.fetch"]
    spec = _SPECS["git.fetch"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_pull_ff_only() -> None:
    """Validate the built-in git.pull_ff_only logical authority contract."""
    _assert_contract("git.pull_ff_only")
    contract = _BY_NAME["git.pull_ff_only"]
    spec = _SPECS["git.pull_ff_only"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_push() -> None:
    """Validate the built-in git.push logical authority contract."""
    _assert_contract("git.push")
    contract = _BY_NAME["git.push"]
    spec = _SPECS["git.push"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_clean_dry_run() -> None:
    """Validate the built-in git.clean_dry_run logical authority contract."""
    _assert_contract("git.clean_dry_run")
    contract = _BY_NAME["git.clean_dry_run"]
    spec = _SPECS["git.clean_dry_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_clean() -> None:
    """Validate the built-in git.clean logical authority contract."""
    _assert_contract("git.clean")
    contract = _BY_NAME["git.clean"]
    spec = _SPECS["git.clean"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_worktree_list() -> None:
    """Validate the built-in git.worktree_list logical authority contract."""
    _assert_contract("git.worktree_list")
    contract = _BY_NAME["git.worktree_list"]
    spec = _SPECS["git.worktree_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_worktree_add() -> None:
    """Validate the built-in git.worktree_add logical authority contract."""
    _assert_contract("git.worktree_add")
    contract = _BY_NAME["git.worktree_add"]
    spec = _SPECS["git.worktree_add"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_worktree_remove() -> None:
    """Validate the built-in git.worktree_remove logical authority contract."""
    _assert_contract("git.worktree_remove")
    contract = _BY_NAME["git.worktree_remove"]
    spec = _SPECS["git.worktree_remove"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_submodule_status() -> None:
    """Validate the built-in git.submodule_status logical authority contract."""
    _assert_contract("git.submodule_status")
    contract = _BY_NAME["git.submodule_status"]
    spec = _SPECS["git.submodule_status"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_submodule_update() -> None:
    """Validate the built-in git.submodule_update logical authority contract."""
    _assert_contract("git.submodule_update")
    contract = _BY_NAME["git.submodule_update"]
    spec = _SPECS["git.submodule_update"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_stash_list() -> None:
    """Validate the built-in git.stash_list logical authority contract."""
    _assert_contract("git.stash_list")
    contract = _BY_NAME["git.stash_list"]
    spec = _SPECS["git.stash_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_stash_show() -> None:
    """Validate the built-in git.stash_show logical authority contract."""
    _assert_contract("git.stash_show")
    contract = _BY_NAME["git.stash_show"]
    spec = _SPECS["git.stash_show"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_stash_push() -> None:
    """Validate the built-in git.stash_push logical authority contract."""
    _assert_contract("git.stash_push")
    contract = _BY_NAME["git.stash_push"]
    spec = _SPECS["git.stash_push"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_git_stash_pop() -> None:
    """Validate the built-in git.stash_pop logical authority contract."""
    _assert_contract("git.stash_pop")
    contract = _BY_NAME["git.stash_pop"]
    spec = _SPECS["git.stash_pop"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_python_version() -> None:
    """Validate the built-in py.python_version logical authority contract."""
    _assert_contract("py.python_version")
    contract = _BY_NAME["py.python_version"]
    spec = _SPECS["py.python_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_compileall() -> None:
    """Validate the built-in py.compileall logical authority contract."""
    _assert_contract("py.compileall")
    contract = _BY_NAME["py.compileall"]
    spec = _SPECS["py.compileall"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_py_compile() -> None:
    """Validate the built-in py.py_compile logical authority contract."""
    _assert_contract("py.py_compile")
    contract = _BY_NAME["py.py_compile"]
    spec = _SPECS["py.py_compile"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_module() -> None:
    """Validate the built-in py.module logical authority contract."""
    _assert_contract("py.module")
    contract = _BY_NAME["py.module"]
    spec = _SPECS["py.module"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_pytest() -> None:
    """Validate the built-in py.pytest logical authority contract."""
    _assert_contract("py.pytest")
    contract = _BY_NAME["py.pytest"]
    spec = _SPECS["py.pytest"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_pytest_collect() -> None:
    """Validate the built-in py.pytest_collect logical authority contract."""
    _assert_contract("py.pytest_collect")
    contract = _BY_NAME["py.pytest_collect"]
    spec = _SPECS["py.pytest_collect"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_ruff_check() -> None:
    """Validate the built-in py.ruff_check logical authority contract."""
    _assert_contract("py.ruff_check")
    contract = _BY_NAME["py.ruff_check"]
    spec = _SPECS["py.ruff_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_ruff_format_check() -> None:
    """Validate the built-in py.ruff_format_check logical authority contract."""
    _assert_contract("py.ruff_format_check")
    contract = _BY_NAME["py.ruff_format_check"]
    spec = _SPECS["py.ruff_format_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_ruff_format() -> None:
    """Validate the built-in py.ruff_format logical authority contract."""
    _assert_contract("py.ruff_format")
    contract = _BY_NAME["py.ruff_format"]
    spec = _SPECS["py.ruff_format"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_mypy() -> None:
    """Validate the built-in py.mypy logical authority contract."""
    _assert_contract("py.mypy")
    contract = _BY_NAME["py.mypy"]
    spec = _SPECS["py.mypy"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_uv_version() -> None:
    """Validate the built-in py.uv_version logical authority contract."""
    _assert_contract("py.uv_version")
    contract = _BY_NAME["py.uv_version"]
    spec = _SPECS["py.uv_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_uv_lock_check() -> None:
    """Validate the built-in py.uv_lock_check logical authority contract."""
    _assert_contract("py.uv_lock_check")
    contract = _BY_NAME["py.uv_lock_check"]
    spec = _SPECS["py.uv_lock_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_uv_lock() -> None:
    """Validate the built-in py.uv_lock logical authority contract."""
    _assert_contract("py.uv_lock")
    contract = _BY_NAME["py.uv_lock"]
    spec = _SPECS["py.uv_lock"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_uv_sync() -> None:
    """Validate the built-in py.uv_sync logical authority contract."""
    _assert_contract("py.uv_sync")
    contract = _BY_NAME["py.uv_sync"]
    spec = _SPECS["py.uv_sync"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_uv_run() -> None:
    """Validate the built-in py.uv_run logical authority contract."""
    _assert_contract("py.uv_run")
    contract = _BY_NAME["py.uv_run"]
    spec = _SPECS["py.uv_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_uv_pip_list() -> None:
    """Validate the built-in py.uv_pip_list logical authority contract."""
    _assert_contract("py.uv_pip_list")
    contract = _BY_NAME["py.uv_pip_list"]
    spec = _SPECS["py.uv_pip_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_uv_pip_check() -> None:
    """Validate the built-in py.uv_pip_check logical authority contract."""
    _assert_contract("py.uv_pip_check")
    contract = _BY_NAME["py.uv_pip_check"]
    spec = _SPECS["py.uv_pip_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_uv_pip_install() -> None:
    """Validate the built-in py.uv_pip_install logical authority contract."""
    _assert_contract("py.uv_pip_install")
    contract = _BY_NAME["py.uv_pip_install"]
    spec = _SPECS["py.uv_pip_install"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_uv_pip_compile() -> None:
    """Validate the built-in py.uv_pip_compile logical authority contract."""
    _assert_contract("py.uv_pip_compile")
    contract = _BY_NAME["py.uv_pip_compile"]
    spec = _SPECS["py.uv_pip_compile"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_pip_version() -> None:
    """Validate the built-in py.pip_version logical authority contract."""
    _assert_contract("py.pip_version")
    contract = _BY_NAME["py.pip_version"]
    spec = _SPECS["py.pip_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_pip_list() -> None:
    """Validate the built-in py.pip_list logical authority contract."""
    _assert_contract("py.pip_list")
    contract = _BY_NAME["py.pip_list"]
    spec = _SPECS["py.pip_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_pip_check() -> None:
    """Validate the built-in py.pip_check logical authority contract."""
    _assert_contract("py.pip_check")
    contract = _BY_NAME["py.pip_check"]
    spec = _SPECS["py.pip_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_pip_show() -> None:
    """Validate the built-in py.pip_show logical authority contract."""
    _assert_contract("py.pip_show")
    contract = _BY_NAME["py.pip_show"]
    spec = _SPECS["py.pip_show"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_pip_download() -> None:
    """Validate the built-in py.pip_download logical authority contract."""
    _assert_contract("py.pip_download")
    contract = _BY_NAME["py.pip_download"]
    spec = _SPECS["py.pip_download"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_coverage_run() -> None:
    """Validate the built-in py.coverage_run logical authority contract."""
    _assert_contract("py.coverage_run")
    contract = _BY_NAME["py.coverage_run"]
    spec = _SPECS["py.coverage_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_coverage_report() -> None:
    """Validate the built-in py.coverage_report logical authority contract."""
    _assert_contract("py.coverage_report")
    contract = _BY_NAME["py.coverage_report"]
    spec = _SPECS["py.coverage_report"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_coverage_xml() -> None:
    """Validate the built-in py.coverage_xml logical authority contract."""
    _assert_contract("py.coverage_xml")
    contract = _BY_NAME["py.coverage_xml"]
    spec = _SPECS["py.coverage_xml"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_coverage_json() -> None:
    """Validate the built-in py.coverage_json logical authority contract."""
    _assert_contract("py.coverage_json")
    contract = _BY_NAME["py.coverage_json"]
    spec = _SPECS["py.coverage_json"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_black_check() -> None:
    """Validate the built-in py.black_check logical authority contract."""
    _assert_contract("py.black_check")
    contract = _BY_NAME["py.black_check"]
    spec = _SPECS["py.black_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_black_format() -> None:
    """Validate the built-in py.black_format logical authority contract."""
    _assert_contract("py.black_format")
    contract = _BY_NAME["py.black_format"]
    spec = _SPECS["py.black_format"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_isort_check() -> None:
    """Validate the built-in py.isort_check logical authority contract."""
    _assert_contract("py.isort_check")
    contract = _BY_NAME["py.isort_check"]
    spec = _SPECS["py.isort_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_isort_write() -> None:
    """Validate the built-in py.isort_write logical authority contract."""
    _assert_contract("py.isort_write")
    contract = _BY_NAME["py.isort_write"]
    spec = _SPECS["py.isort_write"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_bandit_scan() -> None:
    """Validate the built-in py.bandit_scan logical authority contract."""
    _assert_contract("py.bandit_scan")
    contract = _BY_NAME["py.bandit_scan"]
    spec = _SPECS["py.bandit_scan"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_pip_audit() -> None:
    """Validate the built-in py.pip_audit logical authority contract."""
    _assert_contract("py.pip_audit")
    contract = _BY_NAME["py.pip_audit"]
    spec = _SPECS["py.pip_audit"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_tox_run() -> None:
    """Validate the built-in py.tox_run logical authority contract."""
    _assert_contract("py.tox_run")
    contract = _BY_NAME["py.tox_run"]
    spec = _SPECS["py.tox_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_nox_run() -> None:
    """Validate the built-in py.nox_run logical authority contract."""
    _assert_contract("py.nox_run")
    contract = _BY_NAME["py.nox_run"]
    spec = _SPECS["py.nox_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_poetry_check() -> None:
    """Validate the built-in py.poetry_check logical authority contract."""
    _assert_contract("py.poetry_check")
    contract = _BY_NAME["py.poetry_check"]
    spec = _SPECS["py.poetry_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_poetry_lock() -> None:
    """Validate the built-in py.poetry_lock logical authority contract."""
    _assert_contract("py.poetry_lock")
    contract = _BY_NAME["py.poetry_lock"]
    spec = _SPECS["py.poetry_lock"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_poetry_install() -> None:
    """Validate the built-in py.poetry_install logical authority contract."""
    _assert_contract("py.poetry_install")
    contract = _BY_NAME["py.poetry_install"]
    spec = _SPECS["py.poetry_install"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_poetry_run() -> None:
    """Validate the built-in py.poetry_run logical authority contract."""
    _assert_contract("py.poetry_run")
    contract = _BY_NAME["py.poetry_run"]
    spec = _SPECS["py.poetry_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_wheel_build() -> None:
    """Validate the built-in py.wheel_build logical authority contract."""
    _assert_contract("py.wheel_build")
    contract = _BY_NAME["py.wheel_build"]
    spec = _SPECS["py.wheel_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_twine_check() -> None:
    """Validate the built-in py.twine_check logical authority contract."""
    _assert_contract("py.twine_check")
    contract = _BY_NAME["py.twine_check"]
    spec = _SPECS["py.twine_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_py_sphinx_build() -> None:
    """Validate the built-in py.sphinx_build logical authority contract."""
    _assert_contract("py.sphinx_build")
    contract = _BY_NAME["py.sphinx_build"]
    spec = _SPECS["py.sphinx_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_node_version() -> None:
    """Validate the built-in node.node_version logical authority contract."""
    _assert_contract("node.node_version")
    contract = _BY_NAME["node.node_version"]
    spec = _SPECS["node.node_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_node_check() -> None:
    """Validate the built-in node.node_check logical authority contract."""
    _assert_contract("node.node_check")
    contract = _BY_NAME["node.node_check"]
    spec = _SPECS["node.node_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_version() -> None:
    """Validate the built-in node.npm_version logical authority contract."""
    _assert_contract("node.npm_version")
    contract = _BY_NAME["node.npm_version"]
    spec = _SPECS["node.npm_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_ci() -> None:
    """Validate the built-in node.npm_ci logical authority contract."""
    _assert_contract("node.npm_ci")
    contract = _BY_NAME["node.npm_ci"]
    spec = _SPECS["node.npm_ci"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_install() -> None:
    """Validate the built-in node.npm_install logical authority contract."""
    _assert_contract("node.npm_install")
    contract = _BY_NAME["node.npm_install"]
    spec = _SPECS["node.npm_install"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_test() -> None:
    """Validate the built-in node.npm_test logical authority contract."""
    _assert_contract("node.npm_test")
    contract = _BY_NAME["node.npm_test"]
    spec = _SPECS["node.npm_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_run() -> None:
    """Validate the built-in node.npm_run logical authority contract."""
    _assert_contract("node.npm_run")
    contract = _BY_NAME["node.npm_run"]
    spec = _SPECS["node.npm_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_exec() -> None:
    """Validate the built-in node.npm_exec logical authority contract."""
    _assert_contract("node.npm_exec")
    contract = _BY_NAME["node.npm_exec"]
    spec = _SPECS["node.npm_exec"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_pack() -> None:
    """Validate the built-in node.npm_pack logical authority contract."""
    _assert_contract("node.npm_pack")
    contract = _BY_NAME["node.npm_pack"]
    spec = _SPECS["node.npm_pack"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_audit() -> None:
    """Validate the built-in node.npm_audit logical authority contract."""
    _assert_contract("node.npm_audit")
    contract = _BY_NAME["node.npm_audit"]
    spec = _SPECS["node.npm_audit"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_outdated() -> None:
    """Validate the built-in node.npm_outdated logical authority contract."""
    _assert_contract("node.npm_outdated")
    contract = _BY_NAME["node.npm_outdated"]
    spec = _SPECS["node.npm_outdated"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_ls() -> None:
    """Validate the built-in node.npm_ls logical authority contract."""
    _assert_contract("node.npm_ls")
    contract = _BY_NAME["node.npm_ls"]
    spec = _SPECS["node.npm_ls"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_view() -> None:
    """Validate the built-in node.npm_view logical authority contract."""
    _assert_contract("node.npm_view")
    contract = _BY_NAME["node.npm_view"]
    spec = _SPECS["node.npm_view"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npm_cache_verify() -> None:
    """Validate the built-in node.npm_cache_verify logical authority contract."""
    _assert_contract("node.npm_cache_verify")
    contract = _BY_NAME["node.npm_cache_verify"]
    spec = _SPECS["node.npm_cache_verify"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_npx_run() -> None:
    """Validate the built-in node.npx_run logical authority contract."""
    _assert_contract("node.npx_run")
    contract = _BY_NAME["node.npx_run"]
    spec = _SPECS["node.npx_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_pnpm_version() -> None:
    """Validate the built-in node.pnpm_version logical authority contract."""
    _assert_contract("node.pnpm_version")
    contract = _BY_NAME["node.pnpm_version"]
    spec = _SPECS["node.pnpm_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_pnpm_install() -> None:
    """Validate the built-in node.pnpm_install logical authority contract."""
    _assert_contract("node.pnpm_install")
    contract = _BY_NAME["node.pnpm_install"]
    spec = _SPECS["node.pnpm_install"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_pnpm_test() -> None:
    """Validate the built-in node.pnpm_test logical authority contract."""
    _assert_contract("node.pnpm_test")
    contract = _BY_NAME["node.pnpm_test"]
    spec = _SPECS["node.pnpm_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_pnpm_run() -> None:
    """Validate the built-in node.pnpm_run logical authority contract."""
    _assert_contract("node.pnpm_run")
    contract = _BY_NAME["node.pnpm_run"]
    spec = _SPECS["node.pnpm_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_yarn_version() -> None:
    """Validate the built-in node.yarn_version logical authority contract."""
    _assert_contract("node.yarn_version")
    contract = _BY_NAME["node.yarn_version"]
    spec = _SPECS["node.yarn_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_yarn_install() -> None:
    """Validate the built-in node.yarn_install logical authority contract."""
    _assert_contract("node.yarn_install")
    contract = _BY_NAME["node.yarn_install"]
    spec = _SPECS["node.yarn_install"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_yarn_test() -> None:
    """Validate the built-in node.yarn_test logical authority contract."""
    _assert_contract("node.yarn_test")
    contract = _BY_NAME["node.yarn_test"]
    spec = _SPECS["node.yarn_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_yarn_run() -> None:
    """Validate the built-in node.yarn_run logical authority contract."""
    _assert_contract("node.yarn_run")
    contract = _BY_NAME["node.yarn_run"]
    spec = _SPECS["node.yarn_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_eslint_check() -> None:
    """Validate the built-in node.eslint_check logical authority contract."""
    _assert_contract("node.eslint_check")
    contract = _BY_NAME["node.eslint_check"]
    spec = _SPECS["node.eslint_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_eslint_fix() -> None:
    """Validate the built-in node.eslint_fix logical authority contract."""
    _assert_contract("node.eslint_fix")
    contract = _BY_NAME["node.eslint_fix"]
    spec = _SPECS["node.eslint_fix"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_prettier_check() -> None:
    """Validate the built-in node.prettier_check logical authority contract."""
    _assert_contract("node.prettier_check")
    contract = _BY_NAME["node.prettier_check"]
    spec = _SPECS["node.prettier_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_prettier_write() -> None:
    """Validate the built-in node.prettier_write logical authority contract."""
    _assert_contract("node.prettier_write")
    contract = _BY_NAME["node.prettier_write"]
    spec = _SPECS["node.prettier_write"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_tsc_check() -> None:
    """Validate the built-in node.tsc_check logical authority contract."""
    _assert_contract("node.tsc_check")
    contract = _BY_NAME["node.tsc_check"]
    spec = _SPECS["node.tsc_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_tsc_build() -> None:
    """Validate the built-in node.tsc_build logical authority contract."""
    _assert_contract("node.tsc_build")
    contract = _BY_NAME["node.tsc_build"]
    spec = _SPECS["node.tsc_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_vitest_run() -> None:
    """Validate the built-in node.vitest_run logical authority contract."""
    _assert_contract("node.vitest_run")
    contract = _BY_NAME["node.vitest_run"]
    spec = _SPECS["node.vitest_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_jest_run() -> None:
    """Validate the built-in node.jest_run logical authority contract."""
    _assert_contract("node.jest_run")
    contract = _BY_NAME["node.jest_run"]
    spec = _SPECS["node.jest_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_webpack_build() -> None:
    """Validate the built-in node.webpack_build logical authority contract."""
    _assert_contract("node.webpack_build")
    contract = _BY_NAME["node.webpack_build"]
    spec = _SPECS["node.webpack_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_vite_build() -> None:
    """Validate the built-in node.vite_build logical authority contract."""
    _assert_contract("node.vite_build")
    contract = _BY_NAME["node.vite_build"]
    spec = _SPECS["node.vite_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_vite_test() -> None:
    """Validate the built-in node.vite_test logical authority contract."""
    _assert_contract("node.vite_test")
    contract = _BY_NAME["node.vite_test"]
    spec = _SPECS["node.vite_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_rollup_build() -> None:
    """Validate the built-in node.rollup_build logical authority contract."""
    _assert_contract("node.rollup_build")
    contract = _BY_NAME["node.rollup_build"]
    spec = _SPECS["node.rollup_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_bun_version() -> None:
    """Validate the built-in node.bun_version logical authority contract."""
    _assert_contract("node.bun_version")
    contract = _BY_NAME["node.bun_version"]
    spec = _SPECS["node.bun_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_bun_test() -> None:
    """Validate the built-in node.bun_test logical authority contract."""
    _assert_contract("node.bun_test")
    contract = _BY_NAME["node.bun_test"]
    spec = _SPECS["node.bun_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_bun_run() -> None:
    """Validate the built-in node.bun_run logical authority contract."""
    _assert_contract("node.bun_run")
    contract = _BY_NAME["node.bun_run"]
    spec = _SPECS["node.bun_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_deno_version() -> None:
    """Validate the built-in node.deno_version logical authority contract."""
    _assert_contract("node.deno_version")
    contract = _BY_NAME["node.deno_version"]
    spec = _SPECS["node.deno_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_deno_check() -> None:
    """Validate the built-in node.deno_check logical authority contract."""
    _assert_contract("node.deno_check")
    contract = _BY_NAME["node.deno_check"]
    spec = _SPECS["node.deno_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_node_deno_test() -> None:
    """Validate the built-in node.deno_test logical authority contract."""
    _assert_contract("node.deno_test")
    contract = _BY_NAME["node.deno_test"]
    spec = _SPECS["node.deno_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_cargo_version() -> None:
    """Validate the built-in rust.cargo_version logical authority contract."""
    _assert_contract("rust.cargo_version")
    contract = _BY_NAME["rust.cargo_version"]
    spec = _SPECS["rust.cargo_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_metadata() -> None:
    """Validate the built-in rust.metadata logical authority contract."""
    _assert_contract("rust.metadata")
    contract = _BY_NAME["rust.metadata"]
    spec = _SPECS["rust.metadata"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_check() -> None:
    """Validate the built-in rust.check logical authority contract."""
    _assert_contract("rust.check")
    contract = _BY_NAME["rust.check"]
    spec = _SPECS["rust.check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_build() -> None:
    """Validate the built-in rust.build logical authority contract."""
    _assert_contract("rust.build")
    contract = _BY_NAME["rust.build"]
    spec = _SPECS["rust.build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_test() -> None:
    """Validate the built-in rust.test logical authority contract."""
    _assert_contract("rust.test")
    contract = _BY_NAME["rust.test"]
    spec = _SPECS["rust.test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_clippy() -> None:
    """Validate the built-in rust.clippy logical authority contract."""
    _assert_contract("rust.clippy")
    contract = _BY_NAME["rust.clippy"]
    spec = _SPECS["rust.clippy"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_fmt_check() -> None:
    """Validate the built-in rust.fmt_check logical authority contract."""
    _assert_contract("rust.fmt_check")
    contract = _BY_NAME["rust.fmt_check"]
    spec = _SPECS["rust.fmt_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_fmt_write() -> None:
    """Validate the built-in rust.fmt_write logical authority contract."""
    _assert_contract("rust.fmt_write")
    contract = _BY_NAME["rust.fmt_write"]
    spec = _SPECS["rust.fmt_write"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_doc() -> None:
    """Validate the built-in rust.doc logical authority contract."""
    _assert_contract("rust.doc")
    contract = _BY_NAME["rust.doc"]
    spec = _SPECS["rust.doc"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_tree() -> None:
    """Validate the built-in rust.tree logical authority contract."""
    _assert_contract("rust.tree")
    contract = _BY_NAME["rust.tree"]
    spec = _SPECS["rust.tree"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_locate_project() -> None:
    """Validate the built-in rust.locate_project logical authority contract."""
    _assert_contract("rust.locate_project")
    contract = _BY_NAME["rust.locate_project"]
    spec = _SPECS["rust.locate_project"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_package_list() -> None:
    """Validate the built-in rust.package_list logical authority contract."""
    _assert_contract("rust.package_list")
    contract = _BY_NAME["rust.package_list"]
    spec = _SPECS["rust.package_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_package() -> None:
    """Validate the built-in rust.package logical authority contract."""
    _assert_contract("rust.package")
    contract = _BY_NAME["rust.package"]
    spec = _SPECS["rust.package"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_update_dry() -> None:
    """Validate the built-in rust.update_dry logical authority contract."""
    _assert_contract("rust.update_dry")
    contract = _BY_NAME["rust.update_dry"]
    spec = _SPECS["rust.update_dry"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_update() -> None:
    """Validate the built-in rust.update logical authority contract."""
    _assert_contract("rust.update")
    contract = _BY_NAME["rust.update"]
    spec = _SPECS["rust.update"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_fetch() -> None:
    """Validate the built-in rust.fetch logical authority contract."""
    _assert_contract("rust.fetch")
    contract = _BY_NAME["rust.fetch"]
    spec = _SPECS["rust.fetch"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_clean() -> None:
    """Validate the built-in rust.clean logical authority contract."""
    _assert_contract("rust.clean")
    contract = _BY_NAME["rust.clean"]
    spec = _SPECS["rust.clean"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_bench() -> None:
    """Validate the built-in rust.bench logical authority contract."""
    _assert_contract("rust.bench")
    contract = _BY_NAME["rust.bench"]
    spec = _SPECS["rust.bench"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_run() -> None:
    """Validate the built-in rust.run logical authority contract."""
    _assert_contract("rust.run")
    contract = _BY_NAME["rust.run"]
    spec = _SPECS["rust.run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_fix() -> None:
    """Validate the built-in rust.fix logical authority contract."""
    _assert_contract("rust.fix")
    contract = _BY_NAME["rust.fix"]
    spec = _SPECS["rust.fix"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_rustc_version() -> None:
    """Validate the built-in rust.rustc_version logical authority contract."""
    _assert_contract("rust.rustc_version")
    contract = _BY_NAME["rust.rustc_version"]
    spec = _SPECS["rust.rustc_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_rustc_verbose() -> None:
    """Validate the built-in rust.rustc_verbose logical authority contract."""
    _assert_contract("rust.rustc_verbose")
    contract = _BY_NAME["rust.rustc_verbose"]
    spec = _SPECS["rust.rustc_verbose"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_rustfmt_check() -> None:
    """Validate the built-in rust.rustfmt_check logical authority contract."""
    _assert_contract("rust.rustfmt_check")
    contract = _BY_NAME["rust.rustfmt_check"]
    spec = _SPECS["rust.rustfmt_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_rustfmt_write() -> None:
    """Validate the built-in rust.rustfmt_write logical authority contract."""
    _assert_contract("rust.rustfmt_write")
    contract = _BY_NAME["rust.rustfmt_write"]
    spec = _SPECS["rust.rustfmt_write"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_clippy_driver_version() -> None:
    """Validate the built-in rust.clippy_driver_version logical authority contract."""
    _assert_contract("rust.clippy_driver_version")
    contract = _BY_NAME["rust.clippy_driver_version"]
    spec = _SPECS["rust.clippy_driver_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_rustdoc_version() -> None:
    """Validate the built-in rust.rustdoc_version logical authority contract."""
    _assert_contract("rust.rustdoc_version")
    contract = _BY_NAME["rust.rustdoc_version"]
    spec = _SPECS["rust.rustdoc_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_cargo_audit() -> None:
    """Validate the built-in rust.cargo_audit logical authority contract."""
    _assert_contract("rust.cargo_audit")
    contract = _BY_NAME["rust.cargo_audit"]
    spec = _SPECS["rust.cargo_audit"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_cargo_deny_check() -> None:
    """Validate the built-in rust.cargo_deny_check logical authority contract."""
    _assert_contract("rust.cargo_deny_check")
    contract = _BY_NAME["rust.cargo_deny_check"]
    spec = _SPECS["rust.cargo_deny_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_cargo_nextest() -> None:
    """Validate the built-in rust.cargo_nextest logical authority contract."""
    _assert_contract("rust.cargo_nextest")
    contract = _BY_NAME["rust.cargo_nextest"]
    spec = _SPECS["rust.cargo_nextest"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_cargo_expand() -> None:
    """Validate the built-in rust.cargo_expand logical authority contract."""
    _assert_contract("rust.cargo_expand")
    contract = _BY_NAME["rust.cargo_expand"]
    spec = _SPECS["rust.cargo_expand"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_rust_cargo_msrv() -> None:
    """Validate the built-in rust.cargo_msrv logical authority contract."""
    _assert_contract("rust.cargo_msrv")
    contract = _BY_NAME["rust.cargo_msrv"]
    spec = _SPECS["rust.cargo_msrv"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_env() -> None:
    """Validate the built-in go.env logical authority contract."""
    _assert_contract("go.env")
    contract = _BY_NAME["go.env"]
    spec = _SPECS["go.env"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_version() -> None:
    """Validate the built-in go.version logical authority contract."""
    _assert_contract("go.version")
    contract = _BY_NAME["go.version"]
    spec = _SPECS["go.version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_list() -> None:
    """Validate the built-in go.list logical authority contract."""
    _assert_contract("go.list")
    contract = _BY_NAME["go.list"]
    spec = _SPECS["go.list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_mod_download() -> None:
    """Validate the built-in go.mod_download logical authority contract."""
    _assert_contract("go.mod_download")
    contract = _BY_NAME["go.mod_download"]
    spec = _SPECS["go.mod_download"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_mod_tidy() -> None:
    """Validate the built-in go.mod_tidy logical authority contract."""
    _assert_contract("go.mod_tidy")
    contract = _BY_NAME["go.mod_tidy"]
    spec = _SPECS["go.mod_tidy"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_mod_verify() -> None:
    """Validate the built-in go.mod_verify logical authority contract."""
    _assert_contract("go.mod_verify")
    contract = _BY_NAME["go.mod_verify"]
    spec = _SPECS["go.mod_verify"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_mod_graph() -> None:
    """Validate the built-in go.mod_graph logical authority contract."""
    _assert_contract("go.mod_graph")
    contract = _BY_NAME["go.mod_graph"]
    spec = _SPECS["go.mod_graph"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_mod_why() -> None:
    """Validate the built-in go.mod_why logical authority contract."""
    _assert_contract("go.mod_why")
    contract = _BY_NAME["go.mod_why"]
    spec = _SPECS["go.mod_why"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_work_sync() -> None:
    """Validate the built-in go.work_sync logical authority contract."""
    _assert_contract("go.work_sync")
    contract = _BY_NAME["go.work_sync"]
    spec = _SPECS["go.work_sync"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_work_use() -> None:
    """Validate the built-in go.work_use logical authority contract."""
    _assert_contract("go.work_use")
    contract = _BY_NAME["go.work_use"]
    spec = _SPECS["go.work_use"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_fmt() -> None:
    """Validate the built-in go.fmt logical authority contract."""
    _assert_contract("go.fmt")
    contract = _BY_NAME["go.fmt"]
    spec = _SPECS["go.fmt"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_fmt_check() -> None:
    """Validate the built-in go.fmt_check logical authority contract."""
    _assert_contract("go.fmt_check")
    contract = _BY_NAME["go.fmt_check"]
    spec = _SPECS["go.fmt_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_test() -> None:
    """Validate the built-in go.test logical authority contract."""
    _assert_contract("go.test")
    contract = _BY_NAME["go.test"]
    spec = _SPECS["go.test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_test_short() -> None:
    """Validate the built-in go.test_short logical authority contract."""
    _assert_contract("go.test_short")
    contract = _BY_NAME["go.test_short"]
    spec = _SPECS["go.test_short"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_vet() -> None:
    """Validate the built-in go.vet logical authority contract."""
    _assert_contract("go.vet")
    contract = _BY_NAME["go.vet"]
    spec = _SPECS["go.vet"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_build() -> None:
    """Validate the built-in go.build logical authority contract."""
    _assert_contract("go.build")
    contract = _BY_NAME["go.build"]
    spec = _SPECS["go.build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_install() -> None:
    """Validate the built-in go.install logical authority contract."""
    _assert_contract("go.install")
    contract = _BY_NAME["go.install"]
    spec = _SPECS["go.install"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_run() -> None:
    """Validate the built-in go.run logical authority contract."""
    _assert_contract("go.run")
    contract = _BY_NAME["go.run"]
    spec = _SPECS["go.run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_generate() -> None:
    """Validate the built-in go.generate logical authority contract."""
    _assert_contract("go.generate")
    contract = _BY_NAME["go.generate"]
    spec = _SPECS["go.generate"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_clean() -> None:
    """Validate the built-in go.clean logical authority contract."""
    _assert_contract("go.clean")
    contract = _BY_NAME["go.clean"]
    spec = _SPECS["go.clean"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_doc() -> None:
    """Validate the built-in go.doc logical authority contract."""
    _assert_contract("go.doc")
    contract = _BY_NAME["go.doc"]
    spec = _SPECS["go.doc"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_tool_cover() -> None:
    """Validate the built-in go.tool_cover logical authority contract."""
    _assert_contract("go.tool_cover")
    contract = _BY_NAME["go.tool_cover"]
    spec = _SPECS["go.tool_cover"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_tool_pprof() -> None:
    """Validate the built-in go.tool_pprof logical authority contract."""
    _assert_contract("go.tool_pprof")
    contract = _BY_NAME["go.tool_pprof"]
    spec = _SPECS["go.tool_pprof"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_benchstat() -> None:
    """Validate the built-in go.benchstat logical authority contract."""
    _assert_contract("go.benchstat")
    contract = _BY_NAME["go.benchstat"]
    spec = _SPECS["go.benchstat"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_staticcheck() -> None:
    """Validate the built-in go.staticcheck logical authority contract."""
    _assert_contract("go.staticcheck")
    contract = _BY_NAME["go.staticcheck"]
    spec = _SPECS["go.staticcheck"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_go_govulncheck() -> None:
    """Validate the built-in go.govulncheck logical authority contract."""
    _assert_contract("go.govulncheck")
    contract = _BY_NAME["go.govulncheck"]
    spec = _SPECS["go.govulncheck"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_java_version() -> None:
    """Validate the built-in jvm.java_version logical authority contract."""
    _assert_contract("jvm.java_version")
    contract = _BY_NAME["jvm.java_version"]
    spec = _SPECS["jvm.java_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_javac_version() -> None:
    """Validate the built-in jvm.javac_version logical authority contract."""
    _assert_contract("jvm.javac_version")
    contract = _BY_NAME["jvm.javac_version"]
    spec = _SPECS["jvm.javac_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_javac_compile() -> None:
    """Validate the built-in jvm.javac_compile logical authority contract."""
    _assert_contract("jvm.javac_compile")
    contract = _BY_NAME["jvm.javac_compile"]
    spec = _SPECS["jvm.javac_compile"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_jar_list() -> None:
    """Validate the built-in jvm.jar_list logical authority contract."""
    _assert_contract("jvm.jar_list")
    contract = _BY_NAME["jvm.jar_list"]
    spec = _SPECS["jvm.jar_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_jar_create() -> None:
    """Validate the built-in jvm.jar_create logical authority contract."""
    _assert_contract("jvm.jar_create")
    contract = _BY_NAME["jvm.jar_create"]
    spec = _SPECS["jvm.jar_create"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_jar_update() -> None:
    """Validate the built-in jvm.jar_update logical authority contract."""
    _assert_contract("jvm.jar_update")
    contract = _BY_NAME["jvm.jar_update"]
    spec = _SPECS["jvm.jar_update"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_javadoc() -> None:
    """Validate the built-in jvm.javadoc logical authority contract."""
    _assert_contract("jvm.javadoc")
    contract = _BY_NAME["jvm.javadoc"]
    spec = _SPECS["jvm.javadoc"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_mvn_version() -> None:
    """Validate the built-in jvm.mvn_version logical authority contract."""
    _assert_contract("jvm.mvn_version")
    contract = _BY_NAME["jvm.mvn_version"]
    spec = _SPECS["jvm.mvn_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_mvn_validate() -> None:
    """Validate the built-in jvm.mvn_validate logical authority contract."""
    _assert_contract("jvm.mvn_validate")
    contract = _BY_NAME["jvm.mvn_validate"]
    spec = _SPECS["jvm.mvn_validate"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_mvn_test() -> None:
    """Validate the built-in jvm.mvn_test logical authority contract."""
    _assert_contract("jvm.mvn_test")
    contract = _BY_NAME["jvm.mvn_test"]
    spec = _SPECS["jvm.mvn_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_mvn_verify() -> None:
    """Validate the built-in jvm.mvn_verify logical authority contract."""
    _assert_contract("jvm.mvn_verify")
    contract = _BY_NAME["jvm.mvn_verify"]
    spec = _SPECS["jvm.mvn_verify"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_mvn_package() -> None:
    """Validate the built-in jvm.mvn_package logical authority contract."""
    _assert_contract("jvm.mvn_package")
    contract = _BY_NAME["jvm.mvn_package"]
    spec = _SPECS["jvm.mvn_package"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_mvn_dependency_tree() -> None:
    """Validate the built-in jvm.mvn_dependency_tree logical authority contract."""
    _assert_contract("jvm.mvn_dependency_tree")
    contract = _BY_NAME["jvm.mvn_dependency_tree"]
    spec = _SPECS["jvm.mvn_dependency_tree"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_mvn_dependency_analyze() -> None:
    """Validate the built-in jvm.mvn_dependency_analyze logical authority contract."""
    _assert_contract("jvm.mvn_dependency_analyze")
    contract = _BY_NAME["jvm.mvn_dependency_analyze"]
    spec = _SPECS["jvm.mvn_dependency_analyze"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_mvn_clean() -> None:
    """Validate the built-in jvm.mvn_clean logical authority contract."""
    _assert_contract("jvm.mvn_clean")
    contract = _BY_NAME["jvm.mvn_clean"]
    spec = _SPECS["jvm.mvn_clean"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_gradle_version() -> None:
    """Validate the built-in jvm.gradle_version logical authority contract."""
    _assert_contract("jvm.gradle_version")
    contract = _BY_NAME["jvm.gradle_version"]
    spec = _SPECS["jvm.gradle_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_gradle_tasks() -> None:
    """Validate the built-in jvm.gradle_tasks logical authority contract."""
    _assert_contract("jvm.gradle_tasks")
    contract = _BY_NAME["jvm.gradle_tasks"]
    spec = _SPECS["jvm.gradle_tasks"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_gradle_dependencies() -> None:
    """Validate the built-in jvm.gradle_dependencies logical authority contract."""
    _assert_contract("jvm.gradle_dependencies")
    contract = _BY_NAME["jvm.gradle_dependencies"]
    spec = _SPECS["jvm.gradle_dependencies"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_gradle_test() -> None:
    """Validate the built-in jvm.gradle_test logical authority contract."""
    _assert_contract("jvm.gradle_test")
    contract = _BY_NAME["jvm.gradle_test"]
    spec = _SPECS["jvm.gradle_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_gradle_check() -> None:
    """Validate the built-in jvm.gradle_check logical authority contract."""
    _assert_contract("jvm.gradle_check")
    contract = _BY_NAME["jvm.gradle_check"]
    spec = _SPECS["jvm.gradle_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_gradle_build() -> None:
    """Validate the built-in jvm.gradle_build logical authority contract."""
    _assert_contract("jvm.gradle_build")
    contract = _BY_NAME["jvm.gradle_build"]
    spec = _SPECS["jvm.gradle_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_gradle_clean() -> None:
    """Validate the built-in jvm.gradle_clean logical authority contract."""
    _assert_contract("jvm.gradle_clean")
    contract = _BY_NAME["jvm.gradle_clean"]
    spec = _SPECS["jvm.gradle_clean"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_junit_console() -> None:
    """Validate the built-in jvm.junit_console logical authority contract."""
    _assert_contract("jvm.junit_console")
    contract = _BY_NAME["jvm.junit_console"]
    spec = _SPECS["jvm.junit_console"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_checkstyle() -> None:
    """Validate the built-in jvm.checkstyle logical authority contract."""
    _assert_contract("jvm.checkstyle")
    contract = _BY_NAME["jvm.checkstyle"]
    spec = _SPECS["jvm.checkstyle"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_spotbugs() -> None:
    """Validate the built-in jvm.spotbugs logical authority contract."""
    _assert_contract("jvm.spotbugs")
    contract = _BY_NAME["jvm.spotbugs"]
    spec = _SPECS["jvm.spotbugs"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_jdeps() -> None:
    """Validate the built-in jvm.jdeps logical authority contract."""
    _assert_contract("jvm.jdeps")
    contract = _BY_NAME["jvm.jdeps"]
    spec = _SPECS["jvm.jdeps"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_jvm_jlink() -> None:
    """Validate the built-in jvm.jlink logical authority contract."""
    _assert_contract("jvm.jlink")
    contract = _BY_NAME["jvm.jlink"]
    spec = _SPECS["jvm.jlink"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_info() -> None:
    """Validate the built-in dotnet.info logical authority contract."""
    _assert_contract("dotnet.info")
    contract = _BY_NAME["dotnet.info"]
    spec = _SPECS["dotnet.info"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_version() -> None:
    """Validate the built-in dotnet.version logical authority contract."""
    _assert_contract("dotnet.version")
    contract = _BY_NAME["dotnet.version"]
    spec = _SPECS["dotnet.version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_restore() -> None:
    """Validate the built-in dotnet.restore logical authority contract."""
    _assert_contract("dotnet.restore")
    contract = _BY_NAME["dotnet.restore"]
    spec = _SPECS["dotnet.restore"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_build() -> None:
    """Validate the built-in dotnet.build logical authority contract."""
    _assert_contract("dotnet.build")
    contract = _BY_NAME["dotnet.build"]
    spec = _SPECS["dotnet.build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_test() -> None:
    """Validate the built-in dotnet.test logical authority contract."""
    _assert_contract("dotnet.test")
    contract = _BY_NAME["dotnet.test"]
    spec = _SPECS["dotnet.test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_format_check() -> None:
    """Validate the built-in dotnet.format_check logical authority contract."""
    _assert_contract("dotnet.format_check")
    contract = _BY_NAME["dotnet.format_check"]
    spec = _SPECS["dotnet.format_check"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_format_write() -> None:
    """Validate the built-in dotnet.format_write logical authority contract."""
    _assert_contract("dotnet.format_write")
    contract = _BY_NAME["dotnet.format_write"]
    spec = _SPECS["dotnet.format_write"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_pack() -> None:
    """Validate the built-in dotnet.pack logical authority contract."""
    _assert_contract("dotnet.pack")
    contract = _BY_NAME["dotnet.pack"]
    spec = _SPECS["dotnet.pack"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_publish() -> None:
    """Validate the built-in dotnet.publish logical authority contract."""
    _assert_contract("dotnet.publish")
    contract = _BY_NAME["dotnet.publish"]
    spec = _SPECS["dotnet.publish"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_clean() -> None:
    """Validate the built-in dotnet.clean logical authority contract."""
    _assert_contract("dotnet.clean")
    contract = _BY_NAME["dotnet.clean"]
    spec = _SPECS["dotnet.clean"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_list_package() -> None:
    """Validate the built-in dotnet.list_package logical authority contract."""
    _assert_contract("dotnet.list_package")
    contract = _BY_NAME["dotnet.list_package"]
    spec = _SPECS["dotnet.list_package"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_add_package() -> None:
    """Validate the built-in dotnet.add_package logical authority contract."""
    _assert_contract("dotnet.add_package")
    contract = _BY_NAME["dotnet.add_package"]
    spec = _SPECS["dotnet.add_package"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_remove_package() -> None:
    """Validate the built-in dotnet.remove_package logical authority contract."""
    _assert_contract("dotnet.remove_package")
    contract = _BY_NAME["dotnet.remove_package"]
    spec = _SPECS["dotnet.remove_package"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_tool_list() -> None:
    """Validate the built-in dotnet.tool_list logical authority contract."""
    _assert_contract("dotnet.tool_list")
    contract = _BY_NAME["dotnet.tool_list"]
    spec = _SPECS["dotnet.tool_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_tool_restore() -> None:
    """Validate the built-in dotnet.tool_restore logical authority contract."""
    _assert_contract("dotnet.tool_restore")
    contract = _BY_NAME["dotnet.tool_restore"]
    spec = _SPECS["dotnet.tool_restore"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_nuget_list_source() -> None:
    """Validate the built-in dotnet.nuget_list_source logical authority contract."""
    _assert_contract("dotnet.nuget_list_source")
    contract = _BY_NAME["dotnet.nuget_list_source"]
    spec = _SPECS["dotnet.nuget_list_source"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_sln_list() -> None:
    """Validate the built-in dotnet.sln_list logical authority contract."""
    _assert_contract("dotnet.sln_list")
    contract = _BY_NAME["dotnet.sln_list"]
    spec = _SPECS["dotnet.sln_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_sln_add() -> None:
    """Validate the built-in dotnet.sln_add logical authority contract."""
    _assert_contract("dotnet.sln_add")
    contract = _BY_NAME["dotnet.sln_add"]
    spec = _SPECS["dotnet.sln_add"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_sln_remove() -> None:
    """Validate the built-in dotnet.sln_remove logical authority contract."""
    _assert_contract("dotnet.sln_remove")
    contract = _BY_NAME["dotnet.sln_remove"]
    spec = _SPECS["dotnet.sln_remove"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_msbuild() -> None:
    """Validate the built-in dotnet.msbuild logical authority contract."""
    _assert_contract("dotnet.msbuild")
    contract = _BY_NAME["dotnet.msbuild"]
    spec = _SPECS["dotnet.msbuild"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_new_list() -> None:
    """Validate the built-in dotnet.new_list logical authority contract."""
    _assert_contract("dotnet.new_list")
    contract = _BY_NAME["dotnet.new_list"]
    spec = _SPECS["dotnet.new_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_dotnet_new_create() -> None:
    """Validate the built-in dotnet.new_create logical authority contract."""
    _assert_contract("dotnet.new_create")
    contract = _BY_NAME["dotnet.new_create"]
    spec = _SPECS["dotnet.new_create"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_cmake_version() -> None:
    """Validate the built-in build.cmake_version logical authority contract."""
    _assert_contract("build.cmake_version")
    contract = _BY_NAME["build.cmake_version"]
    spec = _SPECS["build.cmake_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_cmake_configure() -> None:
    """Validate the built-in build.cmake_configure logical authority contract."""
    _assert_contract("build.cmake_configure")
    contract = _BY_NAME["build.cmake_configure"]
    spec = _SPECS["build.cmake_configure"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_cmake_build() -> None:
    """Validate the built-in build.cmake_build logical authority contract."""
    _assert_contract("build.cmake_build")
    contract = _BY_NAME["build.cmake_build"]
    spec = _SPECS["build.cmake_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_cmake_install() -> None:
    """Validate the built-in build.cmake_install logical authority contract."""
    _assert_contract("build.cmake_install")
    contract = _BY_NAME["build.cmake_install"]
    spec = _SPECS["build.cmake_install"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_cmake_open() -> None:
    """Validate the built-in build.cmake_open logical authority contract."""
    _assert_contract("build.cmake_open")
    contract = _BY_NAME["build.cmake_open"]
    spec = _SPECS["build.cmake_open"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_ctest() -> None:
    """Validate the built-in build.ctest logical authority contract."""
    _assert_contract("build.ctest")
    contract = _BY_NAME["build.ctest"]
    spec = _SPECS["build.ctest"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_ninja_version() -> None:
    """Validate the built-in build.ninja_version logical authority contract."""
    _assert_contract("build.ninja_version")
    contract = _BY_NAME["build.ninja_version"]
    spec = _SPECS["build.ninja_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_ninja_build() -> None:
    """Validate the built-in build.ninja_build logical authority contract."""
    _assert_contract("build.ninja_build")
    contract = _BY_NAME["build.ninja_build"]
    spec = _SPECS["build.ninja_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_ninja_dry_run() -> None:
    """Validate the built-in build.ninja_dry_run logical authority contract."""
    _assert_contract("build.ninja_dry_run")
    contract = _BY_NAME["build.ninja_dry_run"]
    spec = _SPECS["build.ninja_dry_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_ninja_clean() -> None:
    """Validate the built-in build.ninja_clean logical authority contract."""
    _assert_contract("build.ninja_clean")
    contract = _BY_NAME["build.ninja_clean"]
    spec = _SPECS["build.ninja_clean"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_make_dry() -> None:
    """Validate the built-in build.make_dry logical authority contract."""
    _assert_contract("build.make_dry")
    contract = _BY_NAME["build.make_dry"]
    spec = _SPECS["build.make_dry"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_make_build() -> None:
    """Validate the built-in build.make_build logical authority contract."""
    _assert_contract("build.make_build")
    contract = _BY_NAME["build.make_build"]
    spec = _SPECS["build.make_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_make_clean() -> None:
    """Validate the built-in build.make_clean logical authority contract."""
    _assert_contract("build.make_clean")
    contract = _BY_NAME["build.make_clean"]
    spec = _SPECS["build.make_clean"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_meson_setup() -> None:
    """Validate the built-in build.meson_setup logical authority contract."""
    _assert_contract("build.meson_setup")
    contract = _BY_NAME["build.meson_setup"]
    spec = _SPECS["build.meson_setup"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_meson_compile() -> None:
    """Validate the built-in build.meson_compile logical authority contract."""
    _assert_contract("build.meson_compile")
    contract = _BY_NAME["build.meson_compile"]
    spec = _SPECS["build.meson_compile"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_meson_test() -> None:
    """Validate the built-in build.meson_test logical authority contract."""
    _assert_contract("build.meson_test")
    contract = _BY_NAME["build.meson_test"]
    spec = _SPECS["build.meson_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_bazel_query() -> None:
    """Validate the built-in build.bazel_query logical authority contract."""
    _assert_contract("build.bazel_query")
    contract = _BY_NAME["build.bazel_query"]
    spec = _SPECS["build.bazel_query"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_bazel_build() -> None:
    """Validate the built-in build.bazel_build logical authority contract."""
    _assert_contract("build.bazel_build")
    contract = _BY_NAME["build.bazel_build"]
    spec = _SPECS["build.bazel_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_bazel_test() -> None:
    """Validate the built-in build.bazel_test logical authority contract."""
    _assert_contract("build.bazel_test")
    contract = _BY_NAME["build.bazel_test"]
    spec = _SPECS["build.bazel_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_bazel_clean() -> None:
    """Validate the built-in build.bazel_clean logical authority contract."""
    _assert_contract("build.bazel_clean")
    contract = _BY_NAME["build.bazel_clean"]
    spec = _SPECS["build.bazel_clean"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_just_list() -> None:
    """Validate the built-in build.just_list logical authority contract."""
    _assert_contract("build.just_list")
    contract = _BY_NAME["build.just_list"]
    spec = _SPECS["build.just_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_just_dry() -> None:
    """Validate the built-in build.just_dry logical authority contract."""
    _assert_contract("build.just_dry")
    contract = _BY_NAME["build.just_dry"]
    spec = _SPECS["build.just_dry"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_build_just_run() -> None:
    """Validate the built-in build.just_run logical authority contract."""
    _assert_contract("build.just_run")
    contract = _BY_NAME["build.just_run"]
    spec = _SPECS["build.just_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_version() -> None:
    """Validate the built-in container.docker_version logical authority contract."""
    _assert_contract("container.docker_version")
    contract = _BY_NAME["container.docker_version"]
    spec = _SPECS["container.docker_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_info() -> None:
    """Validate the built-in container.docker_info logical authority contract."""
    _assert_contract("container.docker_info")
    contract = _BY_NAME["container.docker_info"]
    spec = _SPECS["container.docker_info"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_ps() -> None:
    """Validate the built-in container.docker_ps logical authority contract."""
    _assert_contract("container.docker_ps")
    contract = _BY_NAME["container.docker_ps"]
    spec = _SPECS["container.docker_ps"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_images() -> None:
    """Validate the built-in container.docker_images logical authority contract."""
    _assert_contract("container.docker_images")
    contract = _BY_NAME["container.docker_images"]
    spec = _SPECS["container.docker_images"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_inspect() -> None:
    """Validate the built-in container.docker_inspect logical authority contract."""
    _assert_contract("container.docker_inspect")
    contract = _BY_NAME["container.docker_inspect"]
    spec = _SPECS["container.docker_inspect"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_logs() -> None:
    """Validate the built-in container.docker_logs logical authority contract."""
    _assert_contract("container.docker_logs")
    contract = _BY_NAME["container.docker_logs"]
    spec = _SPECS["container.docker_logs"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_top() -> None:
    """Validate the built-in container.docker_top logical authority contract."""
    _assert_contract("container.docker_top")
    contract = _BY_NAME["container.docker_top"]
    spec = _SPECS["container.docker_top"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_stats_once() -> None:
    """Validate the built-in container.docker_stats_once logical authority contract."""
    _assert_contract("container.docker_stats_once")
    contract = _BY_NAME["container.docker_stats_once"]
    spec = _SPECS["container.docker_stats_once"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_history() -> None:
    """Validate the built-in container.docker_history logical authority contract."""
    _assert_contract("container.docker_history")
    contract = _BY_NAME["container.docker_history"]
    spec = _SPECS["container.docker_history"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_image_inspect() -> None:
    """Validate the built-in container.docker_image_inspect logical authority contract."""
    _assert_contract("container.docker_image_inspect")
    contract = _BY_NAME["container.docker_image_inspect"]
    spec = _SPECS["container.docker_image_inspect"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_build() -> None:
    """Validate the built-in container.docker_build logical authority contract."""
    _assert_contract("container.docker_build")
    contract = _BY_NAME["container.docker_build"]
    spec = _SPECS["container.docker_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_pull() -> None:
    """Validate the built-in container.docker_pull logical authority contract."""
    _assert_contract("container.docker_pull")
    contract = _BY_NAME["container.docker_pull"]
    spec = _SPECS["container.docker_pull"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_create() -> None:
    """Validate the built-in container.docker_create logical authority contract."""
    _assert_contract("container.docker_create")
    contract = _BY_NAME["container.docker_create"]
    spec = _SPECS["container.docker_create"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_run() -> None:
    """Validate the built-in container.docker_run logical authority contract."""
    _assert_contract("container.docker_run")
    contract = _BY_NAME["container.docker_run"]
    spec = _SPECS["container.docker_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_start() -> None:
    """Validate the built-in container.docker_start logical authority contract."""
    _assert_contract("container.docker_start")
    contract = _BY_NAME["container.docker_start"]
    spec = _SPECS["container.docker_start"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_stop() -> None:
    """Validate the built-in container.docker_stop logical authority contract."""
    _assert_contract("container.docker_stop")
    contract = _BY_NAME["container.docker_stop"]
    spec = _SPECS["container.docker_stop"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_kill() -> None:
    """Validate the built-in container.docker_kill logical authority contract."""
    _assert_contract("container.docker_kill")
    contract = _BY_NAME["container.docker_kill"]
    spec = _SPECS["container.docker_kill"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_rm() -> None:
    """Validate the built-in container.docker_rm logical authority contract."""
    _assert_contract("container.docker_rm")
    contract = _BY_NAME["container.docker_rm"]
    spec = _SPECS["container.docker_rm"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_rmi() -> None:
    """Validate the built-in container.docker_rmi logical authority contract."""
    _assert_contract("container.docker_rmi")
    contract = _BY_NAME["container.docker_rmi"]
    spec = _SPECS["container.docker_rmi"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_cp() -> None:
    """Validate the built-in container.docker_cp logical authority contract."""
    _assert_contract("container.docker_cp")
    contract = _BY_NAME["container.docker_cp"]
    spec = _SPECS["container.docker_cp"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_exec() -> None:
    """Validate the built-in container.docker_exec logical authority contract."""
    _assert_contract("container.docker_exec")
    contract = _BY_NAME["container.docker_exec"]
    spec = _SPECS["container.docker_exec"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_network_ls() -> None:
    """Validate the built-in container.docker_network_ls logical authority contract."""
    _assert_contract("container.docker_network_ls")
    contract = _BY_NAME["container.docker_network_ls"]
    spec = _SPECS["container.docker_network_ls"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_volume_ls() -> None:
    """Validate the built-in container.docker_volume_ls logical authority contract."""
    _assert_contract("container.docker_volume_ls")
    contract = _BY_NAME["container.docker_volume_ls"]
    spec = _SPECS["container.docker_volume_ls"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_docker_system_df() -> None:
    """Validate the built-in container.docker_system_df logical authority contract."""
    _assert_contract("container.docker_system_df")
    contract = _BY_NAME["container.docker_system_df"]
    spec = _SPECS["container.docker_system_df"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_version() -> None:
    """Validate the built-in container.podman_version logical authority contract."""
    _assert_contract("container.podman_version")
    contract = _BY_NAME["container.podman_version"]
    spec = _SPECS["container.podman_version"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_info() -> None:
    """Validate the built-in container.podman_info logical authority contract."""
    _assert_contract("container.podman_info")
    contract = _BY_NAME["container.podman_info"]
    spec = _SPECS["container.podman_info"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_ps() -> None:
    """Validate the built-in container.podman_ps logical authority contract."""
    _assert_contract("container.podman_ps")
    contract = _BY_NAME["container.podman_ps"]
    spec = _SPECS["container.podman_ps"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_images() -> None:
    """Validate the built-in container.podman_images logical authority contract."""
    _assert_contract("container.podman_images")
    contract = _BY_NAME["container.podman_images"]
    spec = _SPECS["container.podman_images"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_inspect() -> None:
    """Validate the built-in container.podman_inspect logical authority contract."""
    _assert_contract("container.podman_inspect")
    contract = _BY_NAME["container.podman_inspect"]
    spec = _SPECS["container.podman_inspect"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_logs() -> None:
    """Validate the built-in container.podman_logs logical authority contract."""
    _assert_contract("container.podman_logs")
    contract = _BY_NAME["container.podman_logs"]
    spec = _SPECS["container.podman_logs"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_top() -> None:
    """Validate the built-in container.podman_top logical authority contract."""
    _assert_contract("container.podman_top")
    contract = _BY_NAME["container.podman_top"]
    spec = _SPECS["container.podman_top"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_stats_once() -> None:
    """Validate the built-in container.podman_stats_once logical authority contract."""
    _assert_contract("container.podman_stats_once")
    contract = _BY_NAME["container.podman_stats_once"]
    spec = _SPECS["container.podman_stats_once"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_history() -> None:
    """Validate the built-in container.podman_history logical authority contract."""
    _assert_contract("container.podman_history")
    contract = _BY_NAME["container.podman_history"]
    spec = _SPECS["container.podman_history"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_image_inspect() -> None:
    """Validate the built-in container.podman_image_inspect logical authority contract."""
    _assert_contract("container.podman_image_inspect")
    contract = _BY_NAME["container.podman_image_inspect"]
    spec = _SPECS["container.podman_image_inspect"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_build() -> None:
    """Validate the built-in container.podman_build logical authority contract."""
    _assert_contract("container.podman_build")
    contract = _BY_NAME["container.podman_build"]
    spec = _SPECS["container.podman_build"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_pull() -> None:
    """Validate the built-in container.podman_pull logical authority contract."""
    _assert_contract("container.podman_pull")
    contract = _BY_NAME["container.podman_pull"]
    spec = _SPECS["container.podman_pull"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_create() -> None:
    """Validate the built-in container.podman_create logical authority contract."""
    _assert_contract("container.podman_create")
    contract = _BY_NAME["container.podman_create"]
    spec = _SPECS["container.podman_create"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_run() -> None:
    """Validate the built-in container.podman_run logical authority contract."""
    _assert_contract("container.podman_run")
    contract = _BY_NAME["container.podman_run"]
    spec = _SPECS["container.podman_run"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_start() -> None:
    """Validate the built-in container.podman_start logical authority contract."""
    _assert_contract("container.podman_start")
    contract = _BY_NAME["container.podman_start"]
    spec = _SPECS["container.podman_start"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_stop() -> None:
    """Validate the built-in container.podman_stop logical authority contract."""
    _assert_contract("container.podman_stop")
    contract = _BY_NAME["container.podman_stop"]
    spec = _SPECS["container.podman_stop"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_kill() -> None:
    """Validate the built-in container.podman_kill logical authority contract."""
    _assert_contract("container.podman_kill")
    contract = _BY_NAME["container.podman_kill"]
    spec = _SPECS["container.podman_kill"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_rm() -> None:
    """Validate the built-in container.podman_rm logical authority contract."""
    _assert_contract("container.podman_rm")
    contract = _BY_NAME["container.podman_rm"]
    spec = _SPECS["container.podman_rm"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_rmi() -> None:
    """Validate the built-in container.podman_rmi logical authority contract."""
    _assert_contract("container.podman_rmi")
    contract = _BY_NAME["container.podman_rmi"]
    spec = _SPECS["container.podman_rmi"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_cp() -> None:
    """Validate the built-in container.podman_cp logical authority contract."""
    _assert_contract("container.podman_cp")
    contract = _BY_NAME["container.podman_cp"]
    spec = _SPECS["container.podman_cp"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_exec() -> None:
    """Validate the built-in container.podman_exec logical authority contract."""
    _assert_contract("container.podman_exec")
    contract = _BY_NAME["container.podman_exec"]
    spec = _SPECS["container.podman_exec"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_network_ls() -> None:
    """Validate the built-in container.podman_network_ls logical authority contract."""
    _assert_contract("container.podman_network_ls")
    contract = _BY_NAME["container.podman_network_ls"]
    spec = _SPECS["container.podman_network_ls"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_volume_ls() -> None:
    """Validate the built-in container.podman_volume_ls logical authority contract."""
    _assert_contract("container.podman_volume_ls")
    contract = _BY_NAME["container.podman_volume_ls"]
    spec = _SPECS["container.podman_volume_ls"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_container_podman_system_df() -> None:
    """Validate the built-in container.podman_system_df logical authority contract."""
    _assert_contract("container.podman_system_df")
    contract = _BY_NAME["container.podman_system_df"]
    spec = _SPECS["container.podman_system_df"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_pwd() -> None:
    """Validate the built-in posix.pwd logical authority contract."""
    _assert_contract("posix.pwd")
    contract = _BY_NAME["posix.pwd"]
    spec = _SPECS["posix.pwd"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_ls() -> None:
    """Validate the built-in posix.ls logical authority contract."""
    _assert_contract("posix.ls")
    contract = _BY_NAME["posix.ls"]
    spec = _SPECS["posix.ls"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_stat() -> None:
    """Validate the built-in posix.stat logical authority contract."""
    _assert_contract("posix.stat")
    contract = _BY_NAME["posix.stat"]
    spec = _SPECS["posix.stat"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_find() -> None:
    """Validate the built-in posix.find logical authority contract."""
    _assert_contract("posix.find")
    contract = _BY_NAME["posix.find"]
    spec = _SPECS["posix.find"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_du() -> None:
    """Validate the built-in posix.du logical authority contract."""
    _assert_contract("posix.du")
    contract = _BY_NAME["posix.du"]
    spec = _SPECS["posix.du"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_df() -> None:
    """Validate the built-in posix.df logical authority contract."""
    _assert_contract("posix.df")
    contract = _BY_NAME["posix.df"]
    spec = _SPECS["posix.df"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_file() -> None:
    """Validate the built-in posix.file logical authority contract."""
    _assert_contract("posix.file")
    contract = _BY_NAME["posix.file"]
    spec = _SPECS["posix.file"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_sha256sum() -> None:
    """Validate the built-in posix.sha256sum logical authority contract."""
    _assert_contract("posix.sha256sum")
    contract = _BY_NAME["posix.sha256sum"]
    spec = _SPECS["posix.sha256sum"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_wc() -> None:
    """Validate the built-in posix.wc logical authority contract."""
    _assert_contract("posix.wc")
    contract = _BY_NAME["posix.wc"]
    spec = _SPECS["posix.wc"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_head() -> None:
    """Validate the built-in posix.head logical authority contract."""
    _assert_contract("posix.head")
    contract = _BY_NAME["posix.head"]
    spec = _SPECS["posix.head"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_tail() -> None:
    """Validate the built-in posix.tail logical authority contract."""
    _assert_contract("posix.tail")
    contract = _BY_NAME["posix.tail"]
    spec = _SPECS["posix.tail"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_sort() -> None:
    """Validate the built-in posix.sort logical authority contract."""
    _assert_contract("posix.sort")
    contract = _BY_NAME["posix.sort"]
    spec = _SPECS["posix.sort"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_uniq() -> None:
    """Validate the built-in posix.uniq logical authority contract."""
    _assert_contract("posix.uniq")
    contract = _BY_NAME["posix.uniq"]
    spec = _SPECS["posix.uniq"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_cut() -> None:
    """Validate the built-in posix.cut logical authority contract."""
    _assert_contract("posix.cut")
    contract = _BY_NAME["posix.cut"]
    spec = _SPECS["posix.cut"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_tr() -> None:
    """Validate the built-in posix.tr logical authority contract."""
    _assert_contract("posix.tr")
    contract = _BY_NAME["posix.tr"]
    spec = _SPECS["posix.tr"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_grep() -> None:
    """Validate the built-in posix.grep logical authority contract."""
    _assert_contract("posix.grep")
    contract = _BY_NAME["posix.grep"]
    spec = _SPECS["posix.grep"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_sed_print() -> None:
    """Validate the built-in posix.sed_print logical authority contract."""
    _assert_contract("posix.sed_print")
    contract = _BY_NAME["posix.sed_print"]
    spec = _SPECS["posix.sed_print"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_awk() -> None:
    """Validate the built-in posix.awk logical authority contract."""
    _assert_contract("posix.awk")
    contract = _BY_NAME["posix.awk"]
    spec = _SPECS["posix.awk"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_xargs_echo() -> None:
    """Validate the built-in posix.xargs_echo logical authority contract."""
    _assert_contract("posix.xargs_echo")
    contract = _BY_NAME["posix.xargs_echo"]
    spec = _SPECS["posix.xargs_echo"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_readlink() -> None:
    """Validate the built-in posix.readlink logical authority contract."""
    _assert_contract("posix.readlink")
    contract = _BY_NAME["posix.readlink"]
    spec = _SPECS["posix.readlink"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_realpath() -> None:
    """Validate the built-in posix.realpath logical authority contract."""
    _assert_contract("posix.realpath")
    contract = _BY_NAME["posix.realpath"]
    spec = _SPECS["posix.realpath"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_basename() -> None:
    """Validate the built-in posix.basename logical authority contract."""
    _assert_contract("posix.basename")
    contract = _BY_NAME["posix.basename"]
    spec = _SPECS["posix.basename"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_dirname() -> None:
    """Validate the built-in posix.dirname logical authority contract."""
    _assert_contract("posix.dirname")
    contract = _BY_NAME["posix.dirname"]
    spec = _SPECS["posix.dirname"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_date() -> None:
    """Validate the built-in posix.date logical authority contract."""
    _assert_contract("posix.date")
    contract = _BY_NAME["posix.date"]
    spec = _SPECS["posix.date"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_env() -> None:
    """Validate the built-in posix.env logical authority contract."""
    _assert_contract("posix.env")
    contract = _BY_NAME["posix.env"]
    spec = _SPECS["posix.env"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_printenv() -> None:
    """Validate the built-in posix.printenv logical authority contract."""
    _assert_contract("posix.printenv")
    contract = _BY_NAME["posix.printenv"]
    spec = _SPECS["posix.printenv"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_which() -> None:
    """Validate the built-in posix.which logical authority contract."""
    _assert_contract("posix.which")
    contract = _BY_NAME["posix.which"]
    spec = _SPECS["posix.which"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_id() -> None:
    """Validate the built-in posix.id logical authority contract."""
    _assert_contract("posix.id")
    contract = _BY_NAME["posix.id"]
    spec = _SPECS["posix.id"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_uname() -> None:
    """Validate the built-in posix.uname logical authority contract."""
    _assert_contract("posix.uname")
    contract = _BY_NAME["posix.uname"]
    spec = _SPECS["posix.uname"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_ps() -> None:
    """Validate the built-in posix.ps logical authority contract."""
    _assert_contract("posix.ps")
    contract = _BY_NAME["posix.ps"]
    spec = _SPECS["posix.ps"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_mkdir() -> None:
    """Validate the built-in posix.mkdir logical authority contract."""
    _assert_contract("posix.mkdir")
    contract = _BY_NAME["posix.mkdir"]
    spec = _SPECS["posix.mkdir"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_touch() -> None:
    """Validate the built-in posix.touch logical authority contract."""
    _assert_contract("posix.touch")
    contract = _BY_NAME["posix.touch"]
    spec = _SPECS["posix.touch"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_cp() -> None:
    """Validate the built-in posix.cp logical authority contract."""
    _assert_contract("posix.cp")
    contract = _BY_NAME["posix.cp"]
    spec = _SPECS["posix.cp"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_mv() -> None:
    """Validate the built-in posix.mv logical authority contract."""
    _assert_contract("posix.mv")
    contract = _BY_NAME["posix.mv"]
    spec = _SPECS["posix.mv"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_rm() -> None:
    """Validate the built-in posix.rm logical authority contract."""
    _assert_contract("posix.rm")
    contract = _BY_NAME["posix.rm"]
    spec = _SPECS["posix.rm"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_chmod() -> None:
    """Validate the built-in posix.chmod logical authority contract."""
    _assert_contract("posix.chmod")
    contract = _BY_NAME["posix.chmod"]
    spec = _SPECS["posix.chmod"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_ln() -> None:
    """Validate the built-in posix.ln logical authority contract."""
    _assert_contract("posix.ln")
    contract = _BY_NAME["posix.ln"]
    spec = _SPECS["posix.ln"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_tar_list() -> None:
    """Validate the built-in posix.tar_list logical authority contract."""
    _assert_contract("posix.tar_list")
    contract = _BY_NAME["posix.tar_list"]
    spec = _SPECS["posix.tar_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_tar_create() -> None:
    """Validate the built-in posix.tar_create logical authority contract."""
    _assert_contract("posix.tar_create")
    contract = _BY_NAME["posix.tar_create"]
    spec = _SPECS["posix.tar_create"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_tar_extract() -> None:
    """Validate the built-in posix.tar_extract logical authority contract."""
    _assert_contract("posix.tar_extract")
    contract = _BY_NAME["posix.tar_extract"]
    spec = _SPECS["posix.tar_extract"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_gzip_test() -> None:
    """Validate the built-in posix.gzip_test logical authority contract."""
    _assert_contract("posix.gzip_test")
    contract = _BY_NAME["posix.gzip_test"]
    spec = _SPECS["posix.gzip_test"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_gzip_compress() -> None:
    """Validate the built-in posix.gzip_compress logical authority contract."""
    _assert_contract("posix.gzip_compress")
    contract = _BY_NAME["posix.gzip_compress"]
    spec = _SPECS["posix.gzip_compress"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_unzip_list() -> None:
    """Validate the built-in posix.unzip_list logical authority contract."""
    _assert_contract("posix.unzip_list")
    contract = _BY_NAME["posix.unzip_list"]
    spec = _SPECS["posix.unzip_list"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_unzip_extract() -> None:
    """Validate the built-in posix.unzip_extract logical authority contract."""
    _assert_contract("posix.unzip_extract")
    contract = _BY_NAME["posix.unzip_extract"]
    spec = _SPECS["posix.unzip_extract"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_zip_create() -> None:
    """Validate the built-in posix.zip_create logical authority contract."""
    _assert_contract("posix.zip_create")
    contract = _BY_NAME["posix.zip_create"]
    spec = _SPECS["posix.zip_create"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_diff() -> None:
    """Validate the built-in posix.diff logical authority contract."""
    _assert_contract("posix.diff")
    contract = _BY_NAME["posix.diff"]
    spec = _SPECS["posix.diff"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_contract_posix_cmp() -> None:
    """Validate the built-in posix.cmp logical authority contract."""
    _assert_contract("posix.cmp")
    contract = _BY_NAME["posix.cmp"]
    spec = _SPECS["posix.cmp"]
    assert contract.required_capabilities
    assert contract.executable_key == spec.executable_key
    assert tuple(sorted(effect.value for effect in contract.effects))
    assert contract.risk.value in {"low", "moderate", "high"}
    assert isinstance(contract.environment.allowed_keys(), tuple)
    assert contract.to_dict()["description"] == contract.description
    assert contract.arguments.validate(contract.name, _minimal_argv(spec))

def test_recipe_python_verify() -> None:
    """Validate recipe python.verify against the built-in catalog."""
    _assert_recipe("python.verify")
    recipe = DEFAULT_RECIPES.get("python.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_python_preflight() -> None:
    """Validate recipe python.preflight against the built-in catalog."""
    _assert_recipe("python.preflight")
    recipe = DEFAULT_RECIPES.get("python.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_python_fast_verify() -> None:
    """Validate recipe python_fast.verify against the built-in catalog."""
    _assert_recipe("python_fast.verify")
    recipe = DEFAULT_RECIPES.get("python_fast.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_python_fast_preflight() -> None:
    """Validate recipe python_fast.preflight against the built-in catalog."""
    _assert_recipe("python_fast.preflight")
    recipe = DEFAULT_RECIPES.get("python_fast.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_node_verify() -> None:
    """Validate recipe node.verify against the built-in catalog."""
    _assert_recipe("node.verify")
    recipe = DEFAULT_RECIPES.get("node.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_node_preflight() -> None:
    """Validate recipe node.preflight against the built-in catalog."""
    _assert_recipe("node.preflight")
    recipe = DEFAULT_RECIPES.get("node.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_rust_verify() -> None:
    """Validate recipe rust.verify against the built-in catalog."""
    _assert_recipe("rust.verify")
    recipe = DEFAULT_RECIPES.get("rust.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_rust_preflight() -> None:
    """Validate recipe rust.preflight against the built-in catalog."""
    _assert_recipe("rust.preflight")
    recipe = DEFAULT_RECIPES.get("rust.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_go_verify() -> None:
    """Validate recipe go.verify against the built-in catalog."""
    _assert_recipe("go.verify")
    recipe = DEFAULT_RECIPES.get("go.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_go_preflight() -> None:
    """Validate recipe go.preflight against the built-in catalog."""
    _assert_recipe("go.preflight")
    recipe = DEFAULT_RECIPES.get("go.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_jvm_verify() -> None:
    """Validate recipe jvm.verify against the built-in catalog."""
    _assert_recipe("jvm.verify")
    recipe = DEFAULT_RECIPES.get("jvm.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_jvm_preflight() -> None:
    """Validate recipe jvm.preflight against the built-in catalog."""
    _assert_recipe("jvm.preflight")
    recipe = DEFAULT_RECIPES.get("jvm.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_dotnet_verify() -> None:
    """Validate recipe dotnet.verify against the built-in catalog."""
    _assert_recipe("dotnet.verify")
    recipe = DEFAULT_RECIPES.get("dotnet.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_dotnet_preflight() -> None:
    """Validate recipe dotnet.preflight against the built-in catalog."""
    _assert_recipe("dotnet.preflight")
    recipe = DEFAULT_RECIPES.get("dotnet.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_cmake_verify() -> None:
    """Validate recipe cmake.verify against the built-in catalog."""
    _assert_recipe("cmake.verify")
    recipe = DEFAULT_RECIPES.get("cmake.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_cmake_preflight() -> None:
    """Validate recipe cmake.preflight against the built-in catalog."""
    _assert_recipe("cmake.preflight")
    recipe = DEFAULT_RECIPES.get("cmake.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_bazel_verify() -> None:
    """Validate recipe bazel.verify against the built-in catalog."""
    _assert_recipe("bazel.verify")
    recipe = DEFAULT_RECIPES.get("bazel.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_bazel_preflight() -> None:
    """Validate recipe bazel.preflight against the built-in catalog."""
    _assert_recipe("bazel.preflight")
    recipe = DEFAULT_RECIPES.get("bazel.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_git_review_verify() -> None:
    """Validate recipe git_review.verify against the built-in catalog."""
    _assert_recipe("git_review.verify")
    recipe = DEFAULT_RECIPES.get("git_review.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_git_review_preflight() -> None:
    """Validate recipe git_review.preflight against the built-in catalog."""
    _assert_recipe("git_review.preflight")
    recipe = DEFAULT_RECIPES.get("git_review.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_container_review_verify() -> None:
    """Validate recipe container_review.verify against the built-in catalog."""
    _assert_recipe("container_review.verify")
    recipe = DEFAULT_RECIPES.get("container_review.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_container_review_preflight() -> None:
    """Validate recipe container_review.preflight against the built-in catalog."""
    _assert_recipe("container_review.preflight")
    recipe = DEFAULT_RECIPES.get("container_review.preflight")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_polyglot_core_verify() -> None:
    """Validate recipe polyglot.core.verify against the built-in catalog."""
    _assert_recipe("polyglot.core.verify")
    recipe = DEFAULT_RECIPES.get("polyglot.core.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_polyglot_format_verify() -> None:
    """Validate recipe polyglot.format.verify against the built-in catalog."""
    _assert_recipe("polyglot.format.verify")
    recipe = DEFAULT_RECIPES.get("polyglot.format.verify")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_polyglot_test() -> None:
    """Validate recipe polyglot.test against the built-in catalog."""
    _assert_recipe("polyglot.test")
    recipe = DEFAULT_RECIPES.get("polyglot.test")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_repository_review() -> None:
    """Validate recipe repository.review against the built-in catalog."""
    _assert_recipe("repository.review")
    recipe = DEFAULT_RECIPES.get("repository.review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_repository_integrity() -> None:
    """Validate recipe repository.integrity against the built-in catalog."""
    _assert_recipe("repository.integrity")
    recipe = DEFAULT_RECIPES.get("repository.integrity")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_container_observe() -> None:
    """Validate recipe container.observe against the built-in catalog."""
    _assert_recipe("container.observe")
    recipe = DEFAULT_RECIPES.get("container.observe")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_filesystem_observe() -> None:
    """Validate recipe filesystem.observe against the built-in catalog."""
    _assert_recipe("filesystem.observe")
    recipe = DEFAULT_RECIPES.get("filesystem.observe")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_python_security() -> None:
    """Validate recipe python.security against the built-in catalog."""
    _assert_recipe("python.security")
    recipe = DEFAULT_RECIPES.get("python.security")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_rust_security() -> None:
    """Validate recipe rust.security against the built-in catalog."""
    _assert_recipe("rust.security")
    recipe = DEFAULT_RECIPES.get("rust.security")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_go_security() -> None:
    """Validate recipe go.security against the built-in catalog."""
    _assert_recipe("go.security")
    recipe = DEFAULT_RECIPES.get("go.security")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_node_quality() -> None:
    """Validate recipe node.quality against the built-in catalog."""
    _assert_recipe("node.quality")
    recipe = DEFAULT_RECIPES.get("node.quality")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_dotnet_quality() -> None:
    """Validate recipe dotnet.quality against the built-in catalog."""
    _assert_recipe("dotnet.quality")
    recipe = DEFAULT_RECIPES.get("dotnet.quality")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_jvm_quality() -> None:
    """Validate recipe jvm.quality against the built-in catalog."""
    _assert_recipe("jvm.quality")
    recipe = DEFAULT_RECIPES.get("jvm.quality")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_001_python() -> None:
    """Validate recipe assurance.001.python against the built-in catalog."""
    _assert_recipe("assurance.001.python")
    recipe = DEFAULT_RECIPES.get("assurance.001.python")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_002_python_fast() -> None:
    """Validate recipe assurance.002.python_fast against the built-in catalog."""
    _assert_recipe("assurance.002.python_fast")
    recipe = DEFAULT_RECIPES.get("assurance.002.python_fast")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_003_node() -> None:
    """Validate recipe assurance.003.node against the built-in catalog."""
    _assert_recipe("assurance.003.node")
    recipe = DEFAULT_RECIPES.get("assurance.003.node")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_004_rust() -> None:
    """Validate recipe assurance.004.rust against the built-in catalog."""
    _assert_recipe("assurance.004.rust")
    recipe = DEFAULT_RECIPES.get("assurance.004.rust")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_005_go() -> None:
    """Validate recipe assurance.005.go against the built-in catalog."""
    _assert_recipe("assurance.005.go")
    recipe = DEFAULT_RECIPES.get("assurance.005.go")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_006_jvm() -> None:
    """Validate recipe assurance.006.jvm against the built-in catalog."""
    _assert_recipe("assurance.006.jvm")
    recipe = DEFAULT_RECIPES.get("assurance.006.jvm")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_007_dotnet() -> None:
    """Validate recipe assurance.007.dotnet against the built-in catalog."""
    _assert_recipe("assurance.007.dotnet")
    recipe = DEFAULT_RECIPES.get("assurance.007.dotnet")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_008_cmake() -> None:
    """Validate recipe assurance.008.cmake against the built-in catalog."""
    _assert_recipe("assurance.008.cmake")
    recipe = DEFAULT_RECIPES.get("assurance.008.cmake")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_009_bazel() -> None:
    """Validate recipe assurance.009.bazel against the built-in catalog."""
    _assert_recipe("assurance.009.bazel")
    recipe = DEFAULT_RECIPES.get("assurance.009.bazel")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_010_git_review() -> None:
    """Validate recipe assurance.010.git_review against the built-in catalog."""
    _assert_recipe("assurance.010.git_review")
    recipe = DEFAULT_RECIPES.get("assurance.010.git_review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_011_container_review() -> None:
    """Validate recipe assurance.011.container_review against the built-in catalog."""
    _assert_recipe("assurance.011.container_review")
    recipe = DEFAULT_RECIPES.get("assurance.011.container_review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_012_python() -> None:
    """Validate recipe assurance.012.python against the built-in catalog."""
    _assert_recipe("assurance.012.python")
    recipe = DEFAULT_RECIPES.get("assurance.012.python")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_013_python_fast() -> None:
    """Validate recipe assurance.013.python_fast against the built-in catalog."""
    _assert_recipe("assurance.013.python_fast")
    recipe = DEFAULT_RECIPES.get("assurance.013.python_fast")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_014_node() -> None:
    """Validate recipe assurance.014.node against the built-in catalog."""
    _assert_recipe("assurance.014.node")
    recipe = DEFAULT_RECIPES.get("assurance.014.node")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_015_rust() -> None:
    """Validate recipe assurance.015.rust against the built-in catalog."""
    _assert_recipe("assurance.015.rust")
    recipe = DEFAULT_RECIPES.get("assurance.015.rust")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_016_go() -> None:
    """Validate recipe assurance.016.go against the built-in catalog."""
    _assert_recipe("assurance.016.go")
    recipe = DEFAULT_RECIPES.get("assurance.016.go")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_017_jvm() -> None:
    """Validate recipe assurance.017.jvm against the built-in catalog."""
    _assert_recipe("assurance.017.jvm")
    recipe = DEFAULT_RECIPES.get("assurance.017.jvm")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_018_dotnet() -> None:
    """Validate recipe assurance.018.dotnet against the built-in catalog."""
    _assert_recipe("assurance.018.dotnet")
    recipe = DEFAULT_RECIPES.get("assurance.018.dotnet")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_019_cmake() -> None:
    """Validate recipe assurance.019.cmake against the built-in catalog."""
    _assert_recipe("assurance.019.cmake")
    recipe = DEFAULT_RECIPES.get("assurance.019.cmake")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_020_bazel() -> None:
    """Validate recipe assurance.020.bazel against the built-in catalog."""
    _assert_recipe("assurance.020.bazel")
    recipe = DEFAULT_RECIPES.get("assurance.020.bazel")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_021_git_review() -> None:
    """Validate recipe assurance.021.git_review against the built-in catalog."""
    _assert_recipe("assurance.021.git_review")
    recipe = DEFAULT_RECIPES.get("assurance.021.git_review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_022_container_review() -> None:
    """Validate recipe assurance.022.container_review against the built-in catalog."""
    _assert_recipe("assurance.022.container_review")
    recipe = DEFAULT_RECIPES.get("assurance.022.container_review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_023_python() -> None:
    """Validate recipe assurance.023.python against the built-in catalog."""
    _assert_recipe("assurance.023.python")
    recipe = DEFAULT_RECIPES.get("assurance.023.python")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_024_python_fast() -> None:
    """Validate recipe assurance.024.python_fast against the built-in catalog."""
    _assert_recipe("assurance.024.python_fast")
    recipe = DEFAULT_RECIPES.get("assurance.024.python_fast")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_025_node() -> None:
    """Validate recipe assurance.025.node against the built-in catalog."""
    _assert_recipe("assurance.025.node")
    recipe = DEFAULT_RECIPES.get("assurance.025.node")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_026_rust() -> None:
    """Validate recipe assurance.026.rust against the built-in catalog."""
    _assert_recipe("assurance.026.rust")
    recipe = DEFAULT_RECIPES.get("assurance.026.rust")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_027_go() -> None:
    """Validate recipe assurance.027.go against the built-in catalog."""
    _assert_recipe("assurance.027.go")
    recipe = DEFAULT_RECIPES.get("assurance.027.go")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_028_jvm() -> None:
    """Validate recipe assurance.028.jvm against the built-in catalog."""
    _assert_recipe("assurance.028.jvm")
    recipe = DEFAULT_RECIPES.get("assurance.028.jvm")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_029_dotnet() -> None:
    """Validate recipe assurance.029.dotnet against the built-in catalog."""
    _assert_recipe("assurance.029.dotnet")
    recipe = DEFAULT_RECIPES.get("assurance.029.dotnet")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_030_cmake() -> None:
    """Validate recipe assurance.030.cmake against the built-in catalog."""
    _assert_recipe("assurance.030.cmake")
    recipe = DEFAULT_RECIPES.get("assurance.030.cmake")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_031_bazel() -> None:
    """Validate recipe assurance.031.bazel against the built-in catalog."""
    _assert_recipe("assurance.031.bazel")
    recipe = DEFAULT_RECIPES.get("assurance.031.bazel")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_032_git_review() -> None:
    """Validate recipe assurance.032.git_review against the built-in catalog."""
    _assert_recipe("assurance.032.git_review")
    recipe = DEFAULT_RECIPES.get("assurance.032.git_review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_033_container_review() -> None:
    """Validate recipe assurance.033.container_review against the built-in catalog."""
    _assert_recipe("assurance.033.container_review")
    recipe = DEFAULT_RECIPES.get("assurance.033.container_review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_034_python() -> None:
    """Validate recipe assurance.034.python against the built-in catalog."""
    _assert_recipe("assurance.034.python")
    recipe = DEFAULT_RECIPES.get("assurance.034.python")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_035_python_fast() -> None:
    """Validate recipe assurance.035.python_fast against the built-in catalog."""
    _assert_recipe("assurance.035.python_fast")
    recipe = DEFAULT_RECIPES.get("assurance.035.python_fast")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_036_node() -> None:
    """Validate recipe assurance.036.node against the built-in catalog."""
    _assert_recipe("assurance.036.node")
    recipe = DEFAULT_RECIPES.get("assurance.036.node")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_037_rust() -> None:
    """Validate recipe assurance.037.rust against the built-in catalog."""
    _assert_recipe("assurance.037.rust")
    recipe = DEFAULT_RECIPES.get("assurance.037.rust")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_038_go() -> None:
    """Validate recipe assurance.038.go against the built-in catalog."""
    _assert_recipe("assurance.038.go")
    recipe = DEFAULT_RECIPES.get("assurance.038.go")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_039_jvm() -> None:
    """Validate recipe assurance.039.jvm against the built-in catalog."""
    _assert_recipe("assurance.039.jvm")
    recipe = DEFAULT_RECIPES.get("assurance.039.jvm")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_040_dotnet() -> None:
    """Validate recipe assurance.040.dotnet against the built-in catalog."""
    _assert_recipe("assurance.040.dotnet")
    recipe = DEFAULT_RECIPES.get("assurance.040.dotnet")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_041_cmake() -> None:
    """Validate recipe assurance.041.cmake against the built-in catalog."""
    _assert_recipe("assurance.041.cmake")
    recipe = DEFAULT_RECIPES.get("assurance.041.cmake")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_042_bazel() -> None:
    """Validate recipe assurance.042.bazel against the built-in catalog."""
    _assert_recipe("assurance.042.bazel")
    recipe = DEFAULT_RECIPES.get("assurance.042.bazel")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_043_git_review() -> None:
    """Validate recipe assurance.043.git_review against the built-in catalog."""
    _assert_recipe("assurance.043.git_review")
    recipe = DEFAULT_RECIPES.get("assurance.043.git_review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_044_container_review() -> None:
    """Validate recipe assurance.044.container_review against the built-in catalog."""
    _assert_recipe("assurance.044.container_review")
    recipe = DEFAULT_RECIPES.get("assurance.044.container_review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_045_python() -> None:
    """Validate recipe assurance.045.python against the built-in catalog."""
    _assert_recipe("assurance.045.python")
    recipe = DEFAULT_RECIPES.get("assurance.045.python")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_046_python_fast() -> None:
    """Validate recipe assurance.046.python_fast against the built-in catalog."""
    _assert_recipe("assurance.046.python_fast")
    recipe = DEFAULT_RECIPES.get("assurance.046.python_fast")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_047_node() -> None:
    """Validate recipe assurance.047.node against the built-in catalog."""
    _assert_recipe("assurance.047.node")
    recipe = DEFAULT_RECIPES.get("assurance.047.node")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_048_rust() -> None:
    """Validate recipe assurance.048.rust against the built-in catalog."""
    _assert_recipe("assurance.048.rust")
    recipe = DEFAULT_RECIPES.get("assurance.048.rust")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_049_go() -> None:
    """Validate recipe assurance.049.go against the built-in catalog."""
    _assert_recipe("assurance.049.go")
    recipe = DEFAULT_RECIPES.get("assurance.049.go")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_050_jvm() -> None:
    """Validate recipe assurance.050.jvm against the built-in catalog."""
    _assert_recipe("assurance.050.jvm")
    recipe = DEFAULT_RECIPES.get("assurance.050.jvm")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_051_dotnet() -> None:
    """Validate recipe assurance.051.dotnet against the built-in catalog."""
    _assert_recipe("assurance.051.dotnet")
    recipe = DEFAULT_RECIPES.get("assurance.051.dotnet")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_052_cmake() -> None:
    """Validate recipe assurance.052.cmake against the built-in catalog."""
    _assert_recipe("assurance.052.cmake")
    recipe = DEFAULT_RECIPES.get("assurance.052.cmake")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_053_bazel() -> None:
    """Validate recipe assurance.053.bazel against the built-in catalog."""
    _assert_recipe("assurance.053.bazel")
    recipe = DEFAULT_RECIPES.get("assurance.053.bazel")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_054_git_review() -> None:
    """Validate recipe assurance.054.git_review against the built-in catalog."""
    _assert_recipe("assurance.054.git_review")
    recipe = DEFAULT_RECIPES.get("assurance.054.git_review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_055_container_review() -> None:
    """Validate recipe assurance.055.container_review against the built-in catalog."""
    _assert_recipe("assurance.055.container_review")
    recipe = DEFAULT_RECIPES.get("assurance.055.container_review")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_056_python() -> None:
    """Validate recipe assurance.056.python against the built-in catalog."""
    _assert_recipe("assurance.056.python")
    recipe = DEFAULT_RECIPES.get("assurance.056.python")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_057_python_fast() -> None:
    """Validate recipe assurance.057.python_fast against the built-in catalog."""
    _assert_recipe("assurance.057.python_fast")
    recipe = DEFAULT_RECIPES.get("assurance.057.python_fast")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_058_node() -> None:
    """Validate recipe assurance.058.node against the built-in catalog."""
    _assert_recipe("assurance.058.node")
    recipe = DEFAULT_RECIPES.get("assurance.058.node")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_059_rust() -> None:
    """Validate recipe assurance.059.rust against the built-in catalog."""
    _assert_recipe("assurance.059.rust")
    recipe = DEFAULT_RECIPES.get("assurance.059.rust")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)

def test_recipe_assurance_060_go() -> None:
    """Validate recipe assurance.060.go against the built-in catalog."""
    _assert_recipe("assurance.060.go")
    recipe = DEFAULT_RECIPES.get("assurance.060.go")
    assert recipe.contract_names()
    assert len(recipe.contract_names()) == len(recipe.steps)
    assert all(step.contract in _BY_NAME for step in recipe.steps)
