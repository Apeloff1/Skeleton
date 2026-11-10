"""Source regression for fail-closed, stage-isolated App Foundation E2E builds."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/app-foundation-e2e.yml"
DOCKERFILE = ROOT / "frontend/Dockerfile"


class AppFoundationBuildIsolationTests(unittest.TestCase):
    def test_frontend_and_engine_builds_run_independently(self):
        flow = WORKFLOW.read_text(encoding="utf-8")
        frontend = "name: Build frontend production image"
        backend = "name: Build engine and backend images"
        self.assertEqual(flow.count(frontend), 1)
        self.assertEqual(flow.count(backend), 1)
        self.assertLess(flow.index(frontend), flow.index(backend))
        self.assertIn("docker compose -f docker-compose.yml build frontend", flow)
        self.assertIn("docker compose -f docker-compose.yml build skeleton backend", flow)
        self.assertNotIn("docker compose -f docker-compose.yml build skeleton backend frontend", flow)

        frontend_step = flow.split(frontend, 1)[1].split(backend, 1)[0]
        backend_step = flow.split(backend, 1)[1].split("- name: Start stack", 1)[0]
        for step in (frontend_step, backend_step):
            self.assertIn("timeout-minutes:", step)
            self.assertIn("BUILDKIT_PROGRESS: plain", step)
            self.assertNotIn("continue-on-error:", step)
            self.assertNotIn("|| true", step)
        self.assertIn("timeout-minutes: 60", flow)
        self.assertIn("docker compose -f docker-compose.yml up -d mongo skeleton backend frontend", flow)

    def test_frontend_export_is_noninteractive_but_requires_real_setup_artifact(self):
        source = DOCKERFILE.read_text(encoding="utf-8")
        builder = source.split("FROM deps AS builder", 1)[1].split("FROM nginx:", 1)[0]
        self.assertIn("CI=1", builder)
        self.assertIn("EXPO_NO_TELEMETRY=1", builder)
        self.assertIn("yarn export:web", builder)
        self.assertIn('echo "frontend-export-process-exited"', builder)
        self.assertIn("test -f /app/dist/setup.html || test -f /app/dist/setup/index.html", builder)
        self.assertIn('echo "frontend-setup-artifact-verified"', builder)
        self.assertLess(builder.index("yarn export:web"), builder.index("frontend-export-process-exited"))
        self.assertLess(builder.index("frontend-export-process-exited"), builder.index("frontend-setup-artifact-verified"))
        self.assertNotIn("|| true", builder)
        self.assertNotIn("EXPO_NO_METRO_LAZY", builder)


if __name__ == "__main__":
    unittest.main()
