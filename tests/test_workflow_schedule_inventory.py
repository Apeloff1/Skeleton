"""Static schedule audit must be deterministic, bounded, and fail closed."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts import workflow_schedule_inventory as audit


def _workflow(root: Path, name: str, text: str) -> None:
    folder = root / ".github" / "workflows"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def test_schedule_extraction_does_not_read_job_shell_crons() -> None:
    source = """name: Example
on:
  push:
    branches: [main]
  schedule:
    - cron: "2-57/5 * * * *"
    - cron: '43 1,7,13,19 * * *' # staggered
  workflow_dispatch:
jobs:
  example:
    runs-on: ubuntu-latest
    steps:
      - run: 'echo cron: "*/1 * * * *"'
"""
    assert audit.workflow_crons(source) == [
        "2-57/5 * * * *", "43 1,7,13,19 * * *",
    ]


@pytest.mark.parametrize(("cron", "expected"), [
    ("*/5 * * * *", 288),
    ("2-57/5 * * * *", 288),
    ("43 1,7,13,19 * * *", 4),
    ("11,26,41,56 * * * *", 96),
    ("13,43 * * * *", 48),
    ("5 0 * * *", 1),
    ("0 0 1 * *", None),
    ("0 0 * * 1", None),
    ("@daily", None),
    ("*/0 * * * *", None),
    ("77 * * * *", None),
    ("*/5 12-1 * * *", None),
    ("* * * *", None),
])
def test_nominal_daily_wakes_are_conservative(cron: str, expected: int | None) -> None:
    assert audit.nominal_daily_wakes(cron) == expected


def test_inventory_counts_only_known_wakes_and_preserves_unknown(tmp_path: Path) -> None:
    _workflow(tmp_path, "frequent.yml", "name: Frequent\non:\n  schedule:\n    - cron: '*/5 * * * *'\njobs: {}\n")
    _workflow(tmp_path, "weekly.yaml", "name: Weekly\non:\n  schedule:\n    - cron: '17 6 * * 1'\njobs: {}\n")
    _workflow(tmp_path, "manual.yml", "name: Manual\non:\n  workflow_dispatch:\njobs: {}\n")
    report = audit.inventory(tmp_path)
    assert report["workflow_files"] == 3
    assert report["scheduled_workflows"] == 2
    assert report["unknown_or_unreadable"] == 1
    assert report["known_nominal_daily_wakes"] == 288
    by_name = {entry["path"]: entry for entry in report["workflows"]}
    assert by_name["weekly.yaml"]["daily_wakes"] is None
    assert by_name["frequent.yml"]["note"] == "high-frequency recurring wake"
    assert by_name["manual.yml"]["daily_wakes"] == 0


def test_inventory_is_deterministic_and_skips_symlinked_workflows(tmp_path: Path) -> None:
    _workflow(tmp_path, "b.yml", "on:\n  schedule:\n    - cron: '0 12 * * *'\n")
    _workflow(tmp_path, "a.yml", "on:\n  schedule:\n    - cron: '0 0 * * *'\n")
    outside = tmp_path / "outside.yml"
    outside.write_text("on:\n  schedule:\n    - cron: '*/1 * * * *'\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows" / "linked.yml").symlink_to(outside)
    first, second = audit.inventory(tmp_path), audit.inventory(tmp_path)
    assert first == second
    assert [r["path"] for r in first["workflows"]] == ["a.yml", "b.yml"]


def test_empty_or_missing_tree_is_not_a_green_inventory(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        audit.inventory(tmp_path)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    with pytest.raises(ValueError):
        audit.inventory(tmp_path)


def test_json_mode_reports_auditable_scope(tmp_path: Path, capsys) -> None:
    _workflow(tmp_path, "a.yml", "on:\n  schedule:\n    - cron: '30 3 * * *'\n")
    assert audit.main(["--root", str(tmp_path), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == 1
    assert result["scope"] == "worktree-schedule-config-only"
    assert result["known_nominal_daily_wakes"] == 1
    assert "actual completed runs" in result["caveat"]


def test_invalid_top_limit_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        audit.main(["--root", str(tmp_path), "--top", "0"])
    assert exc.value.code == 2
