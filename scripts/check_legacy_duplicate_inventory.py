#!/usr/bin/env python3
"""Fail-closed inventory of duplicate *contracts*, not duplicate filenames.

Issue #969 Seed 20 (``reserve-S097-legacy-duplicate-inventory``) classifies
implementations that enforce the same behavior/contract: two scanners that
enforce the same gate, two HTTP error envelopes, two CLI parsers for the same
command family. Filename-level compatibility shims belong to #1035 / Seed 23
and are out of scope here.

Every discovered contract surface is classified as exactly one of:

* canonical — the implementation new callers use
* duplicate — a second full implementation of the same contract
* overlapping — shares the contract fingerprint but is a subset, wrapper, or
  alternate envelope; not a silent second owner
* unknown — discovered and unclassified (always a gate failure)

Matching uses explicit structural fingerprints: defined function/class names,
AST markers (assignment names, class names, import names, string constants),
and documented aliases that expand the function-name set. Basename equality
never classifies a file. Unknown rows fail closed. This checker never deletes
files and never heuristic-closes a surface.

The walk is bound to ``SCAN_ROOTS``. Stdlib only.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


TASK_KEY = "reserve-S097-legacy-duplicate-inventory"
CONFLICT_DOMAIN = "consolidation.readonly.duplicate_inventory"
INVENTORY_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS: tuple[str, ...] = (
    "scripts",
    "backend/scripts",
    "skeleton/application",
    "skeleton/api",
)
SCAN_ROOT_SET = frozenset(SCAN_ROOTS)

SKIP_PARTS = frozenset(
    {
        "__pycache__",
        ".venv",
        "venv",
        "tests",
        "testing",
        "test",
        "legacy_root",
        "node_modules",
        "satellites",
        "branch-snapshots",
    }
)

CLASSIFICATIONS = ("canonical", "duplicate", "overlapping", "unknown")
CLASSIFICATION_SET = frozenset(CLASSIFICATIONS)
TERMINAL_CLASSIFICATIONS = frozenset({"canonical", "duplicate", "overlapping"})


@dataclass(frozen=True, slots=True)
class ContractMember:
    """One classified implementation of a contract family."""

    path: str
    classification: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ContractFamily:
    """A behavior/contract family identified by structural fingerprints."""

    family_id: str
    function_names: tuple[str, ...]
    ast_markers: tuple[str, ...]
    aliases: tuple[str, ...]
    members: tuple[ContractMember, ...]
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ExtractedFingerprint:
    """Structural names taken from one Python module."""

    path: str
    functions: frozenset[str]
    classes: frozenset[str]
    assigns: frozenset[str]
    imports: frozenset[str]
    strings: frozenset[str]
    parse_error: str = ""

    @property
    def definitions(self) -> frozenset[str]:
        return self.functions | self.classes

    @property
    def markers(self) -> frozenset[str]:
        return self.assigns | self.imports | self.strings | self.classes


# Explicit table. Discovery of an unlisted file that matches a family
# fingerprint fails closed as unknown. Classification only — do not mutate.
FAMILIES: tuple[ContractFamily, ...] = (
    ContractFamily(
        family_id="architecture.boundary.gate",
        function_names=("_matches_module",),
        ast_markers=("forbidden_modules", "excluded_prefixes"),
        aliases=("architecture_boundaries", "canonical dependency boundaries"),
        members=(
            ContractMember(
                path="scripts/check_architecture_boundaries.py",
                classification="canonical",
                notes="Kernel I/O, API reverse-dep, and production import boundaries.",
            ),
            ContractMember(
                path="backend/scripts/check_architecture_boundaries.py",
                classification="overlapping",
                notes="Production import RULES only; subset of the scripts/ gate.",
            ),
        ),
        notes="Two scanners enforce the production-boundary gate; scripts/ is the owner.",
    ),
    ContractFamily(
        family_id="process.safety.subprocess_gate",
        function_names=(
            "walk_python_files",
            "_load_backend_gate",
            "argv_violations",
            "_definitely_string_command",
        ),
        ast_markers=("SUBPROCESS_CALLS",),
        aliases=("process safety", "unsafe process invocation"),
        members=(
            ContractMember(
                path="backend/scripts/check_process_safety.py",
                classification="canonical",
                notes="Alias-aware subprocess/os/asyncio spawn policy for backend/.",
            ),
            ContractMember(
                path="scripts/check_repository_process_safety.py",
                classification="overlapping",
                notes="Composes the backend engine and adds argv string-command checks.",
            ),
        ),
        notes="Same subprocess-safety contract; repository wrapper extends scan roots.",
    ),
    ContractFamily(
        family_id="python.sast.gate",
        function_names=("_load_violation_engine", "javascript_violations"),
        ast_markers=(),
        aliases=("Python SAST", "high-confidence SAST"),
        members=(
            ContractMember(
                path="backend/scripts/check_sast_security.py",
                classification="canonical",
                notes="Violation engine for Python and JavaScript/TypeScript primitives.",
            ),
            ContractMember(
                path="scripts/check_repository_python_sast.py",
                classification="overlapping",
                notes="Loads the canonical violations() engine for skeleton/ and scripts/.",
            ),
        ),
        notes="Single SAST policy, two scan-root adapters. Engine stays in backend/scripts.",
    ),
    ContractFamily(
        family_id="http.error.envelope",
        function_names=(
            "error_response",
            "map_error",
            "install_error_handlers",
            "ApiErrorResponse",
        ),
        ast_markers=("JSONResponse",),
        aliases=("error envelope", "ApiErrorResponse"),
        members=(
            ContractMember(
                path="skeleton/api/errors.py",
                classification="canonical",
                notes="Lattice envelope with type/code/message/context via ApiErrorResponse.",
            ),
            ContractMember(
                path="skeleton/api/responses.py",
                classification="overlapping",
                notes="Helper envelope with code/message/context and no type field.",
            ),
        ),
        notes="Two HTTP error JSON envelopes; callers should use the lattice helper.",
    ),
    ContractFamily(
        family_id="application.command.contract",
        function_names=("command_specs", "parity_matrix", "CommandService"),
        ast_markers=("CONTRACT_VERSION", "CommandSpec"),
        aliases=("command contracts", "API/CLI feature-parity"),
        members=(
            ContractMember(
                path="skeleton/application/command_contracts.py",
                classification="canonical",
                notes="Transport-neutral command family parser shared by API and CLI.",
            ),
        ),
        notes="A second command_specs/CommandService in the allowlist is a duplicate parser.",
    ),
)


def _posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_under_scan_root(relative: str) -> bool:
    return any(relative == prefix or relative.startswith(prefix + "/") for prefix in SCAN_ROOTS)


def iter_scan_python_files(repo_root: Path) -> Iterable[Path]:
    """Yield Python files under the declared allowlist only. Never follow symlinks."""
    seen: set[Path] = set()
    for relative_root in SCAN_ROOTS:
        root = repo_root / relative_root
        if root.is_symlink():
            raise OSError(f"scan root must not be a symlink: {relative_root}")
        if not root.is_dir():
            continue
        stack = [root]
        while stack:
            current = stack.pop()
            child_dirs: list[Path] = []
            python_paths: list[Path] = []
            with os.scandir(current) as entries:
                for entry in sorted(entries, key=lambda item: item.name):
                    if entry.name in SKIP_PARTS:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        child_dirs.append(Path(entry.path))
                    elif (
                        entry.is_file(follow_symlinks=False)
                        and entry.name.endswith(".py")
                    ):
                        python_paths.append(Path(entry.path))
            for path in python_paths:
                absolute = path.resolve()
                relative = _posix(path, repo_root)
                if not _is_under_scan_root(relative):
                    continue
                if absolute in seen:
                    continue
                seen.add(absolute)
                yield path
            stack.extend(reversed(child_dirs))


def _assignment_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(node, ast.Name):
        names.append(node.id)
    elif isinstance(node, ast.Tuple):
        for element in node.elts:
            names.extend(_assignment_names(element))
    elif isinstance(node, ast.Starred):
        names.extend(_assignment_names(node.value))
    return names


def extract_fingerprint(path: Path, *, repo_root: Path | None = None) -> ExtractedFingerprint:
    """Parse one module into function names, AST markers, and string constants."""
    relative = _posix(path, repo_root) if repo_root is not None else path.as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return ExtractedFingerprint(
            path=relative,
            functions=frozenset(),
            classes=frozenset(),
            assigns=frozenset(),
            imports=frozenset(),
            strings=frozenset(),
            parse_error=f"{type(exc).__name__}",
        )
    try:
        tree = ast.parse(text, filename=relative)
    except SyntaxError as exc:
        return ExtractedFingerprint(
            path=relative,
            functions=frozenset(),
            classes=frozenset(),
            assigns=frozenset(),
            imports=frozenset(),
            strings=frozenset(),
            parse_error=f"SyntaxError:{exc.lineno or 0}",
        )

    functions: set[str] = set()
    classes: set[str] = set()
    assigns: set[str] = set()
    imports: set[str] = set()
    strings: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                assigns.update(_assignment_names(target))
        elif isinstance(node, ast.AnnAssign) and node.target is not None:
            assigns.update(_assignment_names(node.target))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.asname or alias.name.split(".", 1)[0])
                imports.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported = alias.asname or alias.name
                imports.add(imported)
                imports.add(alias.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if 0 < len(value) <= 80:
                strings.add(value)

    return ExtractedFingerprint(
        path=relative,
        functions=frozenset(functions),
        classes=frozenset(classes),
        assigns=frozenset(assigns),
        imports=frozenset(imports),
        strings=frozenset(strings),
    )


def _callable_aliases(family: ContractFamily) -> frozenset[str]:
    names = set(family.function_names)
    for alias in family.aliases:
        if alias.isidentifier():
            names.add(alias)
    return frozenset(names)


def file_matches_family(extracted: ExtractedFingerprint, family: ContractFamily) -> bool:
    """True when the module implements the family's structural fingerprint.

    Function/class *definitions* (plus documented identifier aliases) supply
    the behavior names. AST markers must all appear as assignment names,
    imports, class names, or string constants. Basename is ignored.
    """
    if extracted.parse_error:
        return False
    callable_names = _callable_aliases(family)
    if callable_names and not (callable_names & extracted.definitions):
        return False
    if family.ast_markers and not set(family.ast_markers) <= extracted.markers:
        return False
    if not callable_names and not family.ast_markers:
        return False
    return True


def _member_map(
    inventory: Sequence[ContractFamily],
) -> dict[str, tuple[ContractFamily, ContractMember]]:
    mapping: dict[str, tuple[ContractFamily, ContractMember]] = {}
    for family in inventory:
        for member in family.members:
            mapping[member.path] = (family, member)
    return mapping


def collect_violations(
    repo_root: Path = REPO_ROOT,
    *,
    inventory: Sequence[ContractFamily] | None = None,
    require_roots: bool = False,
) -> list[str]:
    """Return inventory defects. Unknown and unclassified matches fail closed."""
    families: Sequence[ContractFamily] = FAMILIES if inventory is None else inventory
    errors: list[str] = []

    if require_roots:
        for relative_root in SCAN_ROOTS:
            source_root = repo_root / relative_root
            if not source_root.is_dir():
                errors.append(f"missing required scan root: {relative_root}")

    seen_family_ids: set[str] = set()
    seen_paths: dict[str, str] = {}
    for family in families:
        if family.family_id in seen_family_ids:
            errors.append(f"family_id must be unique: {family.family_id}")
        else:
            seen_family_ids.add(family.family_id)
        if not family.function_names and not family.ast_markers:
            errors.append(f"{family.family_id}: fingerprint must declare function names or AST markers")
        canonicals = [member.path for member in family.members if member.classification == "canonical"]
        if len(canonicals) != 1:
            errors.append(
                f"{family.family_id}: exactly one canonical member required, found {len(canonicals)}"
            )
        for member in family.members:
            if member.path in seen_paths:
                errors.append(
                    f"path {member.path} is claimed by {seen_paths[member.path]} and {family.family_id}"
                )
            else:
                seen_paths[member.path] = family.family_id
            if member.classification not in CLASSIFICATION_SET:
                errors.append(
                    f"{family.family_id}: {member.path} has invalid classification {member.classification!r}"
                )
            if member.classification == "unknown":
                errors.append(
                    f"{family.family_id}: {member.path} unknown status fails closed"
                )
            if not _is_under_scan_root(member.path):
                errors.append(
                    f"{family.family_id}: {member.path} is outside SCAN_ROOTS allowlist"
                )

    members = _member_map(families)
    extracted_by_path: dict[str, ExtractedFingerprint] = {}
    try:
        scanned = list(iter_scan_python_files(repo_root))
    except OSError as exc:
        return [f"scan failed: {type(exc).__name__}: {exc}", *errors]

    for path in scanned:
        relative = _posix(path, repo_root)
        extracted = extract_fingerprint(path, repo_root=repo_root)
        extracted_by_path[relative] = extracted
        if extracted.parse_error:
            errors.append(f"{relative}: cannot validate Python module: {extracted.parse_error}")
            continue
        matches = [family for family in families if file_matches_family(extracted, family)]
        if not matches:
            continue
        listed = members.get(relative)
        if listed is None:
            family_ids = ", ".join(family.family_id for family in matches)
            errors.append(
                f"unknown contract implementation: {relative} matches {family_ids}"
            )
            continue
        family, member = listed
        if family not in matches:
            errors.append(
                f"{relative}: listed under {family.family_id} but fingerprint matches "
                + ", ".join(item.family_id for item in matches)
            )
        extra = [item.family_id for item in matches if item.family_id != family.family_id]
        if extra:
            errors.append(
                f"{relative}: fingerprint collides with {', '.join(extra)} in addition to {family.family_id}"
            )
        if member.classification == "unknown":
            errors.append(f"{relative}: unknown status fails closed")

    for relative, (family, member) in members.items():
        path = repo_root / relative
        if not path.is_file():
            errors.append(f"{family.family_id}: missing listed path {relative}")
            continue
        extracted = extracted_by_path.get(relative)
        if extracted is None:
            extracted = extract_fingerprint(path, repo_root=repo_root)
        if extracted.parse_error:
            if f"{relative}: cannot validate Python module: {extracted.parse_error}" not in errors:
                errors.append(f"{relative}: cannot validate Python module: {extracted.parse_error}")
            continue
        if not file_matches_family(extracted, family):
            errors.append(
                f"{family.family_id}: {relative} does not match declared function/AST fingerprint"
            )

    return errors


def inventory_table(
    repo_root: Path = REPO_ROOT,
    *,
    inventory: Sequence[ContractFamily] | None = None,
) -> list[dict[str, object]]:
    """Return a serializable table of classified contract surfaces."""
    families: Sequence[ContractFamily] = FAMILIES if inventory is None else inventory
    rows: list[dict[str, object]] = []
    for family in families:
        for member in family.members:
            rows.append(
                {
                    "family_id": family.family_id,
                    "path": member.path,
                    "classification": member.classification,
                    "function_names": list(family.function_names),
                    "ast_markers": list(family.ast_markers),
                    "aliases": list(family.aliases),
                    "notes": member.notes,
                    "exists": (repo_root / member.path).is_file(),
                }
            )
    return rows


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (defaults to the checkout containing this script)",
    )
    parser.add_argument(
        "--require-roots",
        action="store_true",
        default=True,
        help="fail closed when a declared scan root is missing (default)",
    )
    parser.add_argument(
        "--allow-missing-roots",
        action="store_false",
        dest="require_roots",
        help="do not require every SCAN_ROOTS entry to exist",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    errors = collect_violations(root, require_roots=args.require_roots)
    if errors:
        print("legacy-duplicate-inventory: rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    rows = inventory_table(root)
    counts: dict[str, int] = {name: 0 for name in CLASSIFICATIONS}
    for row in rows:
        classification = str(row["classification"])
        counts[classification] = counts.get(classification, 0) + 1
    print(
        "legacy-duplicate-inventory: OK "
        f"(task={TASK_KEY} domain={CONFLICT_DOMAIN} version={INVENTORY_VERSION} "
        f"surfaces={len(rows)} canonical={counts['canonical']} "
        f"duplicate={counts['duplicate']} overlapping={counts['overlapping']} "
        f"unknown={counts['unknown']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
