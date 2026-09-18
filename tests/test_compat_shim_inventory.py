from __future__ import annotations

from pathlib import Path

from scripts.check_compat_shim_inventory import (
    DeadShimError,
    Shim,
    collect_violations,
    inventory_table,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "skeleton" / "kernel").mkdir(parents=True)
    (tmp_path / "backend" / "core").mkdir(parents=True)
    _write(tmp_path, "docs/CANONICAL_MODULE_BOUNDARIES.md", "# boundaries\n")
    return tmp_path


def _reexport(*, status: str = "deprecated") -> Shim:
    return Shim(
        shim_id="kernel.workqueue",
        path="skeleton/kernel/workqueue.py",
        status=status,
        canonical_path="skeleton/kernel/work_queue.py",
        kind="reexport",
        symbols=("FairWorkQueue",),
        references=("docs/CANONICAL_MODULE_BOUNDARIES.md",),
        removal="issue:#969",
    )


def test_repository_compat_shim_inventory_is_closed() -> None:
    assert collect_violations(REPO_ROOT, require_roots=True) == []


def test_inventory_table_uses_closed_statuses_and_references() -> None:
    rows = inventory_table()
    assert rows
    statuses = {row["status"] for row in rows}
    assert statuses <= {"active", "deprecated", "dead", "unknown"}
    assert "unknown" not in statuses
    for row in rows:
        assert row["id"]
        assert row["path"]
        assert row["references"]
        if row["status"] in {"active", "deprecated"}:
            assert row["canonical_path"]
            assert row["removal"]


def test_unclassified_compat_module_is_unknown(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "backend/core/new_compat.py", '"""legacy compatibility surface."""\nX = 1\n')

    violations = collect_violations(root, inventory=())

    assert any("unknown compatibility shim" in item for item in violations)
    assert any("backend/core/new_compat.py" in item for item in violations)


def test_filename_compat_without_classification_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "backend/routes/extra_compat.py", "VALUE = 1\n")

    violations = collect_violations(root, inventory=())

    assert any("backend/routes/extra_compat.py" in item for item in violations)


def test_organism_compat_matrix_is_not_treated_as_a_shim(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "skeleton/organism/compat.py", '"""Compatibility matrix."""\nOK = 1\n')

    assert collect_violations(root, inventory=()) == []


def test_unknown_status_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shim = Shim(
        shim_id="mystery",
        path="skeleton/kernel/workqueue.py",
        status="unknown",
        canonical_path="skeleton/kernel/work_queue.py",
        kind="reexport",
        symbols=("FairWorkQueue",),
        references=("docs/CANONICAL_MODULE_BOUNDARIES.md",),
        removal="issue:#969",
    )
    _write(root, shim.path, "from .work_queue import WorkQueue as FairWorkQueue\n")
    _write(root, shim.canonical_path, "class WorkQueue:\n    pass\n")

    violations = collect_violations(root, inventory=(shim,))

    assert any("unknown status fails closed" in item for item in violations)


def test_active_shim_must_declare_removal(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shim = Shim(
        shim_id="kernel.workqueue",
        path="skeleton/kernel/workqueue.py",
        status="active",
        canonical_path="skeleton/kernel/work_queue.py",
        kind="reexport",
        symbols=("FairWorkQueue",),
        references=("docs/CANONICAL_MODULE_BOUNDARIES.md",),
        removal="",
    )
    _write(root, shim.path, "from .work_queue import WorkQueue as FairWorkQueue\n")
    _write(root, shim.canonical_path, "class WorkQueue:\n    pass\n")

    violations = collect_violations(root, inventory=(shim,))

    assert any("must declare a removal issue/date" in item for item in violations)


def test_shim_must_delegate_into_canonical_owner(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shim = _reexport()
    _write(root, shim.path, "class FairWorkQueue:\n    pass\n")
    _write(root, shim.canonical_path, "class WorkQueue:\n    pass\n")

    violations = collect_violations(root, inventory=(shim,))

    assert any("must delegate into canonical owner" in item for item in violations)


def test_canonical_owner_must_not_import_dedicated_shim(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shim = _reexport()
    _write(root, shim.path, "from .work_queue import WorkQueue as FairWorkQueue\n")
    _write(root, shim.canonical_path, "from .workqueue import FairWorkQueue\n")

    violations = collect_violations(root, inventory=(shim,))

    assert any("must not depend back on shim" in item for item in violations)


def test_dead_shim_that_returns_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shim = _reexport(status="dead")
    _write(root, shim.path, "from .work_queue import WorkQueue as FairWorkQueue\n")
    _write(root, shim.canonical_path, "class WorkQueue:\n    pass\n")

    violations = collect_violations(
        root, inventory=(shim,), dead_probe=lambda _shim: {"ok": True}
    )

    assert any("dead shim silently returned" in item for item in violations)


def test_dead_shim_that_raises_is_allowed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shim = _reexport(status="dead")
    _write(root, shim.path, "from .work_queue import WorkQueue as FairWorkQueue\n")
    _write(root, shim.canonical_path, "class WorkQueue:\n    pass\n")

    def _probe(_shim: Shim) -> object:
        raise DeadShimError(_shim.shim_id)

    assert collect_violations(root, inventory=(shim,), dead_probe=_probe) == []


def test_missing_shim_path_fails_closed_for_live_statuses(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shim = _reexport(status="active")
    _write(root, shim.canonical_path, "class WorkQueue:\n    pass\n")

    violations = collect_violations(root, inventory=(shim,))

    assert any("missing shim path" in item for item in violations)


def test_removed_dead_shim_file_is_allowed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shim = _reexport(status="dead")
    _write(root, shim.canonical_path, "class WorkQueue:\n    pass\n")

    assert collect_violations(root, inventory=(shim,)) == []


def test_parse_failure_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shim = _reexport()
    _write(root, shim.path, "def broken(:\n")
    _write(root, shim.canonical_path, "class WorkQueue:\n    pass\n")

    violations = collect_violations(root, inventory=(shim,))

    assert any("cannot validate Python module: SyntaxError" in item for item in violations)


def test_duplicate_shim_ids_fail_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shim = _reexport()
    _write(root, shim.path, "from .work_queue import WorkQueue as FairWorkQueue\n")
    _write(root, shim.canonical_path, "class WorkQueue:\n    pass\n")

    violations = collect_violations(root, inventory=(shim, shim))

    assert any("shim_id must be a unique" in item for item in violations)


def test_missing_canonical_root_fails_closed_when_required(tmp_path: Path) -> None:
    (tmp_path / "skeleton").mkdir()

    violations = collect_violations(tmp_path, inventory=(), require_roots=True)

    assert any("missing canonical source root: backend" in item for item in violations)


def test_test_trees_are_not_scanned_for_unknown_shims(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "backend/tests/fake_compat.py", '"""compatibility shim"""\nX = 1\n')
    _write(root, "skeleton/testing/fake_compat.py", '"""compatibility shim"""\nX = 1\n')

    assert collect_violations(root, inventory=()) == []
