"""No production bootstrap without a maintenance-mode, app-owned live cortex."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.cortex import live
from skeleton.cortex.live import CortexPersistenceError, initialize_persisted_production


class JeevesFirstBootProductionTests(unittest.TestCase):
    def test_bootstrap_requires_explicit_environment_permission(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(CortexPersistenceError, "operator bootstrap"):
                initialize_persisted_production()

    def test_bootstrap_rejects_more_than_one_epoch(self) -> None:
        with patch.dict(os.environ, {"SKELETON_JEEVES_BOOTSTRAP": "1"}):
            with self.assertRaisesRegex(CortexPersistenceError, "exactly one epoch"):
                initialize_persisted_production(epochs=2)

    def test_bootstrap_cannot_create_unconfigured_scratch(self) -> None:
        with patch.dict(os.environ, {"SKELETON_JEEVES_BOOTSTRAP": "1"}, clear=True):
            with self.assertRaisesRegex(CortexPersistenceError, "SKELETON_OWN"):
                initialize_persisted_production()

    def test_bootstrap_cannot_replace_production_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "live.json"
            state.write_text('{"actual":"production"}', encoding="utf-8")
            with patch.dict(os.environ, {
                "SKELETON_JEEVES_BOOTSTRAP": "1",
                "SKELETON_OWN": str(state),
            }):
                with self.assertRaises(CortexPersistenceError):
                    initialize_persisted_production()
            self.assertEqual(state.read_text(encoding="utf-8"), '{"actual":"production"}')


if __name__ == "__main__":
    unittest.main()
