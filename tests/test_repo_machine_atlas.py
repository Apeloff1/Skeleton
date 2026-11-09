from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.atlas import build_repository_atlas, placement_for_path
from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.config import load_machine_config


CONFIG = """
[repository]
schema_version = 1
name = "atlas-fixture"
default_owner = "supervisor"
max_files = 100
max_file_bytes = 100000
max_context_bytes = 30000

[policy]
require_tests_for_code = false
require_readme_for_top_level_code = false
detect_dependency_cycles = true
detect_oversized_modules = false
oversized_python_lines = 100
oversized_javascript_lines = 100
oversized_generic_lines = 100

[[zone]]
name = "machine"
prefixes = [".machine/", "machine/"]
owner = "repository-control"
criticality = "high"
purpose = "Canonical machine policy and generated discovery contracts."
audience = "machine"
lifecycle = "canonical"

[[zone]]
name = "runtime"
prefixes = ["app/"]
owner = "runtime-team"
criticality = "high"
purpose = "Canonical application runtime."
audience = "both"
lifecycle = "canonical"

[[zone]]
name = "legacy"
prefixes = ["legacy/"]
owner = "runtime-team"
criticality = "low"
purpose = "Compatibility surface pending controlled migration."
audience = "internal"
lifecycle = "transitional"

[ignore]
prefixes = [".git/", "__pycache__/"]
suffixes = [".pyc"]
"""


class RepositoryAtlasTests(unittest.TestCase):
    def fixture(self) -> tempfile.TemporaryDirectory[str]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / ".machine").mkdir()
        (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
        (root / "machine").mkdir()
        (root / "app").mkdir()
        (root / "legacy").mkdir()
        (root / "app" / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "legacy" / "shim.py").write_text("VALUE = 1\n", encoding="utf-8")
        return temp

    def test_zone_metadata_round_trips_into_atlas(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            builder = RepositoryModelBuilder(root)
            atlas = build_repository_atlas(builder.build(), builder.config)
            zones = {item.name: item for item in atlas.zones}
            self.assertEqual(zones["machine"].audience, "machine")
            self.assertEqual(zones["legacy"].lifecycle, "transitional")
            self.assertEqual(zones["runtime"].file_count, 1)
            self.assertEqual(atlas.contract, ".machine/repository.toml")

    def test_placement_uses_first_matching_canonical_zone(self) -> None:
        with self.fixture() as temp:
            config = load_machine_config(Path(temp))
            placement = placement_for_path(config, "app/new_feature.py")
            self.assertEqual(placement.zone, "runtime")
            self.assertEqual(placement.owner, "runtime-team")
            self.assertEqual(placement.lifecycle, "canonical")
            self.assertEqual(placement.matched_prefix, "app/")

    def test_absolute_or_trailing_slash_path_is_rejected(self) -> None:
        with self.fixture() as temp:
            config = load_machine_config(Path(temp))
            with self.assertRaisesRegex(ValueError, "canonical"):
                placement_for_path(config, "/app/new.py")
            with self.assertRaisesRegex(ValueError, "canonical"):
                placement_for_path(config, "app/new/")

    def test_unknown_path_is_explicitly_unclassified(self) -> None:
        with self.fixture() as temp:
            config = load_machine_config(Path(temp))
            placement = placement_for_path(config, "mystery/new.py")
            self.assertEqual(placement.zone, "unclassified")
            self.assertEqual(placement.lifecycle, "transitional")
            self.assertEqual(placement.matched_prefix, "")

    def test_invalid_zone_metadata_fails_closed(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            path = root / ".machine" / "repository.toml"
            path.write_text(
                CONFIG.replace('audience = "machine"', 'audience = "everyone"', 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "audience"):
                load_machine_config(root)


if __name__ == "__main__":
    unittest.main()
