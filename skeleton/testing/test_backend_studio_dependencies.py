"""Verify first-install dependency declarations for on-demand studio capabilities.

Import-only smoke checks are not enough: media video and LAFS probability
features defer optional imports until requests arrive, and therefore can appear
healthy at boot even when their production dependencies were omitted.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class BackendStudioDependenciesTests(unittest.TestCase):
    def test_backend_image_video_and_probability_deps_are_pinned(self) -> None:
        requirements = (ROOT / "backend/requirements.txt").read_text(encoding="utf-8")
        for distribution in ("imageio", "imageio-ffmpeg", "scipy"):
            with self.subTest(distribution=distribution):
                self.assertRegex(
                    requirements,
                    rf"(?m)^{re.escape(distribution)}==[0-9]+\.[0-9]+\.[0-9]+$",
                )

    def test_dependencies_match_actual_runtime_consumers(self) -> None:
        media = (ROOT / "backend/gameforge/media/studio.py").read_text(encoding="utf-8")
        lafs = (ROOT / "backend/gameforge/lafs/lafs_engine.py").read_text(encoding="utf-8")
        self.assertIn("import imageio.v2 as iio", media)
        self.assertIn("import imageio_ffmpeg", media)
        self.assertIn("from scipy import stats", lafs)
        self.assertIn("from scipy.special import", lafs)


if __name__ == "__main__":
    unittest.main()
