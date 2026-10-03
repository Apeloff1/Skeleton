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


def test_propose_refuses_independent_planning_when_live_repo_state_exists(tmp_path, monkeypatch) -> None:
    _init_smoke_repo(tmp_path, monkeypatch)
    repo_state = tmp_path / "repo-state.json"
    repo_state.write_text(
        json.dumps(
            {
                "_shift_supervisor": {
                    "status": "loaded",
                    "team": "night",
                    "generation_id": "gen-1",
                    "plan_items": [
                        {
                            "id": "night-plan-1",
                            "title": "Canonical",
                            "description": "Must be consumed by supervised_studio.",
                            "status": "queued",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    class ForbiddenPlanner:
        @staticmethod
        def redact(value: str) -> str:
            return value

        def reason(self, _request):
            raise AssertionError("independent planner must not run against live supervisor state")

    monkeypatch.setattr(studio_director, "ChatGPTReasoner", ForbiddenPlanner)
    patch_path, audit_path = _artifact_paths(tmp_path)
    with pytest.raises(ValueError, match="supervised_studio"):
        studio_director.propose(
            patch_path=patch_path,
            audit_path=audit_path,
            max_tasks=1,
            cohort_size=4,
            seed="live-state",
            repo_state_path=repo_state,
        )
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["event"] == "run_failed_closed"
    assert records[-1]["stage"] == "planning"


def test_researcher_cannot_author_a_patch_during_squad_execution(tmp_path, monkeypatch) -> None:
    _init_smoke_repo(tmp_path, monkeypatch)
    responses = [
        json.dumps(
            {"tasks": [{"title": "Smoke change", "objective": "Exercise research boundary.", "division": "gameplay_systems", "paths": ["docs/smoke.txt"]}]}
        ),
        json.dumps(
            {
                "findings": ["should stay evidence-only"],
                "patch": "diff --git a/docs/smoke.txt b/docs/smoke.txt\n",
            }
        ),
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
        seed="research-patch",
        repo_state_path=None,
    ) == 0
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == [
        "run_started",
        "plan_created",
        "task_failed_closed",
        "run_finished",
    ]
    failure = records[2]
    assert failure["task"] == "Smoke change"
    assert "researcher must remain evidence-only" in failure["error"]
    assert records[-1]["accepted_tasks"] == 0
    assert records[-1]["emitted_patch_chars"] == 0
    assert patch_path.read_text(encoding="utf-8") == ""


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
        json.dumps(
            {
                "patch": "diff --git a/docs/smoke.txt b/docs/smoke.txt\n--- a/docs/smoke.txt\n+++ b/docs/smoke.txt\n@@ -1 +1 @@\n-old\n+new\n",
                "summary": "repair one",
                "tests": ["smoke"],
            }
        ),
        json.dumps({"approve": True, "reasons": ["review ok after repair"]}),
        json.dumps({"approve": False, "reasons": ["acceptance evidence is still insufficient"], "required_checks": ["missing contract"]}),
        json.dumps(
            {
                "patch": "diff --git a/docs/smoke.txt b/docs/smoke.txt\n--- a/docs/smoke.txt\n+++ b/docs/smoke.txt\n@@ -1 +1 @@\n-old\n+new\n",
                "summary": "repair two",
                "tests": ["smoke"],
            }
        ),
        json.dumps({"approve": True, "reasons": ["review ok after second repair"]}),
        json.dumps({"approve": False, "reasons": ["acceptance evidence remains insufficient"], "required_checks": ["missing contract"]}),
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


def test_path_policy_rejects_existing_symlink_target(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "outside.py"
    target.write_text("secret\n", encoding="utf-8")
    allowed = tmp_path / "skeleton"
    allowed.mkdir()
    link = allowed / "linked.py"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(ValueError, match="symlink"):
        _canonical_path("skeleton/linked.py")


def test_audit_log_builds_hash_chained_records(tmp_path) -> None:
    import hashlib

    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path, "run-chain")
    audit.emit("run_started")
    audit.emit("run_finished", status="no_change")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["sequence"] for row in rows] == [1, 2]
    assert rows[0]["previous_record_sha256"] == "0" * 64
    assert rows[1]["previous_record_sha256"] == rows[0]["record_sha256"]
    for row in rows:
        claimed = row["record_sha256"]
        payload = dict(row)
        payload.pop("record_sha256")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        assert claimed == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_audit_log_resumes_verified_chain(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    first = AuditLog(path, "resume-run")
    first.emit("run_started")
    second = AuditLog(path, "resume-run")
    second.emit("checkpoint")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["sequence"] for row in rows] == [1, 2]
    assert rows[1]["previous_record_sha256"] == rows[0]["record_sha256"]


def test_audit_log_refuses_cross_run_append(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    AuditLog(path, "run-a").emit("run_started")
    with pytest.raises(ValueError, match="different run id"):
        AuditLog(path, "run-b")


def test_audit_log_refuses_tampered_history(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    AuditLog(path, "run-a").emit("run_started")
    row = json.loads(path.read_text(encoding="utf-8"))
    row["event"] = "tampered"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="record hash is invalid"):
        AuditLog(path, "run-a")


def test_task_parser_supports_eight_file_capability():
    paths = [f"docs/capability-{i}.txt" for i in range(8)]
    task = _parse_task({
        "title": "Cross-cutting capability",
        "objective": "Coordinate a bounded multi-file implementation.",
        "division": "gameplay_systems",
        "paths": paths,
    })
    assert len(task.paths) == 8
    with pytest.raises(ValueError, match="1-8"):
        _parse_task({
            "title": "Too broad",
            "objective": "Exceed the bounded capability.",
            "division": "gameplay_systems",
            "paths": paths + ["docs/ninth.txt"],
        })


def test_build_and_review_repairs_reviewer_rejection(monkeypatch):
    task = studio_director.PlannedTask(
        title="Repairable",
        objective="Change bounded implementation.",
        division="gameplay_systems",
        paths=("docs/smoke.txt",),
    )
    monkeypatch.setattr(studio_director, "_read_context", lambda _paths: ("FILE docs/smoke.txt\nold",))
    patch1 = "diff --git a/docs/smoke.txt b/docs/smoke.txt\n--- a/docs/smoke.txt\n+++ b/docs/smoke.txt\n@@ -1 +1 @@\n-old\n+bad\n"
    patch2 = "diff --git a/docs/smoke.txt b/docs/smoke.txt\n--- a/docs/smoke.txt\n+++ b/docs/smoke.txt\n@@ -1 +1 @@\n-old\n+good\n"
    responses = [
        {"findings": ["fixture"], "risks": [], "recommended_checks": ["smoke"]},
        {"patch": patch1, "summary": "first", "tests": ["smoke"]},
        {"approve": False, "reasons": ["wrong value"]},
        {"patch": patch2, "summary": "repaired", "tests": ["smoke"]},
        {"approve": True, "reasons": ["fixed"]},
        {"approve": True, "reasons": ["verified"], "required_checks": ["smoke"]},
    ]
    monkeypatch.setattr(studio_director, "_call_json", lambda *args, **kwargs: responses.pop(0))
    reviewed = studio_director._build_and_review(object(), task, seed="repair")
    assert reviewed is not None
    assert "+good" in reviewed.patch
    assert reviewed.summary == "repaired"


def test_build_and_review_stops_after_bounded_repair_budget(monkeypatch):
    task = studio_director.PlannedTask(
        title="Unrepairable",
        objective="Remain bounded.",
        division="gameplay_systems",
        paths=("docs/smoke.txt",),
    )
    monkeypatch.setattr(studio_director, "_read_context", lambda _paths: ("FILE docs/smoke.txt\nold",))
    patch = "diff --git a/docs/smoke.txt b/docs/smoke.txt\n--- a/docs/smoke.txt\n+++ b/docs/smoke.txt\n@@ -1 +1 @@\n-old\n+new\n"
    responses = [
        {"findings": [], "risks": [], "recommended_checks": []},
        {"patch": patch, "summary": "first", "tests": []},
        {"approve": False, "reasons": ["reject 1"]},
        {"patch": patch, "summary": "repair 1", "tests": []},
        {"approve": False, "reasons": ["reject 2"]},
        {"patch": patch, "summary": "repair 2", "tests": []},
        {"approve": False, "reasons": ["reject 3"]},
    ]
    monkeypatch.setattr(studio_director, "_call_json", lambda *args, **kwargs: responses.pop(0))
    assert studio_director._build_and_review(object(), task, seed="repair") is None


def test_changed_paths_accepts_bounded_new_python_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "skeleton").mkdir()
    patch = (
        "diff --git a/skeleton/new_capability.py b/skeleton/new_capability.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/skeleton/new_capability.py\n"
        "@@ -0,0 +1 @@\n"
        "+VALUE = 1\n"
    )
    assert _changed_paths(patch) == ("skeleton/new_capability.py",)


def test_changed_paths_rejects_new_executable_or_manifest_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "skeleton").mkdir()
    patch = (
        "diff --git a/skeleton/tool.sh b/skeleton/tool.sh\n"
        "new file mode 100755\n"
        "--- /dev/null\n"
        "+++ b/skeleton/tool.sh\n"
        "@@ -0,0 +1 @@\n"
        "+echo unsafe\n"
    )
    with pytest.raises(ValueError):
        _changed_paths(patch)


def test_validation_discovery_finds_related_test(monkeypatch):
    monkeypatch.setattr(
        studio_director,
        "_git",
        lambda *args, **kwargs: "skeleton/foo.py\nskeleton/testing/test_foo.py\n",
    )
    commands = studio_director._discover_validation_commands(["skeleton/foo.py"])
    assert any("skeleton/testing/test_foo.py" in command for command in commands)
    assert any("compileall" in command for command in commands)


def test_validation_executor_rejects_non_allowlisted_command():
    with pytest.raises(ValueError, match="not allowlisted"):
        studio_director._run_validation_commands([("bash", "-c", "echo nope")])


def test_related_context_prioritizes_matching_modules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "skeleton" / "testing").mkdir(parents=True)
    (tmp_path / "skeleton" / "foo.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "skeleton" / "testing" / "test_foo.py").write_text("def test_foo(): pass\n", encoding="utf-8")
    monkeypatch.setattr(
        studio_director,
        "_git",
        lambda *args, **kwargs: "skeleton/foo.py\nskeleton/testing/test_foo.py\n",
    )
    evidence = studio_director._related_repository_context(["skeleton/foo.py"])
    assert any("test_foo.py" in item for item in evidence)


def test_canonical_path_rejects_symlink_ancestor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outside").mkdir()
    (tmp_path / "skeleton").mkdir()
    (tmp_path / "skeleton" / "linked").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink repository path component"):
        _canonical_path("skeleton/linked/escape.py")


def test_changed_paths_rejects_executable_new_file_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "skeleton").mkdir()
    patch = (
        "diff --git a/skeleton/new.py b/skeleton/new.py\n"
        "new file mode 100755\n--- /dev/null\n+++ b/skeleton/new.py\n"
        "@@ -0,0 +1 @@\n+VALUE = 1\n"
    )
    with pytest.raises(ValueError, match="100644"):
        _changed_paths(patch)


def test_changed_paths_rejects_carriage_return_patch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    with pytest.raises(ValueError, match="carriage"):
        _changed_paths("diff --git a/docs/a.txt b/docs/a.txt\r\n")


def test_validation_commands_are_structured_argv(monkeypatch):
    monkeypatch.setattr(studio_director, "_git", lambda *args, **kwargs: "")
    commands = studio_director._discover_validation_commands(["skeleton/a.py"])
    assert commands == (("python", "-m", "compileall", "-q", "skeleton/a.py"),)


def test_validation_executor_rejects_control_character_argument():
    with pytest.raises(ValueError, match="malformed"):
        studio_director._run_validation_commands([
            ("python", "-m", "pytest", "skeleton/testing/test_ok.py\n--collect-only")
        ])


def test_read_context_omits_oversized_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "huge.txt").write_text("x" * 600_000, encoding="utf-8")
    evidence = studio_director._read_context(["docs/huge.txt"])
    assert "exceeds context safety bound" in evidence[0]


def test_validation_executor_uses_reduced_environment(monkeypatch):
    captured = {}
    class Proc:
        pid = 123
        returncode = 0
        def communicate(self, timeout=None):
            return ("ok", "")
    def fake_popen(argv, **kwargs):
        captured.update(kwargs)
        return Proc()
    monkeypatch.setattr(studio_director.subprocess, "Popen", fake_popen)
    ok, _ = studio_director._run_validation_commands([
        ("python", "-m", "compileall", "-q", "skeleton/a.py")
    ])
    assert ok
    env = captured["env"]
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env["PYTHONHASHSEED"] == "0"
    assert "GITHUB_TOKEN" not in env
    assert captured["start_new_session"] is True


def test_validation_timeout_kills_process_group(monkeypatch):
    killed = []
    class Proc:
        pid = 456
        returncode = None
        calls = 0
        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise studio_director.subprocess.TimeoutExpired(("python",), timeout)
            return ("partial", "")
        def kill(self):
            killed.append(("process", self.pid))
    monkeypatch.setattr(studio_director.subprocess, "Popen", lambda *args, **kwargs: Proc())
    monkeypatch.setattr(studio_director.os, "killpg", lambda pid, sig: killed.append(("group", pid)))
    ok, output = studio_director._run_validation_commands([
        ("python", "-m", "compileall", "-q", "skeleton/a.py")
    ])
    assert not ok
    assert ("group", 456) in killed
    assert "TIMEOUT" in output[0]
