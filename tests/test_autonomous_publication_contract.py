from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "skeleton" / "automation" / "specialist_bots.py"


class AutonomousPublicationContractTests(unittest.TestCase):
    def test_worker_surfaces_created_pull_request_url(self) -> None:
        source = WORKER.read_text(encoding="utf-8")

        self.assertIn("capture_output=True", source)
        self.assertIn('text=True,', source)
        self.assertIn('status_payload["pull_request_url"] = publication_url', source)
        self.assertIn(
            'f"https://github.com/{execution.repository}/pull/"',
            source,
        )
        self.assertIn(
            '"pull-request publication returned an invalid URL"',
            source,
        )

    def test_worker_surfaces_deterministic_url_for_followup(self) -> None:
        source = WORKER.read_text(encoding="utf-8")

        self.assertIn(
            'f"https://github.com/{execution.repository}/pull/"',
            source,
        )
        self.assertIn("followup.pr_number", source)


if __name__ == "__main__":
    unittest.main()
