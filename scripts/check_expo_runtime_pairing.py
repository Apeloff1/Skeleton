#!/usr/bin/env python3
"""Fail-closed Expo/React/React Native pairing check for repository CI.

SDK 54's pairing is documented at https://docs.expo.dev/versions/latest/.
New Expo SDK support requires an explicit reviewed update to SUPPORTED.
This does not try to guess future SDK compatibility from package versions.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "frontend" / "package.json"
VERSION = re.compile(r"(?P<operator>[~^]?)(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
SUPPORTED: dict[int, dict[str, tuple[int, int]]] = {
    54: {
        "react-native": (0, 81),
        "react": (19, 1),
        "react-dom": (19, 1),
        "react-native-web": (0, 21),
        "@types/react": (19, 1),
    },
}
EXACT = frozenset({"react-native", "react", "react-dom"})


def _parse_version(name: str, value: object, errors: list[str]) -> tuple[str, int, int, int] | None:
    if not isinstance(value, str):
        errors.append(f"{name}: dependency must be a version string")
        return None
    match = VERSION.fullmatch(value)
    if match is None:
        errors.append(f"{name}: expected a stable three-component version, got {value!r}")
        return None
    operator = match.group("operator")
    if name in EXACT and operator:
        errors.append(f"{name}: exact pin required, got range {value!r}")
    return operator, int(match.group("major")), int(match.group("minor")), int(match.group("patch"))


def validate(manifest: Mapping[str, Any]) -> list[str]:
    """Return all actionable version incompatibilities; an empty list passes."""
    errors: list[str] = []
    deps = manifest.get("dependencies")
    if not isinstance(deps, dict):
        return ["frontend/package.json: dependencies must be an object"]
    expo = _parse_version("expo", deps.get("expo"), errors)
    if expo is None:
        return errors
    sdk = expo[1]
    required = SUPPORTED.get(sdk)
    if required is None:
        errors.append(
            f"expo SDK {sdk}: no reviewed compatibility matrix; add a documented "
            "SDK pairing before upgrading"
        )
        return errors
    for name, expected in required.items():
        version = _parse_version(name, deps.get(name), errors)
        if version is not None and version[1:3] != expected:
            errors.append(
                f"{name}: Expo SDK {sdk} requires {expected[0]}.{expected[1]}.x; "
                f"found {version[1]}.{version[2]}.{version[3]}"
            )
    react = deps.get("react")
    react_dom = deps.get("react-dom")
    if isinstance(react, str) and isinstance(react_dom, str) and react != react_dom:
        errors.append(f"react-dom {react_dom!r} must exactly equal react {react!r}")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: check_expo_runtime_pairing.py [package.json]", file=sys.stderr)
        return 2
    path = Path(args[0]) if args else DEFAULT_MANIFEST
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Expo compatibility check failed: unreadable manifest: {exc}", file=sys.stderr)
        return 1
    if not isinstance(parsed, dict):
        print("Expo compatibility check failed: manifest must be an object", file=sys.stderr)
        return 1
    errors = validate(parsed)
    if errors:
        for issue in errors:
            print("Expo compatibility check failed: " + issue, file=sys.stderr)
        return 1
    print("Expo SDK 54 / React 19.1 / React Native 0.81 dependency pairing verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
