"""Train/serve prompt-framing parity removes prior Instruction/Response mismatch."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.model_runtime.chat_protocol import ChatTranscript
from skeleton.ai.runtime.operational_ai.native_supervised.frames import (
    frame,paired_train,
)
from skeleton.ai.runtime.operational_ai.native_supervised.source import prepare_source
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestTrueChatFrames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=prepare_source()
        cls.pairs=paired_train(cls.source.groups)

    def test_exactly_432_framed_train_examples(self):
        self.assertEqual(len(self.pairs),432)
        self.assertEqual(len({x.item_id for x in self.pairs}),432)

    def test_model_serving_protocol_is_same(self):
        for pair in self.pairs[:24]:
            example=next(x for x in self.source.groups.train if x.item_id==pair.item_id)
            serving=ChatTranscript.parse([{
                "role":"user","content":example.prompt,
            }]).format_prompt()
            self.assertEqual(pair.prompt,serving)
            self.assertIn("[message role=user",pair.prompt)
            self.assertTrue(pair.prompt.endswith("[message role=assistant name= bytes=?]\n"))

    def test_do_not_train_on_prompt_as_response(self):
        for pair in self.pairs:
            self.assertNotEqual(pair.prompt,pair.completion)
            self.assertTrue(pair.completion.strip())
            self.assertEqual(len(pair.completion_sha256),64)

    def test_train_only_ids_are_source_bound(self):
        train_ids={x.item_id for x in self.source.groups.train}
        other={x.item_id for x in self.source.groups.validation+self.source.groups.holdout}
        self.assertEqual({p.item_id for p in self.pairs},train_ids)
        self.assertFalse(train_ids&other)

    def test_changed_training_prompt_changes_source_digest(self):
        example=self.source.groups.train[0]
        modified=frame(replace(example,prompt=example.prompt+" altered"))
        original=frame(example)
        self.assertNotEqual(modified.prompt_sha256,original.prompt_sha256)


if __name__=="__main__":
    unittest.main()
