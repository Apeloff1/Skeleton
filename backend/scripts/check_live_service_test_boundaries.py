#!/usr/bin/env python3
"""Fail closed when live-service backend tests escape their explicit boundary."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "backend" / "tests"
MANIFEST = TEST_ROOT / "live_service_tests.json"
LIVE_MARKER = "pytestmark = pytest.mark.live_service"
LIVE_MARKER_RE = re.compile(r"(?m)^pytestmark\s*=\s*pytest\.mark\.live_service\b")

# These signatures intentionally target the repository's known external-service
# test style rather than generic URL strings used by SSRF/parser unit fixtures.
LIVE_SERVICE_SIGNATURES = (
    re.compile(r"https?://localhost:\d+"),
    re.compile(r"https?://127\.0\.0\.1:\d+"),
    re.compile(r"https://[A-Za-z0-9.-]+\.preview\.emergentagent\.com"),
)


class BoundaryError(ValueError):
    """The live-service test registry is malformed or out of sync."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BoundaryError(
            f"{path.relative_to(ROOT)}: unreadable test boundary source ({type(exc).__name__})"
        ) from exc


def _load_manifest(path: Path = MANIFEST) -> dict[str, dict[str, str]]:
    try:
        raw: Any = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise BoundaryError("live-service manifest is not valid JSON") from exc
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise BoundaryError("live-service manifest must use version 1")
    tests = raw.get("tests")
    if not isinstance(tests, dict) or not tests:
        raise BoundaryError("live-service manifest must contain a non-empty tests mapping")

    normalized: dict[str, dict[str, str]] = {}
    for name, metadata in tests.items():
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"test_[A-Za-z0-9_]+\.py", name)
            or "/" in name
            or "\\" in name
        ):
            raise BoundaryError(f"invalid live-service test name: {name!r}")
        if not isinstance(metadata, dict):
            raise BoundaryError(f"{name}: metadata must be an object")
        reason = metadata.get("reason")
        target = metadata.get("target")
        if not isinstance(reason, str) or len(reason.strip()) < 20:
            raise BoundaryError(f"{name}: reason must be descriptive")
        if not isinstance(target, str) or not target.strip():
            raise BoundaryError(f"{name}: target must be non-empty text")
        normalized[name] = {"reason": reason.strip(), "target": target.strip()}
    return normalized


def _detected_live_signature(text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in LIVE_SERVICE_SIGNATURES)


def audit(
    *,
    test_root: Path = TEST_ROOT,
    manifest_path: Path = MANIFEST,
) -> tuple[str, ...]:
    manifest = _load_manifest(manifest_path)
    findings: list[str] = []

    try:
        test_files = sorted(test_root.glob("test_*.py"))
    except OSError as exc:
        raise BoundaryError(
            f"unable to enumerate backend tests ({type(exc).__name__})"
        ) from exc
    if not test_files:
        raise BoundaryError("backend test inventory is empty")

    inventory = {path.name: path for path in test_files}
    for name in sorted(manifest):
        path = inventory.get(name)
        if path is None:
            findings.append(f"{name}: manifest entry points to a missing test")
            continue
        text = _read_text(path)
        if LIVE_MARKER_RE.search(text) is None:
            findings.append(f"{name}: missing module-level live_service pytest marker")

    for name, path in sorted(inventory.items()):
        text = _read_text(path)
        marked = LIVE_MARKER_RE.search(text) is not None
        detected = _detected_live_signature(text)
        registered = name in manifest
        if detected and not registered:
            findings.append(
                f"{name}: contains a live-service endpoint signature but is not registered"
            )
        if marked and not registered:
            findings.append(
                f"{name}: uses live_service marker but is absent from the manifest"
            )
        if registered and not marked:
            # Already reported above, but keep this branch deliberately empty
            # so registered status never suppresses future detection checks.
            continue

    return tuple(dict.fromkeys(findings))


def main() -> int:
    try:
        findings = audit()
    except BoundaryError as exc:
        print(f"Live-service test boundary failed closed: {exc}", file=sys.stderr)
        return 1
    if findings:
        print("Live-service test boundary violations:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Live-service test boundary passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
