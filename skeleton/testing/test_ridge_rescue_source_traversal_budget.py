"""Source inventory traversal must remain bounded even for ignored files."""
from __future__ import annotations

import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from skeleton.game.gameplay.ridge_rescue import consumer_bundle


class PortableSourceTraversalBudgetTests(unittest.TestCase):
    def test_ignored_source_files_cannot_exhaust_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "consumer_bundle.py").write_text("placeholder", encoding="utf-8")
            for index in range(consumer_bundle.MAX_SCANNED_PATHS + 1):
                (root / f"ignored-{index:04d}.txt").touch()
            with patch.object(consumer_bundle, "__file__", str(root / "consumer_bundle.py")):
                with self.assertRaisesRegex(consumer_bundle.BundleError, "traversal budget"):
                    consumer_bundle.build_bytes()


    def test_source_growth_between_inventory_and_open_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("__init__.py", "consumer_cli.py", "consumer_store.py",
                         "cinder_ridge_campaign.json"):
                (root / name).write_bytes(b"ok")
            original_open = os.open
            target = root / "consumer_cli.py"
            changed = [False]

            def grow_before_open(path, flags, *args, **kwargs):
                if Path(path) == target and not changed[0]:
                    changed[0] = True
                    target.write_bytes(b"x" * (consumer_bundle.MAX_SOURCE_FILE_BYTES + 1))
                return original_open(path, flags, *args, **kwargs)

            with patch.object(consumer_bundle, "__file__", str(root / "consumer_bundle.py")):
                with patch.object(consumer_bundle.os, "open", side_effect=grow_before_open):
                    with self.assertRaisesRegex(consumer_bundle.BundleError,
                                                "source changed during packaging"):
                        consumer_bundle.build_bytes()
            self.assertTrue(changed[0])

    def test_inventory_cap_exceeds_legitimate_source_limit(self) -> None:
        self.assertGreater(consumer_bundle.MAX_SCANNED_PATHS, consumer_bundle.MAX_SOURCE_FILES)


if __name__ == "__main__":
    unittest.main()
