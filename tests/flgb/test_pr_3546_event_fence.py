"""PR 3546: an event with a drifted schema digest must not admit."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_path = Path(__file__).resolve().parents[2] / "skeleton/ai/build/pr_automation/event_schema_fence.py"
_spec = importlib.util.spec_from_file_location("event_schema_fence", _path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
EventFenceError = _mod.EventFenceError
EventSchemaFence = _mod.EventSchemaFence

DIGEST = "ab" * 32


class FenceLaw(unittest.TestCase):
    def test_drift_does_not_admit(self) -> None:
        fence = EventSchemaFence(DIGEST)
        with self.assertRaises(EventFenceError):
            fence.admit(run_id="run-1", schema_digest="cd" * 32)
        self.assertEqual(fence._seen, {})

    def test_match_admits_once(self) -> None:
        fence = EventSchemaFence(DIGEST)
        card = fence.admit(run_id="run-1", schema_digest=DIGEST)
        self.assertEqual(card["stored_prose"], 0)
        with self.assertRaises(EventFenceError):
            fence.admit(run_id="run-1", schema_digest=DIGEST)


if __name__ == "__main__":
    unittest.main()
