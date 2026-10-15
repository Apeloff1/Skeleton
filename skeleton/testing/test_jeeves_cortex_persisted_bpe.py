"""Protect Jeeves's persisted tokenizer after a production cortex reload."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skeleton.cortex.bpe import BytePairEncoder
from skeleton.cortex.neocortex import JeevesCortex


class ProductionCortexBPERestoreTests(unittest.TestCase):
    def test_reloaded_mouths_use_saved_encoder_not_bootstrap_encoder(self) -> None:
        original = JeevesCortex()
        altered = BytePairEncoder(merges=6)
        altered.fit((
            "quest quest quest quest", "gate gate gate", "npc memory quest gate",
        ))
        original.bpe = altered
        original.transformer.bpe = altered
        original.neo_rms.bpe = altered

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "live-own.json"
            original.save(target)
            live = JeevesCortex()
            live.load(target)
            self.assertIs(live.transformer.bpe, live.bpe)
            self.assertIs(live.neo_rms.bpe, live.bpe)
            self.assertEqual(live.bpe.snapshot(), altered.snapshot())
            self.assertEqual(
                live.transformer._ids("quest gate"),
                original.transformer._ids("quest gate"),
            )
            self.assertEqual(
                live.neo_rms._ids("npc memory"),
                original.neo_rms._ids("npc memory"),
            )


if __name__ == "__main__":
    unittest.main()
