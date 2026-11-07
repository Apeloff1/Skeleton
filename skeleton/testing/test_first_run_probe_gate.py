"""First-run service probe regression tests; no real-device claims."""
import unittest

from skeleton.install.first_run_probe_gate import (
    FirstRunGateError, ServiceState, check_first_run,
)
from skeleton.install.wizard_10000x import FirstRunWizard10000x

NAMES = ("backend", "local_ai", "jeeves", "builder", "game_store")


class FirstRunProbeGateTests(unittest.TestCase):
    def test_healthy_pipeline(self):
        result = check_first_run({name: lambda: True for name in NAMES})
        self.assertTrue(result.setup_accessible)
        self.assertTrue(result.guarded_ai_available)
        self.assertTrue(result.playable_enabled)
        self.assertFalse(result.as_dict()["release_ready"])
        self.assertFalse(result.as_dict()["device_qualified"])
        self.assertEqual([s.name for s in result.services], list(NAMES))

    def test_backend_unavailable_keeps_setup_and_blocks_downstream(self):
        called = []
        def backend():
            called.append("backend")
            return False
        def forbidden():
            called.append("downstream")
            raise AssertionError("should not run")
        result = check_first_run({"backend": backend, "local_ai": forbidden})
        self.assertEqual(called, ["backend"])
        self.assertTrue(result.setup_accessible)
        self.assertFalse(result.guarded_ai_available)
        self.assertFalse(result.playable_enabled)
        self.assertEqual(result.services[1].reason, "dependency-unavailable")

    def test_ai_unavailable_disables_playable_but_not_setup(self):
        probes = {name: lambda: True for name in NAMES}
        probes["local_ai"] = lambda: False
        result = check_first_run(probes)
        self.assertEqual(result.services[0].state, ServiceState.READY)
        self.assertEqual(result.services[1].state, ServiceState.UNAVAILABLE)
        self.assertFalse(result.guarded_ai_available)
        self.assertFalse(result.playable_enabled)

    def test_missing_probe_fails_closed(self):
        result = check_first_run({})
        self.assertEqual(result.services[0].reason, "probe-missing")
        self.assertEqual(len(result.services), len(NAMES))

    def test_truthy_non_boolean_is_not_success(self):
        result = check_first_run({"backend": lambda: 1})
        self.assertFalse(result.guarded_ai_available)

    def test_exception_does_not_leak_secret(self):
        def broken():
            raise RuntimeError("token=secret-value")
        result = check_first_run({"backend": broken})
        self.assertEqual(result.services[0].state, ServiceState.FAILED)
        self.assertNotIn("secret-value", str(result.as_dict()))

    def test_unknown_probe_rejected(self):
        with self.assertRaises(FirstRunGateError):
            check_first_run({"release_ready": lambda: True})

    def test_wizard_integration(self):
        wizard = FirstRunWizard10000x()
        result = wizard.check_services({name: lambda: True for name in NAMES})
        self.assertTrue(result.playable_enabled)
        self.assertEqual(len(result.services), 5)


if __name__ == "__main__":
    unittest.main()
