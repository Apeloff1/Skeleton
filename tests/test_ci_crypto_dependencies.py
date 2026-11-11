"""Mutation coverage for CI test-plugin dependency closure."""
from __future__ import annotations

from scripts.check_ci_crypto_dependencies import CRYPTO_REQUIREMENT, REQUIRED_JOBS, validate


def test_current_ci_crypto_dependency_closure() -> None:
    from scripts.check_ci_crypto_dependencies import CI
    assert validate(CI.read_text(encoding="utf-8")) == []


def test_missing_dependency_in_each_job_fails_closed() -> None:
    from scripts.check_ci_crypto_dependencies import CI
    source = CI.read_text(encoding="utf-8")
    for name in REQUIRED_JOBS:
        assert validate(source) == []
        marker = f"  {name}:"
        start = source.index(marker)
        tail = source[start:]
        assert CRYPTO_REQUIREMENT in tail
        cut = start + tail.index(CRYPTO_REQUIREMENT)
        poisoned = source[:cut] + source[cut:].replace(CRYPTO_REQUIREMENT, "", 1)
        assert any(name in failure for failure in validate(poisoned))


def test_not_forged_by_a_dependency_in_an_unrelated_job() -> None:
    from scripts.check_ci_crypto_dependencies import CI
    source = CI.read_text(encoding="utf-8")
    first = source.index("  skeleton-test:")
    last = source.index("  java-accelerators:", first)
    source = source[:first] + source[first:last].replace(CRYPTO_REQUIREMENT, "", 1) + source[last:]
    source += "\n  unrelated-example:\n    run: python -m pip install " + CRYPTO_REQUIREMENT + "\n"
    assert any("skeleton-test" in failure for failure in validate(source))
