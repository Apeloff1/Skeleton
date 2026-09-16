from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

import skeleton.automation.studio_director as studio_director
from skeleton.automation.studio_director import (
    AuditLog,
    _canonical_path,
    _changed_paths,
    _extract_json,
    _parse_task,
    _redact_value,
)


def _init_smoke_repo(tmp_path, monkeypatch) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Studio Smoke"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "studio-smoke@example.invalid"], cwd=tmp_path, check=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "smoke.txt").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/smoke.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "smoke fixture"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    runner_temp = tmp_path.parent / f"{tmp_path.name}-runner"
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _artifact_paths(tmp_path):
    output_dir = tmp_path.parent / f"{tmp_path.name}-outputs"
    output_dir.mkdir(exist_ok=True)
    return output_dir / "proposal.patch", output_dir / "audit.jsonl"


def test_extract_json_accepts_plain_and_fenced_payloads() -> None:
    assert _extract_json('{"tasks": []}') == {"tasks": []}
    assert _extract_json('```json\n{"tasks": []}\n```') == {"tasks": []}


def test_path_policy_allows_normal_source_and_rejects_trust_boundaries() -> None:
    assert _canonical_path("skeleton/gameplay/core.py") == "skeleton/gameplay/core.py"
    assert _canonical_path("backend/api.py") == "backend/api.py"

    for path in (
        "../escape.py",
        ".github/workflows/pwn.yml",
        ".env",
        "pyproject.toml",
        "skeleton/security/auth.py",
        "random-root/file.py",
        "skeleton/gameplay/bad\npath.py",
        r"skeleton\foo.py",
    ):
        with pytest.raises(ValueError):
            _canonical_path(path)


def test_task_parser_requires_known_division_and_bounded_paths() -> None:
    task = _parse_task(
        {
            "title": "Improve mechanics",
            "objective": "Strengthen deterministic combat resolution.",
            "division": "gameplay_systems",
            "paths": ["skeleton/gameplay/core.py"],
        }
    )
    assert task.division == "gameplay_systems"

    with pytest.raises(ValueError):
        _parse_task(
            {
                "title": "x",
                "objective": "y",
                "division": "made_up",
                "paths": ["skeleton/gameplay/core.py"],
            }
        )


def test_patch_parser_prevents_scope_escape_rename_and_delete() -> None:
    patch = """diff --git a/skeleton/foo.py b/skeleton/foo.py
index 1111111..2222222 100644
--- a/skeleton/foo.py
+++ b/skeleton/foo.py
@@ -1 +1 @@
-old
+new
"""
    assert _changed_paths(patch) == ("skeleton/foo.py",)

    escaped = patch.replace("skeleton/foo.py", ".github/workflows/foo.yml")
    with pytest.raises(ValueError):
        _changed_paths(escaped)

    deleted = patch.replace("+++ b/skeleton/foo.py", "+++ /dev/null")
    with pytest.raises(ValueError):
        _changed_paths(deleted)

    backslash_target = patch.replace("skeleton/foo.py", r"skeleton\foo.py")
    with pytest.raises(ValueError, match="backslash"):
        _changed_paths(backslash_target)


def test_patch_parser_binds_git_and_content_headers_to_same_target() -> None:
    patch = """diff --git a/skeleton/foo.py b/skeleton/foo.py
index 1111111..2222222 100644
--- a/skeleton/foo.py
+++ b/skeleton/foo.py
@@ -1 +1 @@
-old
+new
"""

    mismatched_allowed_target = patch.replace(
        "--- a/skeleton/foo.py\n+++ b/skeleton/foo.py",
        "--- a/backend/other.py\n+++ b/backend/other.py",
    )
    with pytest.raises(ValueError, match="headers disagree"):
        _changed_paths(mismatched_allowed_target)

    mismatched_denied_target = patch.replace(
        "--- a/skeleton/foo.py\n+++ b/skeleton/foo.py",
        "--- a/.github/workflows/pwn.yml\n+++ b/.github/workflows/pwn.yml",
    )
    with pytest.raises(ValueError):
        _changed_paths(mismatched_denied_target)


def test_patch_parser_rejects_binary_and_mode_metadata() -> None:
    mode_patch = """diff --git a/skeleton/foo.py b/skeleton/foo.py
old mode 100644
new mode 100755
"""
    with pytest.raises(ValueError, match="metadata"):
        _changed_paths(mode_patch)

    binary_patch = """diff --git a/skeleton/foo.py b/skeleton/foo.py
GIT binary patch
literal 0
HcmV?d00001
"""
    with pytest.raises(ValueError, match="metadata"):
        _changed_paths(binary_patch)


def test_redaction_preserves_nested_json_shapes() -> None:
    value = {
        "outer": [
            "api_key=super-secret",
            {"authorization": "Authorization: Bearer another-secret"},
        ]
    }
    redacted = _redact_value(value)
    encoded = json.dumps(redacted)
    decoded = json.loads(encoded)
    assert decoded["outer"][0] == "api_key=[REDACTED]"
    assert "another-secret" not in encoded


def test_audit_log_redacts_secret_like_values_without_corrupting_json(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path, "run-1")
    audit.emit("test", value="api_key=super-secret", nested={"token": "token=abc123"})
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["run_id"] == "run-1"
    assert "super-secret" not in path.read_text(encoding="utf-8")
    assert "abc123" not in path.read_text(encoding="utf-8")
    assert "[REDACTED]" in row["value"]


def test_propose_smoke_exercises_four_agent_squad_and_restores_worktree(tmp_path, monkeypatch) -> None:
    _init_smoke_repo(tmp_path, monkeypatch)
    responses = [
        json.dumps(
            {
                "tasks": [
                    {
                        "title": "Smoke change",
                        "objective": "Exercise the sealed proposal path.",
                        "division": "gameplay_systems",
                        "paths": ["docs/smoke.txt"],
                    }
                ]
            }
        ),
        json.dumps(
            {
                "findings": ["docs/smoke.txt contains the old fixture value"],
                "risks": ["fixture must remain plain text"],
                "recommended_checks": ["git apply --check", "credential-free smoke"],
            }
        ),
        json.dumps(
            {
                "patch": (
                    "diff --git a/docs/smoke.txt b/docs/smoke.txt\n"
                    "--- a/docs/smoke.txt\n"
                    "+++ b/docs/smoke.txt\n"
                    "@@ -1 +1 @@\n"
                    "-old\n"
                    "+new\n"
                ),
                "summary": "Replace the smoke fixture value.",
                "tests": ["studio smoke"],
            }
        ),
        json.dumps({"approve": True, "reasons": ["bounded fixture-only change"]}),
        json.dumps(
            {
                "approve": True,
                "reasons": ["patch has deterministic smoke coverage"],
                "required_checks": ["credential-free autonomous studio smoke"],
            }
        ),
    ]

    class FakeReasoner:
        def __init__(self) -> None:
            self.index = 0
            self.requests = []

        @staticmethod
        def redact(value: str) -> str:
            return value

        def reason(self, request):
            self.requests.append(request)
            text = responses[self.index]
            self.index += 1
            return SimpleNamespace(ok=True, text=text, error_kind=None)

    monkeypatch.setattr(studio_director, "ChatGPTReasoner", FakeReasoner)
    patch_path, audit_path = _artifact_paths(tmp_path)

    assert studio_director.propose(
        patch_path=patch_path,
        audit_path=audit_path,
        max_tasks=1,
        cohort_size=4,
        seed="smoke-seed",
        repo_state_path=None,
    ) == 0

    patch = patch_path.read_text(encoding="utf-8")
    assert "docs/smoke.txt" in patch
    assert "+new" in patch
    assert (tmp_path / "docs/smoke.txt").read_text(encoding="utf-8") == "old\n"
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status == ""
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == ["run_started", "plan_created", "patch_accepted", "run_finished"]
    accepted = records[2]
    assert accepted["researcher"]
    assert accepted["builder"]
    assert accepted["reviewer"]
    assert accepted["verifier"]
    assert len({accepted["researcher"], accepted["builder"], accepted["reviewer"], accepted["verifier"]}) == 4
    assert accepted["required_checks"] == ["credential-free autonomous studio smoke"]


def test_verifier_can_reject_reviewed_patch_before_it_reaches_ci(tmp_path, monkeypatch) -> None:
    _init_smoke_repo(tmp_path, monkeypatch)
    responses = [
        json.dumps(
            {"tasks": [{"title": "Smoke change", "objective": "Exercise verification.", "division": "gameplay_systems", "paths": ["docs/smoke.txt"]}]}
        ),
        json.dumps({"findings": ["fixture"], "risks": [], "recommended_checks": ["smoke"]}),
        json.dumps(
            {
                "patch": "diff --git a/docs/smoke.txt b/docs/smoke.txt\n--- a/docs/smoke.txt\n+++ b/docs/smoke.txt\n@@ -1 +1 @@\n-old\n+new\n",
                "summary": "change",
                "tests": ["smoke"],
            }
        ),
        json.dumps({"approve": True, "reasons": ["review ok"]}),
        json.dumps({"approve": False, "reasons": ["acceptance evidence is insufficient"], "required_checks": ["missing contract"]}),
    ]

    class FakeReasoner:
        def __init__(self) -> None:
            self.index = 0

        @staticmethod
        def redact(value: str) -> str:
            return value

        def reason(self, _request):
            text = responses[self.index]
            self.index += 1
            return SimpleNamespace(ok=True, text=text, error_kind=None)

    monkeypatch.setattr(studio_director, "ChatGPTReasoner", FakeReasoner)
    patch_path, audit_path = _artifact_paths(tmp_path)
    assert studio_director.propose(
        patch_path=patch_path,
        audit_path=audit_path,
        max_tasks=1,
        cohort_size=4,
        seed="verify-reject",
        repo_state_path=None,
    ) == 0
    assert patch_path.read_text(encoding="utf-8") == ""
    events = [json.loads(line)["event"] for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert events == ["run_started", "plan_created", "patch_rejected_by_squad", "run_finished"]


def test_planner_rejects_overlapping_paths_before_squads_activate(tmp_path, monkeypatch) -> None:
    _init_smoke_repo(tmp_path, monkeypatch)
    responses = [
        json.dumps(
            {
                "tasks": [
                    {"title": "A", "objective": "A", "division": "gameplay_systems", "paths": ["docs/smoke.txt"]},
                    {"title": "B", "objective": "B", "division": "gameplay_systems", "paths": ["docs/smoke.txt"]},
                ]
            }
        )
    ]

    class FakeReasoner:
        @staticmethod
        def redact(value: str) -> str:
            return value

        def reason(self, _request):
            return SimpleNamespace(ok=True, text=responses[0], error_kind=None)

    monkeypatch.setattr(studio_director, "ChatGPTReasoner", FakeReasoner)
    patch_path, audit_path = _artifact_paths(tmp_path)
    with pytest.raises(ValueError, match="overlapping squad paths"):
        studio_director.propose(
            patch_path=patch_path,
            audit_path=audit_path,
            max_tasks=2,
            cohort_size=4,
            seed="overlap",
            repo_state_path=None,
        )
    assert patch_path.read_text(encoding="utf-8") == ""
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["event"] == "run_failed_closed"
    assert records[-1]["stage"] == "planning"


def test_propose_planning_failure_is_audited_and_emits_empty_patch(tmp_path, monkeypatch) -> None:
    _init_smoke_repo(tmp_path, monkeypatch)

    class FailingReasoner:
        @staticmethod
        def redact(value: str) -> str:
            return value

        def reason(self, _request):
            return SimpleNamespace(ok=False, text="", error_kind="missing_api_key")

    monkeypatch.setattr(studio_director, "ChatGPTReasoner", FailingReasoner)
    patch_path, audit_path = _artifact_paths(tmp_path)

    with pytest.raises(RuntimeError, match="failed closed"):
        studio_director.propose(
            patch_path=patch_path,
            audit_path=audit_path,
            max_tasks=1,
            cohort_size=4,
            seed="failure-seed",
            repo_state_path=None,
        )

    assert patch_path.exists()
    assert patch_path.read_text(encoding="utf-8") == ""
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["event"] == "run_failed_closed"
    assert records[-1]["stage"] == "planning"
    assert records[-1]["status"] == "failed_closed"
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status == ""
