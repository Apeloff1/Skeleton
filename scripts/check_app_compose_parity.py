#!/usr/bin/env python3
"""Validate normalized Docker Compose topology against the assembly manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _string_list(value: object, *, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return tuple(sorted(set(value)))


def manifest_topology(manifest: Mapping[str, object]) -> dict[str, dict[str, tuple[str, ...]]]:
    raw_services = manifest.get("services")
    if not isinstance(raw_services, list):
        raise ValueError("manifest services must be a list")

    topology: dict[str, dict[str, tuple[str, ...]]] = {}
    for index, raw_service in enumerate(raw_services):
        service = _mapping(raw_service, label=f"manifest service[{index}]")
        name = service.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"manifest service[{index}] name must be a non-empty string")
        if name in topology:
            raise ValueError(f"manifest service names must be unique: {name!r}")

        depends_on = _string_list(
            service.get("depends_on", []),
            label=f"manifest service {name!r} depends_on",
        )
        raw_profile = service.get("profile")
        if raw_profile in (None, ""):
            profiles: tuple[str, ...] = ()
        elif isinstance(raw_profile, str):
            profiles = (raw_profile,)
        else:
            raise ValueError(f"manifest service {name!r} profile must be a string")

        topology[name] = {
            "depends_on": depends_on,
            "profiles": profiles,
        }
    return topology


def compose_topology(model: Mapping[str, object]) -> dict[str, dict[str, tuple[str, ...]]]:
    raw_services = _mapping(model.get("services"), label="compose services")
    topology: dict[str, dict[str, tuple[str, ...]]] = {}

    for name, raw_service in raw_services.items():
        if not isinstance(name, str) or not name:
            raise ValueError("compose service name must be a non-empty string")
        service = _mapping(raw_service, label=f"compose service {name!r}")

        raw_depends_on = service.get("depends_on", {})
        if raw_depends_on is None:
            depends_on: tuple[str, ...] = ()
        elif isinstance(raw_depends_on, Mapping):
            depends_on = tuple(sorted(str(dep) for dep in raw_depends_on))
        elif isinstance(raw_depends_on, list) and all(
            isinstance(dep, str) for dep in raw_depends_on
        ):
            depends_on = tuple(sorted(set(raw_depends_on)))
        else:
            raise ValueError(
                f"compose service {name!r} depends_on must be an object or list"
            )

        profiles = _string_list(
            service.get("profiles", []),
            label=f"compose service {name!r} profiles",
        )
        topology[name] = {
            "depends_on": depends_on,
            "profiles": profiles,
        }

    return topology


def parity_errors(
    manifest: Mapping[str, object],
    compose_model: Mapping[str, object],
) -> list[str]:
    expected = manifest_topology(manifest)
    actual = compose_topology(compose_model)
    errors: list[str] = []

    expected_names = set(expected)
    actual_names = set(actual)
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    if missing:
        errors.append(f"compose is missing manifest services: {missing}")
    if extra:
        errors.append(f"compose has services absent from manifest: {extra}")

    for name in sorted(expected_names & actual_names):
        expected_deps = expected[name]["depends_on"]
        actual_deps = actual[name]["depends_on"]
        if expected_deps != actual_deps:
            errors.append(
                f"{name}: depends_on drift: manifest={list(expected_deps)} "
                f"compose={list(actual_deps)}"
            )

        expected_profiles = expected[name]["profiles"]
        actual_profiles = actual[name]["profiles"]
        if expected_profiles != actual_profiles:
            errors.append(
                f"{name}: profile drift: manifest={list(expected_profiles)} "
                f"compose={list(actual_profiles)}"
            )

    return errors


def _load_json(path: Path, *, label: str) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} JSON invalid: {exc}") from exc
    return _mapping(payload, label=label)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("compose_model", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("skeleton/app/manifest.json"),
    )
    args = parser.parse_args(argv)

    try:
        manifest = _load_json(args.manifest, label="manifest")
        compose_model = _load_json(args.compose_model, label="compose model")
        errors = parity_errors(manifest, compose_model)
    except (OSError, ValueError) as exc:
        print(f"Compose parity validation failed: {exc}")
        return 1

    if errors:
        print(f"Compose parity validation failed: {len(errors)} issue(s)")
        for error in errors:
            print(f" - {error}")
        return 1

    services = sorted(manifest_topology(manifest))
    print(
        "Compose parity validation passed: "
        f"{len(services)} services with matching dependencies and profiles"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
