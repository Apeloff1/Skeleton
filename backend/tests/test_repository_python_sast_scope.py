from __future__ import annotations

from pathlib import Path
import runpy

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
