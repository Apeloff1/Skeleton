"""Offline cross-plane route syntax, source SHA and uncertainty tests."""
from __future__ import annotations

from hashlib import sha256
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_crossplane_route_scout import (
    JeevesAPIBindingScout, _frontend_calls, _python_api)
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class CrossPlaneRouteScoutTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.inv = self.fixture.inv
        self.py = "backend/routes/feature.py"
        self.js = "frontend/screens/feature.tsx"
        self.backend = (
            "from fastapi import APIRouter\n"
            "router = APIRouter(prefix='/api/feature')\n"
            "@router.get('/status')\n"
            "def status():\n    return {}\n"
            "@router.post('/execute')\n"
            "async def execute():\n    return {}\n"
        )
        self.frontend = (
            "const a = api.get('/api/feature/status');\n"
            "const b = client.post('/api/feature/execute');\n"
            "const c = client.post('/api/feature/status');\n"
            "const d = api.get('/api/feature/missing');\n"
        )
        self.fixture.put(self.py, self.backend)
        self.fixture.put(self.js, self.frontend)
        self.inv.scan()
        self.scout = JeevesAPIBindingScout(self.inv)

    def inspect(self, **kwargs):
        return self.scout.inspect(
            backend_paths=[self.py], frontend_paths=[self.js], **kwargs)

    def test_fastapi_router_literal_and_http_methods_match(self):
        result = self.inspect(expected_snapshot=self.inv._digest)
        self.assertEqual(result["backend_declared_count"], 2)
        self.assertEqual(result["frontend_literal_count"], 4)
        self.assertEqual(result["literal_match_count"], 2)
        self.assertEqual(result["literal_mismatch_count"], 2)
        self.assertEqual({x["reason"] for x in result["unmatched_literal_calls"]},
                         {"literal_http_method_mismatch",
                          "no_literal_backend_declaration"})
        self.assertTrue(result["dynamic_routes_not_claimed"])
        self.assertFalse(result["application_binding_complete"])
        self.assertTrue(result["no_backend_or_frontend_code_executed"])
        self.assertEqual(result, self.inspect())

    def test_fetch_options_do_not_create_false_get_match(self):
        calls, unknown = _frontend_calls("frontend/x.ts",
                "fetch('/api/feature/status', {method: 'POST'})")
        self.assertEqual(unknown, 0)
        self.assertEqual(calls[0]["method"], "UNKNOWN_FETCH_OPTIONS")
        self.fixture.put(self.js,
                         "fetch('/api/feature/status', {method:'POST'})")
        self.inv.scan()
        result = self.inspect()
        self.assertEqual(result["literal_match_count"], 0)
        self.assertEqual(len(result["indeterminate_calls"]), 1)

    def test_dynamic_route_template_is_not_accepted_as_literal(self):
        self.fixture.put(self.js,
                         "client.get('/api/feature/${userId}')\n"
                         "client.get('/api/feature/status?debug=yes')\n")
        self.inv.scan()
        result = self.inspect()
        self.assertEqual(result["frontend_literal_count"], 0)
        self.assertEqual(result["unresolved_or_syntax_errors"], 2)

    def test_backend_dynamic_route_is_not_declared_as_static(self):
        rows, status = _python_api(self.py,
            "from fastapi import APIRouter\n"
            "router=APIRouter(prefix='/api')\n"
            "@router.get(dynamic_path)\n"
            "def x(): return 1\n")
        self.assertEqual(rows, [])
        self.assertEqual(status, "parsed")
        rows, status = _python_api(self.py, "@router.get('a'")
        self.assertEqual(rows, [])
        self.assertEqual(status, "python_parse_error")

    def test_unreviewed_js_script_must_not_run(self):
        sentinel = self.fixture.root / "executed"
        self.fixture.put(self.js,
            "require('fs').writeFileSync('executed', 'BAD')\n"
            "client.get('/api/feature/status')\n")
        self.inv.scan()
        result = self.inspect()
        self.assertEqual(result["literal_match_count"], 1)
        self.assertFalse(sentinel.exists())

    def test_source_identity_and_selected_path_set_fail_closed(self):
        old = self.inspect()
        expected = {row["path"]: row["sha256"]
                    for row in old["source_receipts"]}
        self.assertEqual(self.inspect(expected_sources=expected), old)
        self.fixture.put(self.js, self.frontend.replace("missing", "missinx"))
        self.inv.scan()
        with self.assertRaises(JeevesAppwideError):
            self.inspect(expected_sources=expected)
        # The inventory cursor is metadata-based: equal-length edits
        # require the stronger selected source SHA fence above.
        self.fixture.put(self.js, self.frontend + "// additional source\n")
        self.inv.scan()
        with self.assertRaises(JeevesAppwideError):
            self.inspect(expected_snapshot=old["inventory_snapshot"])

    def test_private_missing_duplicate_oversize_and_wrong_language_rejected(self):
        for options in (
            {"backend_paths": [self.py], "frontend_paths": []},
            {"backend_paths": [self.py], "frontend_paths": [self.py]},
            {"backend_paths": ["machine/.env"], "frontend_paths": [self.js]},
            {"backend_paths": ["backend/missing.py"], "frontend_paths": [self.js]},
            {"backend_paths": [self.js], "frontend_paths": [self.py]},
            {"backend_paths": [True], "frontend_paths": [self.js]},
        ):
            with self.subTest(options=options), self.assertRaises(JeevesAppwideError):
                self.scout.inspect(**options)

    def test_jeeves_action_remains_read_only_and_scoped(self):
        result = JeevesAppwideRuntime(self.inv).invoke(
            "ai.api.bindings", {
                "backend_paths": [self.py],
                "frontend_paths": [self.js]})
        self.assertTrue(result["read_only_or_review_only"])
        self.assertEqual(result["result"]["literal_match_count"], 2)
        self.assertFalse(result["result"]["application_binding_complete"])


if __name__ == "__main__":
    unittest.main()
