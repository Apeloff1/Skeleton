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
            "expected_receipt_verifier": "fixture-verifier-v1",
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


def _receipt_verifier(
    *,
    gap_id: str,
    head: str = "abc123",
    valid: bool = True,
    exit_code: int = 0,
) -> str:
    return (
        "import argparse\n"
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--evidence-out', required=True)\n"
        "args = parser.parse_args()\n"
        f"assert os.environ['GITHUB_SHA'] == 'abc123'\n"
        f"assert os.environ['EVIDENCE_HEAD_SHA'] == 'abc123'\n"
        f"assert os.environ['ACCOUNTABILITY_HEAD_SHA'] == 'abc123'\n"
        "Path(args.evidence_out).write_text(json.dumps({\n"
        "    'schema_version': 1,\n"
        "    'verifier': 'fixture-verifier-v1',\n"
        f"    'gap_id': {gap_id!r},\n"
        f"    'head_sha': {head!r},\n"
        f"    'valid': {valid!r},\n"
        f"    'errors': {[] if valid else ['fixture rejection']!r},\n"
        "}), encoding='utf-8')\n"
        f"raise SystemExit({exit_code})\n"
    )


def test_runner_executes_every_declared_verifier_with_exact_head_receipts(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "scripts/a.py",
        _receipt_verifier(gap_id="gap-0"),
    )
    _write(
        tmp_path,
        "scripts/b.py",
        _receipt_verifier(gap_id="gap-1"),
    )
    _map(tmp_path, ["scripts/a.py", "scripts/b.py"])

    receipt = run_verifiers(tmp_path, head_sha="abc123")

    assert receipt["valid"] is True
    assert receipt["verifier_count"] == 2
    assert receipt["passed_count"] == 2
    assert receipt["failures"] == []
    assert all(result["receipt_head_sha"] == "abc123" for result in receipt["results"])
    assert all(result["receipt_digest"] for result in receipt["results"])


def test_runner_fails_closed_when_one_verifier_rejects(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/a.py",
        _receipt_verifier(gap_id="gap-0"),
    )
    _write(
        tmp_path,
        "scripts/b.py",
        _receipt_verifier(gap_id="gap-1", exit_code=7),
    )
    _map(tmp_path, ["scripts/a.py", "scripts/b.py"])

    receipt = run_verifiers(tmp_path, head_sha="abc123")

    assert receipt["valid"] is False
    assert receipt["passed_count"] == 1
    assert receipt["failures"] == ["G1"]
    assert receipt["results"][1]["returncode"] == 7


def test_runner_rejects_successful_verifier_with_wrong_head_receipt(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "scripts/a.py",
        _receipt_verifier(gap_id="gap-0", head="different-head"),
    )
    _map(tmp_path, ["scripts/a.py"])

    receipt = run_verifiers(tmp_path, head_sha="abc123")

    assert receipt["valid"] is False
    assert receipt["failures"] == ["G0"]
    assert receipt["results"][0]["receipt_error"] == (
        "verifier receipt is not exact-head"
    )


def test_runner_rejects_successful_verifier_with_invalid_receipt(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "scripts/a.py",
        _receipt_verifier(gap_id="gap-0", valid=False),
    )
    _map(tmp_path, ["scripts/a.py"])

    receipt = run_verifiers(tmp_path, head_sha="abc123")

    assert receipt["valid"] is False
    assert receipt["failures"] == ["G0"]
    assert receipt["results"][0]["receipt_error"] == (
        "verifier receipt reports invalid evidence"
    )


def test_runner_rejects_receipt_bound_to_wrong_gap(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/a.py",
        _receipt_verifier(gap_id="gap-wrong"),
    )
    _map(tmp_path, ["scripts/a.py"])

    receipt = run_verifiers(tmp_path, head_sha="abc123")

    assert receipt["valid"] is False
    assert receipt["failures"] == ["G0"]
    assert receipt["results"][0]["receipt_error"] == (
        "verifier receipt gap binding mismatch"
    )


def test_runner_rejects_verifier_path_escape(tmp_path: Path) -> None:
    _map(tmp_path, ["../outside.py"])

    with pytest.raises(RunnerError, match="escapes repository"):
        run_verifiers(tmp_path, head_sha="abc123")


def test_runner_rejects_duplicate_verifier_reuse(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/a.py",
        _receipt_verifier(gap_id="gap-0"),
    )
    _map(tmp_path, ["scripts/a.py", "scripts/a.py"])

    with pytest.raises(RunnerError, match="reused by multiple groups"):
        run_verifiers(tmp_path, head_sha="abc123")


def test_runner_rejects_unexpected_verifier_identity(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/a.py",
        _receipt_verifier(gap_id="gap-0").replace(
            "'fixture-verifier-v1'",
            "'different-verifier-v1'",
        ),
    )
    _map(tmp_path, ["scripts/a.py"])

    receipt = run_verifiers(tmp_path, head_sha="abc123")

    assert receipt["valid"] is False
    assert receipt["failures"] == ["G0"]
    assert receipt["results"][0]["receipt_error"] == (
        "verifier receipt identity mismatch"
    )
