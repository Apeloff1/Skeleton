"""Operator CLI integration: actual on-disk import, search, brief, revision, erase."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.knowledge_cli import main
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedDocument, ReviewedNote


TEXT = "Movement acceleration should be predictable. The camera must not hide threats."


class KnowledgeCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.dbfile = self.folder / "knowledge.sqlite3"
        self.importfile = self.folder / "approved.json"

    def tearDown(self):
        self.temp.cleanup()

    def document(self, *, time="2026-10-08T13:00:00Z", status="active"):
        start = TEXT.index("Movement")
        return {
            "owner": "my-game-studio",
            "source_id": "movement-observation",
            "source_url": "https://research.example.org/movement",
            "title": "Movement observation",
            "text": TEXT if status == "active" else "",
            "observed_at": time,
            "license_id": "first-party-observation",
            "allowed_scopes": ["design_reference", "research"],
            "reviewer_id": "operator-1",
            "approved": status == "active",
            "status": status,
            "notes": [{
                "note_id": "acceleration",
                "mechanic": "movement",
                "statement": "Movement acceleration should be predictable.",
                "start": start,
                "end": start + len("Movement acceleration should be predictable"),
                "stance": "supports",
                "confidence_ppm": 900_000,
                "dependence_group": "original-observation",
                "tags": ["movement", "responsiveness"],
            }] if status == "active" else [],
        }

    def invoke(self, *args):
        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            result = main([
                "--store", str(self.dbfile),
                "--trusted-local-operator",
                *args,
            ])
        data = json.loads(output.getvalue()) if output.getvalue().strip() else None
        return result, data, errors.getvalue()

    def write(self, value):
        self.importfile.write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8",
        )

    def test_import_query_and_grounded_brief_across_reopen(self):
        self.write(self.document())
        code, admitted, errors = self.invoke("import", "--input", str(self.importfile))
        self.assertEqual((code, errors), (0, ""))
        self.assertEqual(admitted["revision"], 0)
        self.assertEqual(admitted["claim_count"], 1)
        code, results, errors = self.invoke(
            "query", "--owner", "my-game-studio", "--text", "movement",
        )
        self.assertEqual((code, errors), (0, ""))
        self.assertEqual(len(results["hits"]), 1)
        hit = results["hits"][0]
        self.assertEqual(hit["source_id"], "movement-observation")
        self.assertEqual(hit["exact_quote"], "Movement acceleration should be predictable")
        self.assertEqual(hit["revision_digest"], admitted["revision_digest"])
        code, brief, _ = self.invoke(
            "brief", "--owner", "my-game-studio", "--text", "movement",
        )
        self.assertEqual(code, 0)
        self.assertTrue(brief["requires_human_decision"])
        self.assertEqual(brief["knowledge_root"], results["knowledge_root"])
        self.assertEqual(brief["citations"][0], hit)
        self.assertEqual(len(brief["brief_digest"]), 64)

    def test_second_revision_invalidates_search_evidence(self):
        self.write(self.document())
        first = self.invoke("import", "--input", str(self.importfile))[1]
        self.write(self.document(time="2026-10-09T13:00:00Z", status="retracted"))
        code, second, errors = self.invoke(
            "import", "--input", str(self.importfile),
            "--expected-parent", first["revision_digest"],
        )
        self.assertEqual((code, errors), (0, ""))
        self.assertEqual(second["parent_digest"], first["revision_digest"])
        self.assertEqual(self.invoke(
            "query", "--owner", "my-game-studio", "--text", "movement",
        )[1]["hits"], [])
        self.assertEqual(len(self.invoke(
            "history", "--owner", "my-game-studio",
            "--source-id", "movement-observation",
        )[1]["revisions"]), 2)

    def test_caller_must_acknowledge_external_operator_authentication(self):
        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main([
                "--store", str(self.dbfile),
                "query", "--owner", "my-game-studio", "--text", "movement",
            ])
        self.assertEqual(code, 2)
        self.assertFalse(output.getvalue())
        self.assertIn("authentication acknowledgement", errors.getvalue())

    def test_import_cannot_auto_approve_source(self):
        source = self.document()
        source["approved"] = False
        self.write(source)
        code, _, errors = self.invoke("import", "--input", str(self.importfile))
        self.assertEqual(code, 2)
        self.assertIn("review", errors)

    def test_unknown_import_keys_rejected(self):
        source = self.document()
        source["auto_execute"] = True
        self.write(source)
        code, _, errors = self.invoke("import", "--input", str(self.importfile))
        self.assertEqual(code, 2)
        self.assertIn("shape", errors)

    def test_duplicate_json_keys_rejected(self):
        self.importfile.write_text('{"owner":"x","owner":"y"}', encoding="utf-8")
        code, _, errors = self.invoke("import", "--input", str(self.importfile))
        self.assertEqual(code, 2)
        self.assertIn("invalid UTF-8 JSON", errors)

    def test_symlink_import_rejected(self):
        approved = self.folder / "actual.json"
        approved.write_text(json.dumps(self.document()), encoding="utf-8")
        link = self.folder / "symlink.json"
        link.symlink_to(approved)
        code, _, errors = self.invoke("import", "--input", str(link))
        self.assertEqual(code, 2)
        self.assertIn("regular local file", errors)

    def test_large_import_rejected(self):
        self.importfile.write_bytes(b" " * 1_800_001)
        code, _, errors = self.invoke("import", "--input", str(self.importfile))
        self.assertEqual(code, 2)
        self.assertIn("byte budget", errors)

    def test_owner_erasure_requires_exact_second_confirmation(self):
        self.write(self.document())
        self.invoke("import", "--input", str(self.importfile))
        code, _, errors = self.invoke(
            "erase-owner", "--owner", "my-game-studio",
            "--confirm-erasure", "wrong",
        )
        self.assertEqual(code, 2)
        self.assertIn("confirmation", errors)
        code, erased, errors = self.invoke(
            "erase-owner", "--owner", "my-game-studio",
            "--confirm-erasure", "my-game-studio",
        )
        self.assertEqual((code, errors), (0, ""))
        self.assertEqual(erased["deleted_revisions"], 1)
        self.assertEqual(self.invoke(
            "query", "--owner", "my-game-studio", "--text", "movement",
        )[1]["hits"], [])

    def test_brief_abstains_from_unmet_independence_requirement(self):
        self.write(self.document())
        self.invoke("import", "--input", str(self.importfile))
        code, _, errors = self.invoke(
            "brief", "--owner", "my-game-studio",
            "--text", "movement", "--minimum-independent-groups", "2",
        )
        self.assertEqual(code, 2)
        self.assertIn("independent", errors)

    def test_operator_can_verify_stable_root(self):
        self.write(self.document())
        self.invoke("import", "--input", str(self.importfile))
        first = self.invoke("root", "--owner", "my-game-studio")[1]
        second = self.invoke("root", "--owner", "my-game-studio")[1]
        self.assertEqual(first, second)
        self.assertEqual(len(first["root"]), 64)


if __name__ == "__main__":
    unittest.main()
