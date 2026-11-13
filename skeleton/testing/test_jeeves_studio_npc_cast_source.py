"""Real authored Expedition NPC spawn and patrol compilation tests."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import unittest

from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile, author_archipelago,
)
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_npc_cast_source import (
    OriginalNpcCastError, compile_original_npc_cast,
    verify_original_npc_cast,
)


def original_world():
    return author_archipelago(
        "original-game", "a" * 64,
        ArchipelagoProfile(seed=17, islands=5, caverns=0),
    )


def original_spawn(name="captain-sera"):
    doc = {
        "kind": "npc_spawn", "npc_id": name,
        "home_waypoint_id": "harbor",
        "patrol_waypoint_ids": ["island_001", "harbor"],
    }
    deps = ["original-world"]
    return {
        "record_id": "npc-" + name,
        "facet": "npc", "document": doc, "revision": 1,
        "depends_on": deps,
        "source_sha256": digest([
            "npc-" + name, "npc", 1, doc, deps,
        ]),
    }


def reseal(record):
    record["source_sha256"] = digest([
        record["record_id"], record["facet"],
        record["revision"], record["document"], record["depends_on"],
    ])
    return record


class OriginalNpcCastTests(unittest.TestCase):
    def setUp(self):
        self.world = original_world()

    def compile(self, *records):
        return compile_original_npc_cast(
            {entry["record_id"]: entry for entry in records},
            self.world, world_source_record_id="original-world",
        )

    def test_real_authored_cast_contains_exact_home_and_patrol(self):
        candidate = self.compile(original_spawn())
        self.assertIsNotNone(candidate)
        native = json.loads(candidate["content"])
        self.assertEqual(native["world_digest"], self.world.digest)
        self.assertEqual(native["schema"], "skeleton.game.original_npc_cast.v1")
        self.assertEqual(native["cast"][0]["design"], {
            "npc_id": "captain-sera", "home": "harbor",
        })
        self.assertEqual(native["cast"][0]["proof"]["steps"], [
            {"new": "island_001"}, {"new": "harbor"},
        ])
        receipt = candidate["receipt"]
        self.assertFalse(receipt["npc_autonomous_intelligence_claimed"])
        self.assertFalse(receipt["native_engine_npc_process_executed"])
        self.assertEqual(receipt["authored_patrol_steps"], 2)
        self.assertEqual(
            sha256(candidate["content"].encode()).hexdigest(),
            receipt["native_cast_json_sha256"],
        )

    def test_full_native_cast_independent_receipt_replay(self):
        candidate = self.compile(original_spawn())
        observed = verify_original_npc_cast(
            candidate["content"], candidate["receipt"],
            world_digest=self.world.digest,
        )
        self.assertEqual(observed["npc_count"], 1)
        self.assertTrue(observed["all_character_source_receipts_replayed"])
        self.assertFalse(observed["actual_npc_engine_movement_observed"])

    def test_repeated_compilation_is_byte_identical(self):
        a = self.compile(original_spawn())
        b = self.compile(original_spawn())
        self.assertEqual(a, b)

    def test_two_authored_characters_compile_deterministically(self):
        candidate = self.compile(original_spawn("guide"), original_spawn("captain"))
        parsed = json.loads(candidate["content"])
        self.assertEqual([v["design"]["npc_id"] for v in parsed["cast"]],
                         ["captain", "guide"])

    def test_missing_authored_patrol_waypoint_refuses_compilation(self):
        source = original_spawn()
        source["document"]["patrol_waypoint_ids"] = ["ghost-island"]
        with self.assertRaisesRegex(OriginalNpcCastError, "real authored world"):
            self.compile(reseal(source))

    def test_missing_world_dependency_refuses_compilation(self):
        source = original_spawn()
        source["depends_on"] = []
        with self.assertRaisesRegex(OriginalNpcCastError, "depend"):
            self.compile(reseal(source))

    def test_changed_npc_data_requires_new_persisted_revision(self):
        source = original_spawn()
        source["document"]["home_waypoint_id"] = "island_001"
        with self.assertRaisesRegex(OriginalNpcCastError, "source revision"):
            self.compile(source)

    def test_duplicate_original_npc_identity_refused(self):
        left = original_spawn()
        right = deepcopy(left)
        right["record_id"] = "other-record"
        reseal(right)
        with self.assertRaisesRegex(OriginalNpcCastError, "duplicated"):
            self.compile(left, right)

    def test_tampered_cast_json_refused_even_with_original_receipt(self):
        candidate = self.compile(original_spawn())
        changed = candidate["content"].replace("island_001", "island_002")
        with self.assertRaisesRegex(OriginalNpcCastError, "bytes"):
            verify_original_npc_cast(
                changed, candidate["receipt"],
                world_digest=self.world.digest,
            )

    def test_cast_cannot_be_attested_to_another_world(self):
        candidate = self.compile(original_spawn())
        with self.assertRaisesRegex(OriginalNpcCastError, "world hash"):
            verify_original_npc_cast(
                candidate["content"], candidate["receipt"],
                world_digest="b" * 64,
            )

    def test_no_authored_npc_means_no_synthetic_cast(self):
        self.assertIsNone(self.compile())

    def test_native_patrol_proof_cannot_be_changed_silently(self):
        candidate = self.compile(original_spawn())
        forged = deepcopy(candidate["receipt"])
        forged["npc_source_records"][0]["patrol_waypoint_ids"] = ["harbor"]
        forged["receipt_sha256"] = digest({
            key: val for key, val in forged.items()
            if key != "receipt_sha256"
        })
        with self.assertRaisesRegex(OriginalNpcCastError, "differ"):
            verify_original_npc_cast(
                candidate["content"], forged,
                world_digest=self.world.digest,
            )


if __name__ == "__main__":
    unittest.main()
