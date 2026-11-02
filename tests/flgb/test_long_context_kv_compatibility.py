"""KV/tokenizer compatibility tests with synthetic generation-fenced heads."""
from __future__ import annotations

from hashlib import sha256
import unittest
from unittest.mock import MagicMock, patch

from skeleton.ai.model_runtime.long_context_kv_compatibility import (
    KvLayout, KvWindowRequest, LongContextKvCompatibility,
)
from skeleton.ai.model_runtime.long_context_progress import _name
from skeleton.ai.model_runtime.long_context_spool import LongContextSpoolError, _canonical


def head(*, token=1, generation=3, start=0, stop=2):
    record = {
        "schema": "skeleton.ai.long-context-head.v1",
        "stream_digest": _name("stream"),
        "checkpoint_digest": "c" * 64,
        "tokenizer_digest": "b" * 64,
        "generation": generation,
    }
    record["record_digest"] = sha256(_canonical(record)).hexdigest()
    window = {
        "start": start, "stop": stop,
        "token_ids": [token] * (stop - start),
        "source_sequence_digest": "d" * 64,
    }
    window["digest"] = sha256(_canonical(window)).hexdigest()
    return {**record, "is_execution_lease": False, "window": window}


class KvCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.heads = MagicMock()
        self.heads.compare_window.return_value = head()
        with patch(
            "skeleton.ai.model_runtime.long_context_kv_compatibility.LongContextProgressHead",
            MagicMock,
        ):
            self.guard = LongContextKvCompatibility(self.heads)
        self.layout = KvLayout("a" * 64, "b" * 64, 2, 2, 8, 64, 256)
        self.request = KvWindowRequest("stream", "c" * 64, 3, 8, 8192)

    def check(self, layout=None, request=None, expected_model_digest="a" * 64):
        return self.guard.observe(
            layout or self.layout, request or self.request,
            expected_model_digest=expected_model_digest,
        )

    def test_cpu_kv_compatible_but_not_execution(self):
        result = self.check()
        self.assertEqual(result["state"], "compatible_observed")
        self.assertEqual(result["estimated_kv_bytes"], 128)
        self.assertEqual(len(result["window_digest"]), 64)
        self.assertFalse(result["is_execution_lease"])
        self.assertFalse(result["kv_tensor_contents_verified"])
        self.assertFalse(result["tokenizer_state_attested"])
        self.assertFalse(result["device_qualified"])
        self.assertNotIn("token_ids", result)
        self.heads.compare_window.assert_called_once()

    def test_gpu_m_chip_never_qualified(self):
        for device in ("gpu", "m_chip"):
            with self.subTest(device=device):
                layout = KvLayout("a" * 64, "b" * 64, 2, 2, 8, 64, 256,
                                  device_kind=device)
                self.assertEqual(self.check(layout)["reason"], "unqualified_device")
        self.heads.compare_window.assert_not_called()

    def test_wrong_model_holds_without_head_access(self):
        self.assertEqual(self.check(expected_model_digest="e" * 64)["reason"],
                         "model_identity_mismatch")
        self.heads.compare_window.assert_not_called()

    def test_stale_or_tampered_head_holds(self):
        for change in (
            {"generation": 4},
            {"generation": True},
            {"is_execution_lease": True},
            {"record_digest": "0" * 64},
            {"tokenizer_digest": "0" * 64},
            {"checkpoint_digest": "0" * 64},
            {"stream_digest": "0" * 64},
            {"schema": "forged"},
        ):
            with self.subTest(change=change):
                self.heads.compare_window.return_value = {**head(), **change}
                self.assertEqual(self.check()["state"], "hold")

    def test_window_mutation_and_vocabulary_bounds_hold(self):
        for change in (
            {"digest": "0" * 64},
            {"token_ids": [999, 999]},
            {"token_ids": [True, 1]},
            {"token_ids": [1]},
            {"stop": 65},
            {"start": 3},
            {"source_sequence_digest": "x"},
        ):
            with self.subTest(change=change):
                observed = head()
                observed["window"] = {**observed["window"], **change}
                self.heads.compare_window.return_value = observed
                self.assertEqual(self.check()["state"], "hold")

    def test_memory_budget_and_context_bounds(self):
        self.assertEqual(self.check(request=KvWindowRequest(
            "stream", "c" * 64, 3, 8, 64))["reason"], "KV_memory_budget_exceeded")
        self.heads.compare_window.return_value = head(stop=3)
        layout = KvLayout("a" * 64, "b" * 64, 2, 2, 8, 2, 256)
        self.assertEqual(self.check(layout)["state"], "hold")

    def test_empty_window_and_unavailable_head(self):
        self.heads.compare_window.return_value = {**head(), "window": None}
        self.assertEqual(self.check()["reason"], "window_exhausted")
        self.heads.compare_window.side_effect = LongContextSpoolError("stale")
        self.assertEqual(self.check()["reason"], "KV_custody_unverified")

    def test_strict_layout_and_request(self):
        for bad in (True, 0, -1, 65537):
            with self.subTest(bad=bad), self.assertRaises(LongContextSpoolError):
                KvLayout("a" * 64, "b" * 64, 2, 2, 8, bad, 256)
        for bad in (0, True, 3, 16):
            with self.subTest(bad=bad), self.assertRaises(LongContextSpoolError):
                KvLayout("a" * 64, "b" * 64, 2, 2, 8, 64, 256,
                         bytes_per_element=bad)
        with self.assertRaises(LongContextSpoolError):
            KvWindowRequest("stream", "c" * 64, True, 8, 8192)
        with self.assertRaises(LongContextSpoolError):
            KvWindowRequest("../stream", "c" * 64, 3, 8, 8192)


if __name__ == "__main__":
    unittest.main()
