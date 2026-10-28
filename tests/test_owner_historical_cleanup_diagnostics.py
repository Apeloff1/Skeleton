"""Credential-free diagnostics tests for owner-authorized historical run cleanup."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "owner_historical_actions_cleanup.py"


def isolated_error_parser():
    """Test the helper without invoking owner-only workflow run side effects."""
    source = SOURCE.read_text(encoding="utf-8")
    syntax = ast.parse(source)
    function = next(
        node for node in syntax.body
        if isinstance(node, ast.FunctionDef) and node.name == "provider_error_evidence"
    )
    namespace = {"json": json}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["provider_error_evidence"]


class OwnerCleanupDiagnosticsTests(unittest.TestCase):
    def test_structured_403_message_and_request_id_are_preserved(self):
        parser = isolated_error_parser()
        result = parser(
            b'{"message":"Could not delete the workflow run","status":"403"}',
            "9AED:341381:E06F73:142EBDD:6ADCEF97",
        )
        self.assertEqual(result["message"], "Could not delete the workflow run")
        self.assertEqual(
            result["request_id"], "9AED:341381:E06F73:142EBDD:6ADCEF97"
        )

    def test_non_json_error_never_leaks_html_or_credentials(self):
        parser = isolated_error_parser()
        result = parser(b"<html>Bearer secret</html>", "abc\nunsafe=token")
        self.assertEqual(result["message"], "unavailable; GitHub returned no JSON message")
        self.assertEqual(result["request_id"], "abcunsafetoken")

    def test_provider_message_is_bounded(self):
        parser = isolated_error_parser()
        result = parser(json.dumps({"message": "x" * 3000}).encode(), "Y" * 300)
        self.assertEqual(len(result["message"]), 240)
        self.assertEqual(len(result["request_id"]), 96)

    def test_http_errors_are_single_attempt_mutations(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('attempts = 3 if method == "GET" else 1', source)
        self.assertIn("confirmed_deleted", source)
        self.assertIn("provider_refusal", source)
        self.assertIn('verify_status != 404', source)
        self.assertIn('status, detail = request("DELETE"', source)


if __name__ == "__main__":
    unittest.main()
