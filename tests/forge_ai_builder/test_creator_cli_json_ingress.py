"""Fail-closed creator CLI JSON ingress regression tests."""

import unittest

from skeleton.forge.creator.command_surface import (
    CreatorCommandError,
    command_from_cli,
)


class CreatorCLIJSONIngressTests(unittest.TestCase):
    def test_valid_creator_request_survives_cli_binding(self):
        command = command_from_cli([
            "create", "original_game", '{"intent":{"goal":"Build an original maze"}}'
        ])
        self.assertEqual(command.operation, "create")
        self.assertEqual(command.project_id, "original_game")
        self.assertEqual(command.payload["intent"]["goal"], "Build an original maze")

    def test_nonfinite_literals_fail_closed_at_json_boundary(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token), self.assertRaises(CreatorCommandError):
                command_from_cli([
                    "create", "original_game", '{"intent":{"untrusted":' + token + '}}'
                ])

    def test_duplicate_nested_fields_fail_closed(self):
        with self.assertRaises(CreatorCommandError):
            command_from_cli([
                "create", "original_game", '{"intent":{"goal":"a","goal":"b"}}'
            ])

    def test_rejected_request_does_not_invoke_handler(self):
        called = []
        def handler(_command):
            called.append(True)
            return {}
        from skeleton.forge.creator.command_surface import dispatch_creator_command
        with self.assertRaises(CreatorCommandError):
            dispatch_creator_command(
                command_from_cli(["create", "original_game", '{"intent":{"goal":NaN}}']),
                handlers={"create": handler},
            )
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
