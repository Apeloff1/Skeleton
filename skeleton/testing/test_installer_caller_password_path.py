"""Installer entrypoint preserves caller-relative private file identity."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import install_app


class InstallerCallerPathTests(unittest.TestCase):
    def test_relative_separate_argument(self) -> None:
        self.assertEqual(
            install_app._caller_bound_arguments(
                ["--admin-password-file", "private/password.txt", "--no-python"],
                Path("/operator"),
            ),
            ["--admin-password-file", "/operator/private/password.txt", "--no-python"],
        )

    def test_relative_equals_argument(self) -> None:
        self.assertEqual(
            install_app._caller_bound_arguments(
                ["--admin-password-file=secret with spaces.txt"], Path("/operator")
            ),
            ["--admin-password-file=/operator/secret with spaces.txt"],
        )

    def test_absolute_file_is_unchanged(self) -> None:
        self.assertEqual(
            install_app._caller_bound_arguments(
                ["--admin-password-file", "/secure/pin.txt"], Path("/operator")
            ),
            ["--admin-password-file", "/secure/pin.txt"],
        )

    def test_missing_operand_is_left_to_parser(self) -> None:
        self.assertEqual(
            install_app._caller_bound_arguments(
                ["--admin-password-file"], Path("/operator")
            ),
            ["--admin-password-file"],
        )

    def test_empty_equals_operand_is_left_to_parser(self) -> None:
        self.assertEqual(
            install_app._caller_bound_arguments(
                ["--admin-password-file="], Path("/operator")
            ),
            ["--admin-password-file="],
        )

    def test_main_runs_canonical_installer_from_checkout(self) -> None:
        with (
            patch.object(install_app.Path, "cwd", return_value=Path("/operator")),
            patch.object(install_app.os, "chdir") as chdir,
            patch.object(install_app.sys, "argv", ["install_app.py", "--admin-password-file", "secret.txt"]),
            patch.object(install_app, "run_app_cli", return_value=0) as cli,
        ):
            self.assertEqual(install_app.main(), 0)
        chdir.assert_called_once_with(install_app.ROOT)
        cli.assert_called_once_with(["install", "--admin-password-file", "/operator/secret.txt"])


if __name__ == "__main__":
    unittest.main()
