"""Creator JSON admission rejects NaN/Infinity before runtime authority.

Both original Forge source and its AI-tree mirror must deny ambiguous JSON
constants without erasing deterministic, valid finite and quoted data.
"""
import unittest

from skeleton.forge.creator import command_surface as canonical
from skeleton.ai.forge.creator import command_surface as mirror


class CreatorNonfiniteAdmissionTests(unittest.TestCase):
    def test_explicit_nonfinite_literals_are_denied_on_both_surfaces(self):
        for surface in (canonical, mirror):
            for token in ("NaN", "Infinity", "-Infinity"):
                for shape in ('{"value": %s}', '{"outer": {"v": %s}}',
                              '{"array": [0, %s]}'):
                    with self.subTest(surface=surface.__name__, token=token, shape=shape):
                        with self.assertRaises(surface.CreatorCommandError):
                            surface._load_json_object(shape % token, label="test")

    def test_api_command_cannot_accept_nonfinite_payload(self):
        for surface in (canonical, mirror):
            for token in ("NaN", "Infinity", "-Infinity"):
                raw = ('{"schema":"creator.command.v1","schema_version":1,'
                       '"operation":"create","project_id":"testproject",'
                       '"payload":{"value":' + token + '}}')
                with self.subTest(surface=surface.__name__, token=token):
                    with self.assertRaises(surface.CreatorCommandError):
                        surface.command_from_api(raw)

    def test_finite_and_quoted_values_remain_accepted(self):
        for surface in (canonical, mirror):
            parsed = surface._load_json_object(
                '{"v":[0,1.25,-2.5,"NaN","Infinity"]}', label="test"
            )
            self.assertEqual(parsed, {"v": [0, 1.25, -2.5, "NaN", "Infinity"]})

    def test_existing_duplicate_field_guard_remains(self):
        for surface in (canonical, mirror):
            with self.assertRaises(surface.CreatorCommandError):
                surface._load_json_object('{"x":1,"x":2}', label="test")


if __name__ == "__main__":
    unittest.main()
