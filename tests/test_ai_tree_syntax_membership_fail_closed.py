"""Regression coverage for fail-closed canonical AI mirror syntax and Git membership."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_ai_file_tree as tree


def test_identical_broken_python_is_not_accepted_as_parity(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    mirror = tmp_path / "mirror.py"
    source.write_text("def unfinished(:\n    pass\n", encoding="utf-8")
    mirror.write_bytes(source.read_bytes())

    assert tree._content_equivalent(source, mirror) is False
    assert any("file semantic/content drift" in item for item in tree._compare(source, mirror))


def test_valid_mirror_python_is_accepted(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    mirror = tmp_path / "mirror.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    mirror.write_bytes(source.read_bytes())

    assert tree._compare(source, mirror) == []


def test_semantically_equal_python_allows_nonfunctional_comments(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    mirror = tmp_path / "mirror.py"
    source.write_text("value = 1\n", encoding="utf-8")
    mirror.write_text("# synced\nvalue = 1\n", encoding="utf-8")

    assert tree._compare(source, mirror) == []


def test_deleted_tracked_member_cannot_disappear_from_both_trees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    original = repo_root / "original"
    mirror = repo_root / "mirror"
    original.mkdir(parents=True)
    mirror.mkdir()
    monkeypatch.setattr(tree, "ROOT", repo_root)

    def tracked_files(command: list[str], **_kwargs: object) -> SimpleNamespace:
        relative_root = command[-1]
        return SimpleNamespace(stdout=f"{relative_root}/deleted.py\0")

    monkeypatch.setattr(tree.subprocess, "run", tracked_files)
    errors = tree._compare(original, mirror)
    assert errors and "tracked tree integrity failure" in errors[0]
    assert "original/deleted.py" in errors[0]


def test_symlinked_tracked_member_is_not_silently_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    original = repo_root / "original"
    mirror = repo_root / "mirror"
    original.mkdir(parents=True)
    mirror.mkdir()
    target = repo_root / "other.py"
    target.write_text("value = 1\n", encoding="utf-8")
    try:
        (original / "link.py").symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    monkeypatch.setattr(tree, "ROOT", repo_root)

    def tracked_files(command: list[str], **_kwargs: object) -> SimpleNamespace:
        relative_root = command[-1]
        return SimpleNamespace(stdout=f"{relative_root}/link.py\0")

    monkeypatch.setattr(tree.subprocess, "run", tracked_files)
    errors = tree._compare(original, mirror)
    assert errors and "tracked tree integrity failure" in errors[0]
    assert "symlink" in errors[0]


def test_nonregular_tracked_member_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    namespace = root / "original"
    namespace.mkdir(parents=True)
    (namespace / "named.py").mkdir()
    monkeypatch.setattr(tree, "ROOT", root)
    monkeypatch.setattr(
        tree.subprocess,
        "run",
        lambda *_a, **_kw: SimpleNamespace(stdout="original/named.py\0"),
    )

    with pytest.raises(RuntimeError, match="nonregular"):
        tree._tree_files(namespace)


def test_missing_mapped_roots_fail_closed(tmp_path: Path) -> None:
    errors = tree._compare(tmp_path / "missing-source", tmp_path / "missing-mirror")
    assert errors and "missing mapped source" in errors[0]
