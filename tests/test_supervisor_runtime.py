from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skeleton.automation import supervisor_runtime as runtime


REPO = "Apeloff1/Skeleton"
BASE = "a" * 40
FP = "b" * 64


def execution(
    *,
    base_sha: str = BASE,
    run_id: str = "1234",
    attempt: str = "1",
) -> runtime.ExecutionIdentity:
    return runtime.ExecutionIdentity(
        repository=REPO,
        base_sha=base_sha,
        default_branch="main",
        run_id=run_id,
        run_attempt=attempt,
    )


class ExecutionIdentityTests(unittest.TestCase):
    def test_round_trip_mapping_is_canonical(self) -> None:
        value = execution()
        rebuilt = runtime.ExecutionIdentity(
            **value.as_dict()
        )
        self.assertEqual(
            rebuilt,
            value,
        )
        self.assertEqual(
            rebuilt.fingerprint,
            value.fingerprint,
        )

    def test_fingerprint_changes_with_base(self) -> None:
        first = execution()
        second = execution(
            base_sha="c" * 40
        )
        self.assertNotEqual(
            first.fingerprint,
            second.fingerprint,
        )

    def test_fingerprint_changes_with_attempt(self) -> None:
        first = execution()
        second = execution(
            attempt="2"
        )
        self.assertNotEqual(
            first.fingerprint,
            second.fingerprint,
        )

    def test_rejects_malformed_repository(self) -> None:
        with self.assertRaises(
            runtime.SupervisorRuntimeError
        ):
            runtime.ExecutionIdentity(
                repository="missing-slash",
                base_sha=BASE,
                default_branch="main",
                run_id="1",
                run_attempt="1",
            )

    def test_rejects_malformed_sha(self) -> None:
        with self.assertRaises(
            runtime.SupervisorRuntimeError
        ):
            execution(base_sha="short")

    def test_rejects_zero_run_id(self) -> None:
        with self.assertRaises(
            runtime.SupervisorRuntimeError
        ):
            execution(run_id="0")

    def test_from_mapping_requires_default_branch(self) -> None:
        with self.assertRaises(
            runtime.SupervisorRuntimeError
        ):
            runtime.ExecutionIdentity.from_mapping(
                {
                    "GITHUB_REPOSITORY": REPO,
                    "GITHUB_SHA": BASE,
                    "GITHUB_RUN_ID": "1",
                    "GITHUB_RUN_ATTEMPT": "1",
                }
            )

    def test_from_mapping_prefers_supervisor_base(self) -> None:
        value = runtime.ExecutionIdentity.from_mapping(
            {
                "GITHUB_REPOSITORY": REPO,
                "GITHUB_SHA": "c" * 40,
                "GITHUB_RUN_ID": "99",
                "GITHUB_RUN_ATTEMPT": "4",
                "SUPERVISOR_BASE_SHA": BASE,
                "SUPERVISOR_DEFAULT_BRANCH": "main",
                "SUPERVISOR_RUN_ID": "1234",
                "SUPERVISOR_RUN_ATTEMPT": "1",
            }
        )
        self.assertEqual(
            value,
            execution(),
        )


class CustodyAndBranchTests(unittest.TestCase):
    def test_worker_custody_fingerprint_binds_worker(self) -> None:
        first = runtime.WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=FP,
            execution=execution(),
        )
        second = runtime.WorkerCustody(
            worker="security-auditor",
            snapshot_fingerprint=FP,
            execution=execution(),
        )
        self.assertNotEqual(
            first.fingerprint,
            second.fingerprint,
        )

    def test_worker_branch_is_stable_across_snapshot_change(self) -> None:
        first = runtime.WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=FP,
            execution=execution(),
        )
        second = runtime.WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint="c" * 64,
            execution=execution(),
        )
        self.assertEqual(
            runtime.deterministic_worker_branch(first),
            runtime.deterministic_worker_branch(second),
        )

    def test_worker_branch_changes_with_base(self) -> None:
        first = runtime.WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=FP,
            execution=execution(),
        )
        second = runtime.WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=FP,
            execution=execution(
                base_sha="d" * 40
            ),
        )
        self.assertNotEqual(
            runtime.deterministic_worker_branch(first),
            runtime.deterministic_worker_branch(second),
        )

    def test_worker_branch_prefix_is_bounded(self) -> None:
        prefix = runtime.worker_branch_prefix(
            "root-cause"
        )
        self.assertEqual(
            prefix,
            "bot/specialist-root-cause-",
        )

    def test_invalid_worker_identity_is_rejected(self) -> None:
        with self.assertRaises(
            runtime.SupervisorRuntimeError
        ):
            runtime.WorkerCustody(
                worker="../escape",
                snapshot_fingerprint=FP,
                execution=execution(),
            )


class CanonicalEvidenceTests(unittest.TestCase):
    def test_canonical_json_is_key_order_independent(self) -> None:
        left = runtime.canonical_json(
            {
                "b": 2,
                "a": 1,
            }
        )
        right = runtime.canonical_json(
            {
                "a": 1,
                "b": 2,
            }
        )
        self.assertEqual(
            left,
            right,
        )

    def test_canonical_json_rejects_nan(self) -> None:
        with self.assertRaises(
            runtime.SupervisorRuntimeError
        ):
            runtime.canonical_json(
                {"x": float("nan")}
            )

    def test_proposal_digest_changes_with_content(self) -> None:
        first = runtime.proposal_digest(
            worker="root-cause",
            snapshot_fingerprint=FP,
            files=[
                {
                    "path": "tests/test_x.py",
                    "content": "x = 1\n",
                }
            ],
        )
        second = runtime.proposal_digest(
            worker="root-cause",
            snapshot_fingerprint=FP,
            files=[
                {
                    "path": "tests/test_x.py",
                    "content": "x = 2\n",
                }
            ],
        )
        self.assertNotEqual(
            first,
            second,
        )


class MutationPathTests(unittest.TestCase):
    def test_allowed_regular_target_resolves_inside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            target = runtime.resolve_mutation_target(
                "tests/test_x.py",
                repo_root=root,
                allowed_prefixes=("tests/",),
                blocked_prefixes=("tests/control/",),
            )
            self.assertEqual(
                target,
                root / "tests" / "test_x.py",
            )

    def test_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.resolve_mutation_target(
                    "../outside.py",
                    repo_root=Path(directory),
                    allowed_prefixes=("tests/",),
                    blocked_prefixes=(),
                )

    def test_rejects_blocked_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "skeleton" / "automation").mkdir(
                parents=True
            )
            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.resolve_mutation_target(
                    "skeleton/automation/secretary.py",
                    repo_root=root,
                    allowed_prefixes=("skeleton/",),
                    blocked_prefixes=(
                        "skeleton/automation/",
                    ),
                )

    def test_rejects_symlink_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            tests = root / "tests"
            try:
                tests.symlink_to(
                    outside,
                    target_is_directory=True,
                )
            except (
                OSError,
                NotImplementedError,
            ) as exc:
                self.skipTest(
                    f"symlinks unavailable: {type(exc).__name__}"
                )

            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.resolve_mutation_target(
                    "tests/test_x.py",
                    repo_root=root,
                    allowed_prefixes=("tests/",),
                    blocked_prefixes=(),
                )

    def test_rejects_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "tests"
            tests.mkdir()
            outside = root / "outside.py"
            outside.write_text(
                "safe\n",
                encoding="utf-8",
            )
            target = tests / "test_x.py"
            try:
                target.symlink_to(outside)
            except (
                OSError,
                NotImplementedError,
            ) as exc:
                self.skipTest(
                    f"symlinks unavailable: {type(exc).__name__}"
                )

            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.resolve_mutation_target(
                    "tests/test_x.py",
                    repo_root=root,
                    allowed_prefixes=("tests/",),
                    blocked_prefixes=(),
                )

    def test_safe_write_creates_regular_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = (
                Path(directory)
                / "tests"
                / "test_x.py"
            )
            runtime.safe_write_text(
                target,
                "x = 1\n",
            )
            self.assertTrue(
                target.is_file()
            )
            self.assertFalse(
                target.is_symlink()
            )
            self.assertEqual(
                target.read_text(
                    encoding="utf-8"
                ),
                "x = 1\n",
            )


class GitGuardTests(unittest.TestCase):
    def make_repo(
        self,
        root: Path,
    ) -> str:
        subprocess.run(
            ["git", "init", "-q"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "config",
                "user.email",
                "tests@example.invalid",
            ],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "config",
                "user.name",
                "tests",
            ],
            cwd=root,
            check=True,
        )
        (root / "tracked.txt").write_text(
            "base\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", "tracked.txt"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "commit",
                "-q",
                "-m",
                "base",
            ],
            cwd=root,
            check=True,
        )
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
        ).strip()

    def test_require_exact_head_accepts_current_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sha = self.make_repo(root)
            runtime.require_exact_head(
                sha,
                cwd=root,
            )

    def test_require_exact_head_rejects_other_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.require_exact_head(
                    "f" * 40,
                    cwd=root,
                )

    def test_require_clean_worktree_rejects_untracked_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            (root / "untracked.txt").write_text(
                "x\n",
                encoding="utf-8",
            )
            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.require_clean_worktree(
                    cwd=root
                )

    def test_validate_staged_paths_accepts_regular_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            target = root / "tests"
            target.mkdir()
            (target / "test_x.py").write_text(
                "x = 1\n",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "git",
                    "add",
                    "tests/test_x.py",
                ],
                cwd=root,
                check=True,
            )
            runtime.validate_staged_paths(
                ["tests/test_x.py"],
                cwd=root,
            )

    def test_validate_staged_paths_rejects_extra_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            for name in (
                "one.txt",
                "two.txt",
            ):
                (root / name).write_text(
                    name,
                    encoding="utf-8",
                )
            subprocess.run(
                [
                    "git",
                    "add",
                    "one.txt",
                    "two.txt",
                ],
                cwd=root,
                check=True,
            )
            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.validate_staged_paths(
                    ["one.txt"],
                    cwd=root,
                )

    def test_validate_staged_paths_rejects_symlink_mode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            target = root / "tracked-link"
            try:
                target.symlink_to("tracked.txt")
            except (
                OSError,
                NotImplementedError,
            ) as exc:
                self.skipTest(
                    f"symlinks unavailable: {type(exc).__name__}"
                )
            subprocess.run(
                ["git", "add", "tracked-link"],
                cwd=root,
                check=True,
            )
            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.validate_staged_paths(
                    ["tracked-link"],
                    cwd=root,
                )


class RemoteObservationTests(unittest.TestCase):
    def test_remote_default_head_uses_exact_repository_ref(
        self,
    ) -> None:
        value = execution()
        with patch(
            "skeleton.automation.supervisor_runtime.subprocess.check_output",
            return_value=BASE + "\n",
        ) as call:
            self.assertEqual(
                runtime.remote_default_head(value),
                BASE,
            )
        args = call.call_args.args[0]
        self.assertEqual(
            args[:2],
            ["gh", "api"],
        )
        self.assertIn(
            f"repos/{REPO}/git/ref/heads/main",
            args,
        )

    def test_remote_base_guard_rejects_advanced_main(
        self,
    ) -> None:
        with patch(
            "skeleton.automation.supervisor_runtime.remote_default_head",
            return_value="d" * 40,
        ):
            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.require_remote_base_unchanged(
                    execution()
                )

    def test_find_open_worker_pr_filters_namespace(
        self,
    ) -> None:
        payload = (
            '[{"number":1,"html_url":"https://example.invalid/1",'
            '"draft":false,"updated_at":"2026-09-19T00:00:00Z",'
            '"head":{"ref":"feature/x","repo":{"full_name":"Apeloff1/Skeleton"}},'
            '"base":{"ref":"main"}},'
            '{"number":2,"html_url":"https://example.invalid/2",'
            '"draft":false,"updated_at":"2026-09-19T00:00:00Z",'
            '"head":{"ref":"bot/specialist-root-cause-aaaaaaaaaaaaaaaa",'
            '"repo":{"full_name":"Apeloff1/Skeleton"}},'
            '"base":{"ref":"main"}}]'
        )
        with patch(
            "skeleton.automation.supervisor_runtime.subprocess.check_output",
            return_value=payload,
        ):
            result = runtime.find_open_pr_for_worker(
                REPO,
                "root-cause",
            )
        self.assertEqual(
            result["number"],
            2,
        )

    def test_find_open_worker_pr_ignores_fork_collision(
        self,
    ) -> None:
        payload = (
            '[{"number":3,"html_url":"https://example.invalid/3",'
            '"draft":false,"updated_at":"2026-09-19T00:00:00Z",'
            '"head":{"ref":"bot/specialist-root-cause-aaaaaaaaaaaaaaaa",'
            '"repo":{"full_name":"attacker/fork"}},'
            '"base":{"ref":"main"}}]'
        )
        with patch(
            "skeleton.automation.supervisor_runtime.subprocess.check_output",
            return_value=payload,
        ):
            result = runtime.find_open_pr_for_worker(
                REPO,
                "root-cause",
            )
        self.assertIsNone(result)

    def test_find_open_worker_pr_fails_closed_on_duplicates(
        self,
    ) -> None:
        payload = (
            '[{"number":1,"html_url":"https://example.invalid/1",'
            '"draft":false,"updated_at":"2026-09-19T00:00:00Z",'
            '"head":{"ref":"bot/specialist-root-cause-a",'
            '"repo":{"full_name":"Apeloff1/Skeleton"}},'
            '"base":{"ref":"main"}},'
            '{"number":2,"html_url":"https://example.invalid/2",'
            '"draft":false,"updated_at":"2026-09-19T00:00:00Z",'
            '"head":{"ref":"bot/specialist-root-cause-b",'
            '"repo":{"full_name":"Apeloff1/Skeleton"}},'
            '"base":{"ref":"main"}}]'
        )
        with patch(
            "skeleton.automation.supervisor_runtime.subprocess.check_output",
            return_value=payload,
        ):
            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.find_open_pr_for_worker(
                    REPO,
                    "root-cause",
                )

    def test_open_pr_query_fails_closed_at_bound(
        self,
    ) -> None:
        item = {
            "number": 1,
            "html_url": "https://example.invalid/1",
            "draft": False,
            "updated_at": "2026-09-19T00:00:00Z",
            "head": {
                "ref": "feature/x",
                "repo": {"full_name": REPO},
            },
            "base": {"ref": "main"},
        }
        import json

        payload = json.dumps([item] * 100)
        with patch(
            "skeleton.automation.supervisor_runtime.subprocess.check_output",
            return_value=payload,
        ):
            with self.assertRaises(
                runtime.SupervisorRuntimeError
            ):
                runtime.find_open_pr_for_worker(
                    REPO,
                    "root-cause",
                )



class WorkerResultEvidenceTests(unittest.TestCase):
    def test_accepts_created_pr_evidence(self) -> None:
        payload = json.dumps({
            "status": "pull-request-created",
            "bot": "root-cause",
            "branch": "bot/specialist-root-cause-aaaaaaaaaaaaaaaa",
            "pull_request": 42,
            "changed_lines": 17,
            "proposal_digest": "a" * 64,
        })
        result = runtime.parse_worker_result(
            payload + "\n",
            worker="root-cause",
        )
        self.assertEqual(result["status"], "pull-request-created")
        self.assertEqual(result["pull_request"], 42)
        self.assertEqual(result["changed_lines"], 17)

    def test_uses_only_final_non_empty_status_line(self) -> None:
        payload = (
            "diagnostic text that must not cross the boundary\n"
            + json.dumps({
                "status": "no-change",
                "bot": "security-auditor",
            })
            + "\n"
        )
        result = runtime.parse_worker_result(
            payload,
            worker="security-auditor",
        )
        self.assertEqual(
            result,
            {"status": "no-change", "bot": "security-auditor"},
        )

    def test_rejects_worker_identity_confusion(self) -> None:
        payload = json.dumps({
            "status": "no-change",
            "bot": "security-auditor",
        })
        with self.assertRaises(runtime.SupervisorRuntimeError):
            runtime.parse_worker_result(payload, worker="root-cause")

    def test_rejects_unknown_status(self) -> None:
        payload = json.dumps({
            "status": "executed-arbitrary-command",
            "bot": "root-cause",
        })
        with self.assertRaises(runtime.SupervisorRuntimeError):
            runtime.parse_worker_result(payload, worker="root-cause")

    def test_rejects_oversized_stdout(self) -> None:
        with self.assertRaises(runtime.SupervisorRuntimeError):
            runtime.parse_worker_result(
                "x" * (runtime.MAX_WORKER_RESULT_BYTES + 1),
                worker="root-cause",
            )

    def test_drops_unadmitted_worker_fields(self) -> None:
        payload = json.dumps({
            "status": "existing-pr",
            "bot": "root-cause",
            "pull_request": 7,
            "provider_raw_output": "must-not-propagate",
            "token": "must-not-propagate",
        })
        result = runtime.parse_worker_result(payload, worker="root-cause")
        self.assertNotIn("provider_raw_output", result)
        self.assertNotIn("token", result)
        self.assertEqual(result["pull_request"], 7)

    def test_rejects_negative_numeric_evidence(self) -> None:
        payload = json.dumps({
            "status": "pull-request-created",
            "bot": "root-cause",
            "changed_lines": -1,
        })
        with self.assertRaises(runtime.SupervisorRuntimeError):
            runtime.parse_worker_result(payload, worker="root-cause")


class EnvironmentSanitizationTests(unittest.TestCase):
    def test_worker_env_removes_process_injection_controls(
        self,
    ) -> None:
        source = {
            "PATH": "/bin",
            "PYTHONINSPECT": "1",
            "PYTHONSTARTUP": "/tmp/pwn.py",
            "PYTHONBREAKPOINT": "evil:hook",
            "BASH_ENV": "/tmp/bashrc",
            "ENV": "/tmp/shrc",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "/tmp/hooks",
            "LD_PRELOAD": "/tmp/evil.so",
            "LD_LIBRARY_PATH": "/tmp",
            "GITHUB_TOKEN": "token",
        }
        clean = runtime.sanitized_worker_env(
            source
        )
        self.assertEqual(
            clean["PATH"],
            "/bin",
        )
        self.assertEqual(
            clean["GITHUB_TOKEN"],
            "token",
        )
        for key in source:
            if key in {
                "PATH",
                "GITHUB_TOKEN",
            }:
                continue
            self.assertNotIn(
                key,
                clean,
            )


if __name__ == "__main__":
    unittest.main()
