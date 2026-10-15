"""The production game trainer MUST fail rather than invent or use a scratch model."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.training.jeeves_production_game_train import (
    ProductionCheckpointError,
    _production_source,
    _publish_new,
)


class ProductionGameCheckpointTests(unittest.TestCase):
    def test_requires_explicit_live_checkpoint_configuration(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ProductionCheckpointError, "SKELETON_OWN"):
                _production_source(None, "0" * 64)

    def test_rejects_scratch_checkpoint_even_with_matching_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "own.json"
            raw = json.dumps({"schema_version": "skeleton.numpy_recurrent_lm.v1",
                              "model_digest": "0" * 64}).encode()
            state.write_bytes(raw)
            with patch.dict(os.environ, {"SKELETON_OWN": str(state)}):
                with self.assertRaisesRegex(ProductionCheckpointError, "persisted Jeeves cortex"):
                    _production_source(state, sha256(raw).hexdigest())
            self.assertEqual(state.read_bytes(), raw)

    def test_refuses_checkpoint_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "own.json"
            state.write_text('{"own":{},"lms":{},"transformer":{}}', encoding="utf-8")
            with patch.dict(os.environ, {"SKELETON_OWN": str(state)}):
                with self.assertRaisesRegex(ProductionCheckpointError, "SHA-256"):
                    _production_source(None, "f" * 64)

    def test_explicit_checkpoint_must_match_live_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "live.json"
            other = Path(tmp) / "other.json"
            base.write_text('{"own":{},"lms":{},"transformer":{}}', encoding="utf-8")
            other.write_bytes(base.read_bytes())
            with patch.dict(os.environ, {"SKELETON_OWN": str(base)}):
                with self.assertRaisesRegex(ProductionCheckpointError, "differs"):
                    _production_source(other, sha256(base.read_bytes()).hexdigest())

    def test_untrained_or_missing_native_transformer_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "own.json"
            for snapshot, fragment in (
                ({}, "weight-bearing"),
                ({"itos": ["<UNK>"], "E": [[0]], "layers": [], "dim": 1,
                  "ctx": 2, "steps": 0, "fitted": 0}, "no training history"),
            ):
                data = json.dumps({"own": {}, "lms": {}, "transformer": snapshot}).encode()
                state.write_bytes(data)
                with patch.dict(os.environ, {"SKELETON_OWN": str(state)}):
                    with self.assertRaisesRegex(ProductionCheckpointError, fragment):
                        _production_source(None, sha256(data).hexdigest())

    def test_candidate_publishing_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "candidate.json"
            _publish_new(target, b"model candidate")
            with self.assertRaisesRegex(ProductionCheckpointError, "existing"):
                _publish_new(target, b"replace")
            self.assertEqual(target.read_bytes(), b"model candidate")


if __name__ == "__main__":
    unittest.main()
