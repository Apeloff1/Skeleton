from __future__ import annotations

from pathlib import Path
import runpy

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "scripts" / "check_repository_python_sast.py"


def _scanner_namespace() -> dict[str, object]:
    return runpy.run_path(str(SCANNER))


def test_repository_python_sast_covers_core_and_tooling() -> None:
    namespace = _scanner_namespace()
    python_files = namespace["python_files"]
    files = list(python_files())
    relative = [path.relative_to(REPO_ROOT) for path in files]

    assert any(path.parts and path.parts[0] == "skeleton" for path in relative)
    assert any(path.parts and path.parts[0] == "scripts" for path in relative)


def test_repository_python_sast_reuses_canonical_violation_engine(tmp_path: Path) -> None:
    namespace = _scanner_namespace()
    load_engine = namespace["_load_violation_engine"]
    violations = load_engine()

    sample = tmp_path / "unsafe.py"
    sample.write_text("value = eval(user_input)\n", encoding="utf-8")

    findings = violations(sample)
    assert any("eval() is forbidden" in finding for finding in findings)



def test_repository_python_sast_main_rejects_zero_file_scan(capsys) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]
    main.__globals__["python_files"] = lambda: iter(())

    assert main() == 2
    captured = capsys.readouterr()
    assert "zero core/tooling Python files scanned" in captured.err


def test_repository_python_sast_required_root_cannot_disappear(tmp_path: Path) -> None:
    namespace = _scanner_namespace()
    python_files = namespace["python_files"]
    python_files.__globals__["SCAN_ROOTS"] = (tmp_path / "missing",)

    with pytest.raises(OSError, match="required scan root is unavailable"):
        list(python_files())


def test_repository_python_sast_required_root_cannot_be_symlink(
    tmp_path: Path,
) -> None:
    namespace = _scanner_namespace()
    python_files = namespace["python_files"]
    real = tmp_path / "real"
    real.mkdir()
    (real / "safe.py").write_text("value = 1\n", encoding="utf-8")
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    python_files.__globals__["SCAN_ROOTS"] = (linked,)

    with pytest.raises(OSError, match="must not be a symlink"):
        list(python_files())


def test_repository_python_sast_main_redacts_traversal_error_details(capsys) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]

    def broken_files():
        raise OSError("sensitive mount detail")
        yield  # pragma: no cover

    main.__globals__["python_files"] = broken_files

    assert main() == 2
    captured = capsys.readouterr()
    assert "Repository Python SAST scan failed: OSError" in captured.err
    assert "sensitive mount detail" not in captured.err
