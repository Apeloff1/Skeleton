"""Preserve private GGUF prompts byte-for-byte through native one-shot CLI.

Tests use a synthetic worker only. They neither load GGUF weights nor
qualify device capacity, model source rights or release readiness.
"""
from __future__ import annotations

from contextlib import nullcontext, redirect_stdout, redirect_stderr
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.cli import main as native_main
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER

# Synthetic installed-source contract shape, not independently validated GGUF rights.
# Keep production require_activated_source strict: only this test patches it.
SYNTHETIC_SOURCE = {
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64, "archive_sha256": "d" * 64,
    "source_sha": "e" * 40, "installed_model_bytes": 2048,
    "installed_shard_count": 1,
}


def argv(*extra):
    return [
        "--mode","once","--model-root","/private/installed",
        "--state-dir","/private/state","--tenant","local",
        "--subject","owner","--prompt-stdin",*extra,
    ]


def dispatch(raw, *, options=()):
    stdin=SimpleNamespace(buffer=BytesIO(raw))
    stdout=StringIO()
    stderr=StringIO()
    worker=FakeWorker()
    with (
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked",
            return_value=(nullcontext(),worker,object()),
        ) as activate,
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdin",
            stdin,
        ),
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            return_value=dict(SYNTHETIC_SOURCE),
        ),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        code=native_main(argv(*options))
    return code,stdout.getvalue(),stderr.getvalue(),worker,activate


class ExactStdinCustodyTests(unittest.TestCase):
    def test_multiline_python_code_retains_all_indentation_and_crlf(self):
        raw=b"    def example():\r\n        return 123\r\n\r\n"
        code,out,err,worker,activate=dispatch(raw)
        self.assertEqual(code,0,err)
        self.assertFalse(err)
        native_key=next(iter(worker.spine.receipts))
        self.assertEqual(native_key[2].encode("utf-8"),raw)
        self.assertEqual(worker.generation_calls,1)

    def test_unicode_and_leading_space_survive_unchanged(self):
        prompt="  Generate a local Norwegian text: blåbær 🌲  \n"
        code,out,err,worker,activate=dispatch(prompt.encode("utf-8"))
        self.assertEqual(code,0,err)
        self.assertEqual(next(iter(worker.spine.receipts))[2],prompt)
        self.assertEqual(worker.generation_calls,1)
        self.assertNotIn("Generate a local Norwegian",out)

    def test_exact_native_request_id_still_binds_one_durable_record(self):
        raw=b"  exact prompt with trailing spaces  \n"
        code,out,err,worker,activate=dispatch(
            raw, options=("--request-id","r_fixed"),
        )
        self.assertEqual(code,0,err)
        receipt=json.loads(out)["output"]
        self.assertEqual(receipt["request_id"],"r_fixed")
        self.assertEqual(next(iter(worker.spine.receipts))[1],"r_fixed")
        self.assertEqual(next(iter(worker.spine.receipts))[2].encode(),raw)
        self.assertEqual(worker.generation_calls,1)

    def test_whitespace_only_denied_before_model_start(self):
        for raw in (b"",b"   ",b"\r\n  \t",b"\n"):
            with self.subTest(raw=repr(raw)):
                code,out,err,worker,activate=dispatch(raw)
                self.assertEqual(code,2)
                self.assertFalse(out)
                activate.assert_not_called()
                self.assertEqual(worker.generation_calls,0)
                self.assertFalse(worker.spine.created)

    def test_overflow_denied_without_model_or_sqlite(self):
        code,out,err,worker,activate=dispatch(b"x"*32769)
        self.assertEqual(code,2)
        self.assertFalse(out)
        activate.assert_not_called()
        self.assertFalse(worker.spine.created)

    def test_invalid_utf8_denied_before_native_activation(self):
        code,out,err,worker,activate=dispatch(b"prefix\xffsuffix")
        self.assertEqual(code,2)
        activate.assert_not_called()
        self.assertFalse(worker.spine.created)
        self.assertNotIn("prefix",err)

    def test_null_byte_rejected_before_native_process(self):
        code,out,err,worker,activate=dispatch(b"valid\x00invalid")
        self.assertEqual(code,2)
        activate.assert_not_called()
        self.assertEqual(worker.generation_calls,0)
        self.assertFalse(worker.spine.created)

    def test_stale_source_identity_is_never_synthetic_acceptance(self):
        code,out,err,worker,activate=dispatch(b"normal private task")
        self.assertEqual(code,0,err)
        result=json.loads(out)
        self.assertEqual(result["status"],"real-offline-turn-committed")
        self.assertEqual(result["output"]["receipt"]["model_sha256"],MODEL)
        self.assertEqual(worker.generation_calls,1)
        # A fake worker is not independent installed-source certification.
        self.assertNotIn("release_certified",result["output"])
        self.assertNotIn("device_qualified",result["output"])


if __name__=="__main__":
    unittest.main()
