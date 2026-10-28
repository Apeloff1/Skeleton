"""Lock previously regressed operator, private-artifact and container boundaries.

Pure stdlib: Repository Hygiene can execute this before installing dependencies.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SecurityBoundaryCustodyTests(unittest.TestCase):
    def test_operator_hold_is_wired_and_rechecked_before_both_writes(self) -> None:
        text = (ROOT / ".github/workflows/automation-traffic-manager.yml").read_text(encoding="utf-8")
        for control in ("SKELETON_AUTOMATION_PAUSED", "SKELETON_AUTOMATION_QUARANTINED"):
            self.assertIn(f"{control}: ${{{{ vars.{control} }}}}", text)
            self.assertEqual(text.count("for variable in SKELETON_AUTOMATION_PAUSED SKELETON_AUTOMATION_QUARANTINED; do"), 2)
        self.assertEqual(text.count("operator_blocked=0"), 2)
        self.assertEqual(text.count('echo "Automation operator hold active; no dispatch or relief."'), 2)

    def test_gitignore_excludes_private_sqlite_sidecars_and_journals(self) -> None:
        source = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for forbidden in ("*.sqlite-wal", "*.sqlite-shm", "*.sqlite3-wal",
                          "*.sqlite3-shm", "*.db-wal", "*.db-shm", "backend/.runtime/"):
            self.assertIn(forbidden, source)

    def test_both_docker_build_contexts_exclude_live_runtime_journals(self) -> None:
        for name in ("Dockerfile.dockerignore", "backend/Dockerfile.dockerignore"):
            with self.subTest(name=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("**/.runtime/", source)
                self.assertIn("!machine/ai_local_model_provisioning.json", source)

    def test_production_build_vault_path_is_explicit(self) -> None:
        dockerfile = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("GALAXY_BUILDS_VAULT_DIR=/app/data/builds_vault", dockerfile)


if __name__ == "__main__":
    unittest.main()
