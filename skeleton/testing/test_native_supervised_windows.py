"""Native response-only target windows; no prompt gradient targets."""
from __future__ import annotations
import unittest
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.runtime.operational_ai.native_supervised.frames import FramedPair
from skeleton.ai.runtime.operational_ai.native_supervised.token_windows import construct
from skeleton.ai.runtime.operational_ai.native_supervised.alignment_proof import prove
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestCompletionOnlyWindows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=TinyTransformer(
            vocab=("hello","world","message","role","assistant","user","bytes",
                   "name","thank","you"),dim=8,ctx=128,seed=1,d_ff=0,
        )
        cls.pair=FramedPair(
            "sample_01","test",
            "[message role=user name= bytes=5]\nhello\n[/message]\n"
            "[message role=assistant name= bytes=?]\n",
            "thank you","a"*64,"b"*64,
        )

    def test_first_completion_window_ends_at_actual_chat_prompt(self):
        cases=construct(self.model,self.pair,max_context=128)
        prompt=tuple(self.model._ids(self.pair.prompt))
        self.assertEqual(cases[0].context,prompt)

    def test_supervision_is_exactly_two_completion_tokens(self):
        cases=construct(self.model,self.pair,max_context=128)
        self.assertEqual(len(cases),2)
        self.assertEqual(tuple(c.target for c in cases),
                         tuple(self.model._ids("thank you")))

    def test_independent_gradient_mask_proof(self):
        result=prove(self.model,self.pair,
                     construct(self.model,self.pair,max_context=128))
        self.assertEqual(result["prompt_gradient_targets"],0)
        self.assertEqual(result["supervised_targets"],2)

    def test_oversized_model_context_request_denied(self):
        with self.assertRaises(SupervisedRejected):
            construct(self.model,self.pair,max_context=4096)

    def test_empty_target_denied(self):
        from dataclasses import replace
        bad=replace(self.pair,completion="   ")
        with self.assertRaises(SupervisedRejected):
            construct(self.model,bad,max_context=128)

    def test_window_targets_are_source_bound(self):
        for case in construct(self.model,self.pair,max_context=128):
            self.assertEqual(case.item_id,"sample_01")


if __name__=="__main__":
    unittest.main()
