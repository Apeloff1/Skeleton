"""Executable admission-custody contract for the checkout-free traffic dispatch job.

The test exercises the actual inline workflow shell in a clean directory. A
stubbed GitHub CLI records side-effect attempts without dispatching workflows.
It guards against reintroducing repository imports into the actions:write job.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from skeleton.automation.traffic_manager import decision_identity_fingerprint


REPOSITORY = "Apeloff1/Skeleton"
BASE_SHA = "0cbff4672f11b996a740e3b31d551fc3a760c0c0"
OBSERVED_AT = 1792816317
RECORDED_FINGERPRINT = (
    "bd47042fa75ac1d29e98c7110ea0c196238305919122187806fe51332977d974"
)


@unittest.skipUnless(shutil.which("bash"), "Requires Bash")
class TrafficDispatchWorkflowTests(unittest.TestCase):
    @staticmethod
    def _script() -> str:
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "automation-traffic-manager.yml"
        ).read_text(encoding="utf-8")
        marker = "  dispatch:\n"
        if marker not in workflow:
            raise AssertionError("Dispatch job missing from workflow")
        dispatch = workflow.split(marker, 1)[1]
        run_marker = "        run: |\n"
        if run_marker not in dispatch:
            raise AssertionError("Inline dispatch shell missing from workflow")
        return textwrap.dedent(dispatch.split(run_marker, 1)[1])

    def _execute(
        self, **overrides: str
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            bin_dir = directory / "bin"
            bin_dir.mkdir()
            stub = bin_dir / "gh"
            stub.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf '%s\\n' \"$*\" >> \"$GH_CALL_LOG\"\n"
                "case \"$1\" in\n"
                "  api) printf '%s\\n' \"$LIVE_SHA\" ;;\n"
                "  workflow) [[ \"$2\" == run ]] || exit 71 ;;\n"
                "  *) exit 72 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            script_path = directory / "dispatch.sh"
            script_path.write_text(self._script(), encoding="utf-8")
            log = directory / "github-calls"
            env = {
                **os.environ,
                "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
                # Do not permit imports from the checked-out repository.
                "PYTHONPATH": str(directory / "absent-package-root"),
                "PYTHONNOUSERSITE": "1",
                "GH_CALL_LOG": str(log),
                "LIVE_SHA": BASE_SHA,
                "GITHUB_REPOSITORY": REPOSITORY,
                "TRAFFIC_DEFAULT_BRANCH": "main",
                "TRAFFIC_ADMITTED_BASE_SHA": BASE_SHA,
                "TRAFFIC_DECISION_BASE_SHA": BASE_SHA,
                "TRAFFIC_DECISION_OBSERVED_AT": str(OBSERVED_AT),
                "TRAFFIC_DECISION_FINGERPRINT": RECORDED_FINGERPRINT,
            }
            env.update(overrides)
            completed = subprocess.run(
                ["bash", "-n", str(script_path)],
                cwd=directory,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            if completed.returncode != 0:
                self.fail(
                    f"Dispatch shell failed syntax validation: {completed.stderr}"
                )
            completed = subprocess.run(
                ["bash", str(script_path)],
                cwd=directory,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
            return completed, calls

    def test_recorded_admission_fingerprint_matches_canonical_implementation(
        self,
    ) -> None:
        self.assertEqual(
            decision_identity_fingerprint(REPOSITORY, BASE_SHA, OBSERVED_AT),
            RECORDED_FINGERPRINT,
        )

    def test_valid_admission_dispatches_one_supervisor_with_exact_sha(self) -> None:
        result, calls = self._execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                "api /repos/Apeloff1/Skeleton/git/ref/heads/main --jq .object.sha",
                "workflow run supervisor.yml --repo Apeloff1/Skeleton "
                f"--ref main -f expected_base_sha={BASE_SHA}",
            ],
        )

    def test_tampered_fingerprint_denies_before_any_api_or_dispatch(self) -> None:
        result, calls = self._execute(
            TRAFFIC_DECISION_FINGERPRINT="0" * 64
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fingerprint failed independent verification", result.stdout)
        self.assertEqual(calls, [])

    def test_observation_epoch_tamper_denies_before_api(self) -> None:
        result, calls = self._execute(
            TRAFFIC_DECISION_OBSERVED_AT=str(OBSERVED_AT + 1)
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_mismatched_decision_sha_denies_before_api(self) -> None:
        result, calls = self._execute(
            TRAFFIC_DECISION_BASE_SHA="b" * 40
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Admission identity differs", result.stdout)
        self.assertEqual(calls, [])

    def test_malformed_admitted_sha_denies_before_api(self) -> None:
        result, calls = self._execute(
            TRAFFIC_ADMITTED_BASE_SHA="not-a-commit"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_stale_default_branch_coalesces_without_dispatch(self) -> None:
        result, calls = self._execute(LIVE_SHA="b" * 40)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Admission became stale", result.stdout)
        self.assertEqual(
            calls,
            ["api /repos/Apeloff1/Skeleton/git/ref/heads/main --jq .object.sha"],
        )

    def test_invalid_live_sha_denies_without_dispatch(self) -> None:
        result, calls = self._execute(LIVE_SHA="not-a-sha")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid default-branch head", result.stdout)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("api "))


if __name__ == "__main__":
    unittest.main()
