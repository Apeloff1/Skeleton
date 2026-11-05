"""Mixed original project work on one native GGUF / SQLite source turn.

The same local model can propose NEW source files and EXISTING edits in one
strict response. Every output is still reviewed as untrusted data by the
independent original-file and new-file guards before any private Git patch
review. Synthetic native replies are not device/model/release proof.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_project_work as mixed,
    desktop_project_context as selected_source,
    desktop_source_repair as repair,
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
    desktop_patch_bundle as patch,
)

MODEL = "a" * 64
SESSION = "s_source_work_owner"


def mixed_payload(*, old_sha, original="src/core.py", modified=None,
                  new_path="src/extra.py", new_text="def extra(): return 2\n"):
    if modified is None:
        modified = "def core():\n    return 2\n"
    return json.dumps({
        "schema": mixed.SCHEMA,
        "new_files": [
            {"path": new_path, "content": new_text},
        ],
        "existing_edits": [
            {
                "path": original,
                "expected_sha256": old_sha,
                "replacement": modified,
            },
        ],
    }, ensure_ascii=False, sort_keys=True)


class StrictMixedPackageTests(unittest.TestCase):
    def test_raw_original_model_payload_is_strict_and_sha_bound(self):
        old_sha = "a"*64
        raw = mixed_payload(old_sha=old_sha)
        parsed = mixed.parse_mixed_work(raw)
        self.assertEqual(len(parsed.new_files), 1)
        self.assertEqual(len(parsed.existing_edits), 1)
        self.assertEqual(parsed.existing_edits[0].expected_sha256, old_sha)
        self.assertEqual(parsed.new_files[0].path, "src/extra.py")
        self.assertEqual(parsed.source_bytes, sum(
            file.bytes for file in (*parsed.new_files, *parsed.existing_edits)
        ))
        self.assertEqual(parsed.package_sha256,
                         sha256(json.dumps(parsed.as_canonical(),
                             ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode()).hexdigest())
        public = parsed.to_public()
        self.assertEqual(public["new_file_count"], 1)
        self.assertEqual(public["existing_edit_count"], 1)
        self.assertTrue(public["operator_review_required"])
        self.assertFalse(public["model_file_write_authorized"])
        self.assertFalse(public["project_files_modified"])
        self.assertFalse(public["git_commands_executed"])
        self.assertNotIn("def extra", repr(public))
        self.assertNotIn("def core", repr(public))
        self.assertIn(workspace.SCHEMA, parsed.new_plan())
        self.assertIn(edits.SCHEMA, parsed.edits_plan())

    def test_malformed_or_escalating_native_schema_never_becomes_approved(self):
        base = json.loads(mixed_payload(old_sha="a"*64))
        variants = [
            {},
            {"schema": mixed.SCHEMA, "new_files": [], "existing_edits": []},
            dict(base, grant_shell=True),
            dict(base, schema="jeeves.workspace.unknown"),
            dict(base, new_files=[dict(base["new_files"][0], executable=True)]),
            dict(base, existing_edits=[dict(base["existing_edits"][0], overwrite=True)]),
            dict(base, existing_edits=[dict(base["existing_edits"][0], expected_sha256="x")]),
            dict(base, new_files=[{"path": "src/core.py", "content": "x=1\n"}]),
            dict(base, new_files=[{"path": "../esc.py", "content": "x=1\n"}]),
            dict(base, new_files=[{"path": ".github/workflows/push.yml", "content": "run: id"}]),
            dict(base, new_files=[{"path": "src/extra.py", "content": "\x00binary"}]),
            dict(base, new_files=[{"path": "src/extra.py", "content": "x"*20000}]),
            dict(base, new_files=[{"path": "src/extra.py", "content": "x=1\n"}]*17),
        ]
        for value in variants:
            with self.subTest(value=repr(value)[:120]), self.assertRaises(mixed.MixedWorkHold):
                mixed.parse_mixed_work(json.dumps(value))

    def test_duplicate_field_nonfinite_json_and_oversized_native_json_fail(self):
        for value in (
            '{"schema":"jeeves.workspace.mixed-project-work.v1","new_files":[],"new_files":[],"existing_edits":[]}',
            '{"schema":"jeeves.workspace.mixed-project-work.v1","new_files":[],"existing_edits":NaN}',
            "x"*32769, "{}", None, True,
        ):
            with self.subTest(value=str(value)[:50]), self.assertRaises(mixed.MixedWorkHold):
                mixed.parse_mixed_work(value)


class NativeContextWorker:
    """Test-only native socket-free SQLite receipt surface; never a model."""

    def __init__(self, replies, on_call=None):
        self.connected = True
        self.session_id = SESSION
        self.model_sha256 = MODEL
        self.replies = list(replies)
        self.on_call = on_call
        self._gate = threading.RLock()
        self._owner = False
        self.calls = []

    @contextmanager
    def exclusive_batch(self, _manifest_sha256):
        self._gate.acquire()
        self._owner = True
        try:
            yield
        finally:
            self._owner = False
            self._gate.release()

    def request(self, op, **fields):
        if not self._owner or op != "turn" or fields.get("context") is not False:
            raise AssertionError("synthetic native source escaped its exclusive custody")
        self.calls.append(dict(fields))
        if self.on_call:
            self.on_call(len(self.calls))
        reply = self.replies.pop(0)
        return {
            "status": "committed-native-chat-turn",
            "request_id": fields["request_id"],
            "turn": {
                "request_id": fields["request_id"],
                "session_id": SESSION,
                "model_sha256": MODEL,
                "answer": reply,
                "output_sha256": sha256(reply.encode("utf-8")).hexdigest(),
                "authoritative_commit": True,
                "replayed": False,
                "device_qualified": False,
                "release_certified": False,
            },
        }


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Original source work needs pinned POSIX/WSL2 project descriptors",
)
class MixedNativeProjectWorkTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="jeeves-mixed-native-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "project"
        self.root.mkdir(mode=0o700)
        (self.root / "src").mkdir(mode=0o700)
        self.existing = self.root / "src/core.py"
        self.original = "def core():\n    return 1\n"
        self.existing.write_text(self.original, encoding="utf-8")
        self.expected_sha = sha256(self.original.encode()).hexdigest()

        def test_root(value):
            return os.open(
                value, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        for module in (workspace, edits, patch, selected_source):
            changed = mock.patch.object(module, "_open_root", side_effect=test_root)
            changed.start()
            self.addCleanup(changed.stop)

    def _request(self, attempts=2):
        context = selected_source.snapshot_project_context(
            self.root, "src/core.py",
        )
        return repair.SourceRepairRequest(
            root=str(self.root), goal="Create supporting module and update core()",
            format="mixed-work", maximum_attempts=attempts,
            source_context=context,
        )

    def _answer(self, **options):
        return mixed_payload(old_sha=self.expected_sha, **options)

    def test_one_authoritative_native_turn_builds_new_and_edits_together(self):
        worker = NativeContextWorker([self._answer()])
        runner = repair.NativeSourceRepairRunner(
            worker, self._request(), approved=True,
        )
        with (
            mock.patch("subprocess.run") as external,
            mock.patch("subprocess.Popen") as process,
        ):
            result = runner.execute()
        self.assertEqual(result.status, "review-required")
        self.assertEqual(len(worker.calls), 1)
        self.assertEqual(result.attempts[0].source_result, "review-required")
        self.assertEqual(len(result.candidate.entries), 2)
        self.assertEqual(result.qualification.status, "parse-clean")
        self.assertEqual([f.kind for f in result.candidate.entries], ["edit", "new"])
        self.assertIn(mixed.SCHEMA, worker.calls[0]["prompt"])
        self.assertIn(self.expected_sha, worker.calls[0]["prompt"])
        self.assertNotIn(self.original, result.public_receipt().__repr__())
        self.assertEqual(
            result.public_receipt()["operator_source_context_sha256"],
            runner.request.source_context.manifest_sha256,
        )
        self.assertFalse(result.public_receipt()["project_files_modified"])
        self.assertFalse((self.root / "src/extra.py").exists())
        self.assertEqual(self.existing.read_text(), self.original)
        external.assert_not_called()
        process.assert_not_called()

    def test_bad_old_digest_receives_finite_repair_new_distinct_request(self):
        wrong = mixed_payload(old_sha="f"*64)
        valid = self._answer()
        worker = NativeContextWorker([wrong, valid])
        result = repair.NativeSourceRepairRunner(
            worker, self._request(), approved=True,
        ).execute()
        self.assertEqual(result.status, "review-required")
        self.assertEqual(len(worker.calls), 2)
        self.assertNotEqual(
            worker.calls[0]["request_id"], worker.calls[1]["request_id"],
        )
        self.assertIn("proposal-schema-or-source-custody",
                      worker.calls[1]["prompt"])
        self.assertEqual(self.existing.read_text(), self.original)

    def test_invalid_python_blocks_model_work_from_becoming_reviewable(self):
        broken = self._answer(new_text="def broken(:\n")
        result = repair.NativeSourceRepairRunner(
            NativeContextWorker([broken]), self._request(attempts=1),
            approved=True,
        ).execute()
        self.assertEqual(result.status, "held-exhausted")
        self.assertEqual(result.attempts[0].source_result, "source-parse-held")
        self.assertIsNone(result.candidate)
        self.assertFalse((self.root / "src/extra.py").exists())

    def test_source_context_changed_during_first_turn_holds_all_mixed_work(self):
        def drift(_call):
            self.existing.write_text("def core():\n    return 777\n", encoding="utf-8")
        worker = NativeContextWorker([self._answer(), self._answer()], on_call=drift)
        runner = repair.NativeSourceRepairRunner(
            worker, self._request(), approved=True,
        )
        with self.assertRaises(selected_source.SourceContextHold):
            runner.execute()
        self.assertEqual(len(worker.calls), 1)
        self.assertFalse((self.root / "src/extra.py").exists())
        self.assertEqual(self.existing.read_text(), "def core():\n    return 777\n")


if __name__ == "__main__":
    unittest.main()
