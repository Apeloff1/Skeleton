"""Regression for first-install readiness identity; no provider is invoked."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from skeleton.app import first_install as module


class FirstInstallProviderIdentityTests(unittest.TestCase):
    def report(self, active, configured=True, available=True):
        service = lambda name: SimpleNamespace(public_url="http://127.0.0.1:8001")
        manifest = SimpleNamespace(service=service)
        host = SimpleNamespace(ready=True, checks=[])
        provider_status = {
            "engine": "skeleton-engine",
            "providers": ["local", "openai"],
            "llm_available": available,
            "availability_observed": True,
            "active": active,
        }
        env = {"AI_PROVIDER": "local", "AI_LOCAL_MODEL_PATH": "/models/owned.gguf"} if configured else {"AI_PROVIDER": "local"}
        with (
            patch.object(module, "inspect_host", return_value=host),
            patch.object(module, "preflight", return_value=[]),
            patch.object(module, "checks_ok", return_value=True),
            patch.object(module, "_runtime_env", return_value=env),
            patch.object(module, "load_manifest", return_value=manifest),
            patch.object(module, "runtime_manifest", return_value=manifest),
            patch.object(module, "critical_backend_route_report", return_value={"observed": True, "ready": True, "missing": []}),
            patch.object(module, "_bounded_json", return_value=provider_status),
            patch("skeleton.app.health.probe_application", return_value=[]),
            patch("skeleton.app.health.probes_ok", return_value=True),
        ):
            return module.first_install_report(Path("."), live=True)

    def test_matching_configured_provider_can_be_observed(self):
        ai = self.report("local")["ai"]
        self.assertTrue(ai["observed"])
        self.assertTrue(ai["available"])

    def test_other_active_provider_cannot_certify_local(self):
        ai = self.report("openai")["ai"]
        self.assertFalse(ai["observed"])
        self.assertIsNone(ai["available"])

    def test_missing_active_identity_fails_closed(self):
        ai = self.report(None)["ai"]
        self.assertFalse(ai["observed"])
        self.assertIsNone(ai["available"])

    def test_unconfigured_local_cannot_be_certified_by_remote_status(self):
        ai = self.report("local", configured=False)["ai"]
        self.assertFalse(ai["observed"])
        self.assertIsNone(ai["available"])

    def test_matching_negative_status_remains_observed(self):
        ai = self.report("local", available=False)["ai"]
        self.assertTrue(ai["observed"])
        self.assertFalse(ai["available"])


if __name__ == "__main__":
    unittest.main()
