from __future__ import annotations

import skeleton.automation.dependabot_merge_policy as policy
from skeleton.automation.dependabot_merge_policy import (
    DEFAULT_REQUIRED_WORKFLOWS,
    GitHubCLI,
    backend_quality_applicable,
    dependency_path_allowed,
    dependency_review_applicable,
    dependency_surface_guard_applicable,
    evaluate_candidate,
    required_workflows_for_files,
    same_candidate_identity,
)


def _pr(**overrides):
    payload = {
        "number": 42,
        "author": {"login": "dependabot[bot]"},
        "headRefName": "dependabot/pip/backend/fastapi-1.2.3",
        "headRefOid": "abc123",
        "baseRefName": "main",
        "isDraft": False,
        "state": "OPEN",
        "mergeable": "MERGEABLE",
        "isCrossRepository": False,
    }
    payload.update(overrides)
    return payload


def _runs(
    required=DEFAULT_REQUIRED_WORKFLOWS,
    *,
    conclusion: str = "success",
    status: str = "completed",
):
    return [
        {
            "name": name,
            "head_sha": "abc123",
            "event": "pull_request",
            "status": status,
            "conclusion": conclusion,
            "run_number": index + 1,
            "run_attempt": 1,
        }
        for index, name in enumerate(required)
    ]


def test_dependency_path_allowlist_is_narrow_and_nested_manifest_safe() -> None:
    for path in (
        "requirements.txt",
        "backend/requirements-dev.txt",
        "pyproject.toml",
        "frontend/package.json",
        "frontend/package-lock.json",
        "nested/uv.lock",
        "nested/pdm.lock",
        "nested/npm-shrinkwrap.json",
    ):
        assert dependency_path_allowed(path)

    for path in (
        ".github/workflows/ci.yml",
        ".github/dependabot.yml",
        "Dockerfile",
        "backend/Dockerfile",
        "scripts/install.sh",
        "../requirements.txt",
        "/tmp/package.json",
        "frontend//package.json",
        "frontend\\package.json",
        "package.json\x00.yml",
    ):
        assert not dependency_path_allowed(path)


def test_path_scoped_gate_selection_matches_current_workflow_surfaces() -> None:
    root_python = ["pyproject.toml"]
    required = required_workflows_for_files(root_python)
    assert "Dependency Review" in required
    assert "Dependency Surface Guard" in required
    assert "Backend Quality" not in required

    frontend = ["frontend/package-lock.json"]
    required = required_workflows_for_files(frontend)
    assert "Dependency Review" in required
    assert "Backend Quality" in required
    assert "Dependency Surface Guard" not in required

    snapshot = [
        "satellites/branch-snapshots/example/frontend/package.json",
        "satellites/branch-snapshots/example/frontend/package-lock.json",
    ]
    required = required_workflows_for_files(snapshot)
    assert "Dependency Surface Guard" in required
    assert "Dependency Review" not in required
    assert "Backend Quality" not in required


def test_dependency_review_ignores_snapshot_and_uncovered_lock_types() -> None:
    assert dependency_review_applicable(["backend/requirements.txt"])
    assert dependency_review_applicable(["frontend/pnpm-lock.yaml"])
    assert not dependency_review_applicable(["nested/uv.lock"])
    assert not dependency_review_applicable(["nested/pdm.lock"])
    assert not dependency_review_applicable(
        ["satellites/branch-snapshots/demo/frontend/package-lock.json"]
    )


def test_dependency_surface_guard_is_exactly_root_pyproject_or_snapshot_tree() -> None:
    assert dependency_surface_guard_applicable(["pyproject.toml"])
    assert dependency_surface_guard_applicable(
        ["satellites/branch-snapshots/demo/frontend/package.json"]
    )
    assert not dependency_surface_guard_applicable(["backend/pyproject.toml"])
    assert not dependency_surface_guard_applicable(["frontend/package-lock.json"])


def test_backend_quality_requires_only_its_broad_code_roots() -> None:
    assert backend_quality_applicable(["backend/requirements.txt"])
    assert backend_quality_applicable(["frontend/package-lock.json"])
    assert backend_quality_applicable(["skeleton/package.json"])
    assert not backend_quality_applicable(["pyproject.toml"])
    assert not backend_quality_applicable(
        ["satellites/branch-snapshots/demo/frontend/package-lock.json"]
    )


def test_candidate_requires_exact_head_green_workflows() -> None:
    files = ["backend/requirements.txt"]
    required = required_workflows_for_files(files)
    decision = evaluate_candidate(
        _pr(),
        files,
        _runs(required),
        base_branch="main",
        required_workflows=required,
    )
    assert decision.ready is True
    assert decision.reasons == ()
    assert decision.head_sha == "abc123"


def test_candidate_fails_closed_on_missing_or_non_green_workflow() -> None:
    files = ["requirements.txt"]
    required = required_workflows_for_files(files)
    missing = _runs(required)[:-1]
    decision = evaluate_candidate(
        _pr(), files, missing, base_branch="main", required_workflows=required
    )
    assert decision.ready is False
    assert any(reason.startswith("missing_workflow:") for reason in decision.reasons)

    failed = _runs(required)
    failed[0] = {**failed[0], "conclusion": "failure"}
    decision = evaluate_candidate(
        _pr(), files, failed, base_branch="main", required_workflows=required
    )
    assert decision.ready is False
    assert f"workflow_not_green:{required[0]}" in decision.reasons


def test_latest_run_wins_so_stale_success_cannot_mask_new_failure() -> None:
    required = DEFAULT_REQUIRED_WORKFLOWS
    runs = _runs(required)
    runs.extend(
        [
            {
                "name": required[0],
                "head_sha": "abc123",
                "event": "pull_request",
                "status": "completed",
                "conclusion": "failure",
                "run_number": 999,
                "run_attempt": 1,
            },
            {
                "name": required[0],
                "head_sha": "other-head",
                "event": "pull_request",
                "status": "completed",
                "conclusion": "success",
                "run_number": 1000,
                "run_attempt": 1,
            },
        ]
    )
    decision = evaluate_candidate(
        _pr(),
        ["nested/uv.lock"],
        runs,
        base_branch="main",
        required_workflows=required,
    )
    assert decision.ready is False
    assert f"workflow_not_green:{required[0]}" in decision.reasons


def test_candidate_rejects_untrusted_or_mutation_sensitive_state() -> None:
    cases = (
        (_pr(author={"login": "attacker"}), "untrusted_author"),
        (_pr(headRefName="feature/not-dependabot"), "untrusted_head"),
        (_pr(isCrossRepository=True), "cross_repository_head"),
        (_pr(baseRefName="release"), "wrong_base"),
        (_pr(isDraft=True), "not_open_ready_pr"),
        (_pr(state="CLOSED"), "not_open_ready_pr"),
        (_pr(mergeable="CONFLICTING"), "not_mergeable"),
        (_pr(headRefOid=""), "missing_head_sha"),
    )
    for candidate, expected in cases:
        decision = evaluate_candidate(
            candidate,
            ["nested/uv.lock"],
            _runs(),
            base_branch="main",
        )
        assert decision.ready is False
        assert expected in decision.reasons


def test_candidate_rejects_empty_or_out_of_scope_diff_and_empty_gate_set() -> None:
    empty = evaluate_candidate(_pr(), [], _runs(), base_branch="main")
    assert "empty_diff" in empty.reasons
    unsafe = evaluate_candidate(
        _pr(),
        ["requirements.txt", ".github/workflows/ci.yml"],
        _runs(),
        base_branch="main",
    )
    assert "out_of_scope_file" in unsafe.reasons
    no_gates = evaluate_candidate(
        _pr(),
        ["nested/uv.lock"],
        [],
        base_branch="main",
        required_workflows=(),
    )
    assert "no_required_workflows" in no_gates.reasons


def test_identity_recheck_rejects_head_state_or_repository_change() -> None:
    before = _pr()
    assert same_candidate_identity(before, dict(before))
    assert not same_candidate_identity(before, _pr(headRefOid="moved"))
    assert not same_candidate_identity(before, _pr(isDraft=True))
    assert not same_candidate_identity(before, _pr(isCrossRepository=True))
    assert not same_candidate_identity(before, _pr(author={"login": "someone-else"}))


def test_base_ancestry_check_requires_current_base_in_candidate_head(monkeypatch) -> None:
    client = GitHubCLI("owner/repo")
    responses = iter(['{"behind_by": 0}', '{"behind_by": 1}'])
    monkeypatch.setattr(client, "_run", lambda args, *, timeout=None: next(responses))
    assert client.head_contains_base("base", "head") is True
    assert client.head_contains_base("base", "stale-head") is False


def test_run_once_rejects_base_move_at_final_mutation_boundary(monkeypatch) -> None:
    files = ["nested/uv.lock"]
    required = required_workflows_for_files(files)

    class FakeClient:
        def __init__(self, repo):
            self.base_heads = iter(("base1", "base1", "base2"))
            self.merges = []

        def open_prs(self):
            return [_pr()]

        def branch_head(self, branch):
            return next(self.base_heads)

        def files(self, number):
            return files

        def runs(self, head_sha):
            return _runs(required)

        def head_contains_base(self, base_sha, head_sha):
            return True

        def pr(self, number):
            return _pr()

        def merge(self, number, expected_head_sha):
            self.merges.append((number, expected_head_sha))

    fake = FakeClient("owner/repo")
    monkeypatch.setattr(policy, "GitHubCLI", lambda repo: fake)
    monkeypatch.delenv("DEPENDABOT_REQUIRED_WORKFLOWS", raising=False)
    assert policy.run_once("owner/repo", "main") == 0
    assert fake.merges == []


def test_run_once_skips_untrusted_pr_before_privileged_metadata_calls(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, repo):
            self.metadata_calls = 0

        def open_prs(self):
            return [_pr(author={"login": "someone-else"})]

        def branch_head(self, branch):
            self.metadata_calls += 1
            raise AssertionError("untrusted PR must not reach privileged evaluation")

    fake = FakeClient("owner/repo")
    monkeypatch.setattr(policy, "GitHubCLI", lambda repo: fake)
    assert policy.run_once("owner/repo", "main") == 0
    assert fake.metadata_calls == 0


def test_merge_mutation_is_bound_to_validated_head_sha(monkeypatch) -> None:
    client = GitHubCLI("owner/repo")
    seen: list[list[str]] = []

    def fake_run(args, *, timeout=None):
        seen.append(list(args))
        return '{"merged": true}'

    monkeypatch.setattr(client, "_run", fake_run)
    client.merge(42, "deadbeef")
    assert seen == [
        [
            "api",
            "-X",
            "PUT",
            "repos/owner/repo/pulls/42/merge",
            "-f",
            "sha=deadbeef",
            "-f",
            "merge_method=squash",
        ]
    ]
