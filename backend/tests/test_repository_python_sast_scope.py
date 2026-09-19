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



def test_repository_python_sast_fails_closed_when_required_root_missing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]
    missing = tmp_path / "missing"
    monkeypatch.setitem(main.__globals__, "SCAN_ROOTS", (missing,))

    assert main() == 1
    assert "required scan root missing" in capsys.readouterr().err


def test_repository_python_sast_fails_closed_when_required_root_is_empty(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setitem(main.__globals__, "SCAN_ROOTS", (empty,))

    assert main() == 1
    assert "no Python files scanned under" in capsys.readouterr().err


def test_repository_python_sast_requires_every_configured_root(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]
    populated = tmp_path / "skeleton"
    empty = tmp_path / "scripts"
    populated.mkdir()
    empty.mkdir()
    (populated / "safe.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setitem(main.__globals__, "SCAN_ROOTS", (populated, empty))

    assert main() == 1
    error = capsys.readouterr().err
    assert "no Python files scanned under" in error
    assert str(empty) in error


def test_repository_python_sast_scans_live_skeleton_build_package(
    tmp_path: Path, monkeypatch
) -> None:
    namespace = _scanner_namespace()
    python_files = namespace["python_files"]
    skeleton = tmp_path / "skeleton"
    scripts = tmp_path / "scripts"
    live_build = skeleton / "build"
    generated_build = scripts / "build"
    live_build.mkdir(parents=True)
    generated_build.mkdir(parents=True)
    scripts.mkdir(exist_ok=True)
    (live_build / "incremental_graph.py").write_text("value = 1\n", encoding="utf-8")
    (generated_build / "generated.py").write_text("value = 1\n", encoding="utf-8")
    (scripts / "tool.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setitem(python_files.__globals__, "REPO_ROOT", tmp_path)
    monkeypatch.setitem(python_files.__globals__, "SCAN_ROOTS", (skeleton, scripts))

    scanned = {path.relative_to(tmp_path).as_posix() for path in python_files()}

    assert "skeleton/build/incremental_graph.py" in scanned
    assert "scripts/tool.py" in scanned
    assert "scripts/build/generated.py" not in scanned


def test_repository_python_sast_redacts_unexpected_traversal_details(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]

    def broken_files():
        raise OSError("sensitive mount detail")
        yield  # pragma: no cover

    monkeypatch.setitem(main.__globals__, "python_files", broken_files)

    assert main() == 1
    error = capsys.readouterr().err
    assert "Repository Python SAST scan failed: OSError" in error
    assert "sensitive mount detail" not in error


def test_repository_python_sast_accepts_nonempty_clean_required_roots(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]
    first = tmp_path / "skeleton"
    second = tmp_path / "scripts"
    first.mkdir()
    second.mkdir()
    (first / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (second / "safe.py").write_text("other = 2\n", encoding="utf-8")
    monkeypatch.setitem(main.__globals__, "SCAN_ROOTS", (first, second))

    assert main() == 0
    output = capsys.readouterr().out
    assert "2 core/tooling Python files" in output
    assert f"{first}=1" in output
    assert f"{second}=1" in output


def test_repository_python_sast_rejects_symlinked_required_root(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]
    real = tmp_path / "real"
    real.mkdir()
    (real / "safe.py").write_text("value = 1\n", encoding="utf-8")
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    monkeypatch.setitem(main.__globals__, "SCAN_ROOTS", (linked,))

    assert main() == 1
    assert "must not be a symlink" in capsys.readouterr().err



def test_repository_python_sast_reuses_module_alias_hardening(tmp_path: Path) -> None:
    namespace = _scanner_namespace()
    load_engine = namespace["_load_violation_engine"]
    violations = load_engine()

    sample = tmp_path / "unsafe_alias.py"
    sample.write_text(
        "import requests\n"
        "network = requests\n"
        "network.get(url, verify=False)\n",
        encoding="utf-8",
    )

    findings = violations(sample)
    assert any("requests.get" in finding and "verify=False" in finding for finding in findings)

def test_repository_python_sast_fails_closed_on_scandir_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]
    root = tmp_path / "skeleton"
    blocked = root / "blocked"
    root.mkdir()
    blocked.mkdir()
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")

    os_module = main.__globals__["os"]
    original_scandir = os_module.scandir

    def selective_scandir(path):
        if Path(path) == blocked:
            raise PermissionError("sensitive traversal detail")
        return original_scandir(path)

    monkeypatch.setitem(main.__globals__, "SCAN_ROOTS", (root,))
    monkeypatch.setattr(os_module, "scandir", selective_scandir)

    assert main() == 1
    error = capsys.readouterr().err
    assert "source traversal failure" in error
    assert "sensitive traversal detail" not in error


def test_repository_python_sast_rejects_symlinked_subtree(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]
    root = tmp_path / "skeleton"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (outside / "hidden.py").write_text("value = eval(user_input)\n", encoding="utf-8")
    link = root / "linked"

    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        import pytest

        pytest.skip(f"symlinks unavailable: {type(exc).__name__}")

    monkeypatch.setitem(main.__globals__, "SCAN_ROOTS", (root,))

    assert main() == 1
    error = capsys.readouterr().err
    assert "source traversal encountered symlink" in error
    assert str(outside) not in error


def test_repository_python_sast_rejects_non_directory_root(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]
    not_a_directory = tmp_path / "skeleton"
    not_a_directory.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setitem(main.__globals__, "SCAN_ROOTS", (not_a_directory,))

    assert main() == 1
    assert "required scan root is not a directory" in capsys.readouterr().err


def test_repository_python_sast_redacts_bootstrap_exception_detail(
    monkeypatch, capsys
) -> None:
    namespace = _scanner_namespace()
    main = namespace["main"]

    def broken_loader():
        raise RuntimeError("sensitive bootstrap detail")

    monkeypatch.setitem(main.__globals__, "_load_violation_engine", broken_loader)

    assert main() == 2
    error = capsys.readouterr().err
    assert "Repository Python SAST bootstrap failed: RuntimeError" in error
    assert "sensitive bootstrap detail" not in error

