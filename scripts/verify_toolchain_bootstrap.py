#!/usr/bin/env python3
"""Verify the pinned Skeleton bootstrap toolchain and host capabilities.

Canonical user command:

    mise run bootstrap

The mise task installs the exact Python/Node/uv versions from .mise.toml and
then executes this verifier under that pinned environment. The verifier never
downloads software itself and never invokes a shell.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "machine" / "toolchain_bootstrap.json"
MISE_PATH = ROOT / ".mise.toml"
MAX_MANIFEST_BYTES = 64 * 1024
EXPECTED_TOOL_NAMES = frozenset({"python", "node", "uv"})
EXPECTED_TOP_KEYS = frozenset(
    {
        "schema_version",
        "manager",
        "manager_config",
        "bootstrap_command",
        "installed_toolchains",
        "verified_capabilities",
        "supported_hosts",
    }
)
VERSION_RE = re.compile(r"^(?:v|Python\s+|uv\s+)?(?P<version>\d+\.\d+\.\d+)\b")
GIT_VERSION_RE = re.compile(r"\bgit version (?P<version>\d+\.\d+(?:\.\d+)?)\b")
JAVA_VERSION_RE = re.compile(
    r"\b(?:java|openjdk)(?:\s+version)?\s+\"?(?P<major>\d+)(?:[._]\d+)*",
    re.IGNORECASE,
)


class ToolchainBootstrapError(ValueError):
    """Bootstrap configuration or observed host state is invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ToolchainBootstrapError(f"cannot stat bootstrap manifest: {path}") from exc
    if size > MAX_MANIFEST_BYTES:
        raise ToolchainBootstrapError("bootstrap manifest exceeds safety bound")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ToolchainBootstrapError("cannot read bootstrap manifest") from exc
    if not isinstance(payload, dict):
        raise ToolchainBootstrapError("bootstrap manifest must be a JSON object")
    return payload


def _read_mise(path: Path) -> dict[str, Any]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ToolchainBootstrapError("cannot read .mise.toml") from exc
    if not isinstance(payload, dict):
        raise ToolchainBootstrapError(".mise.toml must decode to an object")
    return payload


def _bounded_text(value: Any, *, field: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ToolchainBootstrapError(f"{field} must be a non-empty trimmed string")
    if len(value) > maximum or any(ch in value for ch in ("\x00", "\n", "\r")):
        raise ToolchainBootstrapError(f"{field} contains invalid characters or length")
    return value


def _version_tuple(value: str, *, field: str) -> tuple[int, ...]:
    text = _bounded_text(value, field=field, maximum=64)
    parts = text.split(".")
    if not 2 <= len(parts) <= 4 or any(not part.isdigit() for part in parts):
        raise ToolchainBootstrapError(f"{field} must be a dotted numeric version")
    return tuple(int(part) for part in parts)


def load_contract(
    manifest_path: Path = MANIFEST_PATH,
    mise_path: Path = MISE_PATH,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _read_json(manifest_path)
    mise = _read_mise(mise_path)

    if set(manifest) != EXPECTED_TOP_KEYS:
        missing = sorted(EXPECTED_TOP_KEYS - set(manifest))
        extra = sorted(set(manifest) - EXPECTED_TOP_KEYS)
        raise ToolchainBootstrapError(
            f"bootstrap manifest keys mismatch; missing={missing} extra={extra}"
        )
    if manifest["schema_version"] != 1:
        raise ToolchainBootstrapError("unsupported bootstrap manifest schema")
    if manifest["manager"] != "mise":
        raise ToolchainBootstrapError("bootstrap manager must be mise")
    if manifest["manager_config"] != ".mise.toml":
        raise ToolchainBootstrapError("bootstrap manager config must be .mise.toml")
    if manifest["bootstrap_command"] != "mise run bootstrap":
        raise ToolchainBootstrapError("canonical bootstrap command drifted")

    tools = manifest["installed_toolchains"]
    if not isinstance(tools, dict) or set(tools) != EXPECTED_TOOL_NAMES:
        raise ToolchainBootstrapError(
            "installed_toolchains must contain exactly python, node, and uv"
        )
    for name in sorted(EXPECTED_TOOL_NAMES):
        _version_tuple(tools[name], field=f"installed_toolchains.{name}")

    mise_tools = mise.get("tools")
    if not isinstance(mise_tools, dict):
        raise ToolchainBootstrapError(".mise.toml is missing [tools]")
    for name in sorted(EXPECTED_TOOL_NAMES):
        if mise_tools.get(name) != tools[name]:
            raise ToolchainBootstrapError(
                f".mise.toml {name} pin does not match bootstrap manifest"
            )

    tasks = mise.get("tasks")
    bootstrap = tasks.get("bootstrap") if isinstance(tasks, dict) else None
    if not isinstance(bootstrap, dict):
        raise ToolchainBootstrapError(".mise.toml is missing [tasks.bootstrap]")
    expected_run = [
        "mise install",
        "mise exec -- python scripts/verify_toolchain_bootstrap.py",
    ]
    if bootstrap.get("run") != expected_run:
        raise ToolchainBootstrapError("bootstrap task command sequence drifted")

    capabilities = manifest["verified_capabilities"]
    if not isinstance(capabilities, dict) or set(capabilities) != {
        "java_major",
        "git_minimum",
    }:
        raise ToolchainBootstrapError("verified_capabilities keys mismatch")
    java_major = capabilities["java_major"]
    if isinstance(java_major, bool) or not isinstance(java_major, int) or java_major < 1:
        raise ToolchainBootstrapError("java_major must be a positive integer")
    _version_tuple(capabilities["git_minimum"], field="git_minimum")

    hosts = manifest["supported_hosts"]
    if not isinstance(hosts, dict) or set(hosts) != {"systems", "architectures"}:
        raise ToolchainBootstrapError("supported_hosts keys mismatch")
    for field in ("systems", "architectures"):
        values = hosts[field]
        if not isinstance(values, list) or not values:
            raise ToolchainBootstrapError(f"supported_hosts.{field} must be non-empty")
        normalized: list[str] = []
        for value in values:
            text = _bounded_text(value, field=f"supported_hosts.{field}")
            if text in normalized:
                raise ToolchainBootstrapError(
                    f"supported_hosts.{field} contains duplicate {text}"
                )
            normalized.append(text)

    return manifest, mise


def _default_runner(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(command),
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
        )
    except OSError as exc:
        raise ToolchainBootstrapError(
            f"required executable is unavailable: {command[0]}"
        ) from exc
    if result.returncode != 0:
        raise ToolchainBootstrapError(
            f"command failed ({result.returncode}): {' '.join(command)}"
        )
    return result.stdout.strip()


def _exact_tool_version(output: str, *, tool: str) -> str:
    first_line = output.strip().splitlines()[0] if output.strip() else ""
    match = VERSION_RE.match(first_line)
    if match is None:
        raise ToolchainBootstrapError(f"cannot parse {tool} version output")
    return match.group("version")


def _git_version(output: str) -> tuple[int, ...]:
    match = GIT_VERSION_RE.search(output)
    if match is None:
        raise ToolchainBootstrapError("cannot parse git version output")
    return _version_tuple(match.group("version"), field="git version")


def _java_major(output: str) -> int:
    match = JAVA_VERSION_RE.search(output)
    if match is None:
        raise ToolchainBootstrapError("cannot parse Java version output")
    return int(match.group("major"))


def verify_environment(
    manifest: dict[str, Any],
    *,
    runner: Callable[[Sequence[str]], str] | None = None,
    system_name: str | None = None,
    machine_name: str | None = None,
) -> dict[str, Any]:
    run = runner or _default_runner
    system_value = system_name or platform.system()
    machine_value = machine_name or platform.machine()

    hosts = manifest["supported_hosts"]
    if system_value not in hosts["systems"]:
        raise ToolchainBootstrapError(
            f"unsupported host system: {system_value or '<empty>'}"
        )
    if machine_value not in hosts["architectures"]:
        raise ToolchainBootstrapError(
            f"unsupported host architecture: {machine_value or '<empty>'}"
        )

    expected = manifest["installed_toolchains"]
    observed = {
        "python": _exact_tool_version(run(["python", "--version"]), tool="python"),
        "node": _exact_tool_version(run(["node", "--version"]), tool="node"),
        "uv": _exact_tool_version(run(["uv", "--version"]), tool="uv"),
    }
    for name in sorted(EXPECTED_TOOL_NAMES):
        if observed[name] != expected[name]:
            raise ToolchainBootstrapError(
                f"{name} version mismatch: {observed[name]} != {expected[name]}"
            )

    minimum_git = _version_tuple(
        manifest["verified_capabilities"]["git_minimum"],
        field="git_minimum",
    )
    observed_git = _git_version(run(["git", "--version"]))
    if observed_git < minimum_git:
        raise ToolchainBootstrapError(
            "git version is below bootstrap minimum: "
            f"{'.'.join(map(str, observed_git))} < "
            f"{manifest['verified_capabilities']['git_minimum']}"
        )

    observed_java = _java_major(run(["java", "-version"]))
    minimum_java = manifest["verified_capabilities"]["java_major"]
    if observed_java < minimum_java:
        raise ToolchainBootstrapError(
            f"Java major is below bootstrap minimum: {observed_java} < {minimum_java}"
        )

    mise_version = _bounded_text(
        run(["mise", "--version"]).splitlines()[0],
        field="mise version output",
        maximum=256,
    )

    return {
        "schema": 1,
        "bootstrap_command": manifest["bootstrap_command"],
        "system": system_value,
        "architecture": machine_value,
        "toolchains": observed,
        "git_version": ".".join(map(str, observed_git)),
        "java_major": observed_java,
        "mise_version": mise_version,
    }


def main() -> int:
    try:
        manifest, _mise = load_contract()
        evidence = verify_environment(manifest)
    except ToolchainBootstrapError as exc:
        print(f"toolchain bootstrap verification failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
