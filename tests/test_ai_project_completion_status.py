"""Canonical project audit must not confuse checked volumes with working product."""
from __future__ import annotations

from hashlib import sha1
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.product.completion_status import (
    CompletionStatusError, inspect_project,
)


def _write(root: Path, relative: str, payload) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8")


def _blob(path: Path) -> str:
    data = path.read_bytes()
    return sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _setup(root: Path) -> None:
    _write(root, "machine/ai_master_plan.json", {
        "volumes": [{"key": "VOL-000", "implementation_status": "verified",
                     "enterprise_grade_state": "designed"}]
    })
    _write(root, "machine/ai_build_accountability.json", {})
    _write(root, "machine/ai_capabilities.json", {
        "capabilities": [{"capability_id": "assistant.text",
                           "implementation_state": "partial"}]
    })
    _write(root, "machine/ai_app_construction.json", {
        "gap_register": [{"id": "gap-1", "status": "closed"}],
        "planes": [{"id": "application-api", "state": "present"}],
    })
    _write(root, "machine/ai_implementation_handoff.json", {
        "entries": [{"gap": "gap-1", "implementation_status": "closed"}],
    })
    _write(root, "machine/ai_closure_evidence.json", {
        "entries": [{"gap": "gap-1", "closure_decision": "closed"}],
    })
    _write(root, "machine/enterprise_ai_superiority.json", {
        "grade_model": {"states": ["designed", "implemented", "hardened",
                                   "enterprise_qualified", "superior"]},
    })
    _write(root, "machine/ai_masterplan_parse_index.json", {
        "sources": {name: {
            "git_blob_sha": _blob(root / name)
        } for name in (
            "machine/ai_master_plan.json", "machine/ai_build_accountability.json"
        )},
        "volume_summary": {"total": 1, "complete": 1},
    })


class CompletionStatusTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        _setup(self.root)

    def test_verified_plan_is_not_complete_product(self):
        status = inspect_project(self.root)
        report = status.to_dict()
        self.assertEqual(status.plan_percent, 100.0)
        self.assertEqual(status.product_percent, 0.0)
        self.assertEqual(status.enterprise_percent, 0.0)
        self.assertTrue(status.signature_index_fresh)
        self.assertEqual(status.signed_plan_volumes, 1)
        self.assertFalse(report["release_ready"])
        self.assertIsNone(report["overall_percent"])
        self.assertIn("assistant.text", report["product"]["pending"])

    def test_stale_index_revokes_signature_freshness(self):
        target = self.root / "machine/ai_master_plan.json"
        target.write_text(target.read_text() + "\n", encoding="utf-8")
        status = inspect_project(self.root)
        self.assertFalse(status.signature_index_fresh)
        self.assertIsNone(status.signed_plan_volumes)
        self.assertIn("signature parse index", " ".join(status.blockers))

    def test_unchanged_plan_but_accountability_changed_is_stale(self):
        target = self.root / "machine/ai_build_accountability.json"
        target.write_text('{"changed": true}', encoding="utf-8")
        self.assertFalse(inspect_project(self.root).signature_index_fresh)

    def test_unrecognized_enterprise_state_fails_closed(self):
        target = self.root / "machine/ai_master_plan.json"
        payload = json.loads(target.read_text())
        payload["volumes"][0]["enterprise_grade_state"] = "pretend-complete"
        _write(self.root, "machine/ai_master_plan.json", payload)
        with self.assertRaises(CompletionStatusError):
            inspect_project(self.root)

    def test_duplicate_capability_is_rejected(self):
        _write(self.root, "machine/ai_capabilities.json", {
            "capabilities": [
                {"capability_id": "assistant.text", "implementation_state": "partial"},
                {"capability_id": "assistant.text", "implementation_state": "complete"},
            ]
        })
        with self.assertRaises(CompletionStatusError):
            inspect_project(self.root)


if __name__ == "__main__":
    unittest.main()
