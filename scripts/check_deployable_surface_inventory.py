#!/usr/bin/env python3
"""Fail-closed deployable-surface inventory (#969 Seed 27 / reserve-S271).

Classifies the closed deployment set: api, backend, frontend, server, desktop,
web, godot, export. A surface is supported only when a matching
entrypoint/workflow/package/export path exists. Docs-only mentions are
declared. Missing required files, and allowlisted surfaces with neither
evidence nor an explicit unsupported marker, are missing_evidence. Unreadable
inputs are unknown. Unknown and missing_evidence fail closed.

This scanner does not classify source-path kinds, capability privileges, the
Godot adapter contract, or release provenance.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

TASK_ID = "reserve-S271-deployable-surface-inventory"
CONFLICT_DOMAIN = "deployment.readonly.surface_inventory"
INVENTORY_VERSION = 1

CLASS_SUPPORTED = "supported"
CLASS_DECLARED = "declared"
CLASS_MISSING = "missing_evidence"
CLASS_UNKNOWN = "unknown"
CLOSED_CLASSES = frozenset(
    {CLASS_SUPPORTED, CLASS_DECLARED, CLASS_MISSING, CLASS_UNKNOWN}
)
CLOSED_SURFACES = (
    "api",
    "backend",
    "frontend",
    "server",
    "desktop",
    "web",
    "godot",
    "export",
)
CLOSED_SURFACE_SET = frozenset(CLOSED_SURFACES)

DOC_ALLOWLIST = (
    "README.md",
    "AGENTS.md",
    "docs/ARCHITECTURE.md",
    "docs/CONSOLIDATION.md",
)

# Paths owned by other inventories / contracts. Never counted as evidence here.
FORBIDDEN_EVIDENCE = frozenset(
    {
        "skeleton/platform/godot_adapter.py",
        "skeleton/testing/test_godot_adapter.py",
        "skeleton/forge/godot_emit.py",
        "skeleton/release/evidence.py",
        "scripts/release_provenance.py",
        "scripts/check_provenance_source_inventory.py",
        "scripts/check_source_path_inventory.py",
        "skeleton/inventory/capabilities.py",
    }
)

ARCHIVE_PREFIXES = ("satellites/branch-snapshots/",)
SKIP_DIR_NAMES = frozenset(
    {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
)

UNSUPPORTED_RE = re.compile(
    r"deployable-surface-unsupported:\s*([A-Za-z][A-Za-z0-9_-]*)",
    re.IGNORECASE,
)
SURFACE_MARK_RE = re.compile(
    r"deployable-surface:\s*([A-Za-z][A-Za-z0-9_-]*)",
    re.IGNORECASE,
)
UNSUPPORTED_FILE_RE = re.compile(
    r"^(?:docs/deployment/)?([a-z][a-z0-9_-]*)\.unsupported$"
)


@dataclass(frozen=True)
class SurfaceSpec:
    name: str
    entrypoints: tuple[str, ...] = ()
    workflows: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    doc_patterns: tuple[str, ...] = ()
    workflow_hints: tuple[str, ...] = ()
    package_scripts: tuple[str, ...] = ()
    export_patterns: tuple[str, ...] = ()


SURFACE_SPECS: tuple[SurfaceSpec, ...] = (
    SurfaceSpec(
        name="api",
        entrypoints=("skeleton/api/server.py", "deploy.py"),
        workflows=(".github/workflows/packaging-runtime-image.yml",),
        packages=("pyproject.toml",),
        required=("skeleton/api/server.py",),
        doc_patterns=(
            r"\bskeleton\.api\b",
            r"\bSkeleton API\b",
            r"\bREST API surface\b",
        ),
        workflow_hints=("Dockerfile", "skeleton.api", "skeleton/developer/cli.py"),
    ),
    SurfaceSpec(
        name="backend",
        entrypoints=("backend/server.py", "backend/Dockerfile"),
        workflows=(
            ".github/workflows/backend-quality.yml",
            ".github/workflows/packaging-runtime-image.yml",
        ),
        packages=("backend/pyproject.toml",),
        required=("backend/server.py", "backend/Dockerfile"),
        doc_patterns=(r"\bbackend\b",),
        workflow_hints=("backend/Dockerfile", "backend-quality"),
    ),
    SurfaceSpec(
        name="frontend",
        entrypoints=("frontend/Dockerfile",),
        workflows=(".github/workflows/packaging-runtime-image.yml",),
        packages=("frontend/package.json",),
        required=("frontend/package.json", "frontend/Dockerfile"),
        doc_patterns=(r"\bfrontend\b",),
        workflow_hints=("frontend/Dockerfile",),
    ),
    SurfaceSpec(
        name="server",
        entrypoints=("Dockerfile", "docker-compose.yml", "deploy.py"),
        workflows=(".github/workflows/packaging-runtime-image.yml",),
        required=("Dockerfile", "docker-compose.yml"),
        doc_patterns=(r"\bAPI server\b", r"\buvicorn\b"),
        workflow_hints=("Dockerfile", "docker build"),
    ),
    SurfaceSpec(
        name="desktop",
        exports=("backend/gameforge/godot_engine/presets.py",),
        doc_patterns=(r"\bdesktop\b", r"\bWindows Desktop\b"),
        export_patterns=(r"Windows Desktop", r"linuxbsd", r"\bmacos\b", r"Linux/X11"),
    ),
    SurfaceSpec(
        name="web",
        entrypoints=("frontend/Dockerfile",),
        packages=("frontend/package.json",),
        exports=(
            "backend/gameforge/deployment/web_export.py",
            "backend/gameforge/godot_engine/presets.py",
        ),
        doc_patterns=(r"\bweb export\b", r"\bexport:web\b", r"desktop / web"),
        package_scripts=("web", "export:web"),
        export_patterns=(
            r'platform="web"',
            r'name="Web"',
            r"\bWebExport\b",
            r"\bweb build\b",
        ),
    ),
    SurfaceSpec(
        name="godot",
        entrypoints=("backend/godot", "backend/routes/godot_engine.py"),
        exports=(
            "backend/gameforge/godot_engine/__init__.py",
            "backend/gameforge/godot_engine/pipeline.py",
        ),
        required=("backend/gameforge/godot_engine/__init__.py",),
        doc_patterns=(r"\bGodot\b",),
    ),
    SurfaceSpec(
        name="export",
        packages=("frontend/package.json",),
        exports=(
            "backend/gameforge/godot_engine/presets.py",
            "backend/gameforge/deployment/web_export.py",
        ),
        required=("backend/gameforge/godot_engine/presets.py",),
        doc_patterns=(r"\bexport presets\b", r"\bexport_presets"),
        package_scripts=("export:web",),
        export_patterns=(r"\[preset\.\d+\]", r"export_path=", r"\bWebExport\b"),
    ),
)


@dataclass(frozen=True)
class SurfaceItem:
    name: str
    classification: str
    evidence: tuple[str, ...]
    declarations: tuple[str, ...]
    missing: tuple[str, ...]
    note: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "classification": self.classification,
            "evidence": list(self.evidence),
            "declarations": list(self.declarations),
            "missing": list(self.missing),
            "note": self.note,
        }


@dataclass(frozen=True)
class SurfaceInventory:
    task_key: str
    conflict_domain: str
    schema_version: int
    items: tuple[SurfaceItem, ...]
    errors: tuple[str, ...]

    def is_closed(self) -> bool:
        if self.errors:
            return False
        names = tuple(item.name for item in self.items)
        if names != CLOSED_SURFACES:
            return False
        return all(
            item.classification in {CLASS_SUPPORTED, CLASS_DECLARED}
            and item.classification in CLOSED_CLASSES
            for item in self.items
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


def _is_file(path: Path) -> tuple[bool, str | None]:
    try:
        return path.is_file(), None
    except OSError as exc:
        return (
            False,
            f"unreadable deployable surface {path.as_posix()}: {exc.strerror or exc}",
        )


def _read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, f"required file missing: {path.as_posix()}"
    except UnicodeDecodeError as exc:
        return None, f"unreadable deployable surface {path.as_posix()}: {exc.reason}"
    except OSError as exc:
        return (
            None,
            f"unreadable deployable surface {path.as_posix()}: {exc.strerror or exc}",
        )


def _normalize_surface(raw: str) -> str:
    return raw.strip().lower().replace("-", "_") if raw else ""


def _spec_by_name() -> dict[str, SurfaceSpec]:
    return {spec.name: spec for spec in SURFACE_SPECS}


def _compiled(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


def _package_matches(spec: SurfaceSpec, payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if spec.name == "frontend":
        return True
    if not spec.package_scripts:
        return spec.name not in {"web", "export"}
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return False
    keys = {str(key) for key in scripts}
    return any(script in keys for script in spec.package_scripts)


def _text_matches(patterns: Sequence[str], text: str) -> bool:
    if not patterns:
        return True
    return any(pattern.search(text) for pattern in _compiled(patterns))


def _collect_doc_hits(
    root: Path, errors: list[str]
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[str]]:
    declarations: dict[str, list[str]] = {name: [] for name in CLOSED_SURFACES}
    unsupported: dict[str, list[str]] = {name: [] for name in CLOSED_SURFACES}
    extra: list[str] = []
    specs = _spec_by_name()

    scanned: list[Path] = []
    for relative in DOC_ALLOWLIST:
        path = root / relative
        if not _in_scope(root, path):
            continue
        scanned.append(path)

    marker_root = root / "docs" / "deployment"
    try:
        marker_exists = marker_root.is_dir()
    except OSError as exc:
        errors.append(
            f"unreadable deployable surface {_rel(root, marker_root)}: {exc.strerror or exc}"
        )
        marker_exists = False
    if marker_exists:
        try:
            children = sorted(marker_root.iterdir())
        except OSError as exc:
            errors.append(
                f"unreadable deployable surface {_rel(root, marker_root)}: {exc.strerror or exc}"
            )
            children = []
        for child in children:
            if child.suffix == ".unsupported" or child.name.endswith(".unsupported"):
                scanned.append(child)

    seen: set[Path] = set()
    for path in scanned:
        resolved = path.resolve() if path.exists() else path
        if resolved in seen:
            continue
        seen.add(resolved)
        rel = _rel(root, path)
        exists, exist_error = _is_file(path)
        if exist_error:
            errors.append(exist_error.replace(path.as_posix(), rel))
            extra.append(rel)
            continue
        if not exists:
            continue
        text, error = _read_text(path)
        if error:
            errors.append(error.replace(path.as_posix(), rel))
            extra.append(rel)
            continue
        assert text is not None

        file_match = UNSUPPORTED_FILE_RE.fullmatch(rel)
        if file_match:
            name = _normalize_surface(file_match.group(1))
            if name in CLOSED_SURFACE_SET:
                unsupported[name].append(rel)
            else:
                extra.append(f"{rel} ({name})")

        for match in UNSUPPORTED_RE.finditer(text):
            name = _normalize_surface(match.group(1))
            if name in CLOSED_SURFACE_SET:
                unsupported[name].append(rel)
            else:
                extra.append(f"{rel}:{name}")

        for match in SURFACE_MARK_RE.finditer(text):
            name = _normalize_surface(match.group(1))
            if name in CLOSED_SURFACE_SET:
                declarations[name].append(rel)
            else:
                extra.append(f"{rel}:{name}")

        # Doc-term hits are declarations, not evidence.
        for surface_name, surface_spec in specs.items():
            if _text_matches(surface_spec.doc_patterns, text):
                declarations[surface_name].append(rel)

    return declarations, unsupported, extra


def _record_unknown(errors: list[str], message: str) -> None:
    if message not in errors:
        errors.append(message)


def _inspect_path(
    root: Path,
    relative: str,
    spec: SurfaceSpec,
    kind: str,
    errors: list[str],
) -> tuple[str | None, str | None]:
    """Return (evidence_label, missing_or_unknown_note)."""

    if relative in FORBIDDEN_EVIDENCE:
        return None, None
    path = root / relative
    if not _in_scope(root, path):
        return None, None
    exists, exist_error = _is_file(path)
    if exist_error:
        _record_unknown(errors, exist_error.replace(path.as_posix(), relative))
        return None, f"unknown:{relative}"
    if not exists:
        return None, relative if relative in spec.required else None

    if kind == "entrypoint":
        return f"entrypoint:{relative}", None

    text, error = _read_text(path)
    if error:
        _record_unknown(errors, error.replace(path.as_posix(), relative))
        return None, f"unknown:{relative}"
    assert text is not None

    if kind == "workflow":
        if spec.workflow_hints and not any(
            hint in text for hint in spec.workflow_hints
        ):
            return None, None
        return f"workflow:{relative}", None

    if kind == "package":
        if relative.endswith("package.json"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                _record_unknown(
                    errors,
                    f"{relative}: invalid JSON at line {exc.lineno}, column {exc.colno}",
                )
                return None, f"unknown:{relative}"
            if not _package_matches(spec, payload):
                return None, None
        return f"package:{relative}", None

    if kind == "export":
        if spec.export_patterns and not _text_matches(spec.export_patterns, text):
            return None, None
        return f"export:{relative}", None

    _record_unknown(errors, f"{relative}: unknown evidence kind {kind}")
    return None, f"unknown:{relative}"


def _classify_surface(
    spec: SurfaceSpec,
    *,
    evidence: Sequence[str],
    declarations: Sequence[str],
    unsupported: Sequence[str],
    missing_required: Sequence[str],
    unknown_paths: Sequence[str],
) -> SurfaceItem:
    note = ""
    if unknown_paths:
        classification = CLASS_UNKNOWN
        note = "unreadable deployable surface fails closed"
    elif missing_required:
        classification = CLASS_MISSING
        note = "required surface file is missing"
    elif evidence:
        classification = CLASS_SUPPORTED
        note = "matching entrypoint/workflow/package/export path exists"
    elif unsupported or declarations:
        classification = CLASS_DECLARED
        if unsupported:
            note = "declared unsupported; no matching deploy path"
        else:
            note = "docs mention the surface; no matching deploy path"
    else:
        classification = CLASS_MISSING
        note = (
            "allowlisted surface has neither evidence nor explicit unsupported marker"
        )
    return SurfaceItem(
        name=spec.name,
        classification=classification,
        evidence=tuple(evidence),
        declarations=tuple(dict.fromkeys((*declarations, *unsupported))),
        missing=tuple(missing_required),
        note=note,
    )


def scan_deployable_surfaces(root: Path) -> SurfaceInventory:
    errors: list[str] = []
    if SURFACE_SPECS[0].name != CLOSED_SURFACES[0] or len(SURFACE_SPECS) != len(
        CLOSED_SURFACES
    ):
        errors.append("surface spec table must match the closed surface set")
    spec_names = tuple(spec.name for spec in SURFACE_SPECS)
    if spec_names != CLOSED_SURFACES:
        errors.append(
            "surface spec names must equal closed surfaces: "
            + ", ".join(CLOSED_SURFACES)
        )

    declarations, unsupported, extra = _collect_doc_hits(root, errors)
    if extra:
        for item in extra:
            errors.append(f"unknown deployable surface marker: {item}")

    items: list[SurfaceItem] = []
    for spec in SURFACE_SPECS:
        evidence: list[str] = []
        missing_required: list[str] = []
        unknown_paths: list[str] = []

        required = set(spec.required)
        seen_required: set[str] = set()

        checks: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("entrypoint", spec.entrypoints),
            ("workflow", spec.workflows),
            ("package", spec.packages),
            ("export", spec.exports),
        )
        for kind, relatives in checks:
            for relative in relatives:
                label, missing = _inspect_path(root, relative, spec, kind, errors)
                if relative in required:
                    seen_required.add(relative)
                if label:
                    if label not in evidence:
                        evidence.append(label)
                elif missing:
                    if missing.startswith("unknown:"):
                        unknown_paths.append(missing.split(":", 1)[1])
                    elif missing not in missing_required:
                        missing_required.append(missing)

        for relative in spec.required:
            if relative in seen_required:
                continue
            path = root / relative
            exists, exist_error = _is_file(path)
            if exist_error:
                errors.append(exist_error.replace(path.as_posix(), relative))
                unknown_paths.append(relative)
                continue
            if not exists:
                missing_required.append(relative)

        item = _classify_surface(
            spec,
            evidence=evidence,
            declarations=declarations.get(spec.name, ()),
            unsupported=unsupported.get(spec.name, ()),
            missing_required=missing_required,
            unknown_paths=unknown_paths,
        )
        if item.classification not in CLOSED_CLASSES:
            errors.append(
                f"{spec.name}: classification {item.classification} is unknown"
            )
        if item.classification == CLASS_UNKNOWN:
            errors.append(f"{spec.name}: unknown unreadable deployable surface")
        if item.classification == CLASS_MISSING:
            errors.append(f"{spec.name}: {item.note}")
        forbidden_hits = [
            path
            for path in item.evidence
            if path.split(":", 1)[-1] in FORBIDDEN_EVIDENCE
        ]
        if forbidden_hits:
            errors.append(
                f"{spec.name}: evidence collides with out-of-scope inventory "
                + ", ".join(forbidden_hits)
            )
        items.append(item)

    found = {item.name for item in items}
    for name in CLOSED_SURFACES:
        if name not in found:
            errors.append(
                f"{name}: allowlisted surface has neither evidence nor explicit unsupported marker"
            )

    return SurfaceInventory(
        task_key=TASK_ID,
        conflict_domain=CONFLICT_DOMAIN,
        schema_version=INVENTORY_VERSION,
        items=tuple(items),
        errors=tuple(dict.fromkeys(errors)),
    )


def _print_report(inventory: SurfaceInventory) -> None:
    status = "OK" if inventory.is_closed() else "rejected"
    print(f"deployable-surface-inventory: {status}")
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
        evidence = ",".join(item.evidence) if item.evidence else "-"
        print(f"    - {item.name}: {item.classification} evidence={evidence}")
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
    inventory = scan_deployable_surfaces(args.root)
    if args.json:
        json.dump(inventory.to_dict(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        _print_report(inventory)
    return 0 if inventory.is_closed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
