"""Source-bound exact-head reconciliation acceptance; no runtime release claims.

This suite enforces Git-object source identities, guarded mirrors, retained owners,
and optional MIME evidence policy without performing external network or device I/O.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine" / "ai_file_tree.json"
EXPECTED_MAPPINGS = {
    "AIFT-FORGE": ("skeleton/forge", "skeleton/ai/forge"),
    "AIFT-CONTEXT": ("skeleton/context", "skeleton/ai/runtime/context"),
    "AIFT-ECS-ADAPTER": ("skeleton/ecs", "skeleton/ai/runtime/ecs"),
    "AIFT-EXEC-SANDBOX": ("skeleton/sandbox", "skeleton/ai/runtime/sandbox"),
    "AIFT-JEEVES": ("skeleton/jeeves", "skeleton/ai/agents/jeeves"),
    "AIFT-SIMULATION": ("skeleton/simulation", "skeleton/ai/simulation"),
    "AIFT-GAME": ("skeleton/simulation/game", "skeleton/ai/simulation/game"),
    "AIFT-ENGINE-API": ("skeleton/api", "skeleton/ai/runtime/api"),
}
MIRRORS = (
    ("skeleton/forge/ai_builder/procgen/rng.py",
     "skeleton/ai/forge/ai_builder/procgen/rng.py"),
    ("skeleton/forge/ai_builder/edit/session.py",
     "skeleton/ai/forge/ai_builder/edit/session.py"),
    ("skeleton/sandbox/executor.py",
     "skeleton/ai/runtime/sandbox/executor.py"),
    ("skeleton/jeeves/worlds/laptop_flow.py",
     "skeleton/ai/agents/jeeves/worlds/laptop_flow.py"),
    ("skeleton/jeeves/worlds/world_session.py",
     "skeleton/ai/agents/jeeves/worlds/world_session.py"),
    ("skeleton/simulation/game/replay.py",
     "skeleton/ai/simulation/game/replay.py"),
    ("skeleton/simulation/game/golden_grid.py",
     "skeleton/ai/simulation/game/golden_grid.py"),
    ("skeleton/api/v1_edge/edge.py",
     "skeleton/ai/runtime/api/v1_edge/edge.py"),
    ("skeleton/api/v1_edge/quota_store/remote.py",
     "skeleton/ai/runtime/api/v1_edge/quota_store/remote.py"),
    ("skeleton/simulation/physics/vehicle.py", "skeleton/ai/simulation/physics/vehicle.py"),
    ("skeleton/ecs/ai.py", "skeleton/ai/runtime/ecs/ai.py"),
    ("skeleton/forge/archetype_content.py", "skeleton/ai/forge/archetype_content.py"),
    ("skeleton/forge/export.py", "skeleton/ai/forge/export.py"),
    ("skeleton/jeeves/worlds/world_canon.py", "skeleton/ai/agents/jeeves/worlds/world_canon.py"),
    ("skeleton/jeeves/local_inference_bridge.py", "skeleton/ai/agents/jeeves/local_inference_bridge.py"),
    ("skeleton/context/pipeline.py", "skeleton/ai/runtime/context/pipeline.py"),
    ("skeleton/perfgate/cli.py", "skeleton/ai/perfgate/cli.py"),
)
EXPLICIT_RETAINS = {
    "skeleton/perfgate",
    "skeleton/provider_environment.py",
    "skeleton/qualification",
}
LEDGERS = tuple(
    f"docs/qa/DRAFT_SOURCE_CONVERGENCE_2026-11-08_R{i:02d}.md"
    for i in range(3, 14)
)


def git_object(relative: str) -> str:
    """Return the checkout's actual committed object ID, never filesystem size."""
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise AssertionError("invalid source identity path")
    command = subprocess.run(
        ["git", "rev-parse", f"HEAD:{relative}"],
        cwd=ROOT, capture_output=True, text=True, check=True,
        timeout=20,
    )
    value = command.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise AssertionError("invalid Git object ID")
    return value


class SourceConvergenceAssurance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_source_tree_identity_exact_head(self) -> None:
        mappings = self.manifest["mappings"]
        for name, (source, destination) in EXPECTED_MAPPINGS.items():
            with self.subTest(mapping=name):
                matching = [row for row in mappings if row.get("id") == name]
                self.assertEqual(len(matching), 1)
                row = matching[0]
                self.assertEqual(row["source"], source)
                self.assertEqual(row["destination"], destination)
                self.assertEqual(row["kind"], "tree")
                self.assertEqual(row["source_git_object_sha"], git_object(source))

    def test_canonical_and_mirrored_source_bytes(self) -> None:
        for source, mirror in MIRRORS:
            with self.subTest(source=source):
                left, right = ROOT / source, ROOT / mirror
                self.assertFalse(left.is_symlink())
                self.assertFalse(right.is_symlink())
                self.assertTrue(stat.S_ISREG(left.lstat().st_mode))
                self.assertTrue(stat.S_ISREG(right.lstat().st_mode))
                self.assertEqual(git_object(source), git_object(mirror))
                self.assertEqual(
                    hashlib.sha256(left.read_bytes()).digest(),
                    hashlib.sha256(right.read_bytes()).digest(),
                )

    def test_new_top_level_roots_remain_noncanonical(self) -> None:
        retained = self.manifest["retained_outside_ai_tree"]
        retained_by_path = {row["path"]: row for row in retained}
        self.assertEqual(len(retained_by_path), len(retained))
        for path in EXPLICIT_RETAINS:
            with self.subTest(path=path):
                self.assertIn(path, retained_by_path)
                item = retained_by_path[path]
                self.assertTrue(item["owner"].strip())
                self.assertTrue(item["reason"].strip())
                self.assertTrue((ROOT / path).exists())
        self.assertEqual(self.manifest["status"], "staged_mirror")

    def test_all_eleven_audit_ledgers_remain_review_only(self) -> None:
        for name in LEDGERS:
            with self.subTest(ledger=name):
                path = ROOT / name
                self.assertTrue(path.is_file())
                content = path.read_text(encoding="utf-8")
                self.assertIn("DRAFT", content.upper())
                status = content.upper()
                self.assertTrue(any(phrase in status for phrase in (
                    "NO MERGE", "NO MAIN MERGE", "NO MAINLINE SQUASH",
                )), "ledger must hold mainline merge")
                self.assertTrue(any(phrase in status for phrase in (
                    "NO RELEASE", "NO MERGE, RELEASE", "NO MERGE OR RELEASE AUTHORITY",
                )), "ledger must hold production release")

    def test_mime_provenance_does_not_promote_unverified_types(self) -> None:
        from skeleton.ai.webcrawler.media_probe import valid_media_receipt

        rejected = (
            ("text/plain", "text/plain", False, "injected_policy_override"),
            ("text/plain", "application/octet-stream", True,
             "pdf_magic_and_extension"),
            ("application/pdf", "application/octet-stream", True,
             "finite_xml_prefix_and_extension"),
        )
        for values in rejected:
            with self.subTest(receipt=values):
                self.assertFalse(valid_media_receipt(*values))
        self.assertTrue(valid_media_receipt(
            "text/plain", "text/plain", False, "declared_media_kept",
        ))
        self.assertTrue(valid_media_receipt(
            "application/pdf", "application/octet-stream",
            True, "pdf_magic_and_extension",
        ))

    def test_review_preview_is_present_but_never_release_proof(self) -> None:
        from skeleton.jeeves.worlds.laptop_flow import LaptopFlow

        self.assertTrue(callable(getattr(LaptopFlow, "preview_edit", None)))
        self.assertNotEqual(
            self.manifest["status"], "implementation_and_release_certified",
        )


if __name__ == "__main__":
    unittest.main()
