"""Regression coverage for install requirements parity across package formats."""
from __future__ import annotations

import unittest

from scripts.check_root_package_metadata_parity import ROOT, validate


class RootPackageRequirementsParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        cls.setup = (ROOT / "setup.cfg").read_text(encoding="utf-8")

    def test_current_manifest_parity(self) -> None:
        self.assertEqual(validate(self.project, self.setup), [])

    def test_stale_pydantic_floor_is_detected(self) -> None:
        changed = self.setup.replace(
            "\tpydantic[email]>=2.14.1",
            "\tpydantic[email]>=2.14.0",
            1,
        )
        self.assertNotEqual(changed, self.setup)
        issues = validate(self.project, changed)
        self.assertTrue(any("pydantic[email]>=2.14.1" in x for x in issues))
        self.assertTrue(any("pydantic[email]>=2.14.0" in x for x in issues))

    def test_stale_cryptography_and_httpx_floors_are_detected(self) -> None:
        old = self.setup.replace("\tcryptography>=50.0.2",
                                 "\tcryptography>=50.0.1", 1).replace(
            "\thttpx>=0.28.1,<1", "\thttpx>=0.27,<1", 1
        )
        self.assertNotEqual(old, self.setup)
        issues = validate(self.project, old)
        self.assertTrue(any("cryptography>=50.0.2" in x for x in issues))
        self.assertTrue(any("httpx>=0.28.1,<1" in x for x in issues))

    def test_duplicate_core_requirement_fails_closed(self) -> None:
        duplicated = self.setup.replace(
            "\tbcrypt>=4,<5", "\tbcrypt>=4,<5\n\tbcrypt>=4,<5", 1
        )
        self.assertTrue(any("duplicate" in x for x in validate(self.project, duplicated)))

    def test_stale_development_extra_floor_is_detected(self) -> None:
        old = self.setup.replace(
            "\truff>=0.17.2,<0.18", "\truff>=0.17.1,<0.18", 1
        )
        self.assertNotEqual(old, self.setup)
        issues = validate(self.project, old)
        self.assertTrue(any("dev" in issue and "ruff>=0.17.2" in issue for issue in issues))

    def test_hosted_httpx_extra_floor_is_detected(self) -> None:
        old = self.setup.replace(
            "\topenai>=2.54.0,<3\n\thttpx>=0.28.1,<1",
            "\topenai>=2.54.0,<3\n\thttpx>=0.28,<1", 1,
        )
        self.assertNotEqual(old, self.setup)
        issues = validate(self.project, old)
        self.assertTrue(any("hosted-inference" in issue and "httpx>=0.28.1" in issue for issue in issues))

    def test_missing_optional_extra_fails_closed(self) -> None:
        changed = self.setup.replace(
            "jeeves-production-training =\n\ttorch>=2.5,<3\n", "", 1,
        )
        self.assertNotEqual(changed, self.setup)
        self.assertTrue(any("missing optional extra: jeeves-production-training" in issue
                            for issue in validate(self.project, changed)))

    def test_duplicate_optional_extra_requirement_fails_closed(self) -> None:
        changed = self.setup.replace(
            "\ttorch>=2.5,<3",
            "\ttorch>=2.5,<3\n\ttorch>=2.5,<3", 1,
        )
        self.assertNotEqual(changed, self.setup)
        self.assertTrue(any("extra has duplicate" in issue
                            for issue in validate(self.project, changed)))

    def test_malformed_metadata_is_not_accepted(self) -> None:
        with self.assertRaises(ValueError):
            validate("[project]\ndependencies = 4\n", self.setup)


if __name__ == "__main__":
    unittest.main()
