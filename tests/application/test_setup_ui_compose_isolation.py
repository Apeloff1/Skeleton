"""Deterministic regression coverage for protected-stack setup UI recovery."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.app.installer import _isolated_setup_recovery_command


class SetupUiRecoveryIsolationTests(unittest.TestCase):
    def test_inserts_no_deps_without_changing_overlay_or_build_flags(self) -> None:
        original = (
            "docker", "compose", "-f", "compose.yml", "-f", "hot.yml",
            "up", "-d", "--build", "frontend",
        )
        with patch("skeleton.app.installer.compose_command", return_value=original):
            command = _isolated_setup_recovery_command(object(), hot=True)
        self.assertEqual(
            command,
            (
                "docker", "compose", "-f", "compose.yml", "-f", "hot.yml",
                "up", "--no-deps", "-d", "--build", "frontend",
            ),
        )

    def test_rejects_protected_service_in_recovery_command(self) -> None:
        for command in (
            ("docker", "compose", "up", "-d", "backend"),
            ("docker", "compose", "up", "-d", "frontend", "backend"),
            ("docker", "compose", "up", "-d", "backend", "frontend"),
            ("docker", "compose", "-f", "compose.yml"),
            (),
        ):
            with self.subTest(command=command):
                with patch("skeleton.app.installer.compose_command", return_value=command):
                    with self.assertRaises(ValueError):
                        _isolated_setup_recovery_command(object(), hot=False)

    def test_rejects_ambiguous_up_tokens(self) -> None:
        with patch(
            "skeleton.app.installer.compose_command",
            return_value=("docker", "compose", "up", "up", "frontend"),
        ):
            with self.assertRaises(ValueError):
                _isolated_setup_recovery_command(object(), hot=False)

    def test_compose_failure_propagates_to_existing_failure_receipt(self) -> None:
        with patch(
            "skeleton.app.installer.compose_command",
            side_effect=ValueError("invalid recovery topology"),
        ):
            with self.assertRaisesRegex(ValueError, "invalid recovery topology"):
                _isolated_setup_recovery_command(object(), hot=False)


if __name__ == "__main__":
    unittest.main()
