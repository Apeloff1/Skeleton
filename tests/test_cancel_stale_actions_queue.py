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
        self.assertEqual(out["already_moved"], 2)
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


if __name__ == "__main__":
    unittest.main()
