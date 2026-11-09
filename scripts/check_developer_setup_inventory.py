#!/usr/bin/env python3
"""Fail-closed developer setup inventory (#969 Seed 21 / reserve-S101).

Compares declared setup surfaces against a closed classification set:
documented, assumed, drifting, unknown.

Surfaces: README.md, AGENTS.md, pyproject optional-deps, requirements*.txt,
.github/workflows setup steps, and package.json engines. Missing required
files or unreadable docs fail closed. Undocumented tools are never invented
as optional. This scanner does not execute package installs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

TASK_ID = "reserve-S101-developer-setup-audit"
CONFLICT_DOMAIN = "dx.readonly.setup_audit"
INVENTORY_VERSION = 1

CLASS_DOCUMENTED = "documented"
CLASS_ASSUMED = "assumed"
CLASS_DRIFTING = "drifting"
CLASS_UNKNOWN = "unknown"
CLOSED_CLASSES = frozenset(
    {CLASS_DOCUMENTED, CLASS_ASSUMED, CLASS_DRIFTING, CLASS_UNKNOWN}
)

DOC_SURFACES = frozenset({"readme", "agents"})
MACHINE_SURFACES = frozenset({"pyproject", "requirements", "workflow", "package_json"})

KNOWN_TOOLS = frozenset(
    {
        "python",
        "node",
        "uv",
        "yarn",
        "npm",
        "pip",
        "pytest",
        "ruff",
        "mypy",
        "black",
    }
)

REQUIRED_DOCS = ("README.md", "AGENTS.md")
REQUIRED_MACHINE = ("pyproject.toml",)

ARCHIVE_PREFIXES = ("satellites/branch-snapshots/",)
SKIP_DIR_NAMES = frozenset(
    {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
)

RUNTIME_SETUP_ACTIONS: dict[str, str | None] = {
    "actions/setup-python": "python",
    "actions/setup-node": "node",
    "astral-sh/setup-uv": "uv",
    "actions/setup-java": None,
    "actions/setup-go": None,
    "actions/setup-dotnet": None,
    "ruby/setup-ruby": None,
}

ENV_ASSIGN_RE = re.compile(
    r"^\s*(PYTHON_VERSION|NODE_VERSION):\s*[\"']?([^\"'\s#]+)",
    re.MULTILINE,
)
USES_RE = re.compile(r"^\s+(?:-\s+)?uses:\s+(\S+)", re.MULTILINE)
PYTHON_VERSION_RE = re.compile(
    r"python-version:\s*(?:\"([^\"]+)\"|'([^']+)'|(\$\{\{[^}]+\}\})|(\S+))",
    re.IGNORECASE,
)
NODE_VERSION_RE = re.compile(
    r"node-version:\s*(?:\"([^\"]+)\"|'([^']+)'|(\$\{\{[^}]+\}\})|(\S+))",
    re.IGNORECASE,
)
YARN_CACHE_RE = re.compile(r"^\s+cache:\s*yarn\s*$", re.MULTILINE | re.IGNORECASE)
ENV_EXPR_RE = re.compile(r"^\$\{\{\s*env\.([A-Z0-9_]+)\s*\}\}$")
DEP_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[^\]]+\])?\s*([^;#]*)"
)
REQUIREMENT_INCLUDE_RE = re.compile(r"^(?:-r|--requirement)\s+(\S+)")
SPEC_PART_RE = re.compile(r"^(>=|<=|>|<|==|=)?\s*v?(\d+(?:\.\d+)*)")
DOC_TOOL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "python",
        re.compile(
            r"\bpython(?:\s+version)?\b(?:\s*(?:>=?|==|=))?\s*(?P<version>\d+\.\d+(?:\.\d+)?)?",
            re.IGNORECASE,
        ),
    ),
    (
        "node",
        re.compile(
            r"\bnode(?:\.js)?(?:\s+version)?\b(?:\s*(?:>=?|==|=))?\s*(?P<version>\d+(?:\.\d+){0,2})?",
            re.IGNORECASE,
        ),
    ),
    (
        "uv",
        re.compile(
            r"\buv(?:x)?\b(?:\s*(?:==|=))?\s*(?P<version>\d+\.\d+\.\d+)?",
            re.IGNORECASE,
        ),
    ),
    (
        "yarn",
        re.compile(
            r"\byarn\b(?:\s*@\s*)?(?P<version>\d+\.\d+\.\d+)?",
            re.IGNORECASE,
        ),
    ),
    (
        "npm",
        re.compile(r"\bnpm\b", re.IGNORECASE),
    ),
    (
        "pip",
        re.compile(r"\bpip(?:3)?\b", re.IGNORECASE),
    ),
    (
        "pytest",
        re.compile(
            r"\bpytest\b(?:\s*(?:>=?|==|=))?\s*(?P<version>\d+(?:\.\d+)*)?",
            re.IGNORECASE,
        ),
    ),
    (
        "ruff",
        re.compile(
            r"\bruff\b(?:\s*(?:>=?|==|=))?\s*(?P<version>\d+(?:\.\d+)*)?",
            re.IGNORECASE,
        ),
    ),
    (
        "mypy",
        re.compile(r"\bmypy\b", re.IGNORECASE),
    ),
    (
        "black",
        re.compile(r"\bblack\b", re.IGNORECASE),
    ),
)


@dataclass(frozen=True)
class SetupClaim:
    name: str
    version: str | None
    source: str
    surface: str


@dataclass(frozen=True)
class SetupItem:
    name: str
    classification: str
    versions: tuple[str, ...]
    sources: tuple[str, ...]
    surfaces: tuple[str, ...]
    note: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "classification": self.classification,
            "versions": list(self.versions),
            "sources": list(self.sources),
            "surfaces": list(self.surfaces),
            "note": self.note,
        }


@dataclass(frozen=True)
class SetupInventory:
    task_key: str
    conflict_domain: str
    schema_version: int
    items: tuple[SetupItem, ...]
    errors: tuple[str, ...]

    def is_closed(self) -> bool:
        return not self.errors and all(
            item.classification == CLASS_DOCUMENTED for item in self.items
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "task_key": self.task_key,
            "conflict_domain": self.conflict_domain,
            "schema_version": self.schema_version,
            "closed": self.is_closed(),
            "errors": list(self.errors),
            "items": [item.to_dict() for item in self.items],
        }


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _in_scope(root: Path, path: Path) -> bool:
    rel = _rel(root, path)
    if rel.startswith("../") or rel == "..":
        return False
    if any(rel.startswith(prefix) for prefix in ARCHIVE_PREFIXES):
        return False
    return not any(part in SKIP_DIR_NAMES for part in path.parts)


def _read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, f"required file missing: {path.as_posix()}"
    except UnicodeDecodeError as exc:
        return None, f"unreadable documentation or setup file {path.as_posix()}: {exc.reason}"
    except OSError as exc:
        return None, f"unreadable documentation or setup file {path.as_posix()}: {exc.strerror or exc}"


def _unique_claims(claims: Iterable[SetupClaim]) -> list[SetupClaim]:
    seen: set[tuple[str, str | None, str, str]] = set()
    out: list[SetupClaim] = []
    for claim in claims:
        key = (claim.name, claim.version, claim.source, claim.surface)
        if key in seen:
            continue
        seen.add(key)
        out.append(claim)
    return out


def _version_tuple(raw: str) -> tuple[int, ...] | None:
    parts = raw.strip().split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _cmp_prefix(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    if padded_left < padded_right:
        return -1
    if padded_left > padded_right:
        return 1
    return 0


def _same_lineage(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    width = min(len(left), len(right))
    return left[:width] == right[:width]


def parse_version_spec(spec: str) -> tuple[tuple[str, tuple[int, ...]], ...] | None:
    spec = spec.strip()
    if not spec:
        return ()
    parts = [part.strip() for part in spec.split(",") if part.strip()]
    parsed: list[tuple[str, tuple[int, ...]]] = []
    for part in parts:
        match = SPEC_PART_RE.match(part)
        if match is None:
            return None
        operator = match.group(1) or "=="
        if operator == "=":
            operator = "=="
        version = _version_tuple(match.group(2))
        if version is None:
            return None
        parsed.append((operator, version))
    return tuple(parsed)


def _pin_satisfies(pin: tuple[int, ...], constraints: Sequence[tuple[str, tuple[int, ...]]]) -> bool:
    for operator, bound in constraints:
        if operator == "==":
            if not _same_lineage(pin, bound):
                return False
            continue
        comparison = _cmp_prefix(pin, bound)
        if operator == ">=" and comparison < 0:
            return False
        if operator == ">" and comparison <= 0:
            return False
        if operator == "<=" and comparison > 0:
            return False
        if operator == "<" and comparison >= 0:
            return False
    return True


def versions_compatible(specs: Sequence[str | None]) -> bool:
    nonempty = [spec.strip() for spec in specs if isinstance(spec, str) and spec.strip()]
    if len(nonempty) <= 1:
        return True
    constraints: list[tuple[str, tuple[int, ...]]] = []
    pins: list[tuple[int, ...]] = []
    for spec in nonempty:
        parsed = parse_version_spec(spec)
        if parsed is None:
            return False
        for operator, version in parsed:
            constraints.append((operator, version))
            if operator == "==":
                pins.append(version)
    if pins:
        longest = max(pins, key=len)
        for pin in pins:
            if not _same_lineage(longest, pin):
                return False
        return _pin_satisfies(longest, constraints)
    floors = [version for operator, version in constraints if operator in {">=", ">"}]
    caps = [version for operator, version in constraints if operator in {"<=", "<"}]
    if floors and caps:
        return _cmp_prefix(max(floors), min(caps)) < 0
    return True


def parse_dependency_spec(raw: str) -> tuple[str, str | None] | None:
    text = raw.split("#", 1)[0].strip()
    if not text or text.startswith("-"):
        return None
    match = DEP_RE.match(text)
    if match is None:
        return None
    name = match.group(1).lower().replace("_", "-")
    version = match.group(2).strip() or None
    return name, version


def _claims_from_docs(source: str, surface: str, text: str) -> list[SetupClaim]:
    claims: list[SetupClaim] = []
    for name, pattern in DOC_TOOL_PATTERNS:
        for match in pattern.finditer(text):
            version = match.groupdict().get("version")
            claims.append(
                SetupClaim(
                    name=name,
                    version=version.strip() if version else None,
                    source=source,
                    surface=surface,
                )
            )
    return claims


def _claims_from_pyproject(source: str, data: Mapping[str, object], errors: list[str]) -> list[SetupClaim]:
    claims: list[SetupClaim] = []
    project = data.get("project")
    if project is None:
        project = {}
    if not isinstance(project, dict):
        errors.append(f"{source}: project table must be an object")
        return claims

    requires_python = project.get("requires-python")
    if isinstance(requires_python, str) and requires_python.strip():
        claims.append(SetupClaim("python", requires_python.strip(), source, "pyproject"))
    elif requires_python is not None:
        errors.append(f"{source}: requires-python must be a string")

    tool = data.get("tool")
    if isinstance(tool, dict):
        uv = tool.get("uv")
        if isinstance(uv, dict):
            required_version = uv.get("required-version")
            if isinstance(required_version, str) and required_version.strip():
                claims.append(SetupClaim("uv", required_version.strip(), source, "pyproject"))
            elif required_version is not None:
                errors.append(f"{source}: tool.uv.required-version must be a string")

    extras = project.get("optional-dependencies", {})
    if extras is None:
        extras = {}
    if not isinstance(extras, dict):
        errors.append(f"{source}: optional-dependencies must be an object")
        return claims
    for extra_name, deps in extras.items():
        if not isinstance(deps, list):
            errors.append(f"{source}: optional-dependencies.{extra_name} must be a list")
            continue
        for index, dep in enumerate(deps):
            if not isinstance(dep, str):
                errors.append(
                    f"{source}: optional-dependencies.{extra_name}[{index}] must be a string"
                )
                continue
            parsed = parse_dependency_spec(dep)
            if parsed is None:
                errors.append(
                    f"{source}: optional-dependencies.{extra_name}[{index}] is not a requirement spec"
                )
                continue
            name, version = parsed
            if name not in KNOWN_TOOLS:
                continue
            claims.append(SetupClaim(name, version, source, "pyproject"))
    return claims


def _claims_from_requirements(
    root: Path,
    path: Path,
    errors: list[str],
    seen: set[Path] | None = None,
) -> list[SetupClaim]:
    if seen is None:
        seen = set()
    resolved = path.resolve()
    if resolved in seen:
        return []
    seen.add(resolved)
    text, error = _read_text(path)
    source = _rel(root, path)
    if error:
        errors.append(error.replace(path.as_posix(), source))
        return []
    assert text is not None
    claims: list[SetupClaim] = []
    root_resolved = root.resolve()
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        include = REQUIREMENT_INCLUDE_RE.match(line)
        if include:
            included = (path.parent / include.group(1)).resolve()
            try:
                included.relative_to(root_resolved)
            except ValueError:
                errors.append(f"{source}:{lineno}: requirements include escapes the repository root")
                continue
            if not included.is_file():
                errors.append(f"{source}:{lineno}: requirements include is missing: {include.group(1)}")
                continue
            claims.extend(_claims_from_requirements(root, included, errors, seen))
            continue
        parsed = parse_dependency_spec(line)
        if parsed is None:
            errors.append(f"{source}:{lineno}: requirement line is not a closed spec")
            continue
        name, version = parsed
        if name not in KNOWN_TOOLS:
            continue
        claims.append(SetupClaim(name, version, source, "requirements"))
    return claims


def _first_group(match: re.Match[str]) -> str:
    for value in match.groups():
        if value:
            return value.strip()
    return ""


def _resolve_workflow_value(raw: str, env: Mapping[str, str], source: str, errors: list[str]) -> str | None:
    value = raw.strip()
    expr = ENV_EXPR_RE.fullmatch(value)
    if expr is None:
        return value
    key = expr.group(1)
    if key not in env:
        errors.append(f"{source}: unresolved workflow env.{key}")
        return None
    return env[key]


def _action_name(reference: str) -> str:
    action = reference.split("#", 1)[0].strip()
    return action.split("@", 1)[0].strip()


def _claims_from_workflow(source: str, text: str, errors: list[str]) -> list[SetupClaim]:
    env = {match.group(1): match.group(2) for match in ENV_ASSIGN_RE.finditer(text)}
    claims: list[SetupClaim] = []
    python_env = env.get("PYTHON_VERSION")
    if python_env:
        claims.append(SetupClaim("python", python_env, source, "workflow"))
    node_env = env.get("NODE_VERSION")
    if node_env:
        claims.append(SetupClaim("node", node_env, source, "workflow"))

    for match in PYTHON_VERSION_RE.finditer(text):
        resolved = _resolve_workflow_value(_first_group(match), env, source, errors)
        if resolved:
            claims.append(SetupClaim("python", resolved, source, "workflow"))
    for match in NODE_VERSION_RE.finditer(text):
        resolved = _resolve_workflow_value(_first_group(match), env, source, errors)
        if resolved:
            claims.append(SetupClaim("node", resolved, source, "workflow"))
    if YARN_CACHE_RE.search(text):
        claims.append(SetupClaim("yarn", None, source, "workflow"))

    for match in USES_RE.finditer(text):
        action = _action_name(match.group(1))
        if action in RUNTIME_SETUP_ACTIONS:
            tool = RUNTIME_SETUP_ACTIONS[action]
            if tool is None:
                claims.append(SetupClaim(action, None, source, "workflow"))
            else:
                claims.append(SetupClaim(tool, None, source, "workflow"))
            continue
        if action.startswith("docker/setup-"):
            continue
        short = action.rsplit("/", 1)[-1]
        if short.startswith("setup-") and short != "setup-buildx-action":
            claims.append(SetupClaim(action, None, source, "workflow"))
    return claims


def _claims_from_package_json(source: str, data: Mapping[str, object], errors: list[str]) -> list[SetupClaim]:
    claims: list[SetupClaim] = []
    engines = data.get("engines", {})
    if engines is None:
        engines = {}
    if engines != {} and not isinstance(engines, dict):
        errors.append(f"{source}: engines must be an object")
        return claims
    if isinstance(engines, dict):
        for key, value in engines.items():
            name = str(key).strip().lower()
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{source}: engines.{key} must be a non-empty string")
                continue
            claims.append(SetupClaim(name, value.strip(), source, "package_json"))
    package_manager = data.get("packageManager")
    if package_manager is None:
        return claims
    if not isinstance(package_manager, str) or not package_manager.strip():
        errors.append(f"{source}: packageManager must be a non-empty string")
        return claims
    name, _, rest = package_manager.strip().partition("@")
    name = name.strip().lower()
    version = rest.split("+", 1)[0].strip() or None
    if not name:
        errors.append(f"{source}: packageManager is missing a tool name")
        return claims
    claims.append(SetupClaim(name, version, source, "package_json"))
    return claims


def classify_claims(claims: Sequence[SetupClaim]) -> tuple[SetupItem, ...]:
    grouped: dict[str, list[SetupClaim]] = {}
    for claim in claims:
        grouped.setdefault(claim.name, []).append(claim)

    items: list[SetupItem] = []
    for name in sorted(grouped):
        group = grouped[name]
        versions = tuple(
            sorted({claim.version for claim in group if claim.version})
        )
        sources = tuple(sorted({claim.source for claim in group}))
        surfaces = tuple(sorted({claim.surface for claim in group}))
        in_docs = any(claim.surface in DOC_SURFACES for claim in group)
        in_machine = any(claim.surface in MACHINE_SURFACES for claim in group)
        compatible = versions_compatible([claim.version for claim in group])

        if name not in KNOWN_TOOLS:
            classification = CLASS_UNKNOWN
            note = "prerequisite is outside the closed tool catalog"
        elif not compatible:
            classification = CLASS_DRIFTING
            note = "version constraints disagree across setup surfaces"
        elif in_docs and in_machine:
            classification = CLASS_DOCUMENTED
            note = "documented and consistent across setup surfaces"
        elif in_machine and not in_docs:
            classification = CLASS_ASSUMED
            note = "machine-readable setup is undocumented"
        elif in_docs and not in_machine:
            classification = CLASS_DRIFTING
            note = "documented but missing from machine-readable setup"
        else:
            classification = CLASS_UNKNOWN
            note = "prerequisite could not be classified"

        if classification not in CLOSED_CLASSES:
            classification = CLASS_UNKNOWN
            note = "classification escaped the closed class set"
        items.append(
            SetupItem(
                name=name,
                classification=classification,
                versions=versions,
                sources=sources,
                surfaces=surfaces,
                note=note,
            )
        )
    return tuple(items)


def _collect_pyproject_paths(root: Path) -> list[Path]:
    paths = [root / "pyproject.toml"]
    backend = root / "backend" / "pyproject.toml"
    if backend.is_file():
        paths.append(backend)
    return paths


def _collect_requirement_paths(root: Path) -> list[Path]:
    paths = sorted(path for path in root.glob("requirements*.txt") if path.is_file())
    backend = root / "backend" / "requirements.txt"
    if backend.is_file():
        paths.append(backend)
    return paths


def _collect_workflow_paths(root: Path) -> list[Path]:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return []
    paths = [
        path
        for path in sorted(workflow_dir.iterdir())
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    ]
    return paths


def _collect_package_json_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(root.rglob("package.json")):
        if not path.is_file() or not _in_scope(root, path):
            continue
        paths.append(path)
    return paths


def scan_developer_setup(root: Path) -> SetupInventory:
    root = root.resolve()
    errors: list[str] = []
    claims: list[SetupClaim] = []

    for relative in REQUIRED_DOCS:
        path = root / relative
        if not path.is_file():
            errors.append(f"required documentation surface missing: {relative}")
            continue
        text, error = _read_text(path)
        if error:
            errors.append(error.replace(path.as_posix(), relative))
            continue
        assert text is not None
        surface = "readme" if relative == "README.md" else "agents"
        claims.extend(_claims_from_docs(relative, surface, text))

    for relative in REQUIRED_MACHINE:
        path = root / relative
        if not path.is_file():
            errors.append(f"required setup surface missing: {relative}")

    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        errors.append("required setup surface missing: .github/workflows")

    for path in _collect_pyproject_paths(root):
        if not path.is_file():
            continue
        source = _rel(root, path)
        text, error = _read_text(path)
        if error:
            errors.append(error.replace(path.as_posix(), source))
            continue
        assert text is not None
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"{source}: invalid TOML: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{source}: pyproject root must be an object")
            continue
        claims.extend(_claims_from_pyproject(source, data, errors))

    for path in _collect_requirement_paths(root):
        claims.extend(_claims_from_requirements(root, path, errors))

    for path in _collect_workflow_paths(root):
        source = _rel(root, path)
        text, error = _read_text(path)
        if error:
            errors.append(error.replace(path.as_posix(), source))
            continue
        assert text is not None
        claims.extend(_claims_from_workflow(source, text, errors))

    for path in _collect_package_json_paths(root):
        source = _rel(root, path)
        text, error = _read_text(path)
        if error:
            errors.append(error.replace(path.as_posix(), source))
            continue
        assert text is not None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"{source}: invalid JSON at line {exc.lineno}, column {exc.colno}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{source}: package.json root must be an object")
            continue
        claims.extend(_claims_from_package_json(source, data, errors))

    items = classify_claims(_unique_claims(claims))
    return SetupInventory(
        task_key=TASK_ID,
        conflict_domain=CONFLICT_DOMAIN,
        schema_version=INVENTORY_VERSION,
        items=items,
        errors=tuple(errors),
    )


def _print_report(inventory: SetupInventory) -> None:
    status = "OK" if inventory.is_closed() else "rejected"
    print(f"developer-setup-inventory: {status}")
    print(f"  task_key: {inventory.task_key}")
    print(f"  conflict_domain: {inventory.conflict_domain}")
    if inventory.errors:
        print("  errors:")
        for error in inventory.errors:
            print(f"    - {error}")
    print("  items:")
    if not inventory.items:
        print("    (none)")
        return
    for item in inventory.items:
        versions = f" [{', '.join(item.versions)}]" if item.versions else ""
        print(
            f"    - {item.name}: {item.classification}{versions} "
            f"sources={','.join(item.sources)}"
        )
        print(f"      {item.note}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root to inventory",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    inventory = scan_developer_setup(args.root)
    if args.json:
        json.dump(inventory.to_dict(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        _print_report(inventory)
    return 0 if inventory.is_closed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
