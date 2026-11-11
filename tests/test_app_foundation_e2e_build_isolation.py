"""Source regression for fail-closed, stage-isolated App Foundation E2E builds."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/app-foundation-e2e.yml"
DOCKERFILE = ROOT / "frontend/Dockerfile"
GUARD = ROOT / "frontend/scripts/guarded-expo-export.cjs"
GUARD_TEST = ROOT / "frontend/scripts/test-guarded-expo-export.cjs"


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

    def test_supervisor_is_bounded_and_docker_requires_real_export(self):
        source = DOCKERFILE.read_text(encoding="utf-8")
        builder = source.split("FROM deps AS builder", 1)[1].split("FROM nginx:", 1)[0]
        self.assertIn("node --test scripts/test-guarded-expo-export.cjs", builder)
        self.assertIn("node scripts/guarded-expo-export.cjs", builder)
        self.assertIn("(test -f /app/dist/setup.html || test -f /app/dist/setup/index.html)", builder)
        self.assertNotIn("yarn export:web", builder)
        self.assertNotIn("|| true", builder)
        guard = GUARD.read_text(encoding="utf-8")
        tests = GUARD_TEST.read_text(encoding="utf-8")
        self.assertIn("CI: '1'", guard)
        self.assertIn("EXPO_NO_TELEMETRY: '1'", guard)
        self.assertIn("stale dist is not qualifying evidence", guard)
        self.assertIn("if (code !== 0 || signal)", guard)
        self.assertIn("export hard deadline exceeded", guard)
        self.assertIn("export output is not stable", guard)
        self.assertIn("stalled exporter requires stable output", tests)
        self.assertIn("a nonzero exporter exit cannot be masked", tests)


if __name__ == "__main__":
    unittest.main()
