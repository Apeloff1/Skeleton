from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.developer_experience import DeveloperCommandRegistry
from skeleton.ai.runtime.deferred.operations_experience import DeveloperCommand


DIGEST = "a" * 64


def registry() -> DeveloperCommandRegistry:
    return DeveloperCommandRegistry((
        DeveloperCommand("unit", ("python", "-m", "pytest", "tests/unit"), ("python", "-m", "pytest", "tests/unit")),
        DeveloperCommand("repair", ("python", "scripts/repair.py"), ("python", "scripts/repair.py", "--check"), mutating=True),
    ))


def test_registry_is_deterministic_and_binds_contract_receipt() -> None:
    subject = registry()
    assert [item.command_id for item in subject.inventory()] == ["repair", "unit"]
    first = subject.resolve("unit", contract_digest=DIGEST)
    second = subject.resolve("unit", contract_digest=DIGEST)
    assert first.digest == second.digest
    assert first.ci_equivalent == ("python", "-m", "pytest", "tests/unit")


def test_mutating_command_fails_closed_without_explicit_authority() -> None:
    subject = registry()
    with pytest.raises(PermissionError):
        subject.resolve("repair", contract_digest=DIGEST)
    assert subject.resolve("repair", contract_digest=DIGEST, allow_mutation=True).mutating is True


def test_unknown_command_and_ci_drift_fail_closed() -> None:
    subject = registry()
    with pytest.raises(KeyError):
        subject.resolve("missing", contract_digest=DIGEST)
    with pytest.raises(ValueError):
        subject.verify_ci_parity("unit", ("pytest",))
    subject.verify_ci_parity("unit", ("python", "-m", "pytest", "tests/unit"))


@pytest.mark.parametrize("digest", ["", "A" * 64, "a" * 63, "g" * 64])
def test_receipt_rejects_noncanonical_contract_digest(digest: str) -> None:
    with pytest.raises(ValueError):
        registry().resolve("unit", contract_digest=digest)
