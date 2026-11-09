from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skeleton.artifact_plane.plane_audit import SCORES, PlaneAudit


class GB11PlaneAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ledger = self.root / "docs" / "lineage"
        ledger.mkdir(parents=True)
        rows = [
            {
                "plane": "organism",
                "path": "skeleton/organism/state.py",
                "bytes": 10,
                "score": "KEEP",
                "why": "live",
                "stored_prose": 0,
            },
            {
                "plane": "social",
                "path": "skeleton/social/compat.py",
                "bytes": 10,
                "score": "SHIM",
                "why": "alias",
                "stored_prose": 0,
            },
            {
                "plane": "galaxy",
                "path": "skeleton/galaxy/dump.py",
                "bytes": 10,
                "score": "FOLD",
                "why": "dump",
                "stored_prose": 0,
            },
            {
                "plane": "galaxy",
                "path": "skeleton/galaxy/vault.py",
                "bytes": 10,
                "score": "QUARANTINE",
                "why": "vault",
                "stored_prose": 0,
            },
        ]
        (ledger / "plane_audit.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_clean_ledger_hits(self) -> None:
        card = PlaneAudit(self.root).audit()
        self.assertEqual(card["kind"], "plane-audit")
        self.assertEqual(card["hit"], 1)
        self.assertEqual(card["law"], "GB-11")
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["n"], 4)
        self.assertEqual(set(SCORES), {"KEEP", "SHIM", "FOLD", "QUARANTINE"})

    def test_bad_score_fails_closed(self) -> None:
        path = self.root / "docs" / "lineage" / "plane_audit.jsonl"
        path.write_text(
            json.dumps(
                {
                    "plane": "organism",
                    "path": "skeleton/organism/x.py",
                    "score": "DELETE",
                    "stored_prose": 0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        auditor = PlaneAudit(self.root)
        self.assertEqual(auditor.audit()["hit"], 0)
        self.assertEqual(auditor.fail_closed(), 2)

    def test_unscored_disk_file_fails_closed(self) -> None:
        dest = self.root / "skeleton" / "organism"
        dest.mkdir(parents=True)
        (dest / "stray.py").write_text("x=1\n", encoding="utf-8")
        card = PlaneAudit(self.root).audit()
        self.assertEqual(card["hit"], 0)
        self.assertIn("skeleton/organism/stray.py", card["unscored_on_disk"])

    def test_card_json_roundtrip(self) -> None:
        card = PlaneAudit(self.root).audit()
        restored = json.loads(json.dumps(card))
        self.assertEqual(restored["stored_prose"], 0)


if __name__ == "__main__":
    unittest.main()
