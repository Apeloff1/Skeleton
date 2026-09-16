from __future__ import annotations

from skeleton.automation.dependabot_merge_policy import (
    DEFAULT_REQUIRED_WORKFLOWS,
    GitHubCLI,
    dependency_path_allowed,
    evaluate_candidate,
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
    }
    payload.update(overrides)
    return payload


def _runs(*, conclusion: str = "success", status: str = "completed"):
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
        for index, name in enumerate(DEFAULT_REQUIRED_WORKFLOWS)
    ]


def test_dependency_path_allowlist_is_narrow_and_nested_manifest_safe() -> None:
    for path in (
        "requirements.txt",
        "backend/requirements-dev.txt",
        "pyproject.toml",
        "frontend/package.json",
        "frontend/package-lock.json",
        "nested/uv.lock",
    ):
        assert dependency_path_allowed(path)

    for path in (
        ".github/workflows/ci.yml",
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


def test_candidate_requires_exact_head_green_workflows() -> None:
    decision = evaluate_candidate(
        _pr(),
        ["backend/requirements.txt", "frontend/package-lock.json"],
        _runs(),
        base_branch="main",
    )

    assert decision.ready is True
    assert decision.reasons == ()
    assert decision.head_sha == "abc123"


def test_candidate_fails_closed_on_missing_or_non_green_workflow() -> None:
    missing = _runs()[:-1]
    decision = evaluate_candidate(
        _pr(), ["requirements.txt"], missing, base_branch="main"
    )
    assert decision.ready is False
    assert any(reason.startswith("missing_workflow:") for reason in decision.reasons)

    failed = _runs()
    failed[0] = {**failed[0], "conclusion": "failure"}
    decision = evaluate_candidate(
        _pr(), ["requirements.txt"], failed, base_branch="main"
    )
    assert decision.ready is False
    assert f"workflow_not_green:{DEFAULT_REQUIRED_WORKFLOWS[0]}" in decision.reasons


def test_latest_run_wins_so_stale_success_cannot_mask_new_failure() -> None:
    runs = _runs()
    runs.extend(
        [
            {
                "name": DEFAULT_REQUIRED_WORKFLOWS[0],
                "head_sha": "abc123",
                "event": "pull_request",
                "status": "completed",
                "conclusion": "failure",
                "run_number": 999,
                "run_attempt": 1,
            },
            {
                "name": DEFAULT_REQUIRED_WORKFLOWS[0],
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
        _pr(), ["requirements.txt"], runs, base_branch="main"
    )

    assert decision.ready is False
    assert f"workflow_not_green:{DEFAULT_REQUIRED_WORKFLOWS[0]}" in decision.reasons


def test_candidate_rejects_untrusted_or_mutation_sensitive_state() -> None:
    cases = (
        (_pr(author={"login": "attacker"}), "untrusted_author"),
        (_pr(headRefName="feature/not-dependabot"), "untrusted_head"),
        (_pr(baseRefName="release"), "wrong_base"),
        (_pr(isDraft=True), "not_open_ready_pr"),
        (_pr(state="CLOSED"), "not_open_ready_pr"),
        (_pr(mergeable="CONFLICTING"), "not_mergeable"),
        (_pr(headRefOid=""), "missing_head_sha"),
    )

    for candidate, expected in cases:
        decision = evaluate_candidate(
            candidate, ["requirements.txt"], _runs(), base_branch="main"
        )
        assert decision.ready is False
        assert expected in decision.reasons


def test_candidate_rejects_empty_or_out_of_scope_diff_and_empty_gate_set() -> None:
    empty = evaluate_candidate(_pr(), [], _runs(), base_branch="main")
    assert "empty_diff" in empty.reasons

    unsafe = evaluate_candidate(
        _pr(), ["requirements.txt", ".github/workflows/ci.yml"], _runs(), base_branch="main"
    )
    assert "out_of_scope_file" in unsafe.reasons

    no_gates = evaluate_candidate(
        _pr(), ["requirements.txt"], _runs(), base_branch="main", required_workflows=()
    )
    assert "no_required_workflows" in no_gates.reasons


def test_identity_recheck_rejects_head_or_state_change() -> None:
    before = _pr()
    assert same_candidate_identity(before, dict(before))
    assert not same_candidate_identity(before, _pr(headRefOid="moved"))
    assert not same_candidate_identity(before, _pr(isDraft=True))
    assert not same_candidate_identity(before, _pr(author={"login": "someone-else"}))


def test_merge_mutation_is_bound_to_validated_head_sha(monkeypatch) -> None:
    client = GitHubCLI("owner/repo")
    seen: list[list[str]] = []

    def fake_run(args, *, timeout=None):
        seen.append(list(args))
        return '{"merged": true}'

    monkeypatch.setattr(client, "_run", fake_run)

    client.merge(42, "deadbeef")

    assert seen == [[
        "api",
        "-X",
        "PUT",
        "repos/owner/repo/pulls/42/merge",
        "-f",
        "sha=deadbeef",
        "-f",
        "merge_method=squash",
    ]]
