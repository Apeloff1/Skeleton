from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.checkpoint import ObjectiveOutcome, StewardCheckpoint
from skeleton.repo_machine.debt import debt_by_zone, debt_register
from skeleton.repo_machine.intent import ChangeIntent
from skeleton.repo_machine.leases import LeaseRegistry
from skeleton.repo_machine.migration import build_migration_plan
from skeleton.repo_machine.reorganize import propose_reorganization
from skeleton.repo_machine.scheduler import lane_distribution, schedule_objectives
from skeleton.repo_machine.session import build_machine_session
from skeleton.repo_machine.validation_plan import build_validation_plan
from skeleton.repo_machine.work_queue import MachineWorkQueue


CONFIG = """
[repository]
schema_version = 1
name = "scheduler-fixture"
default_owner = "supervisor"
max_files = 5000
max_file_bytes = 500000
max_context_bytes = 30000

[policy]
require_tests_for_code = true
require_readme_for_top_level_code = true
detect_dependency_cycles = true
detect_oversized_modules = true
oversized_python_lines = 40
oversized_javascript_lines = 40
oversized_generic_lines = 40

[[zone]]
name = "app"
prefixes = ["app/"]
owner = "app-owner"
criticality = "high"

[[zone]]
name = "lib"
prefixes = ["lib/"]
owner = "lib-owner"
criticality = "medium"

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
    for name in ("app", "lib", "tests"):
        (root / name).mkdir()
    (root / "app" / "service.py").write_text(
        "import lib.api\n" + "\n".join(
            f"def operation_{i}(): return {i}" for i in range(60)
        ) + "\n",
        encoding="utf-8",
    )
    (root / "app" / "orphan.py").write_text("def orphan(): return 1\n", encoding="utf-8")
    (root / "lib" / "api.py").write_text("def request(): return 1\n", encoding="utf-8")
    (root / "tests" / "test_service.py").write_text(
        "import app.service\n\ndef test_service(): assert True\n",
        encoding="utf-8",
    )
    builder = RepositoryModelBuilder(root)
    return builder, builder.build()


class CheckpointSchedulerTests(unittest.TestCase):
    def test_checkpoint_tracks_lane_streak_and_distribution(self) -> None:
        checkpoint = StewardCheckpoint()
        for i in range(3):
            checkpoint.record(ObjectiveOutcome(
                identity=f"repair-{i}",
                lane="repair",
                completed_at=100 + i,
                repository_fingerprint="a" * 64,
                status="completed",
            ))
        self.assertEqual(checkpoint.lane_streak, "repair")
        self.assertEqual(checkpoint.lane_streak_count, 3)
        self.assertEqual(lane_distribution(checkpoint)["repair"], 1.0)

    def test_scheduler_respects_active_lease_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder, model = fixture(Path(temp))
            queue = MachineWorkQueue()
            queue.refresh(model, builder.config)
            leases = LeaseRegistry()
            leases.acquire(
                objective_id="busy",
                holder="worker",
                conflict_keys=("zone:app",),
                repository_fingerprint=model.fingerprint,
                now=100,
                ttl_seconds=500,
            )
            scheduled = schedule_objectives(
                model,
                queue,
                StewardCheckpoint(),
                leases,
                now=110,
                max_objectives=8,
            )
            self.assertTrue(all(
                "zone:app" not in item.item.conflict_keys
                for item in scheduled
            ))


class ValidationMigrationTests(unittest.TestCase):
    def test_validation_plan_maps_changed_source_to_test(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            intent = ChangeIntent(
                "repair.service",
                "repair",
                "fix service",
                ("app/service.py",),
            )
            plan = build_validation_plan(model, intent)
            targets = {(item.kind, item.value) for item in plan.targets}
            self.assertIn(("test-file", "tests/test_service.py"), targets)

    def test_reorganization_proposal_becomes_reversible_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            builder, _ = fixture(root)
            (root / "misc.py").write_text("x=1\n", encoding="utf-8")
            model = RepositoryModelBuilder(root).build()
            proposal = propose_reorganization(model, builder.config)[0]
            migration = build_migration_plan(model, proposal)
            self.assertEqual(migration.maximum_parallel_phases, 1)
            self.assertEqual(migration.phases[0].name, "observe")
            self.assertEqual(migration.phases[-1].name, "verify")


class DebtSessionTests(unittest.TestCase):
    def test_debt_register_is_priority_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            debt = debt_register(model)
            scores = [item.score for item in debt]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertIn("app", debt_by_zone(model))

    def test_machine_session_is_bounded_and_selects_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder, model = fixture(Path(temp))
            session = build_machine_session(
                model,
                builder.config,
                now=1000,
            )
            payload = session.as_dict()
            self.assertEqual(payload["repository_fingerprint"], model.fingerprint)
            self.assertLessEqual(len(payload["selected"]), 3)
            self.assertIn("coordinator", payload)
            self.assertIn("constraints", payload)


if __name__ == "__main__":
    unittest.main()
