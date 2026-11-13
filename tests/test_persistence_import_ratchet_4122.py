"""Ratchet for the frozen persistence packages (issue #4122, TD ruling on #4267).

``skeleton.persist``, ``skeleton.storage`` and ``skeleton.state`` are deprecated
(docstring-only) in favour of ``skeleton.persistence``. ``ALLOWLIST`` is the
exact set of remaining importers. A new importer fails this test; when you
migrate one, delete its entry (a stale entry also fails), so the count can only
go down. The frozen packages themselves and their ``skeleton/ai/runtime`` twins
are out of scope.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ("persist", "storage", "state")
SCAN_ROOTS = ("skeleton", "backend", "core", "scripts", "tests")
EXCLUDED_ROOTS = (
    "skeleton/persist/",
    "skeleton/storage/",
    "skeleton/state/",
    "skeleton/ai/runtime/storage/",
    "skeleton/ai/runtime/state/",
)
# Files that only *name* the frozen packages to test the freeze/shim itself.
SELF_TESTS = {
    "skeleton/testing/test_persistence_freeze_guard.py",
    "tests/test_persistence_import_ratchet_4122.py",
}

# path -> frozen packages it imports. Shrink only.
ALLOWLIST: dict[str, frozenset[str]] = {
    "skeleton/ai/agents/core/swarm_durable.py": frozenset({'skeleton.state'}),
    "skeleton/ai/agents/jeeves/agent/durable_runtime.py": frozenset({'skeleton.state'}),
    "skeleton/ai/runtime/frontier/runtime/capabilities.py": frozenset({'skeleton.persist'}),
    "skeleton/ai/runtime/training/checkpoint_archive.py": frozenset({'skeleton.storage'}),
    "skeleton/ai/runtime/training/state_cli.py": frozenset({'skeleton.storage'}),
    "skeleton/automation/agents/swarm_durable.py": frozenset({'skeleton.state'}),
    "skeleton/frontier/runtime/capabilities.py": frozenset({'skeleton.persist'}),
    "skeleton/jeeves/agent/durable_runtime.py": frozenset({'skeleton.state'}),
    "skeleton/testing/state_reliability_profiles.py": frozenset({'skeleton.state'}),
    "skeleton/testing/test_cache_architecture.py": frozenset({'skeleton.storage'}),
    "skeleton/testing/test_checkpoint_migrations.py": frozenset({'skeleton.state'}),
    "skeleton/testing/test_content_addressing.py": frozenset({'skeleton.storage'}),
    "skeleton/testing/test_distributed_transactions.py": frozenset({'skeleton.storage'}),
    "skeleton/testing/test_durable_run_store.py": frozenset({'skeleton.state'}),
    "skeleton/testing/test_governed_checkpoint_recovery.py": frozenset({'skeleton.storage'}),
    "skeleton/testing/test_jeeves_durable_runtime.py": frozenset({'skeleton.state'}),
    "skeleton/testing/test_state_reliability_profiles.py": frozenset({'skeleton.state'}),
    "skeleton/testing/test_storage_tiering.py": frozenset({'skeleton.storage'}),
    "skeleton/testing/test_swarm_durable.py": frozenset({'skeleton.state'}),
    "skeleton/testing/test_training_checkpoint_archive.py": frozenset({'skeleton.storage'}),
    "tests/test_persistence_namespace_migration.py": frozenset({'skeleton.persist'}),
}


def _frozen(module: str) -> str | None:
    for name in FROZEN:
        target = f"skeleton.{name}"
        if module == target or module.startswith(target + "."):
            return target
    return None


def _hits(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        mods: list[str] = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            mods = [node.module or ""]
            if node.module == "skeleton":
                mods += [f"skeleton.{a.name}" for a in node.names]
        elif (
            isinstance(node, ast.Call)
            and getattr(node.func, "attr", getattr(node.func, "id", None)) in {"import_module", "__import__"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            mods = [node.args[0].value]
        for mod in mods:
            hit = _frozen(mod)
            if hit:
                out.add(hit)
    return out


def _files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", *SCAN_ROOTS], cwd=ROOT, check=True, capture_output=True
        ).stdout.decode()
        rels = [p for p in out.split("\0") if p.endswith(".py")]
    except (OSError, subprocess.CalledProcessError):
        rels = [p.relative_to(ROOT).as_posix() for r in SCAN_ROOTS for p in (ROOT / r).rglob("*.py")]
    return sorted(
        r for r in rels
        if not r.startswith(EXCLUDED_ROOTS) and r not in SELF_TESTS and "__pycache__" not in r
    )


def current_importers() -> dict[str, frozenset[str]]:
    found: dict[str, frozenset[str]] = {}
    for rel in _files():
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        # Cheap prefilter: only parse files that could name a frozen package.
        if "from skeleton import" not in text and not any(f"skeleton.{n}" in text for n in FROZEN):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        hits = _hits(tree)
        if hits:
            found[rel] = frozenset(hits)
    return found


def test_no_new_frozen_persistence_importers() -> None:
    current = current_importers()
    new = {
        path: sorted(mods - ALLOWLIST.get(path, frozenset()))
        for path, mods in current.items()
        if mods - ALLOWLIST.get(path, frozenset())
    }
    assert new == {}, "new importers of frozen packages (issue #4122); import skeleton.persistence instead"


def test_allowlist_only_shrinks() -> None:
    current = current_importers()
    stale = {
        path: sorted(mods - current.get(path, frozenset()))
        for path, mods in ALLOWLIST.items()
        if mods - current.get(path, frozenset())
    }
    assert stale == {}, "migrated importers: delete these ALLOWLIST entries so the ratchet tightens"


def test_detector_sees_all_import_forms() -> None:
    tree = ast.parse(
        "import skeleton.state\n"
        "from skeleton.storage.cas import X\n"
        "from skeleton import persist\n"
        "import_module('skeleton.persist')\n"
        "from skeleton.persistence.core import store\n"
        "import skeleton.statex\n"
        "from . import state\n"
    )
    assert _hits(tree) == {"skeleton.persist", "skeleton.state", "skeleton.storage"}
