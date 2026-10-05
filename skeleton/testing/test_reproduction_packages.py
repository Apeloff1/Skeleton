from __future__ import annotations

import pytest

from skeleton.research.reproduction import (
    Availability,
    ReproductionDependency,
    ReproductionError,
    ReproductionPackage,
)

D = "a" * 64

def dep(name="data", availability=Availability.AVAILABLE, evidence="receipt:1"):
    return ReproductionDependency(name, D, availability, evidence)

def package(*dependencies):
    return ReproductionPackage(
        "pkg-1", D, "b" * 64, "c" * 64,
        tuple(dependencies or (dep(),)),
        ("install locked environment", "run experiment"),
    )

def test_package_digest_is_deterministic_across_dependency_order():
    a = dep("a")
    b = dep("b")
    assert package(a, b).digest == package(b, a).digest

def test_restricted_dependency_is_explicitly_non_runnable():
    p = package(dep(availability=Availability.RESTRICTED, evidence="license:restricted"))
    assert not p.runnable

def test_unavailable_dependency_is_explicitly_non_runnable():
    p = package(dep(availability=Availability.UNAVAILABLE, evidence="archive:missing"))
    assert not p.runnable

def test_dependency_identity_cannot_be_ambiguous():
    with pytest.raises(ReproductionError, match="unique"):
        package(dep("same"), dep("same"))

def test_package_requires_exact_sha256_artifact_identity():
    with pytest.raises(ReproductionError, match="sha256"):
        ReproductionPackage("pkg-1", "not-a-digest", D, D, (dep(),), ("run",))

def test_package_requires_replay_instructions_and_dependencies():
    with pytest.raises(ReproductionError):
        ReproductionPackage("pkg-1", D, D, D, (), ("run",))
    with pytest.raises(ReproductionError):
        ReproductionPackage("pkg-1", D, D, D, (dep(),), ())
