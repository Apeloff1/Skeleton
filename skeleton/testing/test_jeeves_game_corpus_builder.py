"""Contracts for rights-reviewed project-separated production dataset assembly."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.training.jeeves_game_corpus_builder import (
    INTAKE_SCHEMA, build, partition_projects,
)
from skeleton.ai.training.jeeves_game_corpus import (
    FAMILIES, RIGHTS_SCHEMA, load_approved_corpus,
)
from skeleton.ai.training.jeeves_production_game_train import ProductionCheckpointError


# Distinct project prompts and targets, rather than near-copies where merely
# the project name changes. The strict dataset loader should ACCEPT only
# independently written designs, including this synthetic test fixture.
PROJECTS = (
    ("A desert observatory loses power when the stars vanish during a storm",
     "Introduce a lantern feedback loop and a safe return passage through sand."),
    ("A mountain village hides a rope bridge underneath the communal garden",
     "Reveal that seasonal crop cycles alter the route and support reversible choices."),
    ("Underwater researchers navigate tidal caves to catalog glass organisms",
     "Establish pressure constraints, an oxygen indicator and calm retreat routes."),
    ("A floating market changes its vendor positions after an eclipse celebration",
     "Model reputation through observed bargains and durable economic consequences."),
    ("Ancient mechanical birds migrate through a train depot carrying lost letters",
     "Make deliveries optional with readable schedules and a companion search fallback."),
    ("A small theater rebuilds scenery whenever the audience changes its vote",
     "Offer actor memory, multiple stage exits and consistent dialogue repercussions."),
    ("A volcanic island rotates its bridges using a slow geothermal clock",
     "Provide heat-safe checkpoints, readable timing windows and a recovery ferry."),
    ("A greenhouse spacecraft hosts a drifting botanical research expedition",
     "Balance energy, irrigation and accessibility with reversible experiment choices."),
)


class GameCorpusBuilderTests(unittest.TestCase):
    def _write_intake(self, directory: Path) -> tuple[Path, list[dict]]:
        rows: list[dict] = []
        for index, (situation, answer) in enumerate(PROJECTS):
            project = f"original_project_{index:02d}"
            for family in sorted(FAMILIES):
                rows.append({
                    "schema_version": INTAKE_SCHEMA,
                    "id": project + "_" + family,
                    "source_project_id": project,
                    "family": family,
                    "prompt": situation + f"; plan a thoughtful {family} game system.",
                    "answer": answer + f" Integrate the {family} discipline with measurable outcomes.",
                    "quality_approved": True,
                    "quality_reviewer_id": "fixture_independent_reviewer",
                    "quality_review_note": (
                        "This authored case has explicit player actions, recovery and testable constraints."
                    ),
                    "rights": {
                        "schema_version": RIGHTS_SCHEMA,
                        "source_kind": "original_authoring",
                        "rights_holder": "Skeleton corpus fixture creator",
                        "rights_basis": "Wholly original test examples with fixture-only rights",
                        "review_id": "fixture_rights_review",
                        "training_permitted": True,
                    },
                })
        incoming = directory / "reviewed-intake.jsonl"
        incoming.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        return incoming, rows

    def test_build_publishes_hashed_disjoint_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources, dest = root / "sources", root / "output"
            sources.mkdir()
            dest.mkdir()
            intake, _ = self._write_intake(sources)
            result = build(
                intake=intake, destination=dest, prefix="first_production_candidate",
                partition_seed="reviewed_split_001",
                rights_review_id="operator_rights_review_001",
            )
            self.assertEqual(result["status"],
                             "reviewed_game_dataset_published_candidate_for_rights_confirmation")
            self.assertEqual(result["project_partition"]["heldout_project_count"], 2)
            self.assertEqual(result["project_partition"]["train_project_count"], 6)
            manifest = dest / "first_production_candidate-manifest.json"
            training, evals, receipt = load_approved_corpus(manifest)
            self.assertEqual(len(training), 48)
            self.assertEqual(sum(map(len, evals.values())), 16)
            self.assertTrue(receipt["heldout_used_for_training"] is False)
            lines_train = [
                json.loads(line)
                for line in (dest / "first_production_candidate-train.jsonl").read_text().splitlines()
            ]
            lines_eval = [
                json.loads(line)
                for line in (dest / "first_production_candidate-heldout.jsonl").read_text().splitlines()
            ]
            self.assertFalse(
                {row["source_project_id"] for row in lines_train}
                & {row["source_project_id"] for row in lines_eval}
            )
            self.assertEqual({row["split"] for row in lines_train}, {"train"})
            self.assertEqual({row["split"] for row in lines_eval}, {"heldout"})

    def test_builder_refuses_unreviewed_game_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            intake, rows = self._write_intake(root)
            rows[0]["quality_approved"] = False
            intake.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            destination = root / "approved"
            destination.mkdir()
            with self.assertRaisesRegex(ProductionCheckpointError, "quality approval"):
                build(
                    intake=intake, destination=destination, prefix="project_pack_001",
                    partition_seed="reviewed_split_001", rights_review_id="legal-review",
                )
            self.assertEqual(list(destination.iterdir()), [])

    def test_reject_missing_cross_project_evaluation_diversity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, rows = self._write_intake(root)
            rows = [row for row in rows if row["source_project_id"] == "original_project_00"]
            with self.assertRaisesRegex(ProductionCheckpointError, "independent project groups"):
                partition_projects(rows, seed="partition_one")

    def test_no_clobber_existing_training_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources, dest = root / "sources", root / "output"
            sources.mkdir()
            dest.mkdir()
            intake, _ = self._write_intake(sources)
            options = {
                "intake": intake, "destination": dest,
                "prefix": "game_release_001",
                "partition_seed": "split_001",
                "rights_review_id": "rights_operator_001",
            }
            build(**options)
            manifest = dest / "game_release_001-manifest.json"
            existing = manifest.read_bytes()
            with self.assertRaisesRegex(ProductionCheckpointError, "already contains"):
                build(**options)
            self.assertEqual(manifest.read_bytes(), existing)

    def test_partition_is_deterministic_across_record_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, rows = self._write_intake(Path(temp))
            a, b, proof_a = partition_projects(rows, seed="split_seed_01")
            c, d, proof_b = partition_projects(list(reversed(rows)), seed="split_seed_01")
            self.assertEqual(proof_a, proof_b)
            self.assertEqual({row["id"] for row in a}, {row["id"] for row in c})
            self.assertEqual({row["id"] for row in b}, {row["id"] for row in d})


if __name__ == "__main__":
    unittest.main()
