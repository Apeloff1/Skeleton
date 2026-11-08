"""CLI acceptance: approved source, bounded receipts, fail-closed error output."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from unittest.mock import patch

from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, propose
from skeleton.jeeves.worlds.world_session_cli import run


class SessionCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.world = propose(world_id="cli_world", premise="An ancient gate opens.",
                             protagonist="Mira", region="Vale", goal="Reach the summit")
        self.store = WorldStore(self.temp.name)
        self.store.publish(self.world, create=True)

    def invoke(self, action, raw):
        out, err = io.BytesIO(), io.StringIO()
        code = run(["--root", self.temp.name, "--world-id", "cli_world", action],
                   input_stream=io.BytesIO(raw), output_stream=out, error_stream=err)
        return code, out.getvalue(), err.getvalue()

    def test_export_restore_round_trip(self):
        code, receipt, err = self.invoke("export", b'["pursue_goal"]')
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(receipt)["scene"], "resolution")
        code, restored, err = self.invoke("restore", receipt)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(restored), json.loads(receipt))

    def test_rejects_tampered_receipt_without_output(self):
        _, receipt, _ = self.invoke("export", b'["pursue_goal"]')
        data = json.loads(receipt)
        data["scene"] = "opening"
        code, out, err = self.invoke("restore", json.dumps(data).encode())
        self.assertEqual(code, 2)
        self.assertEqual(out, b"")
        self.assertIn("session_state_mismatch", err)

    def test_rejects_unbounded_input_before_parsing(self):
        code, out, err = self.invoke("restore", b" " * 65537)
        self.assertEqual(code, 2)
        self.assertEqual(out, b"")
        self.assertIn("session_too_large", err)

    def test_rejects_text_stream_without_traceback(self):
        out, err = io.BytesIO(), io.StringIO()
        code = run(["--root", self.temp.name, "--world-id", "cli_world", "export"],
                   input_stream=io.StringIO('["pursue_goal"]'),
                   output_stream=out, error_stream=err)
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), b"")
        self.assertEqual(json.loads(err.getvalue()), {"error": "invalid_session_payload"})

    def test_rejects_nonbytes_stream_result(self):
        class InvalidStream:
            def read(self, limit):
                self.limit = limit
                return None

        stream = InvalidStream()
        out, err = io.BytesIO(), io.StringIO()
        code = run(["--root", self.temp.name, "--world-id", "cli_world", "restore"],
                   input_stream=stream, output_stream=out, error_stream=err)
        self.assertEqual(stream.limit, 65537)
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), b"")
        self.assertEqual(json.loads(err.getvalue()), {"error": "invalid_session_payload"})

    def test_rejects_unknown_world(self):
        out, err = io.BytesIO(), io.StringIO()
        code = run(["--root", self.temp.name, "--world-id", "unknown", "export"],
                   input_stream=io.BytesIO(b"[]"), output_stream=out, error_stream=err)
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), b"")
        self.assertIn("not_found", err)

    def test_rejects_invalid_trace_and_duplicate_keys(self):
        for raw in (b'{"trace":[]}', b'["no_such_choice"]', b'["pursue_goal","pursue_goal"]'):
            with self.subTest(raw=raw):
                code, out, err = self.invoke("export", raw)
                self.assertEqual(code, 2)
                self.assertEqual(out, b"")
                self.assertTrue(err)

    def test_stale_source_receipt_rejected(self):
        _, receipt, _ = self.invoke("export", b'[]')
        revised = json.loads(json.dumps(self.world))
        revised["prompt"] = "A different approved opening."
        from skeleton.jeeves.worlds.world_canon import digest
        self.store.publish(revised, expected_digest=digest(self.world))
        code, out, err = self.invoke("restore", receipt)
        self.assertEqual(code, 2)
        self.assertEqual(out, b"")
        self.assertIn("session_stale_source", err)


if __name__ == "__main__":
    unittest.main()
