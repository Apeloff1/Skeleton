"""Exhaustive regressions for extended logical toolchain contracts.

This matrix is intentionally explicit. Each contract receives independent
tests so a single grammar or metadata regression points directly at the
affected logical command instead of hiding inside a broad parameterized case.
"""

from __future__ import annotations

import hashlib

import pytest

from skeleton.shells.errors import ArgumentRejected
from skeleton.shells.provenance import canonical_json
from skeleton.shells.toolchains import archive, artifact, data, infrastructure, quality


_MODULES = {
    "infrastructure": infrastructure,
    "data": data,
    "artifact": artifact,
    "archive": archive,
    "quality": quality,
}

_SAMPLES = {
    "safe": "value",
    "short": "value",
    "identifier": "sample",
    "path": "workspace/file.txt",
    "module": "package.module",
    "package": "package-name",
    "test": "tests/test_sample.py",
    "git_ref": "main",
    "sha": "abcdef1",
    "integer": "1",
    "https": "https://example.invalid/resource",
}


def _sample(kind: str) -> str:
    if kind.startswith("literal:"):
        return kind.removeprefix("literal:")
    try:
        return _SAMPLES[kind]
    except KeyError as exc:
        raise AssertionError(f"missing sample for constraint {kind!r}") from exc


def _spec(module_name: str, logical_name: str):
    module = _MODULES[module_name]
    for item in module.SPECS:
        if item.logical_name == logical_name:
            return item
    raise AssertionError(f"missing spec: {module_name}:{logical_name}")


def _contract(module_name: str, logical_name: str):
    module = _MODULES[module_name]
    for item in module.CONTRACTS:
        if item.name == logical_name:
            return item
    raise AssertionError(f"missing contract: {module_name}:{logical_name}")


def _prefix(spec) -> tuple[str, ...]:
    if spec.subcommand is not None:
        return (spec.subcommand,)
    return tuple(spec.fixed_prefix)


def _minimal_args(spec) -> tuple[str, ...]:
    values = list(_prefix(spec))
    values.extend(_sample(kind) for kind in spec.positionals)
    required = spec.min_positionals
    if required is None:
        required = len(values)
    while len(values) < required:
        if spec.variadic is None:
            raise AssertionError(
                f"spec {spec.logical_name} cannot satisfy min_positionals"
            )
        values.append(_sample(spec.variadic))
    return tuple(values)


def _unknown_option_args(spec) -> tuple[str, ...]:
    values = list(_minimal_args(spec))
    index = len(_prefix(spec))
    values.insert(index, "--definitely-unknown-option")
    return tuple(values)


def _bad_path_args(spec) -> tuple[str, ...] | None:
    values = list(_minimal_args(spec))
    prefix_len = len(_prefix(spec))
    for index, kind in enumerate(spec.positionals):
        if kind == "path":
            values[prefix_len + index] = "../escape"
            return tuple(values)
    if spec.variadic == "path":
        values.append("../escape")
        return tuple(values)
    for option in spec.options:
        if option.value == "path":
            values.extend((option.name, "../escape"))
            return tuple(values)
    return None


def _mutated_prefix_args(spec) -> tuple[str, ...] | None:
    prefix = _prefix(spec)
    if not prefix:
        return None
    values = list(_minimal_args(spec))
    values[0] = "__wrong_prefix__"
    return tuple(values)


def _contract_digest(contract) -> str:
    return hashlib.sha256(canonical_json(contract.to_dict())).hexdigest()


def test_extended_family_names_are_globally_unique():
    names = [
        contract.name
        for module in _MODULES.values()
        for contract in module.CONTRACTS
    ]
    assert len(names) == len(set(names))


def test_extended_families_are_nonempty():
    assert all(module.CONTRACTS for module in _MODULES.values())


def test_infrastructure_mutators_remain_absent():
    names = {contract.name for contract in infrastructure.CONTRACTS}
    assert not (names & infrastructure.mutation_capable_names())


def test_archive_extraction_operations_remain_absent():
    assert archive.DENIED_EXTRACTION_OPERATIONS


def test_quality_fix_modes_remain_denied():
    assert quality.DENIED_FIX_OR_REMOTE_MODES


def test_data_mutation_flags_remain_denied():
    assert data.DENIED_MUTATION_FLAGS


def test_artifact_mutators_remain_denied():
    assert artifact.DENIED_MUTATORS



def test_terraform_version_registered():
    spec = _spec("infrastructure", "terraform.version")
    contract = _contract("infrastructure", "terraform.version")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_version_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.version")
    contract = _contract("infrastructure", "terraform.version")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_version_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.version")
    contract = _contract("infrastructure", "terraform.version")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_version_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.version")
    contract = _contract("infrastructure", "terraform.version")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_version_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.version")
    contract = _contract("infrastructure", "terraform.version")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_version_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.version")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_version_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.version")
    contract = _contract("infrastructure", "terraform.version")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_version_registered():
    spec = _spec("infrastructure", "tofu.version")
    contract = _contract("infrastructure", "tofu.version")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_version_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.version")
    contract = _contract("infrastructure", "tofu.version")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_version_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.version")
    contract = _contract("infrastructure", "tofu.version")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_version_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.version")
    contract = _contract("infrastructure", "tofu.version")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_version_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.version")
    contract = _contract("infrastructure", "tofu.version")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_version_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.version")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_version_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.version")
    contract = _contract("infrastructure", "tofu.version")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_validate_registered():
    spec = _spec("infrastructure", "terraform.validate")
    contract = _contract("infrastructure", "terraform.validate")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_validate_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.validate")
    contract = _contract("infrastructure", "terraform.validate")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_validate_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.validate")
    contract = _contract("infrastructure", "terraform.validate")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_validate_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.validate")
    contract = _contract("infrastructure", "terraform.validate")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_validate_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.validate")
    contract = _contract("infrastructure", "terraform.validate")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_validate_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.validate")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_validate_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.validate")
    contract = _contract("infrastructure", "terraform.validate")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_validate_registered():
    spec = _spec("infrastructure", "tofu.validate")
    contract = _contract("infrastructure", "tofu.validate")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_validate_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.validate")
    contract = _contract("infrastructure", "tofu.validate")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_validate_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.validate")
    contract = _contract("infrastructure", "tofu.validate")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_validate_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.validate")
    contract = _contract("infrastructure", "tofu.validate")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_validate_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.validate")
    contract = _contract("infrastructure", "tofu.validate")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_validate_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.validate")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_validate_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.validate")
    contract = _contract("infrastructure", "tofu.validate")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_fmt_check_registered():
    spec = _spec("infrastructure", "terraform.fmt_check")
    contract = _contract("infrastructure", "terraform.fmt_check")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_fmt_check_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.fmt_check")
    contract = _contract("infrastructure", "terraform.fmt_check")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_fmt_check_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.fmt_check")
    contract = _contract("infrastructure", "terraform.fmt_check")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_fmt_check_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.fmt_check")
    contract = _contract("infrastructure", "terraform.fmt_check")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_fmt_check_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.fmt_check")
    contract = _contract("infrastructure", "terraform.fmt_check")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_fmt_check_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.fmt_check")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_fmt_check_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.fmt_check")
    contract = _contract("infrastructure", "terraform.fmt_check")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_fmt_check_registered():
    spec = _spec("infrastructure", "tofu.fmt_check")
    contract = _contract("infrastructure", "tofu.fmt_check")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_fmt_check_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.fmt_check")
    contract = _contract("infrastructure", "tofu.fmt_check")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_fmt_check_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.fmt_check")
    contract = _contract("infrastructure", "tofu.fmt_check")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_fmt_check_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.fmt_check")
    contract = _contract("infrastructure", "tofu.fmt_check")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_fmt_check_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.fmt_check")
    contract = _contract("infrastructure", "tofu.fmt_check")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_fmt_check_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.fmt_check")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_fmt_check_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.fmt_check")
    contract = _contract("infrastructure", "tofu.fmt_check")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_providers_registered():
    spec = _spec("infrastructure", "terraform.providers")
    contract = _contract("infrastructure", "terraform.providers")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_providers_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.providers")
    contract = _contract("infrastructure", "terraform.providers")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_providers_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.providers")
    contract = _contract("infrastructure", "terraform.providers")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_providers_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.providers")
    contract = _contract("infrastructure", "terraform.providers")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_providers_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.providers")
    contract = _contract("infrastructure", "terraform.providers")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_providers_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.providers")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_providers_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.providers")
    contract = _contract("infrastructure", "terraform.providers")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_providers_registered():
    spec = _spec("infrastructure", "tofu.providers")
    contract = _contract("infrastructure", "tofu.providers")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_providers_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.providers")
    contract = _contract("infrastructure", "tofu.providers")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_providers_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.providers")
    contract = _contract("infrastructure", "tofu.providers")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_providers_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.providers")
    contract = _contract("infrastructure", "tofu.providers")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_providers_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.providers")
    contract = _contract("infrastructure", "tofu.providers")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_providers_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.providers")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_providers_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.providers")
    contract = _contract("infrastructure", "tofu.providers")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_providers_lock_registered():
    spec = _spec("infrastructure", "terraform.providers_lock")
    contract = _contract("infrastructure", "terraform.providers_lock")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_providers_lock_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.providers_lock")
    contract = _contract("infrastructure", "terraform.providers_lock")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_providers_lock_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.providers_lock")
    contract = _contract("infrastructure", "terraform.providers_lock")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_providers_lock_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.providers_lock")
    contract = _contract("infrastructure", "terraform.providers_lock")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_providers_lock_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.providers_lock")
    contract = _contract("infrastructure", "terraform.providers_lock")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_providers_lock_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.providers_lock")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_providers_lock_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.providers_lock")
    contract = _contract("infrastructure", "terraform.providers_lock")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_providers_lock_registered():
    spec = _spec("infrastructure", "tofu.providers_lock")
    contract = _contract("infrastructure", "tofu.providers_lock")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_providers_lock_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.providers_lock")
    contract = _contract("infrastructure", "tofu.providers_lock")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_providers_lock_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.providers_lock")
    contract = _contract("infrastructure", "tofu.providers_lock")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_providers_lock_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.providers_lock")
    contract = _contract("infrastructure", "tofu.providers_lock")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_providers_lock_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.providers_lock")
    contract = _contract("infrastructure", "tofu.providers_lock")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_providers_lock_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.providers_lock")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_providers_lock_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.providers_lock")
    contract = _contract("infrastructure", "tofu.providers_lock")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_providers_schema_registered():
    spec = _spec("infrastructure", "terraform.providers_schema")
    contract = _contract("infrastructure", "terraform.providers_schema")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_providers_schema_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.providers_schema")
    contract = _contract("infrastructure", "terraform.providers_schema")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_providers_schema_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.providers_schema")
    contract = _contract("infrastructure", "terraform.providers_schema")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_providers_schema_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.providers_schema")
    contract = _contract("infrastructure", "terraform.providers_schema")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_providers_schema_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.providers_schema")
    contract = _contract("infrastructure", "terraform.providers_schema")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_providers_schema_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.providers_schema")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_providers_schema_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.providers_schema")
    contract = _contract("infrastructure", "terraform.providers_schema")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_providers_schema_registered():
    spec = _spec("infrastructure", "tofu.providers_schema")
    contract = _contract("infrastructure", "tofu.providers_schema")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_providers_schema_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.providers_schema")
    contract = _contract("infrastructure", "tofu.providers_schema")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_providers_schema_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.providers_schema")
    contract = _contract("infrastructure", "tofu.providers_schema")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_providers_schema_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.providers_schema")
    contract = _contract("infrastructure", "tofu.providers_schema")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_providers_schema_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.providers_schema")
    contract = _contract("infrastructure", "tofu.providers_schema")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_providers_schema_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.providers_schema")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_providers_schema_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.providers_schema")
    contract = _contract("infrastructure", "tofu.providers_schema")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_workspace_list_registered():
    spec = _spec("infrastructure", "terraform.workspace_list")
    contract = _contract("infrastructure", "terraform.workspace_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_workspace_list_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.workspace_list")
    contract = _contract("infrastructure", "terraform.workspace_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_workspace_list_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.workspace_list")
    contract = _contract("infrastructure", "terraform.workspace_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_workspace_list_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.workspace_list")
    contract = _contract("infrastructure", "terraform.workspace_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_workspace_list_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.workspace_list")
    contract = _contract("infrastructure", "terraform.workspace_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_workspace_list_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.workspace_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_workspace_list_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.workspace_list")
    contract = _contract("infrastructure", "terraform.workspace_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_workspace_list_registered():
    spec = _spec("infrastructure", "tofu.workspace_list")
    contract = _contract("infrastructure", "tofu.workspace_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_workspace_list_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.workspace_list")
    contract = _contract("infrastructure", "tofu.workspace_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_workspace_list_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.workspace_list")
    contract = _contract("infrastructure", "tofu.workspace_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_workspace_list_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.workspace_list")
    contract = _contract("infrastructure", "tofu.workspace_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_workspace_list_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.workspace_list")
    contract = _contract("infrastructure", "tofu.workspace_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_workspace_list_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.workspace_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_workspace_list_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.workspace_list")
    contract = _contract("infrastructure", "tofu.workspace_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_workspace_show_registered():
    spec = _spec("infrastructure", "terraform.workspace_show")
    contract = _contract("infrastructure", "terraform.workspace_show")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_workspace_show_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.workspace_show")
    contract = _contract("infrastructure", "terraform.workspace_show")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_workspace_show_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.workspace_show")
    contract = _contract("infrastructure", "terraform.workspace_show")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_workspace_show_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.workspace_show")
    contract = _contract("infrastructure", "terraform.workspace_show")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_workspace_show_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.workspace_show")
    contract = _contract("infrastructure", "terraform.workspace_show")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_workspace_show_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.workspace_show")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_workspace_show_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.workspace_show")
    contract = _contract("infrastructure", "terraform.workspace_show")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_workspace_show_registered():
    spec = _spec("infrastructure", "tofu.workspace_show")
    contract = _contract("infrastructure", "tofu.workspace_show")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_workspace_show_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.workspace_show")
    contract = _contract("infrastructure", "tofu.workspace_show")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_workspace_show_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.workspace_show")
    contract = _contract("infrastructure", "tofu.workspace_show")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_workspace_show_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.workspace_show")
    contract = _contract("infrastructure", "tofu.workspace_show")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_workspace_show_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.workspace_show")
    contract = _contract("infrastructure", "tofu.workspace_show")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_workspace_show_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.workspace_show")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_workspace_show_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.workspace_show")
    contract = _contract("infrastructure", "tofu.workspace_show")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_state_list_registered():
    spec = _spec("infrastructure", "terraform.state_list")
    contract = _contract("infrastructure", "terraform.state_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_state_list_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.state_list")
    contract = _contract("infrastructure", "terraform.state_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_state_list_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.state_list")
    contract = _contract("infrastructure", "terraform.state_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_state_list_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.state_list")
    contract = _contract("infrastructure", "terraform.state_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_state_list_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.state_list")
    contract = _contract("infrastructure", "terraform.state_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_state_list_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.state_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_state_list_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.state_list")
    contract = _contract("infrastructure", "terraform.state_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_state_list_registered():
    spec = _spec("infrastructure", "tofu.state_list")
    contract = _contract("infrastructure", "tofu.state_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_state_list_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.state_list")
    contract = _contract("infrastructure", "tofu.state_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_state_list_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.state_list")
    contract = _contract("infrastructure", "tofu.state_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_state_list_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.state_list")
    contract = _contract("infrastructure", "tofu.state_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_state_list_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.state_list")
    contract = _contract("infrastructure", "tofu.state_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_state_list_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.state_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_state_list_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.state_list")
    contract = _contract("infrastructure", "tofu.state_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_graph_registered():
    spec = _spec("infrastructure", "terraform.graph")
    contract = _contract("infrastructure", "terraform.graph")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_graph_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.graph")
    contract = _contract("infrastructure", "terraform.graph")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_graph_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.graph")
    contract = _contract("infrastructure", "terraform.graph")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_graph_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.graph")
    contract = _contract("infrastructure", "terraform.graph")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_graph_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.graph")
    contract = _contract("infrastructure", "terraform.graph")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_graph_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.graph")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_graph_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.graph")
    contract = _contract("infrastructure", "terraform.graph")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_graph_registered():
    spec = _spec("infrastructure", "tofu.graph")
    contract = _contract("infrastructure", "tofu.graph")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_graph_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.graph")
    contract = _contract("infrastructure", "tofu.graph")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_graph_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.graph")
    contract = _contract("infrastructure", "tofu.graph")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_graph_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.graph")
    contract = _contract("infrastructure", "tofu.graph")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_graph_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.graph")
    contract = _contract("infrastructure", "tofu.graph")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_graph_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.graph")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_graph_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.graph")
    contract = _contract("infrastructure", "tofu.graph")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_plan_registered():
    spec = _spec("infrastructure", "terraform.plan")
    contract = _contract("infrastructure", "terraform.plan")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_plan_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.plan")
    contract = _contract("infrastructure", "terraform.plan")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_plan_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.plan")
    contract = _contract("infrastructure", "terraform.plan")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_plan_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.plan")
    contract = _contract("infrastructure", "terraform.plan")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_plan_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.plan")
    contract = _contract("infrastructure", "terraform.plan")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_plan_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.plan")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_plan_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.plan")
    contract = _contract("infrastructure", "terraform.plan")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_plan_registered():
    spec = _spec("infrastructure", "tofu.plan")
    contract = _contract("infrastructure", "tofu.plan")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_plan_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.plan")
    contract = _contract("infrastructure", "tofu.plan")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_plan_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.plan")
    contract = _contract("infrastructure", "tofu.plan")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_plan_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.plan")
    contract = _contract("infrastructure", "tofu.plan")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_plan_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.plan")
    contract = _contract("infrastructure", "tofu.plan")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_plan_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.plan")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_plan_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.plan")
    contract = _contract("infrastructure", "tofu.plan")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_init_backend_false_registered():
    spec = _spec("infrastructure", "terraform.init_backend_false")
    contract = _contract("infrastructure", "terraform.init_backend_false")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_init_backend_false_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.init_backend_false")
    contract = _contract("infrastructure", "terraform.init_backend_false")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_init_backend_false_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.init_backend_false")
    contract = _contract("infrastructure", "terraform.init_backend_false")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_init_backend_false_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.init_backend_false")
    contract = _contract("infrastructure", "terraform.init_backend_false")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_init_backend_false_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.init_backend_false")
    contract = _contract("infrastructure", "terraform.init_backend_false")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_init_backend_false_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.init_backend_false")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_init_backend_false_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.init_backend_false")
    contract = _contract("infrastructure", "terraform.init_backend_false")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_init_backend_false_registered():
    spec = _spec("infrastructure", "tofu.init_backend_false")
    contract = _contract("infrastructure", "tofu.init_backend_false")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_init_backend_false_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.init_backend_false")
    contract = _contract("infrastructure", "tofu.init_backend_false")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_init_backend_false_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.init_backend_false")
    contract = _contract("infrastructure", "tofu.init_backend_false")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_init_backend_false_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.init_backend_false")
    contract = _contract("infrastructure", "tofu.init_backend_false")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_init_backend_false_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.init_backend_false")
    contract = _contract("infrastructure", "tofu.init_backend_false")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_init_backend_false_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.init_backend_false")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_init_backend_false_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.init_backend_false")
    contract = _contract("infrastructure", "tofu.init_backend_false")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_terraform_test_registered():
    spec = _spec("infrastructure", "terraform.test")
    contract = _contract("infrastructure", "terraform.test")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_terraform_test_minimal_argv_validates():
    spec = _spec("infrastructure", "terraform.test")
    contract = _contract("infrastructure", "terraform.test")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_terraform_test_rejects_unknown_option():
    spec = _spec("infrastructure", "terraform.test")
    contract = _contract("infrastructure", "terraform.test")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_terraform_test_rejects_nul_argument():
    spec = _spec("infrastructure", "terraform.test")
    contract = _contract("infrastructure", "terraform.test")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_terraform_test_prefix_is_immutable():
    spec = _spec("infrastructure", "terraform.test")
    contract = _contract("infrastructure", "terraform.test")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_terraform_test_metadata_digest_is_stable():
    contract = _contract("infrastructure", "terraform.test")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_terraform_test_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "terraform.test")
    contract = _contract("infrastructure", "terraform.test")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tofu_test_registered():
    spec = _spec("infrastructure", "tofu.test")
    contract = _contract("infrastructure", "tofu.test")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tofu_test_minimal_argv_validates():
    spec = _spec("infrastructure", "tofu.test")
    contract = _contract("infrastructure", "tofu.test")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tofu_test_rejects_unknown_option():
    spec = _spec("infrastructure", "tofu.test")
    contract = _contract("infrastructure", "tofu.test")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tofu_test_rejects_nul_argument():
    spec = _spec("infrastructure", "tofu.test")
    contract = _contract("infrastructure", "tofu.test")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tofu_test_prefix_is_immutable():
    spec = _spec("infrastructure", "tofu.test")
    contract = _contract("infrastructure", "tofu.test")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tofu_test_metadata_digest_is_stable():
    contract = _contract("infrastructure", "tofu.test")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tofu_test_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "tofu.test")
    contract = _contract("infrastructure", "tofu.test")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_version_client_registered():
    spec = _spec("infrastructure", "kubectl.version_client")
    contract = _contract("infrastructure", "kubectl.version_client")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_version_client_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.version_client")
    contract = _contract("infrastructure", "kubectl.version_client")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_version_client_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.version_client")
    contract = _contract("infrastructure", "kubectl.version_client")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_version_client_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.version_client")
    contract = _contract("infrastructure", "kubectl.version_client")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_version_client_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.version_client")
    contract = _contract("infrastructure", "kubectl.version_client")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_version_client_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.version_client")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_version_client_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.version_client")
    contract = _contract("infrastructure", "kubectl.version_client")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_api_resources_registered():
    spec = _spec("infrastructure", "kubectl.api_resources")
    contract = _contract("infrastructure", "kubectl.api_resources")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_api_resources_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.api_resources")
    contract = _contract("infrastructure", "kubectl.api_resources")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_api_resources_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.api_resources")
    contract = _contract("infrastructure", "kubectl.api_resources")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_api_resources_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.api_resources")
    contract = _contract("infrastructure", "kubectl.api_resources")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_api_resources_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.api_resources")
    contract = _contract("infrastructure", "kubectl.api_resources")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_api_resources_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.api_resources")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_api_resources_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.api_resources")
    contract = _contract("infrastructure", "kubectl.api_resources")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_api_versions_registered():
    spec = _spec("infrastructure", "kubectl.api_versions")
    contract = _contract("infrastructure", "kubectl.api_versions")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_api_versions_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.api_versions")
    contract = _contract("infrastructure", "kubectl.api_versions")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_api_versions_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.api_versions")
    contract = _contract("infrastructure", "kubectl.api_versions")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_api_versions_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.api_versions")
    contract = _contract("infrastructure", "kubectl.api_versions")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_api_versions_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.api_versions")
    contract = _contract("infrastructure", "kubectl.api_versions")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_api_versions_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.api_versions")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_api_versions_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.api_versions")
    contract = _contract("infrastructure", "kubectl.api_versions")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_cluster_info_registered():
    spec = _spec("infrastructure", "kubectl.cluster_info")
    contract = _contract("infrastructure", "kubectl.cluster_info")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_cluster_info_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.cluster_info")
    contract = _contract("infrastructure", "kubectl.cluster_info")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_cluster_info_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.cluster_info")
    contract = _contract("infrastructure", "kubectl.cluster_info")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_cluster_info_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.cluster_info")
    contract = _contract("infrastructure", "kubectl.cluster_info")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_cluster_info_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.cluster_info")
    contract = _contract("infrastructure", "kubectl.cluster_info")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_cluster_info_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.cluster_info")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_cluster_info_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.cluster_info")
    contract = _contract("infrastructure", "kubectl.cluster_info")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_current_context_registered():
    spec = _spec("infrastructure", "kubectl.current_context")
    contract = _contract("infrastructure", "kubectl.current_context")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_current_context_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.current_context")
    contract = _contract("infrastructure", "kubectl.current_context")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_current_context_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.current_context")
    contract = _contract("infrastructure", "kubectl.current_context")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_current_context_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.current_context")
    contract = _contract("infrastructure", "kubectl.current_context")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_current_context_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.current_context")
    contract = _contract("infrastructure", "kubectl.current_context")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_current_context_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.current_context")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_current_context_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.current_context")
    contract = _contract("infrastructure", "kubectl.current_context")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_contexts_registered():
    spec = _spec("infrastructure", "kubectl.get_contexts")
    contract = _contract("infrastructure", "kubectl.get_contexts")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_contexts_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_contexts")
    contract = _contract("infrastructure", "kubectl.get_contexts")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_contexts_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_contexts")
    contract = _contract("infrastructure", "kubectl.get_contexts")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_contexts_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_contexts")
    contract = _contract("infrastructure", "kubectl.get_contexts")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_contexts_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_contexts")
    contract = _contract("infrastructure", "kubectl.get_contexts")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_contexts_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_contexts")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_contexts_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_contexts")
    contract = _contract("infrastructure", "kubectl.get_contexts")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_auth_can_i_registered():
    spec = _spec("infrastructure", "kubectl.auth_can_i")
    contract = _contract("infrastructure", "kubectl.auth_can_i")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_auth_can_i_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.auth_can_i")
    contract = _contract("infrastructure", "kubectl.auth_can_i")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_auth_can_i_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.auth_can_i")
    contract = _contract("infrastructure", "kubectl.auth_can_i")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_auth_can_i_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.auth_can_i")
    contract = _contract("infrastructure", "kubectl.auth_can_i")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_auth_can_i_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.auth_can_i")
    contract = _contract("infrastructure", "kubectl.auth_can_i")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_auth_can_i_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.auth_can_i")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_auth_can_i_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.auth_can_i")
    contract = _contract("infrastructure", "kubectl.auth_can_i")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_explain_registered():
    spec = _spec("infrastructure", "kubectl.explain")
    contract = _contract("infrastructure", "kubectl.explain")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_explain_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.explain")
    contract = _contract("infrastructure", "kubectl.explain")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_explain_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.explain")
    contract = _contract("infrastructure", "kubectl.explain")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_explain_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.explain")
    contract = _contract("infrastructure", "kubectl.explain")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_explain_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.explain")
    contract = _contract("infrastructure", "kubectl.explain")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_explain_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.explain")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_explain_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.explain")
    contract = _contract("infrastructure", "kubectl.explain")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_top_pods_registered():
    spec = _spec("infrastructure", "kubectl.top_pods")
    contract = _contract("infrastructure", "kubectl.top_pods")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_top_pods_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.top_pods")
    contract = _contract("infrastructure", "kubectl.top_pods")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_top_pods_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.top_pods")
    contract = _contract("infrastructure", "kubectl.top_pods")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_top_pods_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.top_pods")
    contract = _contract("infrastructure", "kubectl.top_pods")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_top_pods_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.top_pods")
    contract = _contract("infrastructure", "kubectl.top_pods")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_top_pods_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.top_pods")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_top_pods_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.top_pods")
    contract = _contract("infrastructure", "kubectl.top_pods")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_top_nodes_registered():
    spec = _spec("infrastructure", "kubectl.top_nodes")
    contract = _contract("infrastructure", "kubectl.top_nodes")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_top_nodes_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.top_nodes")
    contract = _contract("infrastructure", "kubectl.top_nodes")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_top_nodes_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.top_nodes")
    contract = _contract("infrastructure", "kubectl.top_nodes")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_top_nodes_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.top_nodes")
    contract = _contract("infrastructure", "kubectl.top_nodes")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_top_nodes_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.top_nodes")
    contract = _contract("infrastructure", "kubectl.top_nodes")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_top_nodes_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.top_nodes")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_top_nodes_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.top_nodes")
    contract = _contract("infrastructure", "kubectl.top_nodes")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_pods_registered():
    spec = _spec("infrastructure", "kubectl.get_pods")
    contract = _contract("infrastructure", "kubectl.get_pods")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_pods_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_pods")
    contract = _contract("infrastructure", "kubectl.get_pods")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_pods_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_pods")
    contract = _contract("infrastructure", "kubectl.get_pods")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_pods_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_pods")
    contract = _contract("infrastructure", "kubectl.get_pods")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_pods_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_pods")
    contract = _contract("infrastructure", "kubectl.get_pods")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_pods_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_pods")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_pods_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_pods")
    contract = _contract("infrastructure", "kubectl.get_pods")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_pods_registered():
    spec = _spec("infrastructure", "kubectl.describe_pods")
    contract = _contract("infrastructure", "kubectl.describe_pods")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_pods_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_pods")
    contract = _contract("infrastructure", "kubectl.describe_pods")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_pods_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_pods")
    contract = _contract("infrastructure", "kubectl.describe_pods")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_pods_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_pods")
    contract = _contract("infrastructure", "kubectl.describe_pods")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_pods_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_pods")
    contract = _contract("infrastructure", "kubectl.describe_pods")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_pods_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_pods")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_pods_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_pods")
    contract = _contract("infrastructure", "kubectl.describe_pods")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_deployments_registered():
    spec = _spec("infrastructure", "kubectl.get_deployments")
    contract = _contract("infrastructure", "kubectl.get_deployments")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_deployments_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_deployments")
    contract = _contract("infrastructure", "kubectl.get_deployments")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_deployments_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_deployments")
    contract = _contract("infrastructure", "kubectl.get_deployments")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_deployments_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_deployments")
    contract = _contract("infrastructure", "kubectl.get_deployments")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_deployments_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_deployments")
    contract = _contract("infrastructure", "kubectl.get_deployments")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_deployments_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_deployments")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_deployments_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_deployments")
    contract = _contract("infrastructure", "kubectl.get_deployments")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_deployments_registered():
    spec = _spec("infrastructure", "kubectl.describe_deployments")
    contract = _contract("infrastructure", "kubectl.describe_deployments")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_deployments_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_deployments")
    contract = _contract("infrastructure", "kubectl.describe_deployments")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_deployments_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_deployments")
    contract = _contract("infrastructure", "kubectl.describe_deployments")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_deployments_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_deployments")
    contract = _contract("infrastructure", "kubectl.describe_deployments")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_deployments_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_deployments")
    contract = _contract("infrastructure", "kubectl.describe_deployments")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_deployments_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_deployments")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_deployments_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_deployments")
    contract = _contract("infrastructure", "kubectl.describe_deployments")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_statefulsets_registered():
    spec = _spec("infrastructure", "kubectl.get_statefulsets")
    contract = _contract("infrastructure", "kubectl.get_statefulsets")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_statefulsets_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_statefulsets")
    contract = _contract("infrastructure", "kubectl.get_statefulsets")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_statefulsets_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_statefulsets")
    contract = _contract("infrastructure", "kubectl.get_statefulsets")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_statefulsets_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_statefulsets")
    contract = _contract("infrastructure", "kubectl.get_statefulsets")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_statefulsets_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_statefulsets")
    contract = _contract("infrastructure", "kubectl.get_statefulsets")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_statefulsets_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_statefulsets")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_statefulsets_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_statefulsets")
    contract = _contract("infrastructure", "kubectl.get_statefulsets")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_statefulsets_registered():
    spec = _spec("infrastructure", "kubectl.describe_statefulsets")
    contract = _contract("infrastructure", "kubectl.describe_statefulsets")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_statefulsets_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_statefulsets")
    contract = _contract("infrastructure", "kubectl.describe_statefulsets")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_statefulsets_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_statefulsets")
    contract = _contract("infrastructure", "kubectl.describe_statefulsets")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_statefulsets_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_statefulsets")
    contract = _contract("infrastructure", "kubectl.describe_statefulsets")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_statefulsets_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_statefulsets")
    contract = _contract("infrastructure", "kubectl.describe_statefulsets")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_statefulsets_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_statefulsets")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_statefulsets_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_statefulsets")
    contract = _contract("infrastructure", "kubectl.describe_statefulsets")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_daemonsets_registered():
    spec = _spec("infrastructure", "kubectl.get_daemonsets")
    contract = _contract("infrastructure", "kubectl.get_daemonsets")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_daemonsets_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_daemonsets")
    contract = _contract("infrastructure", "kubectl.get_daemonsets")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_daemonsets_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_daemonsets")
    contract = _contract("infrastructure", "kubectl.get_daemonsets")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_daemonsets_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_daemonsets")
    contract = _contract("infrastructure", "kubectl.get_daemonsets")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_daemonsets_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_daemonsets")
    contract = _contract("infrastructure", "kubectl.get_daemonsets")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_daemonsets_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_daemonsets")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_daemonsets_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_daemonsets")
    contract = _contract("infrastructure", "kubectl.get_daemonsets")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_daemonsets_registered():
    spec = _spec("infrastructure", "kubectl.describe_daemonsets")
    contract = _contract("infrastructure", "kubectl.describe_daemonsets")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_daemonsets_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_daemonsets")
    contract = _contract("infrastructure", "kubectl.describe_daemonsets")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_daemonsets_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_daemonsets")
    contract = _contract("infrastructure", "kubectl.describe_daemonsets")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_daemonsets_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_daemonsets")
    contract = _contract("infrastructure", "kubectl.describe_daemonsets")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_daemonsets_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_daemonsets")
    contract = _contract("infrastructure", "kubectl.describe_daemonsets")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_daemonsets_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_daemonsets")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_daemonsets_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_daemonsets")
    contract = _contract("infrastructure", "kubectl.describe_daemonsets")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_replicasets_registered():
    spec = _spec("infrastructure", "kubectl.get_replicasets")
    contract = _contract("infrastructure", "kubectl.get_replicasets")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_replicasets_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_replicasets")
    contract = _contract("infrastructure", "kubectl.get_replicasets")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_replicasets_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_replicasets")
    contract = _contract("infrastructure", "kubectl.get_replicasets")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_replicasets_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_replicasets")
    contract = _contract("infrastructure", "kubectl.get_replicasets")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_replicasets_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_replicasets")
    contract = _contract("infrastructure", "kubectl.get_replicasets")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_replicasets_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_replicasets")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_replicasets_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_replicasets")
    contract = _contract("infrastructure", "kubectl.get_replicasets")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_replicasets_registered():
    spec = _spec("infrastructure", "kubectl.describe_replicasets")
    contract = _contract("infrastructure", "kubectl.describe_replicasets")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_replicasets_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_replicasets")
    contract = _contract("infrastructure", "kubectl.describe_replicasets")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_replicasets_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_replicasets")
    contract = _contract("infrastructure", "kubectl.describe_replicasets")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_replicasets_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_replicasets")
    contract = _contract("infrastructure", "kubectl.describe_replicasets")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_replicasets_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_replicasets")
    contract = _contract("infrastructure", "kubectl.describe_replicasets")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_replicasets_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_replicasets")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_replicasets_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_replicasets")
    contract = _contract("infrastructure", "kubectl.describe_replicasets")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_services_registered():
    spec = _spec("infrastructure", "kubectl.get_services")
    contract = _contract("infrastructure", "kubectl.get_services")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_services_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_services")
    contract = _contract("infrastructure", "kubectl.get_services")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_services_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_services")
    contract = _contract("infrastructure", "kubectl.get_services")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_services_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_services")
    contract = _contract("infrastructure", "kubectl.get_services")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_services_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_services")
    contract = _contract("infrastructure", "kubectl.get_services")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_services_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_services")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_services_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_services")
    contract = _contract("infrastructure", "kubectl.get_services")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_services_registered():
    spec = _spec("infrastructure", "kubectl.describe_services")
    contract = _contract("infrastructure", "kubectl.describe_services")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_services_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_services")
    contract = _contract("infrastructure", "kubectl.describe_services")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_services_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_services")
    contract = _contract("infrastructure", "kubectl.describe_services")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_services_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_services")
    contract = _contract("infrastructure", "kubectl.describe_services")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_services_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_services")
    contract = _contract("infrastructure", "kubectl.describe_services")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_services_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_services")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_services_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_services")
    contract = _contract("infrastructure", "kubectl.describe_services")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_ingresses_registered():
    spec = _spec("infrastructure", "kubectl.get_ingresses")
    contract = _contract("infrastructure", "kubectl.get_ingresses")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_ingresses_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_ingresses")
    contract = _contract("infrastructure", "kubectl.get_ingresses")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_ingresses_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_ingresses")
    contract = _contract("infrastructure", "kubectl.get_ingresses")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_ingresses_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_ingresses")
    contract = _contract("infrastructure", "kubectl.get_ingresses")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_ingresses_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_ingresses")
    contract = _contract("infrastructure", "kubectl.get_ingresses")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_ingresses_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_ingresses")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_ingresses_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_ingresses")
    contract = _contract("infrastructure", "kubectl.get_ingresses")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_ingresses_registered():
    spec = _spec("infrastructure", "kubectl.describe_ingresses")
    contract = _contract("infrastructure", "kubectl.describe_ingresses")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_ingresses_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_ingresses")
    contract = _contract("infrastructure", "kubectl.describe_ingresses")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_ingresses_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_ingresses")
    contract = _contract("infrastructure", "kubectl.describe_ingresses")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_ingresses_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_ingresses")
    contract = _contract("infrastructure", "kubectl.describe_ingresses")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_ingresses_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_ingresses")
    contract = _contract("infrastructure", "kubectl.describe_ingresses")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_ingresses_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_ingresses")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_ingresses_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_ingresses")
    contract = _contract("infrastructure", "kubectl.describe_ingresses")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_jobs_registered():
    spec = _spec("infrastructure", "kubectl.get_jobs")
    contract = _contract("infrastructure", "kubectl.get_jobs")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_jobs_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_jobs")
    contract = _contract("infrastructure", "kubectl.get_jobs")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_jobs_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_jobs")
    contract = _contract("infrastructure", "kubectl.get_jobs")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_jobs_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_jobs")
    contract = _contract("infrastructure", "kubectl.get_jobs")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_jobs_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_jobs")
    contract = _contract("infrastructure", "kubectl.get_jobs")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_jobs_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_jobs")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_jobs_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_jobs")
    contract = _contract("infrastructure", "kubectl.get_jobs")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_jobs_registered():
    spec = _spec("infrastructure", "kubectl.describe_jobs")
    contract = _contract("infrastructure", "kubectl.describe_jobs")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_jobs_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_jobs")
    contract = _contract("infrastructure", "kubectl.describe_jobs")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_jobs_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_jobs")
    contract = _contract("infrastructure", "kubectl.describe_jobs")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_jobs_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_jobs")
    contract = _contract("infrastructure", "kubectl.describe_jobs")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_jobs_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_jobs")
    contract = _contract("infrastructure", "kubectl.describe_jobs")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_jobs_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_jobs")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_jobs_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_jobs")
    contract = _contract("infrastructure", "kubectl.describe_jobs")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_cronjobs_registered():
    spec = _spec("infrastructure", "kubectl.get_cronjobs")
    contract = _contract("infrastructure", "kubectl.get_cronjobs")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_cronjobs_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_cronjobs")
    contract = _contract("infrastructure", "kubectl.get_cronjobs")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_cronjobs_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_cronjobs")
    contract = _contract("infrastructure", "kubectl.get_cronjobs")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_cronjobs_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_cronjobs")
    contract = _contract("infrastructure", "kubectl.get_cronjobs")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_cronjobs_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_cronjobs")
    contract = _contract("infrastructure", "kubectl.get_cronjobs")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_cronjobs_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_cronjobs")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_cronjobs_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_cronjobs")
    contract = _contract("infrastructure", "kubectl.get_cronjobs")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_cronjobs_registered():
    spec = _spec("infrastructure", "kubectl.describe_cronjobs")
    contract = _contract("infrastructure", "kubectl.describe_cronjobs")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_cronjobs_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_cronjobs")
    contract = _contract("infrastructure", "kubectl.describe_cronjobs")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_cronjobs_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_cronjobs")
    contract = _contract("infrastructure", "kubectl.describe_cronjobs")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_cronjobs_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_cronjobs")
    contract = _contract("infrastructure", "kubectl.describe_cronjobs")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_cronjobs_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_cronjobs")
    contract = _contract("infrastructure", "kubectl.describe_cronjobs")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_cronjobs_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_cronjobs")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_cronjobs_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_cronjobs")
    contract = _contract("infrastructure", "kubectl.describe_cronjobs")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_configmaps_registered():
    spec = _spec("infrastructure", "kubectl.get_configmaps")
    contract = _contract("infrastructure", "kubectl.get_configmaps")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_configmaps_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_configmaps")
    contract = _contract("infrastructure", "kubectl.get_configmaps")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_configmaps_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_configmaps")
    contract = _contract("infrastructure", "kubectl.get_configmaps")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_configmaps_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_configmaps")
    contract = _contract("infrastructure", "kubectl.get_configmaps")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_configmaps_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_configmaps")
    contract = _contract("infrastructure", "kubectl.get_configmaps")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_configmaps_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_configmaps")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_configmaps_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_configmaps")
    contract = _contract("infrastructure", "kubectl.get_configmaps")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_configmaps_registered():
    spec = _spec("infrastructure", "kubectl.describe_configmaps")
    contract = _contract("infrastructure", "kubectl.describe_configmaps")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_configmaps_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_configmaps")
    contract = _contract("infrastructure", "kubectl.describe_configmaps")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_configmaps_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_configmaps")
    contract = _contract("infrastructure", "kubectl.describe_configmaps")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_configmaps_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_configmaps")
    contract = _contract("infrastructure", "kubectl.describe_configmaps")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_configmaps_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_configmaps")
    contract = _contract("infrastructure", "kubectl.describe_configmaps")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_configmaps_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_configmaps")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_configmaps_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_configmaps")
    contract = _contract("infrastructure", "kubectl.describe_configmaps")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_persistentvolumeclaims_registered():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumeclaims")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_persistentvolumeclaims_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumeclaims")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_persistentvolumeclaims_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumeclaims")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_persistentvolumeclaims_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumeclaims")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_persistentvolumeclaims_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumeclaims")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_persistentvolumeclaims_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_persistentvolumeclaims")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_persistentvolumeclaims_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumeclaims")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_persistentvolumeclaims_registered():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumeclaims")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_persistentvolumeclaims_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumeclaims")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_persistentvolumeclaims_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumeclaims")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_persistentvolumeclaims_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumeclaims")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_persistentvolumeclaims_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumeclaims")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_persistentvolumeclaims_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumeclaims")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_persistentvolumeclaims_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumeclaims")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumeclaims")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_persistentvolumes_registered():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumes")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_persistentvolumes_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumes")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_persistentvolumes_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumes")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_persistentvolumes_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumes")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_persistentvolumes_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumes")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_persistentvolumes_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_persistentvolumes")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_persistentvolumes_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.get_persistentvolumes")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_persistentvolumes_registered():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumes")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_persistentvolumes_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumes")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_persistentvolumes_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumes")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_persistentvolumes_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumes")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_persistentvolumes_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumes")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_persistentvolumes_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumes")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_persistentvolumes_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_persistentvolumes")
    contract = _contract("infrastructure", "kubectl.describe_persistentvolumes")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_nodes_registered():
    spec = _spec("infrastructure", "kubectl.get_nodes")
    contract = _contract("infrastructure", "kubectl.get_nodes")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_nodes_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_nodes")
    contract = _contract("infrastructure", "kubectl.get_nodes")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_nodes_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_nodes")
    contract = _contract("infrastructure", "kubectl.get_nodes")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_nodes_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_nodes")
    contract = _contract("infrastructure", "kubectl.get_nodes")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_nodes_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_nodes")
    contract = _contract("infrastructure", "kubectl.get_nodes")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_nodes_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_nodes")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_nodes_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_nodes")
    contract = _contract("infrastructure", "kubectl.get_nodes")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_nodes_registered():
    spec = _spec("infrastructure", "kubectl.describe_nodes")
    contract = _contract("infrastructure", "kubectl.describe_nodes")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_nodes_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_nodes")
    contract = _contract("infrastructure", "kubectl.describe_nodes")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_nodes_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_nodes")
    contract = _contract("infrastructure", "kubectl.describe_nodes")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_nodes_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_nodes")
    contract = _contract("infrastructure", "kubectl.describe_nodes")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_nodes_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_nodes")
    contract = _contract("infrastructure", "kubectl.describe_nodes")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_nodes_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_nodes")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_nodes_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_nodes")
    contract = _contract("infrastructure", "kubectl.describe_nodes")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_namespaces_registered():
    spec = _spec("infrastructure", "kubectl.get_namespaces")
    contract = _contract("infrastructure", "kubectl.get_namespaces")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_namespaces_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_namespaces")
    contract = _contract("infrastructure", "kubectl.get_namespaces")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_namespaces_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_namespaces")
    contract = _contract("infrastructure", "kubectl.get_namespaces")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_namespaces_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_namespaces")
    contract = _contract("infrastructure", "kubectl.get_namespaces")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_namespaces_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_namespaces")
    contract = _contract("infrastructure", "kubectl.get_namespaces")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_namespaces_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_namespaces")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_namespaces_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_namespaces")
    contract = _contract("infrastructure", "kubectl.get_namespaces")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_namespaces_registered():
    spec = _spec("infrastructure", "kubectl.describe_namespaces")
    contract = _contract("infrastructure", "kubectl.describe_namespaces")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_namespaces_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_namespaces")
    contract = _contract("infrastructure", "kubectl.describe_namespaces")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_namespaces_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_namespaces")
    contract = _contract("infrastructure", "kubectl.describe_namespaces")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_namespaces_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_namespaces")
    contract = _contract("infrastructure", "kubectl.describe_namespaces")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_namespaces_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_namespaces")
    contract = _contract("infrastructure", "kubectl.describe_namespaces")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_namespaces_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_namespaces")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_namespaces_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_namespaces")
    contract = _contract("infrastructure", "kubectl.describe_namespaces")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_events_registered():
    spec = _spec("infrastructure", "kubectl.get_events")
    contract = _contract("infrastructure", "kubectl.get_events")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_events_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_events")
    contract = _contract("infrastructure", "kubectl.get_events")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_events_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_events")
    contract = _contract("infrastructure", "kubectl.get_events")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_events_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_events")
    contract = _contract("infrastructure", "kubectl.get_events")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_events_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_events")
    contract = _contract("infrastructure", "kubectl.get_events")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_events_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_events")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_events_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_events")
    contract = _contract("infrastructure", "kubectl.get_events")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_events_registered():
    spec = _spec("infrastructure", "kubectl.describe_events")
    contract = _contract("infrastructure", "kubectl.describe_events")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_events_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_events")
    contract = _contract("infrastructure", "kubectl.describe_events")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_events_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_events")
    contract = _contract("infrastructure", "kubectl.describe_events")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_events_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_events")
    contract = _contract("infrastructure", "kubectl.describe_events")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_events_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_events")
    contract = _contract("infrastructure", "kubectl.describe_events")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_events_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_events")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_events_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_events")
    contract = _contract("infrastructure", "kubectl.describe_events")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_serviceaccounts_registered():
    spec = _spec("infrastructure", "kubectl.get_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.get_serviceaccounts")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_serviceaccounts_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.get_serviceaccounts")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_serviceaccounts_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.get_serviceaccounts")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_serviceaccounts_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.get_serviceaccounts")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_serviceaccounts_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.get_serviceaccounts")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_serviceaccounts_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_serviceaccounts")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_serviceaccounts_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.get_serviceaccounts")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_serviceaccounts_registered():
    spec = _spec("infrastructure", "kubectl.describe_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.describe_serviceaccounts")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_serviceaccounts_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.describe_serviceaccounts")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_serviceaccounts_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.describe_serviceaccounts")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_serviceaccounts_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.describe_serviceaccounts")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_serviceaccounts_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.describe_serviceaccounts")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_serviceaccounts_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_serviceaccounts")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_serviceaccounts_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_serviceaccounts")
    contract = _contract("infrastructure", "kubectl.describe_serviceaccounts")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_networkpolicies_registered():
    spec = _spec("infrastructure", "kubectl.get_networkpolicies")
    contract = _contract("infrastructure", "kubectl.get_networkpolicies")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_networkpolicies_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_networkpolicies")
    contract = _contract("infrastructure", "kubectl.get_networkpolicies")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_networkpolicies_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_networkpolicies")
    contract = _contract("infrastructure", "kubectl.get_networkpolicies")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_networkpolicies_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_networkpolicies")
    contract = _contract("infrastructure", "kubectl.get_networkpolicies")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_networkpolicies_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_networkpolicies")
    contract = _contract("infrastructure", "kubectl.get_networkpolicies")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_networkpolicies_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_networkpolicies")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_networkpolicies_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_networkpolicies")
    contract = _contract("infrastructure", "kubectl.get_networkpolicies")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_networkpolicies_registered():
    spec = _spec("infrastructure", "kubectl.describe_networkpolicies")
    contract = _contract("infrastructure", "kubectl.describe_networkpolicies")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_networkpolicies_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_networkpolicies")
    contract = _contract("infrastructure", "kubectl.describe_networkpolicies")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_networkpolicies_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_networkpolicies")
    contract = _contract("infrastructure", "kubectl.describe_networkpolicies")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_networkpolicies_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_networkpolicies")
    contract = _contract("infrastructure", "kubectl.describe_networkpolicies")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_networkpolicies_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_networkpolicies")
    contract = _contract("infrastructure", "kubectl.describe_networkpolicies")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_networkpolicies_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_networkpolicies")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_networkpolicies_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_networkpolicies")
    contract = _contract("infrastructure", "kubectl.describe_networkpolicies")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_get_horizontalpodautoscalers_registered():
    spec = _spec("infrastructure", "kubectl.get_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.get_horizontalpodautoscalers")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_get_horizontalpodautoscalers_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.get_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.get_horizontalpodautoscalers")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_get_horizontalpodautoscalers_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.get_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.get_horizontalpodautoscalers")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_get_horizontalpodautoscalers_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.get_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.get_horizontalpodautoscalers")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_get_horizontalpodautoscalers_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.get_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.get_horizontalpodautoscalers")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_get_horizontalpodautoscalers_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.get_horizontalpodautoscalers")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_get_horizontalpodautoscalers_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.get_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.get_horizontalpodautoscalers")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_kubectl_describe_horizontalpodautoscalers_registered():
    spec = _spec("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_kubectl_describe_horizontalpodautoscalers_minimal_argv_validates():
    spec = _spec("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_kubectl_describe_horizontalpodautoscalers_rejects_unknown_option():
    spec = _spec("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_kubectl_describe_horizontalpodautoscalers_rejects_nul_argument():
    spec = _spec("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_kubectl_describe_horizontalpodautoscalers_prefix_is_immutable():
    spec = _spec("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_kubectl_describe_horizontalpodautoscalers_metadata_digest_is_stable():
    contract = _contract("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_kubectl_describe_horizontalpodautoscalers_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    contract = _contract("infrastructure", "kubectl.describe_horizontalpodautoscalers")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_helm_version_registered():
    spec = _spec("infrastructure", "helm.version")
    contract = _contract("infrastructure", "helm.version")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_helm_version_minimal_argv_validates():
    spec = _spec("infrastructure", "helm.version")
    contract = _contract("infrastructure", "helm.version")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_helm_version_rejects_unknown_option():
    spec = _spec("infrastructure", "helm.version")
    contract = _contract("infrastructure", "helm.version")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_helm_version_rejects_nul_argument():
    spec = _spec("infrastructure", "helm.version")
    contract = _contract("infrastructure", "helm.version")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_helm_version_prefix_is_immutable():
    spec = _spec("infrastructure", "helm.version")
    contract = _contract("infrastructure", "helm.version")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_helm_version_metadata_digest_is_stable():
    contract = _contract("infrastructure", "helm.version")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_helm_version_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "helm.version")
    contract = _contract("infrastructure", "helm.version")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_helm_env_registered():
    spec = _spec("infrastructure", "helm.env")
    contract = _contract("infrastructure", "helm.env")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_helm_env_minimal_argv_validates():
    spec = _spec("infrastructure", "helm.env")
    contract = _contract("infrastructure", "helm.env")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_helm_env_rejects_unknown_option():
    spec = _spec("infrastructure", "helm.env")
    contract = _contract("infrastructure", "helm.env")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_helm_env_rejects_nul_argument():
    spec = _spec("infrastructure", "helm.env")
    contract = _contract("infrastructure", "helm.env")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_helm_env_prefix_is_immutable():
    spec = _spec("infrastructure", "helm.env")
    contract = _contract("infrastructure", "helm.env")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_helm_env_metadata_digest_is_stable():
    contract = _contract("infrastructure", "helm.env")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_helm_env_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "helm.env")
    contract = _contract("infrastructure", "helm.env")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_helm_lint_registered():
    spec = _spec("infrastructure", "helm.lint")
    contract = _contract("infrastructure", "helm.lint")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_helm_lint_minimal_argv_validates():
    spec = _spec("infrastructure", "helm.lint")
    contract = _contract("infrastructure", "helm.lint")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_helm_lint_rejects_unknown_option():
    spec = _spec("infrastructure", "helm.lint")
    contract = _contract("infrastructure", "helm.lint")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_helm_lint_rejects_nul_argument():
    spec = _spec("infrastructure", "helm.lint")
    contract = _contract("infrastructure", "helm.lint")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_helm_lint_prefix_is_immutable():
    spec = _spec("infrastructure", "helm.lint")
    contract = _contract("infrastructure", "helm.lint")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_helm_lint_metadata_digest_is_stable():
    contract = _contract("infrastructure", "helm.lint")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_helm_lint_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "helm.lint")
    contract = _contract("infrastructure", "helm.lint")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_helm_template_registered():
    spec = _spec("infrastructure", "helm.template")
    contract = _contract("infrastructure", "helm.template")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_helm_template_minimal_argv_validates():
    spec = _spec("infrastructure", "helm.template")
    contract = _contract("infrastructure", "helm.template")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_helm_template_rejects_unknown_option():
    spec = _spec("infrastructure", "helm.template")
    contract = _contract("infrastructure", "helm.template")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_helm_template_rejects_nul_argument():
    spec = _spec("infrastructure", "helm.template")
    contract = _contract("infrastructure", "helm.template")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_helm_template_prefix_is_immutable():
    spec = _spec("infrastructure", "helm.template")
    contract = _contract("infrastructure", "helm.template")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_helm_template_metadata_digest_is_stable():
    contract = _contract("infrastructure", "helm.template")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_helm_template_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "helm.template")
    contract = _contract("infrastructure", "helm.template")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_helm_show_chart_registered():
    spec = _spec("infrastructure", "helm.show_chart")
    contract = _contract("infrastructure", "helm.show_chart")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_helm_show_chart_minimal_argv_validates():
    spec = _spec("infrastructure", "helm.show_chart")
    contract = _contract("infrastructure", "helm.show_chart")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_helm_show_chart_rejects_unknown_option():
    spec = _spec("infrastructure", "helm.show_chart")
    contract = _contract("infrastructure", "helm.show_chart")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_helm_show_chart_rejects_nul_argument():
    spec = _spec("infrastructure", "helm.show_chart")
    contract = _contract("infrastructure", "helm.show_chart")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_helm_show_chart_prefix_is_immutable():
    spec = _spec("infrastructure", "helm.show_chart")
    contract = _contract("infrastructure", "helm.show_chart")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_helm_show_chart_metadata_digest_is_stable():
    contract = _contract("infrastructure", "helm.show_chart")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_helm_show_chart_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "helm.show_chart")
    contract = _contract("infrastructure", "helm.show_chart")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_helm_show_values_registered():
    spec = _spec("infrastructure", "helm.show_values")
    contract = _contract("infrastructure", "helm.show_values")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_helm_show_values_minimal_argv_validates():
    spec = _spec("infrastructure", "helm.show_values")
    contract = _contract("infrastructure", "helm.show_values")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_helm_show_values_rejects_unknown_option():
    spec = _spec("infrastructure", "helm.show_values")
    contract = _contract("infrastructure", "helm.show_values")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_helm_show_values_rejects_nul_argument():
    spec = _spec("infrastructure", "helm.show_values")
    contract = _contract("infrastructure", "helm.show_values")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_helm_show_values_prefix_is_immutable():
    spec = _spec("infrastructure", "helm.show_values")
    contract = _contract("infrastructure", "helm.show_values")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_helm_show_values_metadata_digest_is_stable():
    contract = _contract("infrastructure", "helm.show_values")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_helm_show_values_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "helm.show_values")
    contract = _contract("infrastructure", "helm.show_values")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_helm_show_readme_registered():
    spec = _spec("infrastructure", "helm.show_readme")
    contract = _contract("infrastructure", "helm.show_readme")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_helm_show_readme_minimal_argv_validates():
    spec = _spec("infrastructure", "helm.show_readme")
    contract = _contract("infrastructure", "helm.show_readme")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_helm_show_readme_rejects_unknown_option():
    spec = _spec("infrastructure", "helm.show_readme")
    contract = _contract("infrastructure", "helm.show_readme")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_helm_show_readme_rejects_nul_argument():
    spec = _spec("infrastructure", "helm.show_readme")
    contract = _contract("infrastructure", "helm.show_readme")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_helm_show_readme_prefix_is_immutable():
    spec = _spec("infrastructure", "helm.show_readme")
    contract = _contract("infrastructure", "helm.show_readme")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_helm_show_readme_metadata_digest_is_stable():
    contract = _contract("infrastructure", "helm.show_readme")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_helm_show_readme_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "helm.show_readme")
    contract = _contract("infrastructure", "helm.show_readme")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_helm_dependency_list_registered():
    spec = _spec("infrastructure", "helm.dependency_list")
    contract = _contract("infrastructure", "helm.dependency_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_helm_dependency_list_minimal_argv_validates():
    spec = _spec("infrastructure", "helm.dependency_list")
    contract = _contract("infrastructure", "helm.dependency_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_helm_dependency_list_rejects_unknown_option():
    spec = _spec("infrastructure", "helm.dependency_list")
    contract = _contract("infrastructure", "helm.dependency_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_helm_dependency_list_rejects_nul_argument():
    spec = _spec("infrastructure", "helm.dependency_list")
    contract = _contract("infrastructure", "helm.dependency_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_helm_dependency_list_prefix_is_immutable():
    spec = _spec("infrastructure", "helm.dependency_list")
    contract = _contract("infrastructure", "helm.dependency_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_helm_dependency_list_metadata_digest_is_stable():
    contract = _contract("infrastructure", "helm.dependency_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_helm_dependency_list_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "helm.dependency_list")
    contract = _contract("infrastructure", "helm.dependency_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_helm_repo_list_registered():
    spec = _spec("infrastructure", "helm.repo_list")
    contract = _contract("infrastructure", "helm.repo_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_helm_repo_list_minimal_argv_validates():
    spec = _spec("infrastructure", "helm.repo_list")
    contract = _contract("infrastructure", "helm.repo_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_helm_repo_list_rejects_unknown_option():
    spec = _spec("infrastructure", "helm.repo_list")
    contract = _contract("infrastructure", "helm.repo_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_helm_repo_list_rejects_nul_argument():
    spec = _spec("infrastructure", "helm.repo_list")
    contract = _contract("infrastructure", "helm.repo_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_helm_repo_list_prefix_is_immutable():
    spec = _spec("infrastructure", "helm.repo_list")
    contract = _contract("infrastructure", "helm.repo_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_helm_repo_list_metadata_digest_is_stable():
    contract = _contract("infrastructure", "helm.repo_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_helm_repo_list_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "helm.repo_list")
    contract = _contract("infrastructure", "helm.repo_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_helm_search_repo_registered():
    spec = _spec("infrastructure", "helm.search_repo")
    contract = _contract("infrastructure", "helm.search_repo")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_helm_search_repo_minimal_argv_validates():
    spec = _spec("infrastructure", "helm.search_repo")
    contract = _contract("infrastructure", "helm.search_repo")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_helm_search_repo_rejects_unknown_option():
    spec = _spec("infrastructure", "helm.search_repo")
    contract = _contract("infrastructure", "helm.search_repo")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_helm_search_repo_rejects_nul_argument():
    spec = _spec("infrastructure", "helm.search_repo")
    contract = _contract("infrastructure", "helm.search_repo")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_helm_search_repo_prefix_is_immutable():
    spec = _spec("infrastructure", "helm.search_repo")
    contract = _contract("infrastructure", "helm.search_repo")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_helm_search_repo_metadata_digest_is_stable():
    contract = _contract("infrastructure", "helm.search_repo")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_helm_search_repo_path_escape_is_rejected_when_applicable():
    spec = _spec("infrastructure", "helm.search_repo")
    contract = _contract("infrastructure", "helm.search_repo")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_jq_filter_registered():
    spec = _spec("data", "jq.filter")
    contract = _contract("data", "jq.filter")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_jq_filter_minimal_argv_validates():
    spec = _spec("data", "jq.filter")
    contract = _contract("data", "jq.filter")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_jq_filter_rejects_unknown_option():
    spec = _spec("data", "jq.filter")
    contract = _contract("data", "jq.filter")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_jq_filter_rejects_nul_argument():
    spec = _spec("data", "jq.filter")
    contract = _contract("data", "jq.filter")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_jq_filter_prefix_is_immutable():
    spec = _spec("data", "jq.filter")
    contract = _contract("data", "jq.filter")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_jq_filter_metadata_digest_is_stable():
    contract = _contract("data", "jq.filter")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_jq_filter_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "jq.filter")
    contract = _contract("data", "jq.filter")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_jq_slurp_registered():
    spec = _spec("data", "jq.slurp")
    contract = _contract("data", "jq.slurp")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_jq_slurp_minimal_argv_validates():
    spec = _spec("data", "jq.slurp")
    contract = _contract("data", "jq.slurp")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_jq_slurp_rejects_unknown_option():
    spec = _spec("data", "jq.slurp")
    contract = _contract("data", "jq.slurp")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_jq_slurp_rejects_nul_argument():
    spec = _spec("data", "jq.slurp")
    contract = _contract("data", "jq.slurp")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_jq_slurp_prefix_is_immutable():
    spec = _spec("data", "jq.slurp")
    contract = _contract("data", "jq.slurp")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_jq_slurp_metadata_digest_is_stable():
    contract = _contract("data", "jq.slurp")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_jq_slurp_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "jq.slurp")
    contract = _contract("data", "jq.slurp")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_jq_raw_input_registered():
    spec = _spec("data", "jq.raw_input")
    contract = _contract("data", "jq.raw_input")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_jq_raw_input_minimal_argv_validates():
    spec = _spec("data", "jq.raw_input")
    contract = _contract("data", "jq.raw_input")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_jq_raw_input_rejects_unknown_option():
    spec = _spec("data", "jq.raw_input")
    contract = _contract("data", "jq.raw_input")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_jq_raw_input_rejects_nul_argument():
    spec = _spec("data", "jq.raw_input")
    contract = _contract("data", "jq.raw_input")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_jq_raw_input_prefix_is_immutable():
    spec = _spec("data", "jq.raw_input")
    contract = _contract("data", "jq.raw_input")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_jq_raw_input_metadata_digest_is_stable():
    contract = _contract("data", "jq.raw_input")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_jq_raw_input_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "jq.raw_input")
    contract = _contract("data", "jq.raw_input")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_jq_null_input_registered():
    spec = _spec("data", "jq.null_input")
    contract = _contract("data", "jq.null_input")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_jq_null_input_minimal_argv_validates():
    spec = _spec("data", "jq.null_input")
    contract = _contract("data", "jq.null_input")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_jq_null_input_rejects_unknown_option():
    spec = _spec("data", "jq.null_input")
    contract = _contract("data", "jq.null_input")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_jq_null_input_rejects_nul_argument():
    spec = _spec("data", "jq.null_input")
    contract = _contract("data", "jq.null_input")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_jq_null_input_prefix_is_immutable():
    spec = _spec("data", "jq.null_input")
    contract = _contract("data", "jq.null_input")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_jq_null_input_metadata_digest_is_stable():
    contract = _contract("data", "jq.null_input")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_jq_null_input_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "jq.null_input")
    contract = _contract("data", "jq.null_input")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_jq_seq_registered():
    spec = _spec("data", "jq.seq")
    contract = _contract("data", "jq.seq")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_jq_seq_minimal_argv_validates():
    spec = _spec("data", "jq.seq")
    contract = _contract("data", "jq.seq")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_jq_seq_rejects_unknown_option():
    spec = _spec("data", "jq.seq")
    contract = _contract("data", "jq.seq")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_jq_seq_rejects_nul_argument():
    spec = _spec("data", "jq.seq")
    contract = _contract("data", "jq.seq")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_jq_seq_prefix_is_immutable():
    spec = _spec("data", "jq.seq")
    contract = _contract("data", "jq.seq")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_jq_seq_metadata_digest_is_stable():
    contract = _contract("data", "jq.seq")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_jq_seq_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "jq.seq")
    contract = _contract("data", "jq.seq")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_yq_eval_registered():
    spec = _spec("data", "yq.eval")
    contract = _contract("data", "yq.eval")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_yq_eval_minimal_argv_validates():
    spec = _spec("data", "yq.eval")
    contract = _contract("data", "yq.eval")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_yq_eval_rejects_unknown_option():
    spec = _spec("data", "yq.eval")
    contract = _contract("data", "yq.eval")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_yq_eval_rejects_nul_argument():
    spec = _spec("data", "yq.eval")
    contract = _contract("data", "yq.eval")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_yq_eval_prefix_is_immutable():
    spec = _spec("data", "yq.eval")
    contract = _contract("data", "yq.eval")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_yq_eval_metadata_digest_is_stable():
    contract = _contract("data", "yq.eval")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_yq_eval_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "yq.eval")
    contract = _contract("data", "yq.eval")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_yq_eval_all_registered():
    spec = _spec("data", "yq.eval_all")
    contract = _contract("data", "yq.eval_all")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_yq_eval_all_minimal_argv_validates():
    spec = _spec("data", "yq.eval_all")
    contract = _contract("data", "yq.eval_all")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_yq_eval_all_rejects_unknown_option():
    spec = _spec("data", "yq.eval_all")
    contract = _contract("data", "yq.eval_all")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_yq_eval_all_rejects_nul_argument():
    spec = _spec("data", "yq.eval_all")
    contract = _contract("data", "yq.eval_all")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_yq_eval_all_prefix_is_immutable():
    spec = _spec("data", "yq.eval_all")
    contract = _contract("data", "yq.eval_all")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_yq_eval_all_metadata_digest_is_stable():
    contract = _contract("data", "yq.eval_all")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_yq_eval_all_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "yq.eval_all")
    contract = _contract("data", "yq.eval_all")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_yq_properties_registered():
    spec = _spec("data", "yq.properties")
    contract = _contract("data", "yq.properties")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_yq_properties_minimal_argv_validates():
    spec = _spec("data", "yq.properties")
    contract = _contract("data", "yq.properties")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_yq_properties_rejects_unknown_option():
    spec = _spec("data", "yq.properties")
    contract = _contract("data", "yq.properties")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_yq_properties_rejects_nul_argument():
    spec = _spec("data", "yq.properties")
    contract = _contract("data", "yq.properties")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_yq_properties_prefix_is_immutable():
    spec = _spec("data", "yq.properties")
    contract = _contract("data", "yq.properties")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_yq_properties_metadata_digest_is_stable():
    contract = _contract("data", "yq.properties")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_yq_properties_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "yq.properties")
    contract = _contract("data", "yq.properties")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_yq_json_registered():
    spec = _spec("data", "yq.json")
    contract = _contract("data", "yq.json")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_yq_json_minimal_argv_validates():
    spec = _spec("data", "yq.json")
    contract = _contract("data", "yq.json")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_yq_json_rejects_unknown_option():
    spec = _spec("data", "yq.json")
    contract = _contract("data", "yq.json")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_yq_json_rejects_nul_argument():
    spec = _spec("data", "yq.json")
    contract = _contract("data", "yq.json")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_yq_json_prefix_is_immutable():
    spec = _spec("data", "yq.json")
    contract = _contract("data", "yq.json")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_yq_json_metadata_digest_is_stable():
    contract = _contract("data", "yq.json")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_yq_json_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "yq.json")
    contract = _contract("data", "yq.json")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_rg_search_registered():
    spec = _spec("data", "rg.search")
    contract = _contract("data", "rg.search")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_rg_search_minimal_argv_validates():
    spec = _spec("data", "rg.search")
    contract = _contract("data", "rg.search")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_rg_search_rejects_unknown_option():
    spec = _spec("data", "rg.search")
    contract = _contract("data", "rg.search")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_rg_search_rejects_nul_argument():
    spec = _spec("data", "rg.search")
    contract = _contract("data", "rg.search")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_rg_search_prefix_is_immutable():
    spec = _spec("data", "rg.search")
    contract = _contract("data", "rg.search")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_rg_search_metadata_digest_is_stable():
    contract = _contract("data", "rg.search")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_rg_search_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "rg.search")
    contract = _contract("data", "rg.search")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_rg_files_registered():
    spec = _spec("data", "rg.files")
    contract = _contract("data", "rg.files")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_rg_files_minimal_argv_validates():
    spec = _spec("data", "rg.files")
    contract = _contract("data", "rg.files")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_rg_files_rejects_unknown_option():
    spec = _spec("data", "rg.files")
    contract = _contract("data", "rg.files")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_rg_files_rejects_nul_argument():
    spec = _spec("data", "rg.files")
    contract = _contract("data", "rg.files")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_rg_files_prefix_is_immutable():
    spec = _spec("data", "rg.files")
    contract = _contract("data", "rg.files")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_rg_files_metadata_digest_is_stable():
    contract = _contract("data", "rg.files")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_rg_files_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "rg.files")
    contract = _contract("data", "rg.files")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_rg_files_with_matches_registered():
    spec = _spec("data", "rg.files_with_matches")
    contract = _contract("data", "rg.files_with_matches")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_rg_files_with_matches_minimal_argv_validates():
    spec = _spec("data", "rg.files_with_matches")
    contract = _contract("data", "rg.files_with_matches")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_rg_files_with_matches_rejects_unknown_option():
    spec = _spec("data", "rg.files_with_matches")
    contract = _contract("data", "rg.files_with_matches")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_rg_files_with_matches_rejects_nul_argument():
    spec = _spec("data", "rg.files_with_matches")
    contract = _contract("data", "rg.files_with_matches")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_rg_files_with_matches_prefix_is_immutable():
    spec = _spec("data", "rg.files_with_matches")
    contract = _contract("data", "rg.files_with_matches")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_rg_files_with_matches_metadata_digest_is_stable():
    contract = _contract("data", "rg.files_with_matches")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_rg_files_with_matches_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "rg.files_with_matches")
    contract = _contract("data", "rg.files_with_matches")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_rg_count_registered():
    spec = _spec("data", "rg.count")
    contract = _contract("data", "rg.count")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_rg_count_minimal_argv_validates():
    spec = _spec("data", "rg.count")
    contract = _contract("data", "rg.count")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_rg_count_rejects_unknown_option():
    spec = _spec("data", "rg.count")
    contract = _contract("data", "rg.count")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_rg_count_rejects_nul_argument():
    spec = _spec("data", "rg.count")
    contract = _contract("data", "rg.count")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_rg_count_prefix_is_immutable():
    spec = _spec("data", "rg.count")
    contract = _contract("data", "rg.count")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_rg_count_metadata_digest_is_stable():
    contract = _contract("data", "rg.count")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_rg_count_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "rg.count")
    contract = _contract("data", "rg.count")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_rg_json_registered():
    spec = _spec("data", "rg.json")
    contract = _contract("data", "rg.json")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_rg_json_minimal_argv_validates():
    spec = _spec("data", "rg.json")
    contract = _contract("data", "rg.json")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_rg_json_rejects_unknown_option():
    spec = _spec("data", "rg.json")
    contract = _contract("data", "rg.json")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_rg_json_rejects_nul_argument():
    spec = _spec("data", "rg.json")
    contract = _contract("data", "rg.json")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_rg_json_prefix_is_immutable():
    spec = _spec("data", "rg.json")
    contract = _contract("data", "rg.json")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_rg_json_metadata_digest_is_stable():
    contract = _contract("data", "rg.json")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_rg_json_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "rg.json")
    contract = _contract("data", "rg.json")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_fd_search_registered():
    spec = _spec("data", "fd.search")
    contract = _contract("data", "fd.search")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_fd_search_minimal_argv_validates():
    spec = _spec("data", "fd.search")
    contract = _contract("data", "fd.search")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_fd_search_rejects_unknown_option():
    spec = _spec("data", "fd.search")
    contract = _contract("data", "fd.search")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_fd_search_rejects_nul_argument():
    spec = _spec("data", "fd.search")
    contract = _contract("data", "fd.search")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_fd_search_prefix_is_immutable():
    spec = _spec("data", "fd.search")
    contract = _contract("data", "fd.search")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_fd_search_metadata_digest_is_stable():
    contract = _contract("data", "fd.search")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_fd_search_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "fd.search")
    contract = _contract("data", "fd.search")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_fd_files_registered():
    spec = _spec("data", "fd.files")
    contract = _contract("data", "fd.files")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_fd_files_minimal_argv_validates():
    spec = _spec("data", "fd.files")
    contract = _contract("data", "fd.files")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_fd_files_rejects_unknown_option():
    spec = _spec("data", "fd.files")
    contract = _contract("data", "fd.files")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_fd_files_rejects_nul_argument():
    spec = _spec("data", "fd.files")
    contract = _contract("data", "fd.files")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_fd_files_prefix_is_immutable():
    spec = _spec("data", "fd.files")
    contract = _contract("data", "fd.files")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_fd_files_metadata_digest_is_stable():
    contract = _contract("data", "fd.files")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_fd_files_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "fd.files")
    contract = _contract("data", "fd.files")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_fd_directories_registered():
    spec = _spec("data", "fd.directories")
    contract = _contract("data", "fd.directories")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_fd_directories_minimal_argv_validates():
    spec = _spec("data", "fd.directories")
    contract = _contract("data", "fd.directories")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_fd_directories_rejects_unknown_option():
    spec = _spec("data", "fd.directories")
    contract = _contract("data", "fd.directories")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_fd_directories_rejects_nul_argument():
    spec = _spec("data", "fd.directories")
    contract = _contract("data", "fd.directories")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_fd_directories_prefix_is_immutable():
    spec = _spec("data", "fd.directories")
    contract = _contract("data", "fd.directories")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_fd_directories_metadata_digest_is_stable():
    contract = _contract("data", "fd.directories")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_fd_directories_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "fd.directories")
    contract = _contract("data", "fd.directories")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_fd_symlinks_registered():
    spec = _spec("data", "fd.symlinks")
    contract = _contract("data", "fd.symlinks")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_fd_symlinks_minimal_argv_validates():
    spec = _spec("data", "fd.symlinks")
    contract = _contract("data", "fd.symlinks")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_fd_symlinks_rejects_unknown_option():
    spec = _spec("data", "fd.symlinks")
    contract = _contract("data", "fd.symlinks")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_fd_symlinks_rejects_nul_argument():
    spec = _spec("data", "fd.symlinks")
    contract = _contract("data", "fd.symlinks")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_fd_symlinks_prefix_is_immutable():
    spec = _spec("data", "fd.symlinks")
    contract = _contract("data", "fd.symlinks")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_fd_symlinks_metadata_digest_is_stable():
    contract = _contract("data", "fd.symlinks")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_fd_symlinks_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "fd.symlinks")
    contract = _contract("data", "fd.symlinks")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tree_list_registered():
    spec = _spec("data", "tree.list")
    contract = _contract("data", "tree.list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tree_list_minimal_argv_validates():
    spec = _spec("data", "tree.list")
    contract = _contract("data", "tree.list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tree_list_rejects_unknown_option():
    spec = _spec("data", "tree.list")
    contract = _contract("data", "tree.list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tree_list_rejects_nul_argument():
    spec = _spec("data", "tree.list")
    contract = _contract("data", "tree.list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tree_list_prefix_is_immutable():
    spec = _spec("data", "tree.list")
    contract = _contract("data", "tree.list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tree_list_metadata_digest_is_stable():
    contract = _contract("data", "tree.list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tree_list_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "tree.list")
    contract = _contract("data", "tree.list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tree_json_registered():
    spec = _spec("data", "tree.json")
    contract = _contract("data", "tree.json")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tree_json_minimal_argv_validates():
    spec = _spec("data", "tree.json")
    contract = _contract("data", "tree.json")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tree_json_rejects_unknown_option():
    spec = _spec("data", "tree.json")
    contract = _contract("data", "tree.json")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tree_json_rejects_nul_argument():
    spec = _spec("data", "tree.json")
    contract = _contract("data", "tree.json")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tree_json_prefix_is_immutable():
    spec = _spec("data", "tree.json")
    contract = _contract("data", "tree.json")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tree_json_metadata_digest_is_stable():
    contract = _contract("data", "tree.json")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tree_json_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "tree.json")
    contract = _contract("data", "tree.json")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_tree_xml_registered():
    spec = _spec("data", "tree.xml")
    contract = _contract("data", "tree.xml")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_tree_xml_minimal_argv_validates():
    spec = _spec("data", "tree.xml")
    contract = _contract("data", "tree.xml")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_tree_xml_rejects_unknown_option():
    spec = _spec("data", "tree.xml")
    contract = _contract("data", "tree.xml")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_tree_xml_rejects_nul_argument():
    spec = _spec("data", "tree.xml")
    contract = _contract("data", "tree.xml")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_tree_xml_prefix_is_immutable():
    spec = _spec("data", "tree.xml")
    contract = _contract("data", "tree.xml")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_tree_xml_metadata_digest_is_stable():
    contract = _contract("data", "tree.xml")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_tree_xml_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "tree.xml")
    contract = _contract("data", "tree.xml")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_xmllint_format_registered():
    spec = _spec("data", "xmllint.format")
    contract = _contract("data", "xmllint.format")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_xmllint_format_minimal_argv_validates():
    spec = _spec("data", "xmllint.format")
    contract = _contract("data", "xmllint.format")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_xmllint_format_rejects_unknown_option():
    spec = _spec("data", "xmllint.format")
    contract = _contract("data", "xmllint.format")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_xmllint_format_rejects_nul_argument():
    spec = _spec("data", "xmllint.format")
    contract = _contract("data", "xmllint.format")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_xmllint_format_prefix_is_immutable():
    spec = _spec("data", "xmllint.format")
    contract = _contract("data", "xmllint.format")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_xmllint_format_metadata_digest_is_stable():
    contract = _contract("data", "xmllint.format")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_xmllint_format_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "xmllint.format")
    contract = _contract("data", "xmllint.format")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_xmllint_xpath_registered():
    spec = _spec("data", "xmllint.xpath")
    contract = _contract("data", "xmllint.xpath")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_xmllint_xpath_minimal_argv_validates():
    spec = _spec("data", "xmllint.xpath")
    contract = _contract("data", "xmllint.xpath")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_xmllint_xpath_rejects_unknown_option():
    spec = _spec("data", "xmllint.xpath")
    contract = _contract("data", "xmllint.xpath")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_xmllint_xpath_rejects_nul_argument():
    spec = _spec("data", "xmllint.xpath")
    contract = _contract("data", "xmllint.xpath")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_xmllint_xpath_prefix_is_immutable():
    spec = _spec("data", "xmllint.xpath")
    contract = _contract("data", "xmllint.xpath")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_xmllint_xpath_metadata_digest_is_stable():
    contract = _contract("data", "xmllint.xpath")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_xmllint_xpath_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "xmllint.xpath")
    contract = _contract("data", "xmllint.xpath")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_xmllint_validate_registered():
    spec = _spec("data", "xmllint.validate")
    contract = _contract("data", "xmllint.validate")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_xmllint_validate_minimal_argv_validates():
    spec = _spec("data", "xmllint.validate")
    contract = _contract("data", "xmllint.validate")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_xmllint_validate_rejects_unknown_option():
    spec = _spec("data", "xmllint.validate")
    contract = _contract("data", "xmllint.validate")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_xmllint_validate_rejects_nul_argument():
    spec = _spec("data", "xmllint.validate")
    contract = _contract("data", "xmllint.validate")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_xmllint_validate_prefix_is_immutable():
    spec = _spec("data", "xmllint.validate")
    contract = _contract("data", "xmllint.validate")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_xmllint_validate_metadata_digest_is_stable():
    contract = _contract("data", "xmllint.validate")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_xmllint_validate_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "xmllint.validate")
    contract = _contract("data", "xmllint.validate")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_cloc_count_registered():
    spec = _spec("data", "cloc.count")
    contract = _contract("data", "cloc.count")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_cloc_count_minimal_argv_validates():
    spec = _spec("data", "cloc.count")
    contract = _contract("data", "cloc.count")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_cloc_count_rejects_unknown_option():
    spec = _spec("data", "cloc.count")
    contract = _contract("data", "cloc.count")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_cloc_count_rejects_nul_argument():
    spec = _spec("data", "cloc.count")
    contract = _contract("data", "cloc.count")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_cloc_count_prefix_is_immutable():
    spec = _spec("data", "cloc.count")
    contract = _contract("data", "cloc.count")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_cloc_count_metadata_digest_is_stable():
    contract = _contract("data", "cloc.count")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_cloc_count_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "cloc.count")
    contract = _contract("data", "cloc.count")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_scc_count_registered():
    spec = _spec("data", "scc.count")
    contract = _contract("data", "scc.count")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_scc_count_minimal_argv_validates():
    spec = _spec("data", "scc.count")
    contract = _contract("data", "scc.count")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_scc_count_rejects_unknown_option():
    spec = _spec("data", "scc.count")
    contract = _contract("data", "scc.count")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_scc_count_rejects_nul_argument():
    spec = _spec("data", "scc.count")
    contract = _contract("data", "scc.count")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_scc_count_prefix_is_immutable():
    spec = _spec("data", "scc.count")
    contract = _contract("data", "scc.count")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_scc_count_metadata_digest_is_stable():
    contract = _contract("data", "scc.count")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_scc_count_path_escape_is_rejected_when_applicable():
    spec = _spec("data", "scc.count")
    contract = _contract("data", "scc.count")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_file_registered():
    spec = _spec("artifact", "artifact.file")
    contract = _contract("artifact", "artifact.file")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_file_minimal_argv_validates():
    spec = _spec("artifact", "artifact.file")
    contract = _contract("artifact", "artifact.file")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_file_rejects_unknown_option():
    spec = _spec("artifact", "artifact.file")
    contract = _contract("artifact", "artifact.file")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_file_rejects_nul_argument():
    spec = _spec("artifact", "artifact.file")
    contract = _contract("artifact", "artifact.file")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_file_prefix_is_immutable():
    spec = _spec("artifact", "artifact.file")
    contract = _contract("artifact", "artifact.file")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_file_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.file")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_file_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.file")
    contract = _contract("artifact", "artifact.file")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_strings_registered():
    spec = _spec("artifact", "artifact.strings")
    contract = _contract("artifact", "artifact.strings")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_strings_minimal_argv_validates():
    spec = _spec("artifact", "artifact.strings")
    contract = _contract("artifact", "artifact.strings")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_strings_rejects_unknown_option():
    spec = _spec("artifact", "artifact.strings")
    contract = _contract("artifact", "artifact.strings")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_strings_rejects_nul_argument():
    spec = _spec("artifact", "artifact.strings")
    contract = _contract("artifact", "artifact.strings")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_strings_prefix_is_immutable():
    spec = _spec("artifact", "artifact.strings")
    contract = _contract("artifact", "artifact.strings")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_strings_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.strings")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_strings_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.strings")
    contract = _contract("artifact", "artifact.strings")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_readelf_headers_registered():
    spec = _spec("artifact", "artifact.readelf_headers")
    contract = _contract("artifact", "artifact.readelf_headers")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_readelf_headers_minimal_argv_validates():
    spec = _spec("artifact", "artifact.readelf_headers")
    contract = _contract("artifact", "artifact.readelf_headers")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_readelf_headers_rejects_unknown_option():
    spec = _spec("artifact", "artifact.readelf_headers")
    contract = _contract("artifact", "artifact.readelf_headers")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_readelf_headers_rejects_nul_argument():
    spec = _spec("artifact", "artifact.readelf_headers")
    contract = _contract("artifact", "artifact.readelf_headers")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_readelf_headers_prefix_is_immutable():
    spec = _spec("artifact", "artifact.readelf_headers")
    contract = _contract("artifact", "artifact.readelf_headers")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_readelf_headers_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.readelf_headers")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_readelf_headers_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.readelf_headers")
    contract = _contract("artifact", "artifact.readelf_headers")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_readelf_sections_registered():
    spec = _spec("artifact", "artifact.readelf_sections")
    contract = _contract("artifact", "artifact.readelf_sections")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_readelf_sections_minimal_argv_validates():
    spec = _spec("artifact", "artifact.readelf_sections")
    contract = _contract("artifact", "artifact.readelf_sections")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_readelf_sections_rejects_unknown_option():
    spec = _spec("artifact", "artifact.readelf_sections")
    contract = _contract("artifact", "artifact.readelf_sections")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_readelf_sections_rejects_nul_argument():
    spec = _spec("artifact", "artifact.readelf_sections")
    contract = _contract("artifact", "artifact.readelf_sections")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_readelf_sections_prefix_is_immutable():
    spec = _spec("artifact", "artifact.readelf_sections")
    contract = _contract("artifact", "artifact.readelf_sections")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_readelf_sections_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.readelf_sections")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_readelf_sections_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.readelf_sections")
    contract = _contract("artifact", "artifact.readelf_sections")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_readelf_symbols_registered():
    spec = _spec("artifact", "artifact.readelf_symbols")
    contract = _contract("artifact", "artifact.readelf_symbols")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_readelf_symbols_minimal_argv_validates():
    spec = _spec("artifact", "artifact.readelf_symbols")
    contract = _contract("artifact", "artifact.readelf_symbols")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_readelf_symbols_rejects_unknown_option():
    spec = _spec("artifact", "artifact.readelf_symbols")
    contract = _contract("artifact", "artifact.readelf_symbols")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_readelf_symbols_rejects_nul_argument():
    spec = _spec("artifact", "artifact.readelf_symbols")
    contract = _contract("artifact", "artifact.readelf_symbols")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_readelf_symbols_prefix_is_immutable():
    spec = _spec("artifact", "artifact.readelf_symbols")
    contract = _contract("artifact", "artifact.readelf_symbols")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_readelf_symbols_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.readelf_symbols")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_readelf_symbols_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.readelf_symbols")
    contract = _contract("artifact", "artifact.readelf_symbols")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_readelf_relocs_registered():
    spec = _spec("artifact", "artifact.readelf_relocs")
    contract = _contract("artifact", "artifact.readelf_relocs")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_readelf_relocs_minimal_argv_validates():
    spec = _spec("artifact", "artifact.readelf_relocs")
    contract = _contract("artifact", "artifact.readelf_relocs")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_readelf_relocs_rejects_unknown_option():
    spec = _spec("artifact", "artifact.readelf_relocs")
    contract = _contract("artifact", "artifact.readelf_relocs")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_readelf_relocs_rejects_nul_argument():
    spec = _spec("artifact", "artifact.readelf_relocs")
    contract = _contract("artifact", "artifact.readelf_relocs")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_readelf_relocs_prefix_is_immutable():
    spec = _spec("artifact", "artifact.readelf_relocs")
    contract = _contract("artifact", "artifact.readelf_relocs")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_readelf_relocs_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.readelf_relocs")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_readelf_relocs_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.readelf_relocs")
    contract = _contract("artifact", "artifact.readelf_relocs")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_readelf_dynamic_registered():
    spec = _spec("artifact", "artifact.readelf_dynamic")
    contract = _contract("artifact", "artifact.readelf_dynamic")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_readelf_dynamic_minimal_argv_validates():
    spec = _spec("artifact", "artifact.readelf_dynamic")
    contract = _contract("artifact", "artifact.readelf_dynamic")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_readelf_dynamic_rejects_unknown_option():
    spec = _spec("artifact", "artifact.readelf_dynamic")
    contract = _contract("artifact", "artifact.readelf_dynamic")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_readelf_dynamic_rejects_nul_argument():
    spec = _spec("artifact", "artifact.readelf_dynamic")
    contract = _contract("artifact", "artifact.readelf_dynamic")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_readelf_dynamic_prefix_is_immutable():
    spec = _spec("artifact", "artifact.readelf_dynamic")
    contract = _contract("artifact", "artifact.readelf_dynamic")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_readelf_dynamic_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.readelf_dynamic")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_readelf_dynamic_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.readelf_dynamic")
    contract = _contract("artifact", "artifact.readelf_dynamic")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_readelf_notes_registered():
    spec = _spec("artifact", "artifact.readelf_notes")
    contract = _contract("artifact", "artifact.readelf_notes")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_readelf_notes_minimal_argv_validates():
    spec = _spec("artifact", "artifact.readelf_notes")
    contract = _contract("artifact", "artifact.readelf_notes")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_readelf_notes_rejects_unknown_option():
    spec = _spec("artifact", "artifact.readelf_notes")
    contract = _contract("artifact", "artifact.readelf_notes")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_readelf_notes_rejects_nul_argument():
    spec = _spec("artifact", "artifact.readelf_notes")
    contract = _contract("artifact", "artifact.readelf_notes")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_readelf_notes_prefix_is_immutable():
    spec = _spec("artifact", "artifact.readelf_notes")
    contract = _contract("artifact", "artifact.readelf_notes")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_readelf_notes_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.readelf_notes")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_readelf_notes_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.readelf_notes")
    contract = _contract("artifact", "artifact.readelf_notes")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_readelf_version_info_registered():
    spec = _spec("artifact", "artifact.readelf_version_info")
    contract = _contract("artifact", "artifact.readelf_version_info")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_readelf_version_info_minimal_argv_validates():
    spec = _spec("artifact", "artifact.readelf_version_info")
    contract = _contract("artifact", "artifact.readelf_version_info")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_readelf_version_info_rejects_unknown_option():
    spec = _spec("artifact", "artifact.readelf_version_info")
    contract = _contract("artifact", "artifact.readelf_version_info")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_readelf_version_info_rejects_nul_argument():
    spec = _spec("artifact", "artifact.readelf_version_info")
    contract = _contract("artifact", "artifact.readelf_version_info")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_readelf_version_info_prefix_is_immutable():
    spec = _spec("artifact", "artifact.readelf_version_info")
    contract = _contract("artifact", "artifact.readelf_version_info")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_readelf_version_info_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.readelf_version_info")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_readelf_version_info_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.readelf_version_info")
    contract = _contract("artifact", "artifact.readelf_version_info")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_readelf_debug_registered():
    spec = _spec("artifact", "artifact.readelf_debug")
    contract = _contract("artifact", "artifact.readelf_debug")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_readelf_debug_minimal_argv_validates():
    spec = _spec("artifact", "artifact.readelf_debug")
    contract = _contract("artifact", "artifact.readelf_debug")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_readelf_debug_rejects_unknown_option():
    spec = _spec("artifact", "artifact.readelf_debug")
    contract = _contract("artifact", "artifact.readelf_debug")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_readelf_debug_rejects_nul_argument():
    spec = _spec("artifact", "artifact.readelf_debug")
    contract = _contract("artifact", "artifact.readelf_debug")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_readelf_debug_prefix_is_immutable():
    spec = _spec("artifact", "artifact.readelf_debug")
    contract = _contract("artifact", "artifact.readelf_debug")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_readelf_debug_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.readelf_debug")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_readelf_debug_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.readelf_debug")
    contract = _contract("artifact", "artifact.readelf_debug")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_objdump_headers_registered():
    spec = _spec("artifact", "artifact.objdump_headers")
    contract = _contract("artifact", "artifact.objdump_headers")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_objdump_headers_minimal_argv_validates():
    spec = _spec("artifact", "artifact.objdump_headers")
    contract = _contract("artifact", "artifact.objdump_headers")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_objdump_headers_rejects_unknown_option():
    spec = _spec("artifact", "artifact.objdump_headers")
    contract = _contract("artifact", "artifact.objdump_headers")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_objdump_headers_rejects_nul_argument():
    spec = _spec("artifact", "artifact.objdump_headers")
    contract = _contract("artifact", "artifact.objdump_headers")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_objdump_headers_prefix_is_immutable():
    spec = _spec("artifact", "artifact.objdump_headers")
    contract = _contract("artifact", "artifact.objdump_headers")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_objdump_headers_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.objdump_headers")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_objdump_headers_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.objdump_headers")
    contract = _contract("artifact", "artifact.objdump_headers")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_objdump_sections_registered():
    spec = _spec("artifact", "artifact.objdump_sections")
    contract = _contract("artifact", "artifact.objdump_sections")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_objdump_sections_minimal_argv_validates():
    spec = _spec("artifact", "artifact.objdump_sections")
    contract = _contract("artifact", "artifact.objdump_sections")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_objdump_sections_rejects_unknown_option():
    spec = _spec("artifact", "artifact.objdump_sections")
    contract = _contract("artifact", "artifact.objdump_sections")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_objdump_sections_rejects_nul_argument():
    spec = _spec("artifact", "artifact.objdump_sections")
    contract = _contract("artifact", "artifact.objdump_sections")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_objdump_sections_prefix_is_immutable():
    spec = _spec("artifact", "artifact.objdump_sections")
    contract = _contract("artifact", "artifact.objdump_sections")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_objdump_sections_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.objdump_sections")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_objdump_sections_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.objdump_sections")
    contract = _contract("artifact", "artifact.objdump_sections")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_objdump_symbols_registered():
    spec = _spec("artifact", "artifact.objdump_symbols")
    contract = _contract("artifact", "artifact.objdump_symbols")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_objdump_symbols_minimal_argv_validates():
    spec = _spec("artifact", "artifact.objdump_symbols")
    contract = _contract("artifact", "artifact.objdump_symbols")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_objdump_symbols_rejects_unknown_option():
    spec = _spec("artifact", "artifact.objdump_symbols")
    contract = _contract("artifact", "artifact.objdump_symbols")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_objdump_symbols_rejects_nul_argument():
    spec = _spec("artifact", "artifact.objdump_symbols")
    contract = _contract("artifact", "artifact.objdump_symbols")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_objdump_symbols_prefix_is_immutable():
    spec = _spec("artifact", "artifact.objdump_symbols")
    contract = _contract("artifact", "artifact.objdump_symbols")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_objdump_symbols_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.objdump_symbols")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_objdump_symbols_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.objdump_symbols")
    contract = _contract("artifact", "artifact.objdump_symbols")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_objdump_disassemble_registered():
    spec = _spec("artifact", "artifact.objdump_disassemble")
    contract = _contract("artifact", "artifact.objdump_disassemble")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_objdump_disassemble_minimal_argv_validates():
    spec = _spec("artifact", "artifact.objdump_disassemble")
    contract = _contract("artifact", "artifact.objdump_disassemble")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_objdump_disassemble_rejects_unknown_option():
    spec = _spec("artifact", "artifact.objdump_disassemble")
    contract = _contract("artifact", "artifact.objdump_disassemble")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_objdump_disassemble_rejects_nul_argument():
    spec = _spec("artifact", "artifact.objdump_disassemble")
    contract = _contract("artifact", "artifact.objdump_disassemble")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_objdump_disassemble_prefix_is_immutable():
    spec = _spec("artifact", "artifact.objdump_disassemble")
    contract = _contract("artifact", "artifact.objdump_disassemble")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_objdump_disassemble_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.objdump_disassemble")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_objdump_disassemble_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.objdump_disassemble")
    contract = _contract("artifact", "artifact.objdump_disassemble")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_objdump_contents_registered():
    spec = _spec("artifact", "artifact.objdump_contents")
    contract = _contract("artifact", "artifact.objdump_contents")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_objdump_contents_minimal_argv_validates():
    spec = _spec("artifact", "artifact.objdump_contents")
    contract = _contract("artifact", "artifact.objdump_contents")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_objdump_contents_rejects_unknown_option():
    spec = _spec("artifact", "artifact.objdump_contents")
    contract = _contract("artifact", "artifact.objdump_contents")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_objdump_contents_rejects_nul_argument():
    spec = _spec("artifact", "artifact.objdump_contents")
    contract = _contract("artifact", "artifact.objdump_contents")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_objdump_contents_prefix_is_immutable():
    spec = _spec("artifact", "artifact.objdump_contents")
    contract = _contract("artifact", "artifact.objdump_contents")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_objdump_contents_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.objdump_contents")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_objdump_contents_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.objdump_contents")
    contract = _contract("artifact", "artifact.objdump_contents")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_nm_registered():
    spec = _spec("artifact", "artifact.nm")
    contract = _contract("artifact", "artifact.nm")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_nm_minimal_argv_validates():
    spec = _spec("artifact", "artifact.nm")
    contract = _contract("artifact", "artifact.nm")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_nm_rejects_unknown_option():
    spec = _spec("artifact", "artifact.nm")
    contract = _contract("artifact", "artifact.nm")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_nm_rejects_nul_argument():
    spec = _spec("artifact", "artifact.nm")
    contract = _contract("artifact", "artifact.nm")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_nm_prefix_is_immutable():
    spec = _spec("artifact", "artifact.nm")
    contract = _contract("artifact", "artifact.nm")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_nm_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.nm")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_nm_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.nm")
    contract = _contract("artifact", "artifact.nm")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_size_registered():
    spec = _spec("artifact", "artifact.size")
    contract = _contract("artifact", "artifact.size")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_size_minimal_argv_validates():
    spec = _spec("artifact", "artifact.size")
    contract = _contract("artifact", "artifact.size")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_size_rejects_unknown_option():
    spec = _spec("artifact", "artifact.size")
    contract = _contract("artifact", "artifact.size")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_size_rejects_nul_argument():
    spec = _spec("artifact", "artifact.size")
    contract = _contract("artifact", "artifact.size")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_size_prefix_is_immutable():
    spec = _spec("artifact", "artifact.size")
    contract = _contract("artifact", "artifact.size")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_size_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.size")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_size_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.size")
    contract = _contract("artifact", "artifact.size")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_ar_list_registered():
    spec = _spec("artifact", "artifact.ar_list")
    contract = _contract("artifact", "artifact.ar_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_ar_list_minimal_argv_validates():
    spec = _spec("artifact", "artifact.ar_list")
    contract = _contract("artifact", "artifact.ar_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_ar_list_rejects_unknown_option():
    spec = _spec("artifact", "artifact.ar_list")
    contract = _contract("artifact", "artifact.ar_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_ar_list_rejects_nul_argument():
    spec = _spec("artifact", "artifact.ar_list")
    contract = _contract("artifact", "artifact.ar_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_ar_list_prefix_is_immutable():
    spec = _spec("artifact", "artifact.ar_list")
    contract = _contract("artifact", "artifact.ar_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_ar_list_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.ar_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_ar_list_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.ar_list")
    contract = _contract("artifact", "artifact.ar_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_ar_verbose_list_registered():
    spec = _spec("artifact", "artifact.ar_verbose_list")
    contract = _contract("artifact", "artifact.ar_verbose_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_ar_verbose_list_minimal_argv_validates():
    spec = _spec("artifact", "artifact.ar_verbose_list")
    contract = _contract("artifact", "artifact.ar_verbose_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_ar_verbose_list_rejects_unknown_option():
    spec = _spec("artifact", "artifact.ar_verbose_list")
    contract = _contract("artifact", "artifact.ar_verbose_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_ar_verbose_list_rejects_nul_argument():
    spec = _spec("artifact", "artifact.ar_verbose_list")
    contract = _contract("artifact", "artifact.ar_verbose_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_ar_verbose_list_prefix_is_immutable():
    spec = _spec("artifact", "artifact.ar_verbose_list")
    contract = _contract("artifact", "artifact.ar_verbose_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_ar_verbose_list_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.ar_verbose_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_ar_verbose_list_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.ar_verbose_list")
    contract = _contract("artifact", "artifact.ar_verbose_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_otool_libraries_registered():
    spec = _spec("artifact", "artifact.otool_libraries")
    contract = _contract("artifact", "artifact.otool_libraries")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_otool_libraries_minimal_argv_validates():
    spec = _spec("artifact", "artifact.otool_libraries")
    contract = _contract("artifact", "artifact.otool_libraries")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_otool_libraries_rejects_unknown_option():
    spec = _spec("artifact", "artifact.otool_libraries")
    contract = _contract("artifact", "artifact.otool_libraries")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_otool_libraries_rejects_nul_argument():
    spec = _spec("artifact", "artifact.otool_libraries")
    contract = _contract("artifact", "artifact.otool_libraries")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_otool_libraries_prefix_is_immutable():
    spec = _spec("artifact", "artifact.otool_libraries")
    contract = _contract("artifact", "artifact.otool_libraries")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_otool_libraries_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.otool_libraries")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_otool_libraries_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.otool_libraries")
    contract = _contract("artifact", "artifact.otool_libraries")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_otool_headers_registered():
    spec = _spec("artifact", "artifact.otool_headers")
    contract = _contract("artifact", "artifact.otool_headers")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_otool_headers_minimal_argv_validates():
    spec = _spec("artifact", "artifact.otool_headers")
    contract = _contract("artifact", "artifact.otool_headers")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_otool_headers_rejects_unknown_option():
    spec = _spec("artifact", "artifact.otool_headers")
    contract = _contract("artifact", "artifact.otool_headers")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_otool_headers_rejects_nul_argument():
    spec = _spec("artifact", "artifact.otool_headers")
    contract = _contract("artifact", "artifact.otool_headers")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_otool_headers_prefix_is_immutable():
    spec = _spec("artifact", "artifact.otool_headers")
    contract = _contract("artifact", "artifact.otool_headers")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_otool_headers_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.otool_headers")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_otool_headers_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.otool_headers")
    contract = _contract("artifact", "artifact.otool_headers")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_otool_symbols_registered():
    spec = _spec("artifact", "artifact.otool_symbols")
    contract = _contract("artifact", "artifact.otool_symbols")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_otool_symbols_minimal_argv_validates():
    spec = _spec("artifact", "artifact.otool_symbols")
    contract = _contract("artifact", "artifact.otool_symbols")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_otool_symbols_rejects_unknown_option():
    spec = _spec("artifact", "artifact.otool_symbols")
    contract = _contract("artifact", "artifact.otool_symbols")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_otool_symbols_rejects_nul_argument():
    spec = _spec("artifact", "artifact.otool_symbols")
    contract = _contract("artifact", "artifact.otool_symbols")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_otool_symbols_prefix_is_immutable():
    spec = _spec("artifact", "artifact.otool_symbols")
    contract = _contract("artifact", "artifact.otool_symbols")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_otool_symbols_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.otool_symbols")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_otool_symbols_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.otool_symbols")
    contract = _contract("artifact", "artifact.otool_symbols")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_codesign_display_registered():
    spec = _spec("artifact", "artifact.codesign_display")
    contract = _contract("artifact", "artifact.codesign_display")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_codesign_display_minimal_argv_validates():
    spec = _spec("artifact", "artifact.codesign_display")
    contract = _contract("artifact", "artifact.codesign_display")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_codesign_display_rejects_unknown_option():
    spec = _spec("artifact", "artifact.codesign_display")
    contract = _contract("artifact", "artifact.codesign_display")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_codesign_display_rejects_nul_argument():
    spec = _spec("artifact", "artifact.codesign_display")
    contract = _contract("artifact", "artifact.codesign_display")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_codesign_display_prefix_is_immutable():
    spec = _spec("artifact", "artifact.codesign_display")
    contract = _contract("artifact", "artifact.codesign_display")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_codesign_display_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.codesign_display")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_codesign_display_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.codesign_display")
    contract = _contract("artifact", "artifact.codesign_display")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_wasm2wat_registered():
    spec = _spec("artifact", "artifact.wasm2wat")
    contract = _contract("artifact", "artifact.wasm2wat")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_wasm2wat_minimal_argv_validates():
    spec = _spec("artifact", "artifact.wasm2wat")
    contract = _contract("artifact", "artifact.wasm2wat")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_wasm2wat_rejects_unknown_option():
    spec = _spec("artifact", "artifact.wasm2wat")
    contract = _contract("artifact", "artifact.wasm2wat")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_wasm2wat_rejects_nul_argument():
    spec = _spec("artifact", "artifact.wasm2wat")
    contract = _contract("artifact", "artifact.wasm2wat")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_wasm2wat_prefix_is_immutable():
    spec = _spec("artifact", "artifact.wasm2wat")
    contract = _contract("artifact", "artifact.wasm2wat")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_wasm2wat_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.wasm2wat")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_wasm2wat_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.wasm2wat")
    contract = _contract("artifact", "artifact.wasm2wat")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_wasm_objdump_headers_registered():
    spec = _spec("artifact", "artifact.wasm_objdump_headers")
    contract = _contract("artifact", "artifact.wasm_objdump_headers")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_wasm_objdump_headers_minimal_argv_validates():
    spec = _spec("artifact", "artifact.wasm_objdump_headers")
    contract = _contract("artifact", "artifact.wasm_objdump_headers")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_wasm_objdump_headers_rejects_unknown_option():
    spec = _spec("artifact", "artifact.wasm_objdump_headers")
    contract = _contract("artifact", "artifact.wasm_objdump_headers")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_wasm_objdump_headers_rejects_nul_argument():
    spec = _spec("artifact", "artifact.wasm_objdump_headers")
    contract = _contract("artifact", "artifact.wasm_objdump_headers")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_wasm_objdump_headers_prefix_is_immutable():
    spec = _spec("artifact", "artifact.wasm_objdump_headers")
    contract = _contract("artifact", "artifact.wasm_objdump_headers")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_wasm_objdump_headers_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.wasm_objdump_headers")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_wasm_objdump_headers_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.wasm_objdump_headers")
    contract = _contract("artifact", "artifact.wasm_objdump_headers")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_wasm_objdump_details_registered():
    spec = _spec("artifact", "artifact.wasm_objdump_details")
    contract = _contract("artifact", "artifact.wasm_objdump_details")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_wasm_objdump_details_minimal_argv_validates():
    spec = _spec("artifact", "artifact.wasm_objdump_details")
    contract = _contract("artifact", "artifact.wasm_objdump_details")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_wasm_objdump_details_rejects_unknown_option():
    spec = _spec("artifact", "artifact.wasm_objdump_details")
    contract = _contract("artifact", "artifact.wasm_objdump_details")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_wasm_objdump_details_rejects_nul_argument():
    spec = _spec("artifact", "artifact.wasm_objdump_details")
    contract = _contract("artifact", "artifact.wasm_objdump_details")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_wasm_objdump_details_prefix_is_immutable():
    spec = _spec("artifact", "artifact.wasm_objdump_details")
    contract = _contract("artifact", "artifact.wasm_objdump_details")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_wasm_objdump_details_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.wasm_objdump_details")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_wasm_objdump_details_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.wasm_objdump_details")
    contract = _contract("artifact", "artifact.wasm_objdump_details")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_artifact_wasm_objdump_disassemble_registered():
    spec = _spec("artifact", "artifact.wasm_objdump_disassemble")
    contract = _contract("artifact", "artifact.wasm_objdump_disassemble")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_artifact_wasm_objdump_disassemble_minimal_argv_validates():
    spec = _spec("artifact", "artifact.wasm_objdump_disassemble")
    contract = _contract("artifact", "artifact.wasm_objdump_disassemble")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_artifact_wasm_objdump_disassemble_rejects_unknown_option():
    spec = _spec("artifact", "artifact.wasm_objdump_disassemble")
    contract = _contract("artifact", "artifact.wasm_objdump_disassemble")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_artifact_wasm_objdump_disassemble_rejects_nul_argument():
    spec = _spec("artifact", "artifact.wasm_objdump_disassemble")
    contract = _contract("artifact", "artifact.wasm_objdump_disassemble")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_artifact_wasm_objdump_disassemble_prefix_is_immutable():
    spec = _spec("artifact", "artifact.wasm_objdump_disassemble")
    contract = _contract("artifact", "artifact.wasm_objdump_disassemble")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_artifact_wasm_objdump_disassemble_metadata_digest_is_stable():
    contract = _contract("artifact", "artifact.wasm_objdump_disassemble")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_artifact_wasm_objdump_disassemble_path_escape_is_rejected_when_applicable():
    spec = _spec("artifact", "artifact.wasm_objdump_disassemble")
    contract = _contract("artifact", "artifact.wasm_objdump_disassemble")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_tar_list_registered():
    spec = _spec("archive", "archive.tar_list")
    contract = _contract("archive", "archive.tar_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_tar_list_minimal_argv_validates():
    spec = _spec("archive", "archive.tar_list")
    contract = _contract("archive", "archive.tar_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_tar_list_rejects_unknown_option():
    spec = _spec("archive", "archive.tar_list")
    contract = _contract("archive", "archive.tar_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_tar_list_rejects_nul_argument():
    spec = _spec("archive", "archive.tar_list")
    contract = _contract("archive", "archive.tar_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_tar_list_prefix_is_immutable():
    spec = _spec("archive", "archive.tar_list")
    contract = _contract("archive", "archive.tar_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_tar_list_metadata_digest_is_stable():
    contract = _contract("archive", "archive.tar_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_tar_list_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.tar_list")
    contract = _contract("archive", "archive.tar_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_tar_compare_registered():
    spec = _spec("archive", "archive.tar_compare")
    contract = _contract("archive", "archive.tar_compare")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_tar_compare_minimal_argv_validates():
    spec = _spec("archive", "archive.tar_compare")
    contract = _contract("archive", "archive.tar_compare")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_tar_compare_rejects_unknown_option():
    spec = _spec("archive", "archive.tar_compare")
    contract = _contract("archive", "archive.tar_compare")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_tar_compare_rejects_nul_argument():
    spec = _spec("archive", "archive.tar_compare")
    contract = _contract("archive", "archive.tar_compare")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_tar_compare_prefix_is_immutable():
    spec = _spec("archive", "archive.tar_compare")
    contract = _contract("archive", "archive.tar_compare")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_tar_compare_metadata_digest_is_stable():
    contract = _contract("archive", "archive.tar_compare")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_tar_compare_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.tar_compare")
    contract = _contract("archive", "archive.tar_compare")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_tar_create_registered():
    spec = _spec("archive", "archive.tar_create")
    contract = _contract("archive", "archive.tar_create")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_tar_create_minimal_argv_validates():
    spec = _spec("archive", "archive.tar_create")
    contract = _contract("archive", "archive.tar_create")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_tar_create_rejects_unknown_option():
    spec = _spec("archive", "archive.tar_create")
    contract = _contract("archive", "archive.tar_create")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_tar_create_rejects_nul_argument():
    spec = _spec("archive", "archive.tar_create")
    contract = _contract("archive", "archive.tar_create")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_tar_create_prefix_is_immutable():
    spec = _spec("archive", "archive.tar_create")
    contract = _contract("archive", "archive.tar_create")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_tar_create_metadata_digest_is_stable():
    contract = _contract("archive", "archive.tar_create")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_tar_create_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.tar_create")
    contract = _contract("archive", "archive.tar_create")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_unzip_list_registered():
    spec = _spec("archive", "archive.unzip_list")
    contract = _contract("archive", "archive.unzip_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_unzip_list_minimal_argv_validates():
    spec = _spec("archive", "archive.unzip_list")
    contract = _contract("archive", "archive.unzip_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_unzip_list_rejects_unknown_option():
    spec = _spec("archive", "archive.unzip_list")
    contract = _contract("archive", "archive.unzip_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_unzip_list_rejects_nul_argument():
    spec = _spec("archive", "archive.unzip_list")
    contract = _contract("archive", "archive.unzip_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_unzip_list_prefix_is_immutable():
    spec = _spec("archive", "archive.unzip_list")
    contract = _contract("archive", "archive.unzip_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_unzip_list_metadata_digest_is_stable():
    contract = _contract("archive", "archive.unzip_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_unzip_list_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.unzip_list")
    contract = _contract("archive", "archive.unzip_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_unzip_test_registered():
    spec = _spec("archive", "archive.unzip_test")
    contract = _contract("archive", "archive.unzip_test")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_unzip_test_minimal_argv_validates():
    spec = _spec("archive", "archive.unzip_test")
    contract = _contract("archive", "archive.unzip_test")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_unzip_test_rejects_unknown_option():
    spec = _spec("archive", "archive.unzip_test")
    contract = _contract("archive", "archive.unzip_test")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_unzip_test_rejects_nul_argument():
    spec = _spec("archive", "archive.unzip_test")
    contract = _contract("archive", "archive.unzip_test")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_unzip_test_prefix_is_immutable():
    spec = _spec("archive", "archive.unzip_test")
    contract = _contract("archive", "archive.unzip_test")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_unzip_test_metadata_digest_is_stable():
    contract = _contract("archive", "archive.unzip_test")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_unzip_test_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.unzip_test")
    contract = _contract("archive", "archive.unzip_test")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_zipinfo_registered():
    spec = _spec("archive", "archive.zipinfo")
    contract = _contract("archive", "archive.zipinfo")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_zipinfo_minimal_argv_validates():
    spec = _spec("archive", "archive.zipinfo")
    contract = _contract("archive", "archive.zipinfo")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_zipinfo_rejects_unknown_option():
    spec = _spec("archive", "archive.zipinfo")
    contract = _contract("archive", "archive.zipinfo")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_zipinfo_rejects_nul_argument():
    spec = _spec("archive", "archive.zipinfo")
    contract = _contract("archive", "archive.zipinfo")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_zipinfo_prefix_is_immutable():
    spec = _spec("archive", "archive.zipinfo")
    contract = _contract("archive", "archive.zipinfo")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_zipinfo_metadata_digest_is_stable():
    contract = _contract("archive", "archive.zipinfo")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_zipinfo_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.zipinfo")
    contract = _contract("archive", "archive.zipinfo")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_gzip_test_registered():
    spec = _spec("archive", "archive.gzip_test")
    contract = _contract("archive", "archive.gzip_test")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_gzip_test_minimal_argv_validates():
    spec = _spec("archive", "archive.gzip_test")
    contract = _contract("archive", "archive.gzip_test")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_gzip_test_rejects_unknown_option():
    spec = _spec("archive", "archive.gzip_test")
    contract = _contract("archive", "archive.gzip_test")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_gzip_test_rejects_nul_argument():
    spec = _spec("archive", "archive.gzip_test")
    contract = _contract("archive", "archive.gzip_test")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_gzip_test_prefix_is_immutable():
    spec = _spec("archive", "archive.gzip_test")
    contract = _contract("archive", "archive.gzip_test")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_gzip_test_metadata_digest_is_stable():
    contract = _contract("archive", "archive.gzip_test")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_gzip_test_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.gzip_test")
    contract = _contract("archive", "archive.gzip_test")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_gzip_list_registered():
    spec = _spec("archive", "archive.gzip_list")
    contract = _contract("archive", "archive.gzip_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_gzip_list_minimal_argv_validates():
    spec = _spec("archive", "archive.gzip_list")
    contract = _contract("archive", "archive.gzip_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_gzip_list_rejects_unknown_option():
    spec = _spec("archive", "archive.gzip_list")
    contract = _contract("archive", "archive.gzip_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_gzip_list_rejects_nul_argument():
    spec = _spec("archive", "archive.gzip_list")
    contract = _contract("archive", "archive.gzip_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_gzip_list_prefix_is_immutable():
    spec = _spec("archive", "archive.gzip_list")
    contract = _contract("archive", "archive.gzip_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_gzip_list_metadata_digest_is_stable():
    contract = _contract("archive", "archive.gzip_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_gzip_list_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.gzip_list")
    contract = _contract("archive", "archive.gzip_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_bzip2_test_registered():
    spec = _spec("archive", "archive.bzip2_test")
    contract = _contract("archive", "archive.bzip2_test")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_bzip2_test_minimal_argv_validates():
    spec = _spec("archive", "archive.bzip2_test")
    contract = _contract("archive", "archive.bzip2_test")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_bzip2_test_rejects_unknown_option():
    spec = _spec("archive", "archive.bzip2_test")
    contract = _contract("archive", "archive.bzip2_test")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_bzip2_test_rejects_nul_argument():
    spec = _spec("archive", "archive.bzip2_test")
    contract = _contract("archive", "archive.bzip2_test")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_bzip2_test_prefix_is_immutable():
    spec = _spec("archive", "archive.bzip2_test")
    contract = _contract("archive", "archive.bzip2_test")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_bzip2_test_metadata_digest_is_stable():
    contract = _contract("archive", "archive.bzip2_test")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_bzip2_test_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.bzip2_test")
    contract = _contract("archive", "archive.bzip2_test")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_xz_test_registered():
    spec = _spec("archive", "archive.xz_test")
    contract = _contract("archive", "archive.xz_test")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_xz_test_minimal_argv_validates():
    spec = _spec("archive", "archive.xz_test")
    contract = _contract("archive", "archive.xz_test")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_xz_test_rejects_unknown_option():
    spec = _spec("archive", "archive.xz_test")
    contract = _contract("archive", "archive.xz_test")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_xz_test_rejects_nul_argument():
    spec = _spec("archive", "archive.xz_test")
    contract = _contract("archive", "archive.xz_test")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_xz_test_prefix_is_immutable():
    spec = _spec("archive", "archive.xz_test")
    contract = _contract("archive", "archive.xz_test")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_xz_test_metadata_digest_is_stable():
    contract = _contract("archive", "archive.xz_test")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_xz_test_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.xz_test")
    contract = _contract("archive", "archive.xz_test")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_xz_list_registered():
    spec = _spec("archive", "archive.xz_list")
    contract = _contract("archive", "archive.xz_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_xz_list_minimal_argv_validates():
    spec = _spec("archive", "archive.xz_list")
    contract = _contract("archive", "archive.xz_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_xz_list_rejects_unknown_option():
    spec = _spec("archive", "archive.xz_list")
    contract = _contract("archive", "archive.xz_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_xz_list_rejects_nul_argument():
    spec = _spec("archive", "archive.xz_list")
    contract = _contract("archive", "archive.xz_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_xz_list_prefix_is_immutable():
    spec = _spec("archive", "archive.xz_list")
    contract = _contract("archive", "archive.xz_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_xz_list_metadata_digest_is_stable():
    contract = _contract("archive", "archive.xz_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_xz_list_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.xz_list")
    contract = _contract("archive", "archive.xz_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_zstd_test_registered():
    spec = _spec("archive", "archive.zstd_test")
    contract = _contract("archive", "archive.zstd_test")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_zstd_test_minimal_argv_validates():
    spec = _spec("archive", "archive.zstd_test")
    contract = _contract("archive", "archive.zstd_test")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_zstd_test_rejects_unknown_option():
    spec = _spec("archive", "archive.zstd_test")
    contract = _contract("archive", "archive.zstd_test")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_zstd_test_rejects_nul_argument():
    spec = _spec("archive", "archive.zstd_test")
    contract = _contract("archive", "archive.zstd_test")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_zstd_test_prefix_is_immutable():
    spec = _spec("archive", "archive.zstd_test")
    contract = _contract("archive", "archive.zstd_test")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_zstd_test_metadata_digest_is_stable():
    contract = _contract("archive", "archive.zstd_test")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_zstd_test_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.zstd_test")
    contract = _contract("archive", "archive.zstd_test")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_zstd_list_registered():
    spec = _spec("archive", "archive.zstd_list")
    contract = _contract("archive", "archive.zstd_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_zstd_list_minimal_argv_validates():
    spec = _spec("archive", "archive.zstd_list")
    contract = _contract("archive", "archive.zstd_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_zstd_list_rejects_unknown_option():
    spec = _spec("archive", "archive.zstd_list")
    contract = _contract("archive", "archive.zstd_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_zstd_list_rejects_nul_argument():
    spec = _spec("archive", "archive.zstd_list")
    contract = _contract("archive", "archive.zstd_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_zstd_list_prefix_is_immutable():
    spec = _spec("archive", "archive.zstd_list")
    contract = _contract("archive", "archive.zstd_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_zstd_list_metadata_digest_is_stable():
    contract = _contract("archive", "archive.zstd_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_zstd_list_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.zstd_list")
    contract = _contract("archive", "archive.zstd_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_7z_list_registered():
    spec = _spec("archive", "archive.7z_list")
    contract = _contract("archive", "archive.7z_list")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_7z_list_minimal_argv_validates():
    spec = _spec("archive", "archive.7z_list")
    contract = _contract("archive", "archive.7z_list")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_7z_list_rejects_unknown_option():
    spec = _spec("archive", "archive.7z_list")
    contract = _contract("archive", "archive.7z_list")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_7z_list_rejects_nul_argument():
    spec = _spec("archive", "archive.7z_list")
    contract = _contract("archive", "archive.7z_list")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_7z_list_prefix_is_immutable():
    spec = _spec("archive", "archive.7z_list")
    contract = _contract("archive", "archive.7z_list")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_7z_list_metadata_digest_is_stable():
    contract = _contract("archive", "archive.7z_list")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_7z_list_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.7z_list")
    contract = _contract("archive", "archive.7z_list")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_7z_test_registered():
    spec = _spec("archive", "archive.7z_test")
    contract = _contract("archive", "archive.7z_test")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_7z_test_minimal_argv_validates():
    spec = _spec("archive", "archive.7z_test")
    contract = _contract("archive", "archive.7z_test")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_7z_test_rejects_unknown_option():
    spec = _spec("archive", "archive.7z_test")
    contract = _contract("archive", "archive.7z_test")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_7z_test_rejects_nul_argument():
    spec = _spec("archive", "archive.7z_test")
    contract = _contract("archive", "archive.7z_test")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_7z_test_prefix_is_immutable():
    spec = _spec("archive", "archive.7z_test")
    contract = _contract("archive", "archive.7z_test")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_7z_test_metadata_digest_is_stable():
    contract = _contract("archive", "archive.7z_test")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_7z_test_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.7z_test")
    contract = _contract("archive", "archive.7z_test")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_zip_test_registered():
    spec = _spec("archive", "archive.zip_test")
    contract = _contract("archive", "archive.zip_test")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_zip_test_minimal_argv_validates():
    spec = _spec("archive", "archive.zip_test")
    contract = _contract("archive", "archive.zip_test")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_zip_test_rejects_unknown_option():
    spec = _spec("archive", "archive.zip_test")
    contract = _contract("archive", "archive.zip_test")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_zip_test_rejects_nul_argument():
    spec = _spec("archive", "archive.zip_test")
    contract = _contract("archive", "archive.zip_test")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_zip_test_prefix_is_immutable():
    spec = _spec("archive", "archive.zip_test")
    contract = _contract("archive", "archive.zip_test")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_zip_test_metadata_digest_is_stable():
    contract = _contract("archive", "archive.zip_test")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_zip_test_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.zip_test")
    contract = _contract("archive", "archive.zip_test")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_archive_zip_create_registered():
    spec = _spec("archive", "archive.zip_create")
    contract = _contract("archive", "archive.zip_create")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_archive_zip_create_minimal_argv_validates():
    spec = _spec("archive", "archive.zip_create")
    contract = _contract("archive", "archive.zip_create")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_archive_zip_create_rejects_unknown_option():
    spec = _spec("archive", "archive.zip_create")
    contract = _contract("archive", "archive.zip_create")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_archive_zip_create_rejects_nul_argument():
    spec = _spec("archive", "archive.zip_create")
    contract = _contract("archive", "archive.zip_create")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_archive_zip_create_prefix_is_immutable():
    spec = _spec("archive", "archive.zip_create")
    contract = _contract("archive", "archive.zip_create")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_archive_zip_create_metadata_digest_is_stable():
    contract = _contract("archive", "archive.zip_create")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_archive_zip_create_path_escape_is_rejected_when_applicable():
    spec = _spec("archive", "archive.zip_create")
    contract = _contract("archive", "archive.zip_create")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_shellcheck_registered():
    spec = _spec("quality", "quality.shellcheck")
    contract = _contract("quality", "quality.shellcheck")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_shellcheck_minimal_argv_validates():
    spec = _spec("quality", "quality.shellcheck")
    contract = _contract("quality", "quality.shellcheck")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_shellcheck_rejects_unknown_option():
    spec = _spec("quality", "quality.shellcheck")
    contract = _contract("quality", "quality.shellcheck")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_shellcheck_rejects_nul_argument():
    spec = _spec("quality", "quality.shellcheck")
    contract = _contract("quality", "quality.shellcheck")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_shellcheck_prefix_is_immutable():
    spec = _spec("quality", "quality.shellcheck")
    contract = _contract("quality", "quality.shellcheck")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_shellcheck_metadata_digest_is_stable():
    contract = _contract("quality", "quality.shellcheck")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_shellcheck_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.shellcheck")
    contract = _contract("quality", "quality.shellcheck")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_hadolint_registered():
    spec = _spec("quality", "quality.hadolint")
    contract = _contract("quality", "quality.hadolint")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_hadolint_minimal_argv_validates():
    spec = _spec("quality", "quality.hadolint")
    contract = _contract("quality", "quality.hadolint")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_hadolint_rejects_unknown_option():
    spec = _spec("quality", "quality.hadolint")
    contract = _contract("quality", "quality.hadolint")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_hadolint_rejects_nul_argument():
    spec = _spec("quality", "quality.hadolint")
    contract = _contract("quality", "quality.hadolint")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_hadolint_prefix_is_immutable():
    spec = _spec("quality", "quality.hadolint")
    contract = _contract("quality", "quality.hadolint")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_hadolint_metadata_digest_is_stable():
    contract = _contract("quality", "quality.hadolint")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_hadolint_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.hadolint")
    contract = _contract("quality", "quality.hadolint")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_actionlint_registered():
    spec = _spec("quality", "quality.actionlint")
    contract = _contract("quality", "quality.actionlint")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_actionlint_minimal_argv_validates():
    spec = _spec("quality", "quality.actionlint")
    contract = _contract("quality", "quality.actionlint")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_actionlint_rejects_unknown_option():
    spec = _spec("quality", "quality.actionlint")
    contract = _contract("quality", "quality.actionlint")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_actionlint_rejects_nul_argument():
    spec = _spec("quality", "quality.actionlint")
    contract = _contract("quality", "quality.actionlint")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_actionlint_prefix_is_immutable():
    spec = _spec("quality", "quality.actionlint")
    contract = _contract("quality", "quality.actionlint")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_actionlint_metadata_digest_is_stable():
    contract = _contract("quality", "quality.actionlint")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_actionlint_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.actionlint")
    contract = _contract("quality", "quality.actionlint")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_yamllint_registered():
    spec = _spec("quality", "quality.yamllint")
    contract = _contract("quality", "quality.yamllint")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_yamllint_minimal_argv_validates():
    spec = _spec("quality", "quality.yamllint")
    contract = _contract("quality", "quality.yamllint")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_yamllint_rejects_unknown_option():
    spec = _spec("quality", "quality.yamllint")
    contract = _contract("quality", "quality.yamllint")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_yamllint_rejects_nul_argument():
    spec = _spec("quality", "quality.yamllint")
    contract = _contract("quality", "quality.yamllint")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_yamllint_prefix_is_immutable():
    spec = _spec("quality", "quality.yamllint")
    contract = _contract("quality", "quality.yamllint")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_yamllint_metadata_digest_is_stable():
    contract = _contract("quality", "quality.yamllint")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_yamllint_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.yamllint")
    contract = _contract("quality", "quality.yamllint")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_semgrep_scan_registered():
    spec = _spec("quality", "quality.semgrep_scan")
    contract = _contract("quality", "quality.semgrep_scan")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_semgrep_scan_minimal_argv_validates():
    spec = _spec("quality", "quality.semgrep_scan")
    contract = _contract("quality", "quality.semgrep_scan")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_semgrep_scan_rejects_unknown_option():
    spec = _spec("quality", "quality.semgrep_scan")
    contract = _contract("quality", "quality.semgrep_scan")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_semgrep_scan_rejects_nul_argument():
    spec = _spec("quality", "quality.semgrep_scan")
    contract = _contract("quality", "quality.semgrep_scan")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_semgrep_scan_prefix_is_immutable():
    spec = _spec("quality", "quality.semgrep_scan")
    contract = _contract("quality", "quality.semgrep_scan")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_semgrep_scan_metadata_digest_is_stable():
    contract = _contract("quality", "quality.semgrep_scan")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_semgrep_scan_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.semgrep_scan")
    contract = _contract("quality", "quality.semgrep_scan")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_checkov_directory_registered():
    spec = _spec("quality", "quality.checkov_directory")
    contract = _contract("quality", "quality.checkov_directory")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_checkov_directory_minimal_argv_validates():
    spec = _spec("quality", "quality.checkov_directory")
    contract = _contract("quality", "quality.checkov_directory")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_checkov_directory_rejects_unknown_option():
    spec = _spec("quality", "quality.checkov_directory")
    contract = _contract("quality", "quality.checkov_directory")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_checkov_directory_rejects_nul_argument():
    spec = _spec("quality", "quality.checkov_directory")
    contract = _contract("quality", "quality.checkov_directory")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_checkov_directory_prefix_is_immutable():
    spec = _spec("quality", "quality.checkov_directory")
    contract = _contract("quality", "quality.checkov_directory")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_checkov_directory_metadata_digest_is_stable():
    contract = _contract("quality", "quality.checkov_directory")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_checkov_directory_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.checkov_directory")
    contract = _contract("quality", "quality.checkov_directory")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_checkov_file_registered():
    spec = _spec("quality", "quality.checkov_file")
    contract = _contract("quality", "quality.checkov_file")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_checkov_file_minimal_argv_validates():
    spec = _spec("quality", "quality.checkov_file")
    contract = _contract("quality", "quality.checkov_file")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_checkov_file_rejects_unknown_option():
    spec = _spec("quality", "quality.checkov_file")
    contract = _contract("quality", "quality.checkov_file")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_checkov_file_rejects_nul_argument():
    spec = _spec("quality", "quality.checkov_file")
    contract = _contract("quality", "quality.checkov_file")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_checkov_file_prefix_is_immutable():
    spec = _spec("quality", "quality.checkov_file")
    contract = _contract("quality", "quality.checkov_file")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_checkov_file_metadata_digest_is_stable():
    contract = _contract("quality", "quality.checkov_file")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_checkov_file_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.checkov_file")
    contract = _contract("quality", "quality.checkov_file")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_conftest_test_registered():
    spec = _spec("quality", "quality.conftest_test")
    contract = _contract("quality", "quality.conftest_test")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_conftest_test_minimal_argv_validates():
    spec = _spec("quality", "quality.conftest_test")
    contract = _contract("quality", "quality.conftest_test")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_conftest_test_rejects_unknown_option():
    spec = _spec("quality", "quality.conftest_test")
    contract = _contract("quality", "quality.conftest_test")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_conftest_test_rejects_nul_argument():
    spec = _spec("quality", "quality.conftest_test")
    contract = _contract("quality", "quality.conftest_test")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_conftest_test_prefix_is_immutable():
    spec = _spec("quality", "quality.conftest_test")
    contract = _contract("quality", "quality.conftest_test")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_conftest_test_metadata_digest_is_stable():
    contract = _contract("quality", "quality.conftest_test")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_conftest_test_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.conftest_test")
    contract = _contract("quality", "quality.conftest_test")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_conftest_verify_registered():
    spec = _spec("quality", "quality.conftest_verify")
    contract = _contract("quality", "quality.conftest_verify")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_conftest_verify_minimal_argv_validates():
    spec = _spec("quality", "quality.conftest_verify")
    contract = _contract("quality", "quality.conftest_verify")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_conftest_verify_rejects_unknown_option():
    spec = _spec("quality", "quality.conftest_verify")
    contract = _contract("quality", "quality.conftest_verify")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_conftest_verify_rejects_nul_argument():
    spec = _spec("quality", "quality.conftest_verify")
    contract = _contract("quality", "quality.conftest_verify")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_conftest_verify_prefix_is_immutable():
    spec = _spec("quality", "quality.conftest_verify")
    contract = _contract("quality", "quality.conftest_verify")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_conftest_verify_metadata_digest_is_stable():
    contract = _contract("quality", "quality.conftest_verify")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_conftest_verify_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.conftest_verify")
    contract = _contract("quality", "quality.conftest_verify")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_opa_eval_registered():
    spec = _spec("quality", "quality.opa_eval")
    contract = _contract("quality", "quality.opa_eval")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_opa_eval_minimal_argv_validates():
    spec = _spec("quality", "quality.opa_eval")
    contract = _contract("quality", "quality.opa_eval")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_opa_eval_rejects_unknown_option():
    spec = _spec("quality", "quality.opa_eval")
    contract = _contract("quality", "quality.opa_eval")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_opa_eval_rejects_nul_argument():
    spec = _spec("quality", "quality.opa_eval")
    contract = _contract("quality", "quality.opa_eval")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_opa_eval_prefix_is_immutable():
    spec = _spec("quality", "quality.opa_eval")
    contract = _contract("quality", "quality.opa_eval")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_opa_eval_metadata_digest_is_stable():
    contract = _contract("quality", "quality.opa_eval")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_opa_eval_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.opa_eval")
    contract = _contract("quality", "quality.opa_eval")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_opa_check_registered():
    spec = _spec("quality", "quality.opa_check")
    contract = _contract("quality", "quality.opa_check")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_opa_check_minimal_argv_validates():
    spec = _spec("quality", "quality.opa_check")
    contract = _contract("quality", "quality.opa_check")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_opa_check_rejects_unknown_option():
    spec = _spec("quality", "quality.opa_check")
    contract = _contract("quality", "quality.opa_check")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_opa_check_rejects_nul_argument():
    spec = _spec("quality", "quality.opa_check")
    contract = _contract("quality", "quality.opa_check")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_opa_check_prefix_is_immutable():
    spec = _spec("quality", "quality.opa_check")
    contract = _contract("quality", "quality.opa_check")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_opa_check_metadata_digest_is_stable():
    contract = _contract("quality", "quality.opa_check")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_opa_check_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.opa_check")
    contract = _contract("quality", "quality.opa_check")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_opa_fmt_diff_registered():
    spec = _spec("quality", "quality.opa_fmt_diff")
    contract = _contract("quality", "quality.opa_fmt_diff")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_opa_fmt_diff_minimal_argv_validates():
    spec = _spec("quality", "quality.opa_fmt_diff")
    contract = _contract("quality", "quality.opa_fmt_diff")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_opa_fmt_diff_rejects_unknown_option():
    spec = _spec("quality", "quality.opa_fmt_diff")
    contract = _contract("quality", "quality.opa_fmt_diff")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_opa_fmt_diff_rejects_nul_argument():
    spec = _spec("quality", "quality.opa_fmt_diff")
    contract = _contract("quality", "quality.opa_fmt_diff")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_opa_fmt_diff_prefix_is_immutable():
    spec = _spec("quality", "quality.opa_fmt_diff")
    contract = _contract("quality", "quality.opa_fmt_diff")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_opa_fmt_diff_metadata_digest_is_stable():
    contract = _contract("quality", "quality.opa_fmt_diff")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_opa_fmt_diff_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.opa_fmt_diff")
    contract = _contract("quality", "quality.opa_fmt_diff")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_kubeconform_registered():
    spec = _spec("quality", "quality.kubeconform")
    contract = _contract("quality", "quality.kubeconform")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_kubeconform_minimal_argv_validates():
    spec = _spec("quality", "quality.kubeconform")
    contract = _contract("quality", "quality.kubeconform")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_kubeconform_rejects_unknown_option():
    spec = _spec("quality", "quality.kubeconform")
    contract = _contract("quality", "quality.kubeconform")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_kubeconform_rejects_nul_argument():
    spec = _spec("quality", "quality.kubeconform")
    contract = _contract("quality", "quality.kubeconform")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_kubeconform_prefix_is_immutable():
    spec = _spec("quality", "quality.kubeconform")
    contract = _contract("quality", "quality.kubeconform")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_kubeconform_metadata_digest_is_stable():
    contract = _contract("quality", "quality.kubeconform")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_kubeconform_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.kubeconform")
    contract = _contract("quality", "quality.kubeconform")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_kube_score_registered():
    spec = _spec("quality", "quality.kube_score")
    contract = _contract("quality", "quality.kube_score")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_kube_score_minimal_argv_validates():
    spec = _spec("quality", "quality.kube_score")
    contract = _contract("quality", "quality.kube_score")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_kube_score_rejects_unknown_option():
    spec = _spec("quality", "quality.kube_score")
    contract = _contract("quality", "quality.kube_score")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_kube_score_rejects_nul_argument():
    spec = _spec("quality", "quality.kube_score")
    contract = _contract("quality", "quality.kube_score")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_kube_score_prefix_is_immutable():
    spec = _spec("quality", "quality.kube_score")
    contract = _contract("quality", "quality.kube_score")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_kube_score_metadata_digest_is_stable():
    contract = _contract("quality", "quality.kube_score")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_kube_score_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.kube_score")
    contract = _contract("quality", "quality.kube_score")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_gitleaks_detect_registered():
    spec = _spec("quality", "quality.gitleaks_detect")
    contract = _contract("quality", "quality.gitleaks_detect")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_gitleaks_detect_minimal_argv_validates():
    spec = _spec("quality", "quality.gitleaks_detect")
    contract = _contract("quality", "quality.gitleaks_detect")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_gitleaks_detect_rejects_unknown_option():
    spec = _spec("quality", "quality.gitleaks_detect")
    contract = _contract("quality", "quality.gitleaks_detect")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_gitleaks_detect_rejects_nul_argument():
    spec = _spec("quality", "quality.gitleaks_detect")
    contract = _contract("quality", "quality.gitleaks_detect")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_gitleaks_detect_prefix_is_immutable():
    spec = _spec("quality", "quality.gitleaks_detect")
    contract = _contract("quality", "quality.gitleaks_detect")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_gitleaks_detect_metadata_digest_is_stable():
    contract = _contract("quality", "quality.gitleaks_detect")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_gitleaks_detect_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.gitleaks_detect")
    contract = _contract("quality", "quality.gitleaks_detect")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_gitleaks_git_registered():
    spec = _spec("quality", "quality.gitleaks_git")
    contract = _contract("quality", "quality.gitleaks_git")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_gitleaks_git_minimal_argv_validates():
    spec = _spec("quality", "quality.gitleaks_git")
    contract = _contract("quality", "quality.gitleaks_git")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_gitleaks_git_rejects_unknown_option():
    spec = _spec("quality", "quality.gitleaks_git")
    contract = _contract("quality", "quality.gitleaks_git")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_gitleaks_git_rejects_nul_argument():
    spec = _spec("quality", "quality.gitleaks_git")
    contract = _contract("quality", "quality.gitleaks_git")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_gitleaks_git_prefix_is_immutable():
    spec = _spec("quality", "quality.gitleaks_git")
    contract = _contract("quality", "quality.gitleaks_git")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_gitleaks_git_metadata_digest_is_stable():
    contract = _contract("quality", "quality.gitleaks_git")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_gitleaks_git_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.gitleaks_git")
    contract = _contract("quality", "quality.gitleaks_git")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_trivy_fs_registered():
    spec = _spec("quality", "quality.trivy_fs")
    contract = _contract("quality", "quality.trivy_fs")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_trivy_fs_minimal_argv_validates():
    spec = _spec("quality", "quality.trivy_fs")
    contract = _contract("quality", "quality.trivy_fs")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_trivy_fs_rejects_unknown_option():
    spec = _spec("quality", "quality.trivy_fs")
    contract = _contract("quality", "quality.trivy_fs")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_trivy_fs_rejects_nul_argument():
    spec = _spec("quality", "quality.trivy_fs")
    contract = _contract("quality", "quality.trivy_fs")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_trivy_fs_prefix_is_immutable():
    spec = _spec("quality", "quality.trivy_fs")
    contract = _contract("quality", "quality.trivy_fs")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_trivy_fs_metadata_digest_is_stable():
    contract = _contract("quality", "quality.trivy_fs")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_trivy_fs_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.trivy_fs")
    contract = _contract("quality", "quality.trivy_fs")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_trivy_config_registered():
    spec = _spec("quality", "quality.trivy_config")
    contract = _contract("quality", "quality.trivy_config")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_trivy_config_minimal_argv_validates():
    spec = _spec("quality", "quality.trivy_config")
    contract = _contract("quality", "quality.trivy_config")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_trivy_config_rejects_unknown_option():
    spec = _spec("quality", "quality.trivy_config")
    contract = _contract("quality", "quality.trivy_config")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_trivy_config_rejects_nul_argument():
    spec = _spec("quality", "quality.trivy_config")
    contract = _contract("quality", "quality.trivy_config")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_trivy_config_prefix_is_immutable():
    spec = _spec("quality", "quality.trivy_config")
    contract = _contract("quality", "quality.trivy_config")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_trivy_config_metadata_digest_is_stable():
    contract = _contract("quality", "quality.trivy_config")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_trivy_config_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.trivy_config")
    contract = _contract("quality", "quality.trivy_config")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_syft_scan_registered():
    spec = _spec("quality", "quality.syft_scan")
    contract = _contract("quality", "quality.syft_scan")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_syft_scan_minimal_argv_validates():
    spec = _spec("quality", "quality.syft_scan")
    contract = _contract("quality", "quality.syft_scan")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_syft_scan_rejects_unknown_option():
    spec = _spec("quality", "quality.syft_scan")
    contract = _contract("quality", "quality.syft_scan")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_syft_scan_rejects_nul_argument():
    spec = _spec("quality", "quality.syft_scan")
    contract = _contract("quality", "quality.syft_scan")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_syft_scan_prefix_is_immutable():
    spec = _spec("quality", "quality.syft_scan")
    contract = _contract("quality", "quality.syft_scan")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_syft_scan_metadata_digest_is_stable():
    contract = _contract("quality", "quality.syft_scan")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_syft_scan_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.syft_scan")
    contract = _contract("quality", "quality.syft_scan")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_osv_scan_source_registered():
    spec = _spec("quality", "quality.osv_scan_source")
    contract = _contract("quality", "quality.osv_scan_source")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_osv_scan_source_minimal_argv_validates():
    spec = _spec("quality", "quality.osv_scan_source")
    contract = _contract("quality", "quality.osv_scan_source")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_osv_scan_source_rejects_unknown_option():
    spec = _spec("quality", "quality.osv_scan_source")
    contract = _contract("quality", "quality.osv_scan_source")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_osv_scan_source_rejects_nul_argument():
    spec = _spec("quality", "quality.osv_scan_source")
    contract = _contract("quality", "quality.osv_scan_source")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_osv_scan_source_prefix_is_immutable():
    spec = _spec("quality", "quality.osv_scan_source")
    contract = _contract("quality", "quality.osv_scan_source")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_osv_scan_source_metadata_digest_is_stable():
    contract = _contract("quality", "quality.osv_scan_source")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_osv_scan_source_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.osv_scan_source")
    contract = _contract("quality", "quality.osv_scan_source")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_markdownlint_registered():
    spec = _spec("quality", "quality.markdownlint")
    contract = _contract("quality", "quality.markdownlint")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_markdownlint_minimal_argv_validates():
    spec = _spec("quality", "quality.markdownlint")
    contract = _contract("quality", "quality.markdownlint")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_markdownlint_rejects_unknown_option():
    spec = _spec("quality", "quality.markdownlint")
    contract = _contract("quality", "quality.markdownlint")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_markdownlint_rejects_nul_argument():
    spec = _spec("quality", "quality.markdownlint")
    contract = _contract("quality", "quality.markdownlint")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_markdownlint_prefix_is_immutable():
    spec = _spec("quality", "quality.markdownlint")
    contract = _contract("quality", "quality.markdownlint")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_markdownlint_metadata_digest_is_stable():
    contract = _contract("quality", "quality.markdownlint")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_markdownlint_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.markdownlint")
    contract = _contract("quality", "quality.markdownlint")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_sqlfluff_lint_registered():
    spec = _spec("quality", "quality.sqlfluff_lint")
    contract = _contract("quality", "quality.sqlfluff_lint")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_sqlfluff_lint_minimal_argv_validates():
    spec = _spec("quality", "quality.sqlfluff_lint")
    contract = _contract("quality", "quality.sqlfluff_lint")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_sqlfluff_lint_rejects_unknown_option():
    spec = _spec("quality", "quality.sqlfluff_lint")
    contract = _contract("quality", "quality.sqlfluff_lint")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_sqlfluff_lint_rejects_nul_argument():
    spec = _spec("quality", "quality.sqlfluff_lint")
    contract = _contract("quality", "quality.sqlfluff_lint")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_sqlfluff_lint_prefix_is_immutable():
    spec = _spec("quality", "quality.sqlfluff_lint")
    contract = _contract("quality", "quality.sqlfluff_lint")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_sqlfluff_lint_metadata_digest_is_stable():
    contract = _contract("quality", "quality.sqlfluff_lint")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_sqlfluff_lint_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.sqlfluff_lint")
    contract = _contract("quality", "quality.sqlfluff_lint")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_sqlfluff_parse_registered():
    spec = _spec("quality", "quality.sqlfluff_parse")
    contract = _contract("quality", "quality.sqlfluff_parse")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_sqlfluff_parse_minimal_argv_validates():
    spec = _spec("quality", "quality.sqlfluff_parse")
    contract = _contract("quality", "quality.sqlfluff_parse")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_sqlfluff_parse_rejects_unknown_option():
    spec = _spec("quality", "quality.sqlfluff_parse")
    contract = _contract("quality", "quality.sqlfluff_parse")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_sqlfluff_parse_rejects_nul_argument():
    spec = _spec("quality", "quality.sqlfluff_parse")
    contract = _contract("quality", "quality.sqlfluff_parse")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_sqlfluff_parse_prefix_is_immutable():
    spec = _spec("quality", "quality.sqlfluff_parse")
    contract = _contract("quality", "quality.sqlfluff_parse")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_sqlfluff_parse_metadata_digest_is_stable():
    contract = _contract("quality", "quality.sqlfluff_parse")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_sqlfluff_parse_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.sqlfluff_parse")
    contract = _contract("quality", "quality.sqlfluff_parse")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)


def test_quality_spectral_lint_registered():
    spec = _spec("quality", "quality.spectral_lint")
    contract = _contract("quality", "quality.spectral_lint")
    assert contract.name == spec.logical_name
    assert contract.executable_key == spec.executable_key


def test_quality_spectral_lint_minimal_argv_validates():
    spec = _spec("quality", "quality.spectral_lint")
    contract = _contract("quality", "quality.spectral_lint")
    args = _minimal_args(spec)
    assert contract.arguments.validate(contract.name, args) == args


def test_quality_spectral_lint_rejects_unknown_option():
    spec = _spec("quality", "quality.spectral_lint")
    contract = _contract("quality", "quality.spectral_lint")
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, _unknown_option_args(spec))


def test_quality_spectral_lint_rejects_nul_argument():
    spec = _spec("quality", "quality.spectral_lint")
    contract = _contract("quality", "quality.spectral_lint")
    args = _minimal_args(spec) + ("bad\\x00argument",)
    with pytest.raises(ArgumentRejected):
        contract.arguments.validate(contract.name, args)


def test_quality_spectral_lint_prefix_is_immutable():
    spec = _spec("quality", "quality.spectral_lint")
    contract = _contract("quality", "quality.spectral_lint")
    mutated = _mutated_prefix_args(spec)
    if mutated is None:
        assert contract.arguments.required_prefix == ()
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, mutated)


def test_quality_spectral_lint_metadata_digest_is_stable():
    contract = _contract("quality", "quality.spectral_lint")
    first = _contract_digest(contract)
    second = _contract_digest(contract)
    assert first == second
    assert len(first) == 64
    assert contract.effects
    assert contract.tags


def test_quality_spectral_lint_path_escape_is_rejected_when_applicable():
    spec = _spec("quality", "quality.spectral_lint")
    contract = _contract("quality", "quality.spectral_lint")
    args = _bad_path_args(spec)
    if args is None:
        assert "path" not in spec.positionals
        assert spec.variadic != "path"
    else:
        with pytest.raises(ArgumentRejected):
            contract.arguments.validate(contract.name, args)
