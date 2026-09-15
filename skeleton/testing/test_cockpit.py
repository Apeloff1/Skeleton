"""Tests for the web cockpit."""

from __future__ import annotations

import inspect
import unittest


class TestCockpit(unittest.TestCase):
    def test_cockpit_html_is_self_contained(self):
        from skeleton.api.cockpit import COCKPIT_HTML

        # No external resources — must work offline.
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

    def test_cockpit_uses_text_nodes_for_remote_data(self):
        from skeleton.api.cockpit import COCKPIT_HTML

        # API-provided topic, phase and provider names must never be injected as HTML.
        self.assertNotIn("innerHTML", COCKPIT_HTML)
        self.assertIn("document.createElement", COCKPIT_HTML)
        self.assertIn("textContent", COCKPIT_HTML)
        self.assertIn("replaceChildren", COCKPIT_HTML)

    def test_cockpit_bounds_and_serializes_polling(self):
        from skeleton.api.cockpit import COCKPIT_HTML

        # A hung endpoint must not block the cockpit forever and refreshes must not pile up.
        self.assertIn("AbortController", COCKPIT_HTML)
        self.assertIn("REQUEST_TIMEOUT_MS", COCKPIT_HTML)
        self.assertIn("if (refreshing) return", COCKPIT_HTML)
        self.assertIn("visibilitychange", COCKPIT_HTML)
        self.assertNotIn("setInterval", COCKPIT_HTML)

    def test_cockpit_exposes_connection_state(self):
        from skeleton.api.cockpit import COCKPIT_HTML

        for state in ("CONNECTING", "LIVE", "DEGRADED", "OFFLINE"):
            self.assertIn(state, COCKPIT_HTML)

    def test_app_factory_mounts_cockpit(self):
        # The create_app source must reference the cockpit router.
        import skeleton.api.server as server

        src = inspect.getsource(server.create_app)
        self.assertIn("cockpit", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
