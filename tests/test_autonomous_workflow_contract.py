from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AutonomousWorkflowContractTests(unittest.TestCase):
    def _workflow(self, name: str) -> str:
        return (ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8"
        )

    def test_scheduled_admission_dispatches_exact_supervisor_sha(self) -> None:
        traffic = self._workflow("automation-traffic-manager.yml")

        self.assertIn('schedule:', traffic)
        self.assertIn('cron: "*/10 * * * *"', traffic)
        self.assertIn("TRAFFIC_ADMITTED_BASE_SHA", traffic)
        self.assertIn("TRAFFIC_DECISION_BASE_SHA", traffic)
        self.assertIn('test "$TRAFFIC_ADMITTED_BASE_SHA" = "$TRAFFIC_DECISION_BASE_SHA"', traffic)
        self.assertIn("live_sha=$(gh api", traffic)
        self.assertIn('if [[ "$live_sha" != "$TRAFFIC_ADMITTED_BASE_SHA" ]]; then', traffic)
        self.assertIn("gh workflow run supervisor.yml", traffic)
        self.assertIn('-f "expected_base_sha=$TRAFFIC_ADMITTED_BASE_SHA"', traffic)

    def test_supervisor_rejects_stale_caller_and_seals_secretary_handoff(self) -> None:
        supervisor = self._workflow("supervisor.yml")

        self.assertIn("workflow_call:", supervisor)
        self.assertIn("workflow_dispatch:", supervisor)
        self.assertIn("expected_base_sha:", supervisor)
        self.assertIn('test "$SUPERVISOR_BASE_SHA" = "$SUPERVISOR_CALLER_BASE_SHA"', supervisor)
        self.assertIn("delegation_b64:", supervisor)
        self.assertIn("snapshot_fingerprint:", supervisor)
        self.assertIn("execution_fingerprint:", supervisor)
        self.assertIn("SUPERVISOR_DELEGATION_B64:", supervisor)
        self.assertIn("python -m skeleton.automation.secretary", supervisor)

    def test_secretary_is_the_only_worker_dispatch_boundary(self) -> None:
        secretary = (
            ROOT / ".github" / "workflows" / "supervisor.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("name: Admit custody and dispatch isolated workers", secretary)
        self.assertIn("permissions:", secretary)
        self.assertIn("contents: write", secretary)
        self.assertIn("pull-requests: write", secretary)
        self.assertIn("--delegation-b64", secretary)
        self.assertNotIn("specialist_bots", secretary)

    def test_workflow_chain_has_no_direct_model_to_worker_dispatch(self) -> None:
        traffic = self._workflow("automation-traffic-manager.yml")
        supervisor = self._workflow("supervisor.yml")

        for workflow in (traffic, supervisor):
            self.assertNotIn("MODEL_API_KEY", workflow.split("permissions:")[0])
            self.assertNotIn("python -m skeleton.automation.specialist_bots", workflow)

        self.assertIn("python -m skeleton.automation.supervisor", supervisor)
        self.assertIn("python -m skeleton.automation.secretary", supervisor)


if __name__ == "__main__":
    unittest.main()
