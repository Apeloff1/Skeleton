from __future__ import annotations

import skeleton.automation.dependabot_merge_policy as policy


def _pr():
    return {
        "number": 42,
        "author": {"login": "dependabot[bot]"},
        "headRefName": "dependabot/pip/backend/example-2.0",
        "headRefOid": "head-sha",
        "baseRefName": "main",
        "isDraft": False,
        "state": "OPEN",
        "mergeable": "MERGEABLE",
    }


def _runs():
    return [
        {
            "name": name,
            "head_sha": "head-sha",
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "run_number": index + 1,
            "run_attempt": 1,
        }
        for index, name in enumerate(policy.DEFAULT_REQUIRED_WORKFLOWS)
    ]


class FakeClient:
    base_sequence = ["base-sha", "base-sha", "base-sha"]
    contains = True
    instances = []

    def __init__(self, repo):
        self.repo = repo
        self.base_reads = iter(type(self).base_sequence)
        self.merges = []
        type(self).instances.append(self)

    def open_prs(self):
        return [_pr()]

    def branch_head(self, branch):
        assert branch == "main"
        return next(self.base_reads)

    def files(self, number):
        assert number == 42
        return ["requirements.txt"]

    def runs(self, head_sha):
        assert head_sha == "head-sha"
        return _runs()

    def candidate_contains_base(self, base_sha, head_sha):
        assert base_sha == "base-sha"
        assert head_sha == "head-sha"
        return type(self).contains

    def pr(self, number):
        assert number == 42
        return _pr()

    def merge(self, number, expected_head_sha):
        self.merges.append((number, expected_head_sha))


def _install(monkeypatch, *, base_sequence, contains=True):
    FakeClient.base_sequence = list(base_sequence)
    FakeClient.contains = contains
    FakeClient.instances = []
    monkeypatch.setattr(policy, "GitHubCLI", FakeClient)


def test_stable_base_and_containment_are_required_before_merge(monkeypatch) -> None:
    _install(monkeypatch, base_sequence=["base-sha", "base-sha", "base-sha"])

    assert policy.run_once("owner/repo", "main") == 1
    assert FakeClient.instances[0].merges == [(42, "head-sha")]


def test_base_move_between_validation_and_mutation_fails_closed(monkeypatch) -> None:
    _install(monkeypatch, base_sequence=["base-sha", "moved-base"])

    assert policy.run_once("owner/repo", "main") == 0
    assert FakeClient.instances[0].merges == []


def test_candidate_missing_current_base_fails_closed(monkeypatch) -> None:
    _install(monkeypatch, base_sequence=["base-sha"], contains=False)

    assert policy.run_once("owner/repo", "main") == 0
    assert FakeClient.instances[0].merges == []


def test_final_base_move_after_revalidation_fails_closed(monkeypatch) -> None:
    _install(monkeypatch, base_sequence=["base-sha", "base-sha", "moved-base"])

    assert policy.run_once("owner/repo", "main") == 0
    assert FakeClient.instances[0].merges == []
