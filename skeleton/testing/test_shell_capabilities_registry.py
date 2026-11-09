from pathlib import Path
import sys
import pytest

from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.errors import CapabilityDenied
from skeleton.shells.registry import ExecutableRegistry, ExecutableSpec


def test_capability_grant_round_trip_names():
    grant = CapabilityGrant.from_names(["execute", "stdin"], principal="jeeves")
    assert grant.has(ShellCapability.EXECUTE)
    assert grant.has(ShellCapability.STDIN)
    assert grant.principal == "jeeves"
    assert grant.to_dict()["capabilities"] == ["execute", "stdin"]


def test_capability_unknown_name_fails():
    with pytest.raises(ValueError):
        CapabilityGrant.from_names(["root-everything"])


def test_capability_require_denies_missing():
    grant = CapabilityGrant.execution_only()
    with pytest.raises(CapabilityDenied):
        grant.require(ShellCapability.CUSTOM_ENV, command="python")


def test_capability_narrow_never_widens():
    parent = CapabilityGrant.from_names(["execute", "stdin", "retry"])
    child = parent.narrow([ShellCapability.EXECUTE, ShellCapability.STDIN])
    assert child.capabilities == frozenset({ShellCapability.EXECUTE, ShellCapability.STDIN})
    with pytest.raises(CapabilityDenied):
        child.narrow([ShellCapability.EXECUTE, ShellCapability.RETRY])


def test_capability_intersection_is_only_common_authority():
    left = CapabilityGrant.from_names(["execute", "stdin", "retry"], principal="same")
    right = CapabilityGrant.from_names(["execute", "parallel"], principal="same")
    combined = left.intersect(right)
    assert combined.capabilities == frozenset({ShellCapability.EXECUTE})
    assert combined.principal == "same"


def test_registry_register_resolve_and_alias():
    registry = ExecutableRegistry()
    spec = registry.register_path("python", str(Path(sys.executable).resolve()), tags=["runtime", "python"])
    registry.alias("py", "python")
    assert registry.resolve("python") == spec
    assert registry.resolve("py") == spec
    assert registry.by_tag("python") == (spec,)


def test_registry_rejects_relative_executable():
    with pytest.raises(ValueError):
        ExecutableSpec("python", "python")


def test_registry_rejects_invalid_names_and_tags():
    path = str(Path(sys.executable).resolve())
    with pytest.raises(ValueError):
        ExecutableSpec("bad name", path)
    with pytest.raises(ValueError):
        ExecutableSpec("python", path, tags=frozenset({"bad tag"}))


def test_registry_duplicate_requires_replace():
    registry = ExecutableRegistry()
    path = str(Path(sys.executable).resolve())
    registry.register_path("python", path)
    with pytest.raises(ValueError):
        registry.register_path("python", path)
    registry.register_path("python", path, replace=True, description="replacement")
    assert registry.resolve("python").description == "replacement"


def test_registry_alias_requires_existing_target():
    registry = ExecutableRegistry()
    with pytest.raises(KeyError):
        registry.alias("py", "python")


def test_registry_freeze_blocks_mutation_and_is_deterministic():
    path = str(Path(sys.executable).resolve())
    a = ExecutableRegistry()
    a.register_path("python", path, tags=["b", "a"])
    a.alias("py", "python")
    first = a.freeze()
    with pytest.raises(RuntimeError):
        a.register_path("other", path)

    b = ExecutableRegistry()
    b.register_path("python", path, tags=["a", "b"])
    b.alias("py", "python")
    second = b.freeze()
    assert first.digest == second.digest
    assert first.resolve("py").name == "python"


def test_registry_remove_removes_aliases():
    path = str(Path(sys.executable).resolve())
    registry = ExecutableRegistry()
    registry.register_path("python", path)
    registry.alias("py", "python")
    registry.remove("python")
    with pytest.raises(KeyError):
        registry.resolve("py")


def test_snapshot_policy_mapping_contains_only_canonical_names():
    path = str(Path(sys.executable).resolve())
    registry = ExecutableRegistry()
    registry.register_path("python", path)
    registry.alias("py", "python")
    mapping = registry.snapshot().to_policy_mapping()
    assert mapping == {"python": path}
    assert "py" not in mapping
