"""Original-byte source windows and local-only production dispatch.

The tests do not invoke any provider, generate model weights or grant tools.
They assert that the canonical layer transition does not bypass the original
state/identity contract or silently weaken explicit overlap validation.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.production_fabric.product import api, dispatcher, cli
from skeleton.ai.runtime.operational_ai.offline_cognition.families.duplicate_filter import evidence
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.core.sources import bind_source
from skeleton.ai.runtime.operational_ai.offline_cognition.core.evidence_pipeline import EvidenceDocument


class ProductionLayeringAndEvidence(unittest.TestCase):
    def setUp(self):
        self.payload = ("café 🦊 original bounded source text " * 8).encode("utf8")
        self.receipt = bind_source(
            self.payload,source_id="local_doc",tenant="local",subject="owner",
            approved=True,
        )
        self.document = EvidenceDocument(
            self.receipt,self.payload,(1.0,0.0),"a"*64,
        )

    def test_compatibility_api_is_same_pure_dispatcher_class(self):
        self.assertIs(api.LocalAPI,dispatcher.LocalAPI)
        self.assertIs(cli.LocalAPI,dispatcher.LocalAPI)

    def test_pure_dispatcher_has_no_network_or_model_provider(self):
        engine=mock.Mock()
        engine.inspect.return_value={"status":"fixture-only"}
        data=dispatcher.LocalAPI(engine).dispatch({
            "method":"inspect","session":"session_1",
        })
        self.assertEqual(data,{"status":"fixture-only"})
        engine.inspect.assert_called_once_with("session_1")
        engine.generate.assert_not_called()
        engine.play.assert_not_called()
        engine.verify.assert_not_called()

    def test_small_default_window_generates_exact_original_byte_spans(self):
        spans=evidence.passages(self.document,window_bytes=32)
        self.assertGreater(len(spans),1)
        catalog=evidence.index((self.document,),tenant="local",subject="owner")
        for span in spans:
            self.assertLessEqual(span.end-span.start,32)
            self.assertTrue(evidence.citation(catalog,span)["exact_bytes_verified"])

    def test_explicit_oversized_overlap_stays_fail_closed(self):
        with self.assertRaises(CognitionError):
            evidence.passages(
                self.document,window_bytes=32,overlap_bytes=128,
            )

    def test_full_sized_default_preserves_original_overlap_semantics(self):
        a=evidence.passages(self.document,window_bytes=2048)
        b=evidence.passages(
            self.document,window_bytes=2048,overlap_bytes=128,
        )
        self.assertEqual(a,b)

    def test_bad_small_windows_do_not_gain_automatic_approval(self):
        for window in (0,True,15,65537,"32"):
            with self.subTest(window=repr(window)),self.assertRaises(CognitionError):
                evidence.passages(self.document,window_bytes=window)

    def test_user_explicit_bad_overlap_types_remain_held(self):
        for overlap in (True,-1,32,100000,"8",1.0):
            with self.subTest(overlap=repr(overlap)),self.assertRaises(CognitionError):
                evidence.passages(
                    self.document,window_bytes=32,overlap_bytes=overlap,
                )

    def test_no_native_inference_claim_in_evidence_report(self):
        self.assertFalse(evidence.contract()["native_generation_executed"])
        self.assertFalse(evidence.contract()["rights_independently_proved"])


if __name__=="__main__":
    unittest.main()
