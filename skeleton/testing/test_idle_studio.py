from __future__ import annotations

import json
import unittest

from skeleton.automation.idle_studio import (
    FLEET,
    FLEET_SIZE,
    MAX_SNAPSHOT_PAGES,
    ROLE_PROFILES,
    SNAPSHOT_PAGE_SIZE,
    GitHubClient,
    GitHubError,
    StudioConfig,
    WorkItem,
    assign_workers,
    canonical_commit_oid,
    parse_proposal,
    repository_is_idle,
    safe_change_path,
    task_fingerprint,
)


class IdleStudioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = StudioConfig(
            active_workers=8,
            tasks_per_run=4,
            max_model_calls=6,
            max_files_per_change=3,
            max_file_bytes=10_000,
            max_total_change_bytes=20_000,
            max_open_studio_prs=12,
            dry_run=True,
        )

    def test_fleet_has_exactly_one_thousand_stable_unique_workers(self) -> None:
        self.assertEqual(len(FLEET), FLEET_SIZE)
        self.assertEqual(len({worker.worker_id for worker in FLEET}), FLEET_SIZE)
        expected_per_role = FLEET_SIZE // len(ROLE_PROFILES)
        for profile in ROLE_PROFILES:
            self.assertEqual(sum(worker.role == profile.name for worker in FLEET), expected_per_role)

    def test_assignment_is_deterministic_and_prefers_matching_role(self) -> None:
        task = WorkItem("security:42", "security", "Fix trust boundary", "evidence", 100)
        first = assign_workers([task], 1)
        second = assign_workers([task], 1)
        self.assertEqual(first, second)
        role = first[0][1].role
        profile = next(item for item in ROLE_PROFILES if item.name == role)
        self.assertIn("security", profile.kinds)

    def test_assignment_uses_unique_workers_within_sweep(self) -> None:
        tasks = [WorkItem(f"issue:{i}", "backlog", f"Task {i}", "evidence", 50) for i in range(8)]
        assignments = assign_workers(tasks, 8)
        self.assertEqual(len(assignments), 8)
        self.assertEqual(len({worker.worker_id for _, worker in assignments}), 8)

    def test_safe_paths_allow_product_code_but_block_control_plane(self) -> None:
        self.assertTrue(safe_change_path("skeleton/game/mechanics.py"))
        self.assertTrue(safe_change_path("backend/api/router.py"))
        self.assertTrue(safe_change_path("tests/test_router.py"))
        self.assertTrue(safe_change_path("docs/architecture.md"))
        for path in (
            ".github/workflows/idle.yml",
            "../escape.py",
            "/absolute.py",
            ".env",
            "deploy/prod.sh",
            "Dockerfile",
            "backend/../../.github/workflows/x.yml",
            "backend/blob.bin",
        ):
            self.assertFalse(safe_change_path(path), path)

    def test_valid_proposal_is_parsed_and_python_is_statically_compiled(self) -> None:
        raw = json.dumps(
            {
                "summary": "Add a focused helper and regression test.",
                "files": [
                    {"path": "skeleton/example.py", "content": "def answer():\n    return 42\n"},
                    {"path": "tests/test_example.py", "content": "def test_answer():\n    assert 42 == 42\n"},
                ],
                "verification": ["CI should run the focused regression"],
            }
        )
        proposal = parse_proposal(raw, self.config)
        self.assertEqual(len(proposal.files), 2)
        self.assertIn("focused helper", proposal.summary)

    def test_proposal_rejects_control_plane_and_duplicate_paths(self) -> None:
        blocked = json.dumps({"summary": "bad", "files": [{"path": ".github/workflows/x.yml", "content": "name: x"}]})
        with self.assertRaises(ValueError):
            parse_proposal(blocked, self.config)

        duplicate = json.dumps(
            {
                "summary": "bad",
                "files": [
                    {"path": "skeleton/x.py", "content": "x = 1\n"},
                    {"path": "skeleton/x.py", "content": "x = 2\n"},
                ],
            }
        )
        with self.assertRaises(ValueError):
            parse_proposal(duplicate, self.config)

    def test_proposal_rejects_python_syntax_error(self) -> None:
        raw = json.dumps({"summary": "bad", "files": [{"path": "skeleton/x.py", "content": "def nope(:\n"}]})
        with self.assertRaises(SyntaxError):
            parse_proposal(raw, self.config)

    def test_repository_idle_ignores_current_run_but_blocks_other_active_runs(self) -> None:
        current_only = [{"id": 10, "status": "in_progress"}, {"id": 9, "status": "completed"}]
        self.assertTrue(repository_is_idle(current_only, "10"))
        busy = current_only + [{"id": 11, "status": "queued"}]
        self.assertFalse(repository_is_idle(busy, "10"))

    def test_task_fingerprint_is_stable_and_task_specific(self) -> None:
        a = WorkItem("issue:1", "backlog", "One", "x", 1)
        b = WorkItem("issue:2", "backlog", "One", "x", 1)
        self.assertEqual(task_fingerprint(a), task_fingerprint(a))
        self.assertNotEqual(task_fingerprint(a), task_fingerprint(b))

    def test_recent_runs_paginates_complete_prefix(self) -> None:
        client = GitHubClient("Apeloff1/Skeleton", "token")
        calls: list[str] = []

        def fake_api(method: str, path: str, payload=None):
            calls.append(path)
            self.assertEqual(method, "GET")
            if path.endswith("page=1"):
                return {"workflow_runs": [{"id": n} for n in range(SNAPSHOT_PAGE_SIZE)]}
            if path.endswith("page=2"):
                return {"workflow_runs": [{"id": 99}]}
            raise AssertionError(path)

        client._api = fake_api  # type: ignore[method-assign]
        runs = client.recent_runs()
        self.assertEqual(len(runs), SNAPSHOT_PAGE_SIZE + 1)
        self.assertEqual(runs[-1]["id"], 99)
        self.assertEqual(len(calls), 2)

    def test_recent_runs_scan_bound_fails_closed(self) -> None:
        client = GitHubClient("Apeloff1/Skeleton", "token")
        calls: list[str] = []

        def fake_api(method: str, path: str, payload=None):
            calls.append(path)
            return {"workflow_runs": [{"id": n} for n in range(SNAPSHOT_PAGE_SIZE)]}

        client._api = fake_api  # type: ignore[method-assign]
        with self.assertRaises(GitHubError) as ctx:
            client.recent_runs()
        self.assertIn("bounded identity scan", str(ctx.exception))
        self.assertEqual(len(calls), MAX_SNAPSHOT_PAGES)

    def test_branch_sha_canonicalizes_and_rejects_malformed_oid(self) -> None:
        client = GitHubClient("Apeloff1/Skeleton", "token")
        sha = "a" * 40

        def ok_api(method: str, path: str, payload=None):
            self.assertEqual(method, "GET")
            self.assertEqual(path, "/git/ref/heads/main")
            return {"object": {"sha": sha.upper()}}

        client._api = ok_api  # type: ignore[method-assign]
        self.assertEqual(client.branch_sha("main"), sha)
        self.assertEqual(canonical_commit_oid(sha.upper()), sha)

        def bad_api(method: str, path: str, payload=None):
            return {"object": {"sha": "abc123"}}

        client._api = bad_api  # type: ignore[method-assign]
        with self.assertRaises(GitHubError) as ctx:
            client.branch_sha("main")
        self.assertIn("40-character hex commit OID", str(ctx.exception))

    def test_commit_tree_sha_quotes_canonical_oid_before_lookup(self) -> None:
        client = GitHubClient("Apeloff1/Skeleton", "token")
        sha = "b" * 40
        tree = "c" * 40
        calls: list[str] = []

        def fake_api(method: str, path: str, payload=None):
            calls.append(path)
            self.assertEqual(method, "GET")
            return {"tree": {"sha": tree.upper()}}

        client._api = fake_api  # type: ignore[method-assign]
        self.assertEqual(client.commit_tree_sha(sha.upper()), tree)
        self.assertEqual(calls, [f"/git/commits/{sha}"])
        self.assertNotIn(sha.upper(), calls[0])

        with self.assertRaises(GitHubError) as ctx:
            client.commit_tree_sha("abc123")
        self.assertIn("40-character hex commit OID", str(ctx.exception))
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
