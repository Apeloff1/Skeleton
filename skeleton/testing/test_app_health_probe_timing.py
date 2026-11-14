"""Fail-closed timing validation for consumer setup and health probes."""
import math
import unittest
from unittest.mock import patch

from skeleton.app.health import probe_http, probe_local_setup, wait_for_application


class InvalidProbeTimingTests(unittest.TestCase):
    def test_http_rejects_malformed_timeout_before_network(self):
        with patch("skeleton.app.health._open_direct_health", side_effect=AssertionError("network")):
            for invalid in (True, False, None, "2", float("nan"), math.inf, -1, 0, 31):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    probe_http("backend", "http://127.0.0.1:8000/health", timeout=invalid)

    def test_setup_rejects_malformed_timeout_before_network(self):
        from types import SimpleNamespace
        service = SimpleNamespace(name="setup", public_url="http://127.0.0.1:3000", health_path="/setup")
        for invalid in (True, False, None, "2", math.nan, math.inf, -1, 0, 11):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                probe_local_setup(service, timeout=invalid)

    def test_wait_rejects_bad_timing_before_manifest_or_network(self):
        with patch("skeleton.app.health.load_manifest", side_effect=AssertionError("manifest")):
            for invalid in (True, False, None, "2", math.nan, math.inf, -1, 0, 31):
                with self.subTest(timeout=invalid), self.assertRaises(ValueError):
                    wait_for_application(timeout=invalid)
            for invalid in (True, False, None, "2", math.nan, math.inf, -1, 31):
                with self.subTest(delay=invalid), self.assertRaises(ValueError):
                    wait_for_application(delay=invalid)

    def test_valid_boundaries_do_not_raise_timing_validation(self):
        with patch("skeleton.app.health._open_direct_health", side_effect=OSError("offline")):
            self.assertFalse(probe_http("backend", "http://127.0.0.1:8000/health", timeout=0.01).ok)
            self.assertFalse(probe_http("backend", "http://127.0.0.1:8000/health", timeout=30.0).ok)


if __name__ == "__main__":
    unittest.main()
