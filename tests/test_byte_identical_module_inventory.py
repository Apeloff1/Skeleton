"""Tests for scripts/check_byte_identical_modules.py (issue #80)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_byte_identical_modules", ROOT / "scripts" / "check_byte_identical_modules.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

BODY = "def f():\n    return 1\n" + "# pad\n" * 60


def _tree(tmp_path: Path, files: dict[str, str]) -> list[Path]:
    out = []
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        out.append(p)
    return out


def test_groups_identical_files_and_skips_small_and_init(tmp_path):
    files = _tree(tmp_path, {
        "skeleton/a/x.py": BODY,
        "skeleton/ai/a/x.py": BODY,
        "skeleton/b/__init__.py": BODY,
        "skeleton/c/tiny.py": "x = 1\n",
        "skeleton/d/tiny.py": "x = 1\n",
        "skeleton/e/unique.py": BODY + "# unique\n",
    })
    groups = mod.find_twin_groups(root=tmp_path, files=files)
    assert list(groups.values()) == [["skeleton/a/x.py", "skeleton/ai/a/x.py"]]


def test_excludes_branch_snapshots(tmp_path):
    files = _tree(tmp_path, {
        "skeleton/a/x.py": BODY,
        "satellites/branch-snapshots/s/x.py": BODY,
    })
    assert mod.find_twin_groups(root=tmp_path, files=files) == {}


def test_compare_flags_new_groups_and_reports_progress():
    baseline = {"h1": ["a.py", "b.py", "c.py"], "h2": ["d.py", "e.py"]}
    # h1 shrank to a pair (progress, not failure); h2 resolved; f/g is new.
    current = {"h1x": ["a.py", "b.py"], "h3": ["f.py", "g.py"]}
    result = mod.compare(current, baseline)
    assert result["new"] == [["f.py", "g.py"]]
    assert ["d.py", "e.py"] in result["resolved"]


def test_repository_matches_committed_baseline():
    current = mod.find_twin_groups()
    result = mod.compare(current, mod.load_baseline())
    assert result["new"] == [], f"new byte-identical clones: {result['new'][:5]}"
