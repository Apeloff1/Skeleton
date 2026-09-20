from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.architecture_layers import derive_architecture_layers
from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.checkpoint import StewardCheckpoint
from skeleton.repo_machine.leases import LeaseRegistry
from skeleton.repo_machine.parallel_plan import build_parallel_waves
from skeleton.repo_machine.scheduler import schedule_objectives
from skeleton.repo_machine.work_queue import MachineWorkQueue


CONFIG = """
[repository]
schema_version = 1
name = "architecture-fixture"
default_owner = "supervisor"
max_files = 1000
max_file_bytes = 100000
max_context_bytes = 30000

[policy]
require_tests_for_code = true
require_readme_for_top_level_code = true
detect_dependency_cycles = true
detect_oversized_modules = true
oversized_python_lines = 3
oversized_javascript_lines = 100
oversized_generic_lines = 100

[[zone]]
name = "api"
prefixes = ["api/"]
owner = "api-owner"
criticality = "high"

[[zone]]
name = "service"
prefixes = ["service/"]
owner = "service-owner"
criticality = "medium"

[[zone]]
name = "core"
prefixes = ["core/"]
owner = "core-owner"
criticality = "high"

[[zone]]
name = "tests"
prefixes = ["tests/"]
owner = "quality-owner"
criticality = "high"

[ignore]
prefixes = [".git/", "__pycache__/"]
suffixes = [".pyc"]
"""


def fixture(root: Path):
    (root / ".machine").mkdir()
    (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
    for name in ("api", "service", "core", "tests"):
        (root / name).mkdir()
        (root / name / "__init__.py").write_text("", encoding="utf-8")
    (root / "core" / "domain.py").write_text(
        "def domain(): return 1\n",
        encoding="utf-8",
    )
    (root / "service" / "logic.py").write_text(
        "import core.domain\n\ndef logic(): return 1\n",
        encoding="utf-8",
    )
    (root / "api" / "main.py").write_text(
        "import service.logic\n\ndef main(): return 1\n",
        encoding="utf-8",
    )
    builder = RepositoryModelBuilder(root)
    return builder, builder.build()


class ArchitectureLayerTests(unittest.TestCase):
    def test_layers_follow_dependency_depth(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            architecture = derive_architecture_layers(model)
            level = {
                zone: layer.level
                for layer in architecture.layers
                for zone in layer.zones
            }
            self.assertLess(level["core"], level["service"])
            self.assertLess(level["service"], level["api"])


class ParallelWaveTests(unittest.TestCase):
    def test_waves_do_not_share_conflict_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder, model = fixture(Path(temp))
            queue = MachineWorkQueue()
            queue.refresh(model, builder.config)
            scheduled = schedule_objectives(
                model,
                queue,
                StewardCheckpoint(),
                LeaseRegistry(),
                now=100,
                max_objectives=8,
            )
            waves = build_parallel_waves(model, scheduled)
            for wave in waves:
                seen: set[str] = set()
                for objective in wave.objectives:
                    self.assertFalse(seen.intersection(objective.item.conflict_keys))
                    seen.update(objective.item.conflict_keys)


if __name__ == "__main__":
    unittest.main()
