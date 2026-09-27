from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_ai_accountability_verifiers import RunnerError, run_verifiers


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _map(root: Path, scripts: list[str]) -> None:
    groups = [
        {
            "key": f"G{index}",
            "gap_id": f"gap-{index}",
            "verifier_script": script,
        }
        for index, script in enumerate(scripts)
    ]
    payload = {
        "schema_version": 1,
        "rules": {
            "queue_task_count": len(groups) * 3,
            "tasks_per_group": 3,
        },
        "groups": groups,
    }
    _write(
        root,
        "machine/ai_accountability_closure_map.json",
        json.dumps(payload),
    )


def test_runner_executes_every_declared_verifier_with_exact_head(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "scripts/a.py",
        "import os\n"
        "assert os.environ['GITHUB_SHA'] == 'abc123'\n"
        "assert os.environ['EVIDENCE_HEAD_SHA'] == 'abc123'\n",
    )
    _write(
        tmp_path,
        "scripts/b.py",
        "import os\n"
        "assert os.environ['ACCOUNTABILITY_HEAD_SHA'] == 'abc123'\n",
    )
    _map(tmp_path, ["scripts/a.py", "scripts/b.py"])

    receipt = run_verifiers(tmp_path, head_sha="abc123")

    assert receipt["valid"] is True
    assert receipt["verifier_count"] == 2
    assert receipt["passed_count"] == 2
    assert receipt["failures"] == []


def test_runner_fails_closed_when_one_verifier_rejects(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/a.py", "raise SystemExit(0)\n")
    _write(tmp_path, "scripts/b.py", "raise SystemExit(7)\n")
    _map(tmp_path, ["scripts/a.py", "scripts/b.py"])

    receipt = run_verifiers(tmp_path, head_sha="abc123")

    assert receipt["valid"] is False
    assert receipt["passed_count"] == 1
    assert receipt["failures"] == ["G1"]
    assert receipt["results"][1]["returncode"] == 7


def test_runner_rejects_verifier_path_escape(tmp_path: Path) -> None:
    _map(tmp_path, ["../outside.py"])

    with pytest.raises(RunnerError, match="escapes repository"):
        run_verifiers(tmp_path, head_sha="abc123")


def test_runner_rejects_duplicate_verifier_reuse(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/a.py", "raise SystemExit(0)\n")
    _map(tmp_path, ["scripts/a.py", "scripts/a.py"])

    with pytest.raises(RunnerError, match="reused by multiple groups"):
        run_verifiers(tmp_path, head_sha="abc123")
