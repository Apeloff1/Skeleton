"""Tests for the web cockpit."""

from __future__ import annotations

import unittest


class TestCockpit(unittest.TestCase):
    def test_cockpit_html_is_self_contained(self):
        from skeleton.api.cockpit import COCKPIT_HTML

        # No external resources — must work offline
        self.assertNotIn("http://", COCKPIT_HTML.replace("http://localhost", ""))
        self.assertNotIn("cdn", COCKPIT_HTML.lower())
        self.assertNotIn("<script src", COCKPIT_HTML)
        self.assertNotIn("<link", COCKPIT_HTML)

    def test_cockpit_polls_api_surfaces(self):
        from skeleton.api.cockpit import COCKPIT_HTML

        for surface in ("/api/v1/health", "/api/v1/genesis", "/api/v1/genesis/handles", "/cortex/status"):
            self.assertIn(surface, COCKPIT_HTML)

    def test_cockpit_renders_key_panels(self):
        from skeleton.api.cockpit import COCKPIT_HTML

        for panel in ("System Health", "Genesis Boot", "Cortex", "Jeeves", "Handles by Phase"):
            self.assertIn(panel, COCKPIT_HTML)

    def test_app_factory_mounts_cockpit(self):
        from pathlib import Path
        # The create_app source must reference the cockpit router
        import skeleton.api.server as server
        import inspect
        src = inspect.getsource(server.create_app)
        self.assertIn("cockpit", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
