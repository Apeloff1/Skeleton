#!/usr/bin/env python3
"""Fail-closed inventory of Skeleton compatibility shims.

See ``docs/CANONICAL_MODULE_BOUNDARIES.md``: a capability has one canonical
owner. Compatibility shims may exist during migration, but they must delegate
into that owner, must not grow a second production implementation, and must
never be depended on by the canonical owner.

Every discovered shim is classified as exactly one of:

* active — delegates to the canonical owner and still has a supported surface
* deprecated — still delegates, but is marked for removal
* dead — retired; invoking it must raise rather than return a value
* unknown — discovered and unclassified (always a gate failure)

Unknown rows, missing owners, reverse dependencies, and dead shims that
silently return all fail closed. This module is stdlib-only so it can run
before project dependencies are installed.
"""

from __future__ import annotations

from importlib import import_module

import ast
import re
import sys
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

STATUSES = ("active", "deprecated", "dead", "unknown")
STATUS_SET = frozenset(STATUSES)
KINDS = ("reexport", "alias", "facade", "route", "guarded", "namespace")
KIND_SET = frozenset(KINDS)

PRODUCTION_ROOTS = ("skeleton", "backend")
SKIP_PARTS = frozenset({"tests", "testing", "test", "__pycache__", ".venv", "venv"})
COMPAT_FILENAME_RE = re.compile(r"compat", re.IGNORECASE)
SHIM_DOC_RE = re.compile(
    r"backward-compatible alias"
    r"|this shim exists"
    r"|compatibility shim"
    r"|compatibility facade"
    r"|compatibility namespace"
    r"|legacy llm compatibility"
    r"|legacy compatibility surface"
    r"|legacy academy compatibility"
    r"|guarded shim\s+[—-]",
    re.IGNORECASE,
)

# Filename matches that are domain "compat" language, not module shims.
NOT_SHIM_COMPAT_PATHS = {
    "skeleton/organism/compat.py": (
        "style/mechanic/tone compatibility matrix, not a module shim"
    ),
}


class DeadShimError(RuntimeError):
    """Raised when a retired compatibility shim is invoked."""


@dataclass(frozen=True)
class Shim:
    shim_id: str
    path: str
    status: str
    canonical_path: str
    kind: str
    symbols: tuple[str, ...]
    references: tuple[str, ...]
    removal: str
    notes: str = ""


# Explicit table. Discovery of an unlisted production shim fails closed as unknown.
SHIMS: tuple[Shim, ...] = (
    Shim(
        shim_id="kernel.workqueue",
        path="skeleton/kernel/workqueue.py",
        status="deprecated",
        canonical_path="skeleton/kernel/work_queue.py",
        kind="reexport",
        symbols=("FairWorkQueue", "QueueFullError", "WorkItem"),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "skeleton/testing/test_build_plan_smoke.py",
        ),
        removal="issue:#969",
        notes="Import alias onto weighted-fair DRR WorkQueue; test-locked only.",
    ),
    Shim(
        shim_id="kernel.fair_queue",
        path="skeleton/kernel/fair_queue.py",
        status="deprecated",
        canonical_path="skeleton/kernel/work_queue.py",
        kind="reexport",
        symbols=("FairWorkQueue", "QueueError", "QueueFullError", "WorkItem"),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "skeleton/testing/test_build_plan_smoke.py",
        ),
        removal="issue:#969",
        notes="Orphan heap queue folded into work_queue; names mapped for import compat.",
    ),
    Shim(
        shim_id="kernel.vclock",
        path="skeleton/kernel/vclock.py",
        status="deprecated",
        canonical_path="skeleton/kernel/clocks.py",
        kind="reexport",
        symbols=("ClockError", "ClockRegistry", "VectorClock", "order_events"),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "skeleton/testing/test_build_plan_smoke.py",
        ),
        removal="issue:#969",
        notes="Mutable duplicate folded into clocks.VectorClock.",
    ),
    Shim(
        shim_id="jeeves.core.JeevesCore",
        path="skeleton/jeeves/core.py",
        status="active",
        canonical_path="skeleton/jeeves/core.py",
        kind="alias",
        symbols=("JeevesCore",),
        references=("tests/test_ci1_jeeves_shims.py",),
        removal="issue:#969",
        notes="CI-1 alias: JeevesCore is Jeeves. llm_core.JeevesCore stays distinct.",
    ),
    Shim(
        shim_id="backend.ai_provider_compat",
        path="backend/core/ai_provider_compat.py",
        status="deprecated",
        canonical_path="backend/core/ai_provider.py",
        kind="facade",
        symbols=("LlmChat", "UserMessage", "ChatResponse"),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/PROVIDER_RUNTIME.md",
            "backend/tests/test_ai_provider_compat.py",
        ),
        removal="docs/PROVIDER_RUNTIME.md",
        notes="Legacy chat builder routed through ProviderRegistry; not a second runtime.",
    ),
    Shim(
        shim_id="backend.emergentintegrations.chat",
        path="backend/emergentintegrations/llm/chat.py",
        status="deprecated",
        canonical_path="backend/core/ai_provider_compat.py",
        kind="reexport",
        symbols=("ChatResponse", "LlmChat", "UserMessage"),
        references=(
            "docs/PROVIDER_RUNTIME.md",
            "scripts/check_provider_runtime_boundary.py",
        ),
        removal="docs/PROVIDER_RUNTIME.md",
        notes="Local Emergent import path; new code must use core.ai_provider.",
    ),
    Shim(
        shim_id="backend.emergentintegrations.llm",
        path="backend/emergentintegrations/llm/__init__.py",
        status="deprecated",
        canonical_path="backend/emergentintegrations/llm/chat.py",
        kind="reexport",
        symbols=("LlmChat", "UserMessage"),
        references=("docs/PROVIDER_RUNTIME.md",),
        removal="docs/PROVIDER_RUNTIME.md",
        notes="Package re-export of the local Emergent chat facade.",
    ),
    Shim(
        shim_id="backend.emergentintegrations",
        path="backend/emergentintegrations/__init__.py",
        status="deprecated",
        canonical_path="backend/core/ai_provider_compat.py",
        kind="namespace",
        symbols=(),
        references=("docs/PROVIDER_RUNTIME.md",),
        removal="docs/PROVIDER_RUNTIME.md",
        notes="Historical package path kept importable during provider migration.",
    ),
    Shim(
        shim_id="backend.academy_legacy_compat",
        path="backend/routes/academy_legacy_compat.py",
        status="deprecated",
        canonical_path="backend/routes/academy_v3.py",
        kind="route",
        symbols=("router", "get_topic_module_compat"),
        references=("backend/tests/test_academy_legacy_compat.py",),
        removal="FastAPI deprecated=True; sunset unset",
        notes="Maps retired v2 topic/module URL onto academy_v3 bible/section data.",
    ),
    Shim(
        shim_id="backend.cag_guarded",
        path="backend/services/cag.py",
        status="deprecated",
        canonical_path="skeleton/memory/prefix_renderer.py",
        kind="guarded",
        symbols=("CAGPrefix", "PrefixRegistry", "build_prefix"),
        references=("docs/CANONICAL_MODULE_BOUNDARIES.md",),
        removal="issue:#969",
        notes="Re-exports skeleton.memory.prefix_renderer when importable; local fallback otherwise.",
    ),
    Shim(
        shim_id="backend.mag_guarded",
        path="backend/services/mag.py",
        status="deprecated",
        canonical_path="skeleton/memory/warmer.py",
        kind="guarded",
        symbols=("Filler", "FillerStore", "MemoryWarmer"),
        references=("docs/CANONICAL_MODULE_BOUNDARIES.md",),
        removal="issue:#969",
        notes="Re-exports skeleton.memory.warmer when importable; local fallback otherwise.",
    ),
    Shim(
        shim_id="backend.server.ai_service",
        path="backend/server.py",
        status="active",
        canonical_path="backend/services/ai_assistant_svc.py",
        kind="reexport",
        symbols=("AIAssistantService", "ai_service"),
        references=("backend/services/ai_assistant_svc.py",),
        removal="issue:#969",
        notes="Phase-9 extraction re-export: from server import ai_service.",
    ),
    Shim(
        shim_id="backend.server.quantum_compiler",
        path="backend/server.py",
        status="active",
        canonical_path="backend/services/quantum_compiler_svc.py",
        kind="reexport",
        symbols=("QuantumCompilerService", "quantum_compiler"),
        references=(
            "backend/services/quantum_compiler_svc.py",
            "backend/routes/compiler_tools.py",
        ),
        removal="issue:#969",
        notes="Phase-8 extraction re-export used by compiler_tools.",
    ),
    Shim(
        shim_id="backend.server.self_healer",
        path="backend/server.py",
        status="active",
        canonical_path="backend/services/self_healer_svc.py",
        kind="reexport",
        symbols=("SelfHealingService", "self_healer"),
        references=("backend/services/self_healer_svc.py",),
        removal="issue:#969",
        notes="Phase-7 extraction re-export of self_healer singleton.",
    ),
    Shim(
        shim_id="backend.server.import_export",
        path="backend/server.py",
        status="active",
        canonical_path="backend/services/import_export_svc.py",
        kind="reexport",
        symbols=("ImportExportService", "import_export"),
        references=("backend/services/import_export_svc.py",),
        removal="issue:#969",
        notes="Phase-7 extraction re-export: from server import import_export.",
    ),
    Shim(
        shim_id="backend.server.ai_hub",
        path="backend/server.py",
        status="active",
        canonical_path="backend/services/ai_hub_svc.py",
        kind="reexport",
        symbols=("AIHubService", "get_ai_hub", "ai_hub"),
        references=("backend/services/ai_hub_svc.py",),
        removal="issue:#969",
        notes="Phase-7 extraction; singleton eager-inited for back-compat.",
    ),
    Shim(
        shim_id="backend.galaxy_studio.save_vault_entry",
        path="backend/routes/galaxy_studio.py",
        status="active",
        canonical_path="backend/routes/galaxy_studio_state.py",
        kind="alias",
        symbols=("_save_vault_entry",),
        references=("backend/routes/galaxy_studio.py",),
        removal="issue:#969",
        notes="Binds galaxy_studio_state.save_vault_entry for in-file call sites.",
    ),
)


def inventory_table(shims: Iterable[Shim] = SHIMS) -> tuple[dict[str, object], ...]:
    """Return the shim table as JSON-ready rows."""
    rows = []
    for shim in shims:
        rows.append(
            {
                "id": shim.shim_id,
                "path": shim.path,
                "status": shim.status,
                "canonical_path": shim.canonical_path,
                "kind": shim.kind,
                "symbols": list(shim.symbols),
                "references": list(shim.references),
                "removal": shim.removal,
                "notes": shim.notes,
            }
        )
    return tuple(rows)


def _posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _production_python_files(root: Path) -> Iterable[Path]:
    for name in PRODUCTION_ROOTS:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in SKIP_PARTS for part in path.relative_to(root).parts):
                continue
            yield path


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def discover_shim_paths(
    root: Path, cache: dict[Path, ast.AST | str] | None = None
) -> dict[str, str]:
    """Map production paths that look like shims to the discovery reason."""
    found: dict[str, str] = {}
    for path in _production_python_files(root):
        rel = _posix(path, root)
        if COMPAT_FILENAME_RE.search(path.name):
            found[rel] = "filename"
            continue
        parsed = _parse(path, cache)
        if parsed == "unreadable":
            found[rel] = "unreadable"
            continue
        if isinstance(parsed, str) and parsed.startswith("SyntaxError"):
            found[rel] = "syntax-error"
            continue
        if isinstance(parsed, ast.AST) and SHIM_DOC_RE.search(ast.get_docstring(parsed) or ""):
            found[rel] = "docstring"
    return found


def _module_names_for(rel: str) -> set[str]:
    if not rel.endswith(".py"):
        return set()
    dotted = rel[: -len(".py")].replace("/", ".")
    names = {dotted}
    if dotted.startswith("backend."):
        names.add(dotted[len("backend.") :])
    return names


def _imported_names(tree: ast.AST, file_rel: str) -> set[str]:
    names: set[str] = set()
    file_parts = list(Path(file_rel).with_suffix("").parts)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            package = file_parts[:-1]
            if node.level:
                drop = node.level - 1
                if drop:
                    package = package[: len(package) - drop]
                if node.module:
                    names.add(".".join([*package, *node.module.split(".")]))
                    names.add(node.module)
                else:
                    names.add(".".join(package))
            elif node.module:
                names.add(node.module)
            names.update(alias.name for alias in node.names)
    return names


def _parse(path: Path, cache: dict[Path, ast.AST | str] | None = None) -> ast.AST | str:
    if cache is not None and path in cache:
        return cache[path]
    text = _read_text(path)
    if text is None:
        result: ast.AST | str = "unreadable"
    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                result = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            result = f"SyntaxError: {exc}"
    if cache is not None:
        cache[path] = result
    return result


def _canonical_imports_shim(
    canonical: Path,
    shim: Shim,
    repo_root: Path,
    *,
    module_level: bool,
    cache: dict[Path, ast.AST | str] | None = None,
) -> bool:
    parsed = _parse(canonical, cache)
    if not isinstance(parsed, ast.AST):
        return False
    imported = _imported_names(parsed, _posix(canonical, repo_root))
    if module_level:
        return bool(imported & _module_names_for(shim.path))
    return any(name in imported for name in shim.symbols if name)


def _shim_imports_canonical(
    shim_path: Path,
    shim: Shim,
    repo_root: Path,
    cache: dict[Path, ast.AST | str] | None = None,
) -> bool:
    if shim.path == shim.canonical_path:
        return True
    if shim.kind == "namespace":
        return True
    parsed = _parse(shim_path, cache)
    if not isinstance(parsed, ast.AST):
        return False
    imported = _imported_names(parsed, shim.path)
    canonical_modules = _module_names_for(shim.canonical_path)
    stem = Path(shim.canonical_path).stem
    return bool(imported & canonical_modules) or stem in imported


_DEAD_PROBE_IMPORTERS = {
    "backend.core.ai_provider_compat": lambda: import_module("backend.core.ai_provider_compat"),
    "backend.emergentintegrations.__init__": lambda: import_module("backend.emergentintegrations.__init__"),
    "backend.emergentintegrations.llm.__init__": lambda: import_module("backend.emergentintegrations.llm.__init__"),
    "backend.emergentintegrations.llm.chat": lambda: import_module("backend.emergentintegrations.llm.chat"),
    "backend.routes.academy_legacy_compat": lambda: import_module("backend.routes.academy_legacy_compat"),
    "backend.routes.galaxy_studio": lambda: import_module("backend.routes.galaxy_studio"),
    "backend.server": lambda: import_module("backend.server"),
    "backend.services.cag": lambda: import_module("backend.services.cag"),
    "backend.services.mag": lambda: import_module("backend.services.mag"),
    "skeleton.jeeves.core": lambda: import_module("skeleton.jeeves.core"),
    "skeleton.kernel.fair_queue": lambda: import_module("skeleton.kernel.fair_queue"),
    "skeleton.kernel.vclock": lambda: import_module("skeleton.kernel.vclock"),
    "skeleton.kernel.workqueue": lambda: import_module("skeleton.kernel.workqueue"),
}

def default_dead_probe(shim: Shim) -> object:
    """Importing a dead shim that still loads is a silent return."""
    if not shim.path.endswith(".py"):
        return shim.path
    module_name = sorted(_module_names_for(shim.path), key=len, reverse=True)[0]
    importer = _DEAD_PROBE_IMPORTERS.get(module_name)
    if importer is None:
        return f"unapproved dead-shim module: {module_name}"
    return importer()


def collect_violations(
    repo_root: Path = REPO_ROOT,
    *,
    inventory: tuple[Shim, ...] | None = None,
    require_roots: bool = False,
    dead_probe: Callable[[Shim], object] | None = None,
) -> list[str]:
    """Return human-readable violations. Empty means the inventory is closed."""
    shims = SHIMS if inventory is None else inventory
    violations: list[str] = []
    cache: dict[Path, ast.AST | str] = {}

    if require_roots:
        for name in PRODUCTION_ROOTS:
            if not (repo_root / name).is_dir():
                violations.append(f"missing canonical source root: {name}")

    if not isinstance(shims, (list, tuple)):
        return ["compat shim inventory must be a list of Shim records"]

    seen_ids: set[str] = set()
    covered_paths: set[str] = set()
    path_counts = Counter(shim.path for shim in shims if isinstance(shim, Shim))
    for index, shim in enumerate(shims):
        label = f"shims[{index}]"
        if not isinstance(shim, Shim):
            violations.append(f"{label} must be a Shim record")
            continue
        if not shim.shim_id or shim.shim_id in seen_ids:
            violations.append(f"{label}: shim_id must be a unique non-empty string")
        seen_ids.add(shim.shim_id)
        if shim.status not in STATUS_SET:
            violations.append(f"{shim.shim_id}: status must be one of {sorted(STATUS_SET)}")
        if shim.kind not in KIND_SET:
            violations.append(f"{shim.shim_id}: kind must be one of {sorted(KIND_SET)}")
        if shim.status == "unknown":
            violations.append(f"{shim.shim_id}: unknown status fails closed")
        if shim.status in {"active", "deprecated"} and not shim.removal:
            violations.append(f"{shim.shim_id}: {shim.status} shim must declare a removal issue/date")
        if shim.status in {"active", "deprecated"} and not shim.canonical_path:
            violations.append(f"{shim.shim_id}: {shim.status} shim must declare canonical_path")
        if not shim.references:
            violations.append(f"{shim.shim_id}: references must not be empty")

        shim_file = repo_root / shim.path
        if shim.status == "dead" and not shim_file.exists():
            covered_paths.add(shim.path)
            continue
        if not shim_file.is_file():
            violations.append(f"{shim.shim_id}: missing shim path {shim.path}")
            continue
        covered_paths.add(shim.path)

        for ref in shim.references:
            if ref.startswith("issue:") or "://" in ref:
                continue
            if not (repo_root / ref).exists():
                violations.append(f"{shim.shim_id}: missing reference {ref}")

        parsed = _parse(shim_file, cache)
        if isinstance(parsed, str):
            violations.append(f"{shim.shim_id}: cannot validate Python module: {parsed}")

        if shim.canonical_path and not (repo_root / shim.canonical_path).is_file():
            violations.append(f"{shim.shim_id}: missing canonical_path {shim.canonical_path}")
        elif (
            isinstance(parsed, ast.AST)
            and shim.canonical_path
            and shim.status in {"active", "deprecated"}
        ):
            if not _shim_imports_canonical(shim_file, shim, repo_root, cache):
                violations.append(
                    f"{shim.shim_id}: shim must delegate into canonical owner {shim.canonical_path}"
                )
            canonical_file = repo_root / shim.canonical_path
            dedicated = shim.kind != "alias" and path_counts[shim.path] == 1
            if shim.path != shim.canonical_path and _canonical_imports_shim(
                canonical_file,
                shim,
                repo_root,
                module_level=dedicated,
                cache=cache,
            ):
                violations.append(
                    f"{shim.shim_id}: canonical owner must not depend back on shim"
                )

        if shim.status == "dead":
            probe = default_dead_probe if dead_probe is None else dead_probe
            try:
                result = probe(shim)
            except Exception:
                pass
            else:
                violations.append(
                    f"{shim.shim_id}: dead shim silently returned {result!r}"
                )

    discovered = discover_shim_paths(repo_root, cache)
    for rel, reason in sorted(discovered.items()):
        if rel in NOT_SHIM_COMPAT_PATHS:
            if rel in covered_paths:
                violations.append(f"{rel}: listed as both a shim and a non-shim compat path")
            continue
        if rel not in covered_paths:
            violations.append(f"{rel}: unknown compatibility shim ({reason})")

    return violations


def render_table(shims: Iterable[Shim] = SHIMS) -> str:
    lines = ["id\tstatus\tpath\tcanonical_path\tremoval"]
    for shim in shims:
        lines.append(
            f"{shim.shim_id}\t{shim.status}\t{shim.path}\t{shim.canonical_path}\t{shim.removal}"
        )
    return "\n".join(lines)


def main() -> int:
    violations = collect_violations(REPO_ROOT, require_roots=True)
    print(render_table())
    if not violations:
        print("compat shim inventory: ok")
        return 0
    print("compat shim inventory violations:", file=sys.stderr)
    for item in violations:
        print(f"- {item}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
