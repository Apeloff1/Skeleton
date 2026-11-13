"""Anti-pattern exceptions cannot silently erase findings without admission."""
from __future__ import annotations

import pytest

from skeleton.eval.antipatterns import (
    AntiPattern,
    AntiPatternError,
    AntiPatternException,
    AntiPatternFinding,
    AntiPatternRegistry,
)


def pattern(name="AP.001"):
    return AntiPattern(name, "historic failure", r"eval\(", "reviewed implementation")


def exception(name="AP.001", expires=4):
    return AntiPatternException(name, "src/module.py", "OWNER.001", "reviewed exception", expires)


def registry():
    return AntiPatternRegistry((pattern(),))


def test_typed_registry_compiles_and_reports_deterministic_findings():
    detector = registry()
    assert detector.scan("src/module.py", "safe()\neval('unsafe')") == (
        AntiPatternFinding("AP.001", "src/module.py", 2, "eval('unsafe')"),
    )


def test_live_exception_expires_without_erasing_findings():
    detector = registry()
    finding = detector.scan("src/module.py", "eval('unsafe')")
    assert detector.unresolved(finding, (exception(),), 4) == ()
    assert detector.unresolved(finding, (exception(),), 5) == finding


@pytest.mark.parametrize("patterns", [
    (pattern(), pattern()),
    (pattern(), "not typed"),
    {"AP.001": pattern()},
])
def test_duplicate_or_malformed_detector_registry_denied(patterns):
    with pytest.raises(AntiPatternError):
        AntiPatternRegistry(patterns)


@pytest.mark.parametrize(
    ("findings", "exceptions", "tick"),
    [
        ((AntiPatternFinding("AP.002", "src/module.py", 1, "eval()"),), (), 1),
        ((), (exception("AP.002"),), 1),
        ((), (exception(), exception()), 1),
        ((), ("not typed",), 1),
        ((), (), float("nan")),
        ((), (), True),
        ((), (), -1),
        ("not a typed tuple", (), 0),
    ],
)
def test_invalid_exception_or_finding_admission_denied(findings, exceptions, tick):
    with pytest.raises(AntiPatternError):
        registry().unresolved(findings, exceptions, tick)


def test_outside_path_exception_does_not_suppress_findings():
    detector = registry()
    finding = detector.scan("src/module.py", "eval('unsafe')")
    unrelated = AntiPatternException(
        "AP.001", "src/other.py", "OWNER.001", "unrelated waiver", 100
    )
    assert detector.unresolved(finding, (unrelated,), 3) == finding
