#!/usr/bin/env python3
"""Verify the two installable root package metadata sources agree.

An editable install through requirements.txt may resolve metadata through
pyproject.toml or setup.cfg. Both must advertise identical runtime floors.
"""
from __future__ import annotations

import configparser
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _requirements(values: object) -> list[str]:
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ValueError("dependencies must be a list of nonempty requirement strings")
    return [value.strip() for value in values]



_REQ_NAME = re.compile(
    r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)(?=\[|[<>=!~;@]|\s|$)"
)


def _validate_unique_packages(values: list[str], origin: str, issues: list[str]) -> None:
    """Disallow two constraints on the same canonical distribution name."""
    observed: set[str] = set()
    for value in values:
        match = _REQ_NAME.match(value)
        if match is None:
            raise ValueError(f"{origin}: malformed package requirement")
        canonical = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        if canonical in observed:
            issues.append(f"{origin}: duplicate distribution {canonical}")
        observed.add(canonical)

def validate(pyproject_text: str, setup_text: str) -> list[str]:
    """Return core metadata mismatches, raising for malformed metadata."""
    project = tomllib.loads(pyproject_text)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(setup_text)
    declared = _requirements(project["project"]["dependencies"])
    setup = cfg.get("options", "install_requires")
    from_setup = _requirements([line.strip() for line in setup.splitlines() if line.strip()])
    issues: list[str] = []
    _validate_unique_packages(declared, "pyproject core", issues)
    _validate_unique_packages(from_setup, "setup.cfg core", issues)
    if len(set(declared)) != len(declared):
        issues.append("pyproject core dependencies contain duplicate requirement strings")
    if len(set(from_setup)) != len(from_setup):
        issues.append("setup.cfg core dependencies contain duplicate requirement strings")
    for requirement in sorted(set(declared) - set(from_setup)):
        issues.append("setup.cfg missing exact pyproject requirement: " + requirement)
    for requirement in sorted(set(from_setup) - set(declared)):
        issues.append("setup.cfg introduces divergent requirement: " + requirement)

    # The optional feature sets are another supported installation surface.
    # Compare complete extras rather than one dependency (e.g. OpenAI only).
    optional = project["project"].get("optional-dependencies", {})
    if not isinstance(optional, dict):
        raise ValueError("optional-dependencies must be a mapping")
    setup_extras = {
        name: _requirements([line.strip() for line in raw.splitlines() if line.strip()])
        for name, raw in cfg.items("options.extras_require")
    }
    for extra in sorted(set(optional) | set(setup_extras)):
        if extra not in optional:
            issues.append("setup.cfg introduces unreviewed extra: " + extra)
            continue
        if extra not in setup_extras:
            issues.append("setup.cfg missing optional extra: " + extra)
            continue
        expected = _requirements(optional[extra])
        actual = setup_extras[extra]
        _validate_unique_packages(expected, "pyproject extra " + extra, issues)
        _validate_unique_packages(actual, "setup.cfg extra " + extra, issues)
        if len(expected) != len(set(expected)):
            issues.append("pyproject extra has duplicate requirements: " + extra)
        if len(actual) != len(set(actual)):
            issues.append("setup.cfg extra has duplicate requirements: " + extra)
        for requirement in sorted(set(expected) - set(actual)):
            issues.append("setup.cfg extra " + extra + " missing: " + requirement)
        for requirement in sorted(set(actual) - set(expected)):
            issues.append("setup.cfg extra " + extra + " divergent: " + requirement)
    return issues


def main() -> int:
    try:
        issues = validate(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
            (ROOT / "setup.cfg").read_text(encoding="utf-8"),
        )
    except (OSError, UnicodeError, ValueError, KeyError, configparser.Error) as exc:
        print(f"Root package dependency contract invalid: {type(exc).__name__}: {exc}")
        return 1
    if issues:
        for issue in issues:
            print("Root package dependency mismatch:", issue)
        return 1
    print("Root package dependency metadata aligned across pyproject.toml and setup.cfg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
