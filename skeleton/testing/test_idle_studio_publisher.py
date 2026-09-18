from __future__ import annotations

import unittest

from skeleton.automation.idle_studio import (
    ChangeProposal,
    FLEET,
    ProposedFile,
    StudioConfig,
    WorkItem,
)
from skeleton.automation.idle_studio_publisher import publish_entries
from skeleton.automation.idle_studio_v2 import (
    PACKAGE_VERSION,
    ResearchDecision,
    ReviewDecision,
    VerificationDecision,
    choose_squad,
    entry_for,
)


class _FakeGitHub:
    def __init__(self, base_sha: str, branch_states: list[str] | None = None, pulls=None) -> None:
        self.base_sha = base_sha
        self.branch_states = list(branch_states or [base_sha, base_sha, base_sha])
        self.pulls = list(pulls or [])
        self.refs: list[tuple[str, str]] = []
        self.created_pulls: list[dict] = []
        self.blobs: list[str] = []

    def open_pulls(self):
        return list(self.pulls)

    def branch_sha(self, branch: str) -> str:
        self.assert_main(branch)
        return self.branch_states.pop(0) if self.branch_states else self.base_sha

    @staticmethod
    def assert_main(branch: str) -> None:
        if branch != "main":
            raise AssertionError(f"unexpected branch lookup: {branch}")

    def commit_tree_sha(self, commit_sha: str) -> str:
        if commit_sha != self.base_sha:
            raise AssertionError("publisher used an unexpected base commit")
        return "tree-base"

    def create_blob(self, content: str) -> str:
        self.blobs.append(content)
        return f"blob-{len(self.blobs)}"

    def create_tree(self, base_tree: str, blobs):
        if base_tree != "tree-base":
            raise AssertionError("publisher used an unexpected base tree")
        if not blobs:
            raise AssertionError("publisher attempted an empty tree")
        return "tree-new"

    def create_commit(self, message: str, tree_sha: str, parent_sha: str) -> str:
        if tree_sha != "tree-new" or parent_sha != self.base_sha or not message:
            raise AssertionError("invalid commit inputs")
        return "commit-new"

    def create_ref(self, branch: str, sha: str) -> None:
        self.refs.append((branch, sha))

    def create_pull(self, *, title: str, branch: str, body: str):
        result = {
            "number": 999,
            "html_url": "https://example.invalid/pull/999",
            "title": title,
            "branch": branch,
            "body": body,
        }
        self.created_pulls.append(result)
        return result


class IdleStudioPublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = StudioConfig(
            active_workers=8,
            tasks_per_run=4,
            max_model_calls=9,
            max_files_per_change=4,
            max_file_bytes=10_000,
            max_total_change_bytes=20_000,
            max_open_studio_prs=12,
            dry_run=False,
        )
        self.base_sha = "a" * 40
        self.task = WorkItem(
            "issue:4242",
            "security",
            "Fix bounded trust boundary",
            "sealed evidence",
            100,
        )
        self.builder = next(worker for worker in FLEET if worker.role == "security")
        self.squad = choose_squad(self.task, self.builder)
        self.proposal = ChangeProposal(
            summary="Add a focused regression-safe helper.",
            files=(ProposedFile("skeleton/example.py", "def answer():\n    return 42\n"),),
            verification_notes=("CI must validate the helper",),
        )
        self.research = ResearchDecision(
            findings=("The trust boundary is narrow.",),
            recommended_checks=("focused security regression",),
        )
        self.review = ReviewDecision(True, "Scoped and independently reviewable.")
        self.verification = VerificationDecision(
            True,
            "Credential-free CI can validate this change.",
            ("focused security regression",),
        )
        self.entry = entry_for(
            self.task,
            self.squad,
            self.research,
            self.review,
            self.verification,
            self.proposal,
        )

    def package(self):
        return {
            "version": PACKAGE_VERSION,
            "status": "ready",
            "base_sha": self.base_sha,
            "planner": None,
            "entries": [self.entry],
        }

    def test_publish_rechecks_main_and_opens_review_pr_with_squad_provenance(self) -> None:
        github = _FakeGitHub(self.base_sha)
        published = publish_entries(self.package(), self.config, github, run_id="123", attempt="2")
        self.assertEqual(len(published), 1)
        self.assertEqual(len(github.refs), 1)
        self.assertEqual(len(github.created_pulls), 1)
        self.assertTrue(github.refs[0][0].startswith(f"idle-studio/{self.builder.worker_id}/"))
        body = github.created_pulls[0]["body"]
        for worker_id in self.squad.worker_ids:
            self.assertIn(worker_id, body)
        self.assertIn("Four-agent squad provenance", body)
        self.assertIn("Required deterministic checks", body)
        self.assertIn("idle-studio-task:issue:4242", body)
        self.assertEqual(published[0]["squad"], list(self.squad.worker_ids))

    def test_main_move_before_final_branch_boundary_aborts_mutation(self) -> None:
        moved = "b" * 40
        github = _FakeGitHub(self.base_sha, [self.base_sha, moved])
        with self.assertRaises(RuntimeError):
            publish_entries(self.package(), self.config, github, run_id="123", attempt="1")
        self.assertEqual(github.refs, [])
        self.assertEqual(github.created_pulls, [])

    def test_main_move_after_branch_creation_refuses_pr(self) -> None:
        moved = "c" * 40
        github = _FakeGitHub(self.base_sha, [self.base_sha, self.base_sha, moved])
        with self.assertRaises(RuntimeError):
            publish_entries(self.package(), self.config, github, run_id="123", attempt="1")
        self.assertEqual(len(github.refs), 1)
        self.assertEqual(github.created_pulls, [])

    def test_existing_task_claim_is_not_published_again(self) -> None:
        pulls = [
            {
                "body": "<!-- idle-studio-task:issue:4242 -->",
                "head": {"ref": "idle-studio/idle-0000/already"},
            }
        ]
        github = _FakeGitHub(self.base_sha, pulls=pulls)
        published = publish_entries(self.package(), self.config, github, run_id="123", attempt="1")
        self.assertEqual(published, [])
        self.assertEqual(github.refs, [])
        self.assertEqual(github.created_pulls, [])

    def test_open_pr_ceiling_applies_backpressure(self) -> None:
        pulls = [
            {"body": "", "head": {"ref": f"idle-studio/worker/{index}"}}
            for index in range(self.config.max_open_studio_prs)
        ]
        github = _FakeGitHub(self.base_sha, pulls=pulls)
        published = publish_entries(self.package(), self.config, github, run_id="123", attempt="1")
        self.assertEqual(published, [])
        self.assertEqual(github.refs, [])


    def test_malformed_package_base_sha_is_rejected(self) -> None:
        github = _FakeGitHub(self.base_sha)
        package = self.package()
        package["base_sha"] = "not-an-oid"
        with self.assertRaises(ValueError):
            publish_entries(package, self.config, github, run_id="123", attempt="1")
        self.assertEqual(github.refs, [])
        self.assertEqual(github.created_pulls, [])


if __name__ == "__main__":
    unittest.main()
