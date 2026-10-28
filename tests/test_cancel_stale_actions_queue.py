"""Adversarial age/scope/cancel acceptance tests for stale Actions queue expiry."""
from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from scripts.cancel_stale_actions_queue import (
    CleanupError, GitHubActions, MAX_AGE_SECONDS, cleanup, stale_queued,
)


def stamp(second: int) -> str:
    return datetime.fromtimestamp(second, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeGitHub(GitHubActions):
    def __init__(self, runs: list[dict[str, object]], *, response: int = 202,
                 terminal: bool = False):
        super().__init__("Apeloff1/Skeleton", "test-token")
        self.rows = {int(row["id"]): dict(row) for row in runs}
        self.response = response
        self.terminal = terminal
        self.posts: list[int] = []
        self.mutate_to_running: set[int] = set()
        self.job_running: set[int] = set()

    def queued_runs(self):
        return list(self.rows.values())

    def unchanged_and_queued(self, row, *, now, current):
        item = self.rows[row["id"]]
        if row["id"] in self.mutate_to_running:
            item["status"] = "in_progress"
        return row["id"] not in self.job_running and stale_queued(
            item, now=now, current=current
        )

    def cancel(self, run_id):
        self.posts.append(run_id)
        return self.response

    def checked_get(self, path):
        ident = int(path.rsplit("/", 1)[-1])
        state = dict(self.rows[ident])
        if self.terminal:
            state["status"] = "completed"
            state["conclusion"] = "cancelled"
        return state


class CleanupPolicyTests(unittest.TestCase):
    NOW = 1_800_000_000

    def run_row(self, identifier, *, age, status="queued"):
        return {
            "id": identifier, "status": status,
            "created_at": stamp(self.NOW - age),
        }

    def test_strict_three_hour_boundary(self):
        for age in (1, MAX_AGE_SECONDS - 1, MAX_AGE_SECONDS):
            self.assertFalse(stale_queued(self.run_row(1, age=age),
                                          now=self.NOW, current=55))
        self.assertTrue(stale_queued(
            self.run_row(1, age=MAX_AGE_SECONDS + 1),
            now=self.NOW, current=55,
        ))

    def test_only_queued_and_not_self(self):
        for status in ("in_progress", "waiting", "pending", "requested", "completed"):
            self.assertFalse(stale_queued(
                self.run_row(1, age=20000, status=status),
                now=self.NOW, current=2,
            ))
        self.assertFalse(stale_queued(
            self.run_row(1, age=20000), now=self.NOW, current=1,
        ))

    def test_malformed_or_future_timestamp_fails_closed(self):
        for value in ("", "not-a-time", "2026-10-28T01:02:03", None):
            row = self.run_row(1, age=20000)
            row["created_at"] = value
            with self.assertRaises(CleanupError):
                stale_queued(row, now=self.NOW, current=2)
        with self.assertRaises(CleanupError):
            stale_queued(self.run_row(1, age=-3), now=self.NOW, current=2)

    @patch("scripts.cancel_stale_actions_queue.time.time", return_value=1_800_000_000)
    def test_recheck_skips_started_job_and_preserves_new_work(self, _time):
        rows = [
            self.run_row(1, age=20000),
            self.run_row(2, age=100),
            self.run_row(3, age=30000),
            self.run_row(4, age=25000),
        ]
        client = FakeGitHub(rows)
        client.mutate_to_running.add(3)
        client.job_running.add(4)
        out = cleanup(client, now=self.NOW, current=5)
        self.assertEqual(client.posts, [1])
        self.assertEqual(out["older_than_three_hours"], 3)
        self.assertEqual(out["already_moved_or_protected"], 2)
        self.assertEqual(out["cancel_requested"], 1)
        self.assertEqual(out["confirmed_cancelled"], 0)

    @patch("scripts.cancel_stale_actions_queue.time.time", return_value=1_800_000_000)
    def test_provider_conflict_never_claims_cancelled(self, _time):
        client = FakeGitHub([self.run_row(91, age=20000)], response=409)
        out = cleanup(client, now=self.NOW, current=99)
        self.assertEqual(out["provider_conflict"], 1)
        self.assertEqual(out["cancel_requested"], 0)
        self.assertEqual(out["confirmed_cancelled"], 0)

    @patch("scripts.cancel_stale_actions_queue.time.time", return_value=1_800_000_000)
    def test_acknowledgement_is_not_terminal_success(self, _time):
        client = FakeGitHub([self.run_row(90, age=20000)], terminal=True)
        out = cleanup(client, now=self.NOW, current=99)
        self.assertEqual(out["cancel_requested"], 1)
        self.assertEqual(out["confirmed_cancelled"], 1)

    @patch("scripts.cancel_stale_actions_queue.time.time", return_value=1_800_000_000)
    def test_dry_run_does_not_mutate_any_run(self, _time):
        client = FakeGitHub([self.run_row(11, age=20000)])
        out = cleanup(client, now=self.NOW, current=99, dry_run=True)
        self.assertEqual(client.posts, [])
        self.assertEqual(out["considered"], 1)



class AssociatedPRPolicyTests(unittest.TestCase):
    """Provider age never supersedes GitHub's current PR-head identity."""

    SHA = "a" * 40
    NEW_SHA = "b" * 40

    def row(self, *, event="pull_request", sha=None, branch="feat/current"):
        return {
            "id": 567, "event": event,
            "head_sha": self.SHA if sha is None else sha,
            "head_branch": branch, "status": "queued",
            "created_at": stamp(1_800_000_000 - 20000),
            "path": ".github/workflows/merge-readiness.yml",
            "workflow_id": 42,
        }

    def check(self, *, state="open", head=None, branch="feat/current",
              associated=True):
        client = GitHubActions("Apeloff1/Skeleton", "token")
        linked = [{"number": 99}] if associated else []
        pr = {
            "number": 99, "state": state,
            "base": {"repo": {"full_name": "Apeloff1/Skeleton"}},
            "head": {"sha": self.SHA if head is None else head,
                     "ref": branch},
        }
        def api(path):
            if "/commits/" in path:
                return linked
            if path.endswith("/pulls/99"):
                return pr
            raise AssertionError(f"unexpected URL {path}")
        with patch.object(client, "checked_get", side_effect=api):
            return client.confirmed_obsolete(self.row())

    def test_current_head_required_check_cannot_expire(self):
        self.assertFalse(self.check(state="open"))
        self.assertFalse(self.check(state="open", head=self.SHA))

    def test_superseded_pr_head_can_expire(self):
        self.assertTrue(self.check(state="open", head=self.NEW_SHA))

    def test_closed_pr_run_can_expire(self):
        self.assertTrue(self.check(state="closed"))

    def test_unassociated_branch_does_not_prove_obsolescence(self):
        self.assertFalse(self.check(associated=False))
        self.assertFalse(self.check(branch="feat/unrelated"))

    def test_no_age_only_main_or_dynamic_cleanup(self):
        client = GitHubActions("Apeloff1/Skeleton", "token")
        with patch.object(client, "checked_get") as read:
            self.assertFalse(client.confirmed_obsolete(self.row(event="push")))
            self.assertFalse(client.confirmed_obsolete(
                self.row(event="workflow_run")))
            self.assertFalse(client.confirmed_obsolete(
                self.row(event="dynamic")))
            self.assertFalse(client.confirmed_obsolete(
                self.row(sha="untrusted")))
            read.assert_not_called()

    def test_invalid_pr_association_fails_closed(self):
        client = GitHubActions("Apeloff1/Skeleton", "token")
        with patch.object(client, "checked_get", return_value={"oops": True}):
            with self.assertRaises(CleanupError):
                client.confirmed_obsolete(self.row())

    def test_current_head_wins_over_another_obsolete_association(self):
        client = GitHubActions("Apeloff1/Skeleton", "token")
        linked = [{"number": 99}, {"number": 100}]
        def api(path):
            if "/commits/" in path:
                return linked
            number = int(path.rsplit("/", 1)[-1])
            return {
                "number": number,
                "state": "closed" if number == 99 else "open",
                "base": {"repo": {"full_name": "Apeloff1/Skeleton"}},
                "head": {"sha": self.SHA, "ref": "feat/current"},
            }
        with patch.object(client, "checked_get", side_effect=api):
            self.assertFalse(client.confirmed_obsolete(self.row()))

    def test_identity_change_between_inventory_and_preflight_fails(self):
        row = self.row()
        client = GitHubActions("Apeloff1/Skeleton", "token")
        detail = dict(row, head_sha=self.NEW_SHA)
        with patch.object(client, "checked_get", return_value=detail):
            with self.assertRaises(CleanupError):
                client.unchanged_and_queued(row, now=1_800_000_000,
                                           current=999)

    @patch("scripts.cancel_stale_actions_queue.time.time",
           return_value=1_800_000_000)
    def test_known_provider_409_is_backed_off_without_post(self, _time):
        client = FakeGitHub([
            {"id": 34952509012, "status": "queued",
             "created_at": stamp(1_800_000_000 - 20000)},
        ])
        result = cleanup(client, now=1_800_000_000, current=555)
        self.assertEqual(client.posts, [])
        self.assertEqual(result["provider_backed_off"], 1)



    def test_incomplete_or_invalid_jobs_fail_closed(self):
        row = self.row()
        client = GitHubActions("Apeloff1/Skeleton", "token")
        states = (
            {"total_count": 2, "jobs": [{"status": "queued"}]},
            {"total_count": 1, "jobs": [None]},
            {"total_count": 1, "jobs": [{"status": "invented"}]},
        )
        for jobs in states:
            def api(path):
                if path.endswith("/actions/runs/567"):
                    return row
                if "/commits/" in path:
                    return [{"number": 99}]
                if path.endswith("/pulls/99"):
                    return {
                        "number": 99, "state": "closed",
                        "base": {"repo": {"full_name": "Apeloff1/Skeleton"}},
                        "head": {"sha": self.SHA, "ref": "feat/current"},
                    }
                if path.endswith("/jobs?per_page=100"):
                    return jobs
                raise AssertionError(path)
            with self.subTest(jobs=jobs), patch.object(
                client, "checked_get", side_effect=api
            ), self.assertRaises(CleanupError):
                client.unchanged_and_queued(row, now=1_800_000_000,
                                            current=999)

    @patch("scripts.cancel_stale_actions_queue.time.time",
           return_value=1_800_000_000)
    def test_real_cleanup_never_posts_for_current_head(self, _time):
        row = self.row()
        client = GitHubActions("Apeloff1/Skeleton", "token")
        def api(path):
            if path.endswith("/actions/runs/567"):
                return row
            if "/commits/" in path:
                return [{"number": 99}]
            if path.endswith("/pulls/99"):
                return {
                    "number": 99, "state": "open",
                    "base": {"repo": {"full_name": "Apeloff1/Skeleton"}},
                    "head": {"sha": self.SHA, "ref": "feat/current"},
                }
            raise AssertionError("unexpected job inventory request: " + path)
        with patch.object(client, "queued_runs", return_value=[row]), \
             patch.object(client, "checked_get", side_effect=api), \
             patch.object(client, "cancel") as cancel:
            result = cleanup(client, now=1_800_000_000, current=999)
        cancel.assert_not_called()
        self.assertEqual(result["already_moved_or_protected"], 1)
        self.assertEqual(result["cancel_requested"], 0)



if __name__ == "__main__":
    unittest.main()
