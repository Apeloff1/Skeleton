"""Offline handoff contract and tamper rejection across reviewed-world custody."""
from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest

from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose,
)
from skeleton.jeeves.worlds.world_handoff_cli import (
    HANDOFF_SCHEMA, build_handoff, run, verify_handoff,
)


class PortableHandoffTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = directory.name
        self.world = propose(
            world_id="handoff_world", premise="A new path beyond the ridge.",
            protagonist="Mira", region="Vale", goal="Find the summit",
        )
        self.store = WorldStore(self.root)
        self.approved = self.store.publish(self.world, create=True)

    def test_deterministic_build_and_verify(self):
        first = build_handoff(self.world, self.approved)
        second = build_handoff(self.world, self.approved)
        self.assertEqual(canonical(first), canonical(second))
        self.assertEqual(first["schema"], HANDOFF_SCHEMA)
        self.assertEqual(first["world_id"], "handoff_world")
        self.assertEqual(verify_handoff(canonical(first))["source_digest"], self.approved)
        html = base64.b64decode(first["html_base64"], validate=True)
        self.assertIn(b"Content-Security-Policy", html)
        self.assertIn(b"world-data", html)
        self.assertEqual(len(html), first["html_bytes"])

    def test_approval_is_required_and_exact(self):
        for wrong in ("", "X" * 64, "0" * 64, None, 3):
            with self.subTest(wrong=wrong):
                with self.assertRaises(CanonError):
                    build_handoff(self.world, wrong)

    def test_rejects_mutated_payload_and_metadata(self):
        valid = build_handoff(self.world, self.approved)
        mutations = [
            ("html_sha256", "0" * 64),
            ("html_bytes", valid["html_bytes"] + 1),
            ("world_id", "other_world"),
            ("source_digest", "0" * 64),
            ("schema", "unknown"),
            ("html_base64", "not base64!"),
        ]
        for key, value in mutations:
            with self.subTest(key=key):
                mutated = dict(valid)
                mutated[key] = value
                with self.assertRaises(CanonError):
                    verify_handoff(canonical(mutated))

    def test_rejects_manifest_proof_tampering(self):
        valid = build_handoff(self.world, self.approved)
        mutated = json.loads(canonical(valid))
        mutated["manifest"]["proof"]["states_explored"] += 1
        with self.assertRaises(CanonError):
            verify_handoff(canonical(mutated))

    def test_build_cli_does_not_modify_approved_world(self):
        out, err = io.BytesIO(), io.StringIO()
        status = run(["--root", self.root, "--world-id", "handoff_world",
                      "--approved-digest", self.approved, "build"],
                     output_stream=out, error_stream=err)
        self.assertEqual((status, err.getvalue()), (0, ""))
        receipt = json.loads(out.getvalue())
        self.assertEqual(receipt["source_digest"], self.approved)
        self.assertEqual(digest(self.store.read("handoff_world")), self.approved)

    def test_verify_cli_accepts_valid_handoff(self):
        raw = canonical(build_handoff(self.world, self.approved))
        out, err = io.BytesIO(), io.StringIO()
        status = run(["verify"], input_stream=io.BytesIO(raw),
                     output_stream=out, error_stream=err)
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out.getvalue())["world_id"], "handoff_world")

    def test_build_cli_rejects_missing_or_stale_approval(self):
        for approval in (None, "0" * 64):
            args = ["--root", self.root, "--world-id", "handoff_world"]
            if approval is not None:
                args += ["--approved-digest", approval]
            out, err = io.BytesIO(), io.StringIO()
            status = run(args + ["build"], output_stream=out, error_stream=err)
            self.assertEqual(status, 2)
            self.assertEqual(out.getvalue(), b"")
            self.assertIn(json.loads(err.getvalue())["error"],
                          {"approval_required", "stale_source"})

    def test_verify_cli_rejects_text_stream(self):
        out, err = io.BytesIO(), io.StringIO()
        status = run(["verify"], input_stream=io.StringIO("{}"),
                     output_stream=out, error_stream=err)
        self.assertEqual(status, 2)
        self.assertEqual(out.getvalue(), b"")
        self.assertEqual(json.loads(err.getvalue())["error"], "invalid_handoff")

    def test_verify_rejects_duplicate_json_keys(self):
        with self.assertRaises(CanonError):
            verify_handoff(b'{"schema":"a","schema":"b"}')


if __name__ == "__main__":
    unittest.main()
